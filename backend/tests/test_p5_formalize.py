"""P5 formalization tests: Retry Policy classification, queue Pause/Resume,
INTERRUPTED state + recovery, and durable Cancel (P5-T009/T013/T014/T015/T016).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ComfyUIError, ProviderUnavailableError, StudioError
from app.db import models  # noqa: F401
from app.db.models import Generation
from app.domain.episode import EpisodeCreate
from app.domain.generation import GenerationCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate
from app.generations import worker as worker_module
from app.generations.retry_policy import RetryOutcome, classify_failure
from app.generations.state import validate_transition
from app.services import (
    EpisodeService,
    GenerationService,
    ProjectService,
    SceneService,
    ShotService,
)

pytestmark = pytest.mark.usefixtures("reset_worker")


# ---- fixture: reset process-level worker state between tests ----

@pytest.fixture()
def reset_worker():
    worker_module.reset_worker_state()
    yield
    worker_module.reset_worker_state()


@pytest.fixture()
def route_worker_to_test_db(session_factory, monkeypatch):
    """Point the global DB-poll worker at the isolated test DB (as conftest does for
    the TestClient), so direct run_generation calls touch the same tables as the test."""
    from app.db import session as db_session_module

    factory, _ = session_factory
    monkeypatch.setattr(db_session_module, "session_factory_provider", lambda: factory)
    return factory, _


def _make_generation(session_factory, max_attempts: int = 3) -> str:
    factory, _ = session_factory
    with factory() as session:
        project = ProjectService(session).create_project(ProjectCreate(name="P5F"))
        episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
        scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
        shot = ShotService(session).create_shot(
            scene.id, ShotCreate(shot_type="medium", image_prompt="p5 formalize")
        )
        generation = GenerationService(session).create_generation(
            shot.id, GenerationCreate(type="image", max_attempts=max_attempts)
        )
        return generation.id


# ================= P5-T009 Retry Policy =================

def test_retry_policy_classification() -> None:
    # Retryable: provider unavailable / transient connection/timeout.
    assert classify_failure(ProviderUnavailableError("unreachable")) is RetryOutcome.RETRYABLE
    assert classify_failure(ProviderUnavailableError("ComfyUI timed out")) is RetryOutcome.RETRYABLE
    assert classify_failure(OSError("Connection reset by peer")) is RetryOutcome.RETRYABLE
    assert classify_failure(TimeoutError("timed out")) is RetryOutcome.RETRYABLE

    # NonRetryable: deterministic infra/template/output problems.
    assert classify_failure(ComfyUIError("workflow rejected")) is RetryOutcome.NON_RETRYABLE
    assert classify_failure(ComfyUIError("no output images")) is RetryOutcome.NON_RETRYABLE
    assert classify_failure(ValueError("invalid seed")) is RetryOutcome.NON_RETRYABLE
    assert classify_failure(FileNotFoundError("no such file")) is RetryOutcome.NON_RETRYABLE

    # No exception object (unsuccessful result) → NonRetryable.
    assert classify_failure(None, "Provider returned failure.") is RetryOutcome.NON_RETRYABLE

    # Generic StudioError with a transient-sounding message → Retryable.
    assert classify_failure(StudioError("connection to provider lost")) is RetryOutcome.RETRYABLE
    # Generic StudioError otherwise → NonRetryable.
    assert classify_failure(StudioError("backend bug")) is RetryOutcome.NON_RETRYABLE


def test_retryable_failure_goes_to_backoff(session_factory) -> None:
    gen_id = _make_generation(session_factory, max_attempts=3)
    factory, _ = session_factory
    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
        row = session.get(Generation, gen_id)
        worker_module._handle_failure(
            factory, gen_id, row.project_id, row.shot_id, "unreachable provider",
            exc=ProviderUnavailableError("ComfyUI unreachable"),
        )
    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "retrying"
        assert row.attempts == 1  # one attempt consumed, backoff scheduled
        assert row.next_attempt_at is not None


def test_nonretryable_failure_fails_immediately_without_churning_attempts(session_factory) -> None:
    """NonRetryable (e.g. ComfyUI template/no-output problem) must go straight to
    'failed' and NOT consume the attempt budget / enter backoff."""
    gen_id = _make_generation(session_factory, max_attempts=3)
    factory, _ = session_factory
    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
        row = session.get(Generation, gen_id)
        worker_module._handle_failure(
            factory, gen_id, row.project_id, row.shot_id, "no output images in history",
            exc=ComfyUIError("No output images found."),
        )
    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "failed"
        assert row.attempts == 0  # attempt budget NOT burned on a deterministic error


def test_unsuccessful_result_is_nonretryable(session_factory) -> None:
    """An ImageResult(success=False) yields no exception → NonRetryable fail-fast."""
    gen_id = _make_generation(session_factory, max_attempts=3)
    factory, _ = session_factory
    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
        row = session.get(Generation, gen_id)
        worker_module._handle_failure(factory, gen_id, row.project_id, row.shot_id, "Provider returned failure.")
    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "failed"
        assert row.attempts == 0


# ================= P5-T013/T014 Pause / Resume =================

def test_pause_resume_queue_api(client: TestClient) -> None:
    resp = client.get("/api/v1/generations/queue-status")
    assert resp.status_code == 200
    assert resp.json()["paused"] is False

    paused = client.post("/api/v1/generations/pause")
    assert paused.status_code == 200
    assert paused.json()["paused"] is True

    status = client.get("/api/v1/generations/queue-status").json()
    assert status["paused"] is True

    resumed = client.post("/api/v1/generations/resume")
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False


def test_pause_stops_scheduling_new_tasks(session_factory, route_worker_to_test_db, monkeypatch) -> None:
    """While paused, the worker loop does NOT schedule queued jobs (they stay queued).
    After resume, the same loop picks them up. (Pause only gates *scheduling new*
    tasks; running ones keep going — this test covers the scheduling gate.)"""
    factory, _ = route_worker_to_test_db
    monkeypatch.setattr(worker_module, "POLL_INTERVAL_SECONDS", 0.02)
    gen_id = _make_generation(session_factory)

    async def _drive(paused_first: bool) -> str:
        worker_module.pause_queue() if paused_first else worker_module.resume_queue()
        loop_task = asyncio.create_task(worker_module.worker_loop())
        try:
            # While paused the job must stay queued.
            if paused_first:
                for _ in range(30):
                    await asyncio.sleep(0.03)
                    with factory() as session:
                        status = session.get(Generation, gen_id).status
                    assert status == "queued", f"paused loop must not schedule, got {status}"
                worker_module.resume_queue()
            # Once resumed, it completes.
            for _ in range(200):
                await asyncio.sleep(0.03)
                with factory() as session:
                    status = session.get(Generation, gen_id).status
                if status == "completed":
                    return status
            return "timeout"
        finally:
            worker_module.resume_queue()
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass

    assert asyncio.run(_drive(paused_first=True)) == "completed"


def test_queue_status_counts(session_factory) -> None:
    _make_generation(session_factory)  # one queued row
    factory, _ = session_factory
    status = worker_module.queue_status(factory=factory)
    assert status["paused"] is False
    assert status["pending"] == 1
    assert status["pending_total"] == 1
    assert status["running"] == 0


# ================= P5-T016 INTERRUPTED =================

def test_interrupted_is_a_terminal_status() -> None:
    from app.core.errors import ConflictError

    validate_transition("running", "interrupted")  # legal
    with pytest.raises(ConflictError):
        validate_transition("queued", "interrupted")  # only running → interrupted
    with pytest.raises(ConflictError):
        validate_transition("interrupted", "queued")  # terminal


def test_expired_lease_with_budget_marks_interrupted(session_factory) -> None:
    """P5-T017 abnormal-task detection: a running row whose lease expired AND whose
    attempt budget is exhausted becomes 'interrupted' (not 'failed')."""
    gen_id = _make_generation(session_factory, max_attempts=1)
    factory, _ = session_factory
    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
        row = session.get(Generation, gen_id)
        row.lease_expires_at = "2000-01-01T00:00:00+00:00"
        session.commit()
    worker_module.recover_expired_leases(factory=factory)
    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "interrupted"
        assert row.completed_at is not None


# ================= P5-T015 Durable Cancel =================

def test_running_cancel_moves_to_cancelling_then_worker_finalizes(
    session_factory, route_worker_to_test_db
) -> None:
    """A cancel on a running row is persisted as durable 'cancelling'; the worker's
    finish path (_handle_cancelled) finalizes it to cancelled instead of saving output."""
    factory, _ = route_worker_to_test_db
    gen_id = _make_generation(session_factory)
    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
    # The service persists the durable cancelling marker for a running row.
    with factory() as session:
        service = GenerationService(session)
        gen = service.cancel_generation(gen_id)
        assert gen.status == "cancelling"
    # The worker finalizes the durable marker (this is the in-process finish path).
    with factory() as session:
        row = session.get(Generation, gen_id)
        worker_module._handle_cancelled(factory, gen_id, row.project_id, row.shot_id)
    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "cancelled"
        assert row.completed_at is not None
        assert row.output_asset_id is None  # no asset persisted


def test_cancelling_is_durable_across_restart(session_factory, route_worker_to_test_db) -> None:
    """The 'cancelling' marker is a DB column, NOT a process-level set — so it survives
    a restart. A new worker's lease recovery finalizes it to 'cancelled' (not outputs)."""
    factory, _ = route_worker_to_test_db
    gen_id = _make_generation(session_factory)
    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
    with factory() as session:
        GenerationService(session).cancel_generation(gen_id)
    # Simulate the generating process died (lease expired) + a fresh process with NO
    # in-memory _cancelled hint.
    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "cancelling"  # durable marker persisted
        row.lease_expires_at = "2000-01-01T00:00:00+00:00"
        session.commit()
    worker_module._cancelled.clear()
    # The new worker recovers the cancelling row purely from the DB → cancelled.
    worker_module.recover_expired_leases(factory=factory)
    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "cancelled"
        assert row.output_asset_id is None  # no asset persisted
        assert "cancelled" in (row.error_message or "").lower()
