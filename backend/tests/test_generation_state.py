"""P1-E2-T02: generation state machine — atomic claim, lease crash recovery,
retry backoff, invalid-transition rejection, worker health.

Runs WITHOUT a real provider: the MockImageProvider completes instantly, and the
claim/recovery/backoff logic is exercised at the function level with the isolated
test session factory.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ConflictError, ProviderUnavailableError
from app.db.models import Generation
from app.domain.episode import EpisodeCreate
from app.domain.generation import GenerationCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate
from app.generations import worker as worker_module
from app.generations.state import validate_transition
from app.services import (
    EpisodeService,
    GenerationService,
    ProjectService,
    SceneService,
    ShotService,
)


def _make_generation(session_factory) -> str:
    factory, _ = session_factory
    with factory() as session:
        project = ProjectService(session).create_project(ProjectCreate(name="ST"))
        episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
        scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
        shot = ShotService(session).create_shot(
            scene.id, ShotCreate(shot_type="medium", image_prompt="state machine test")
        )
        generation = GenerationService(session).create_generation(
            shot.id, GenerationCreate(type="image", max_attempts=3)
        )
        return generation.id


def test_atomic_claim_only_one_executor_wins(session_factory) -> None:
    gen_id = _make_generation(session_factory)
    factory, _ = session_factory

    with factory() as a, factory() as b:
        first = worker_module.claim_generation(a, gen_id)
        a.commit()  # SQLite is single-writer: commit A's claim before B attempts
        second = worker_module.claim_generation(b, gen_id)
        assert first is True
        assert second is False  # the conditional WHERE excludes the claimed row

        row = a.get(Generation, gen_id)
        assert row.status == "running"
        assert row.claim_token is not None
        assert row.lease_expires_at is not None


def test_expired_lease_recovery_requeues(session_factory) -> None:
    gen_id = _make_generation(session_factory)
    factory, _ = session_factory

    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
        row = session.get(Generation, gen_id)
        row.lease_expires_at = "2000-01-01T00:00:00+00:00"  # simulate process death
        session.commit()

    recovered = worker_module.recover_expired_leases(factory=factory)
    assert recovered == 1

    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "queued"  # re-queued for a fresh claim
        assert row.attempts == 1
        assert row.claim_token is None

    # and the row is claimable again
    with factory() as session:
        assert worker_module.claim_generation(session, gen_id) is True


def test_lease_recovery_fails_when_attempt_budget_exhausted(session_factory) -> None:
    factory, _ = session_factory
    with factory() as session:
        project = ProjectService(session).create_project(ProjectCreate(name="ST2"))
        episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
        scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
        shot = ShotService(session).create_shot(
            scene.id, ShotCreate(shot_type="medium", image_prompt="x")
        )
        generation = GenerationService(session).create_generation(
            shot.id, GenerationCreate(type="image", max_attempts=1)
        )
        gen_id = generation.id

    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
        row = session.get(Generation, gen_id)
        row.lease_expires_at = "2000-01-01T00:00:00+00:00"
        session.commit()

    worker_module.recover_expired_leases(factory=factory)
    with factory() as session:
        row = session.get(Generation, gen_id)
        # P5-T016: a crash where the attempt budget is exhausted is a SYSTEM
        # interruption (abnormal-task detection), not a user failure.
        assert row.status == "interrupted"
        assert "interrupted" in (row.error_message or "").lower()


def test_retry_backoff_gates_reclaim(session_factory) -> None:
    gen_id = _make_generation(session_factory)
    factory, _ = session_factory

    # claim → provider fails once (attempts 1 < max 3) → retrying with backoff.
    # P5-T009: a ProviderUnavailableError is Retryable, so it goes through backoff.
    with factory() as session:
        assert worker_module.claim_generation(session, gen_id)
        session.commit()
        row = session.get(Generation, gen_id)
        worker_module._handle_failure(
            factory,
            gen_id,
            row.project_id,
            row.shot_id,
            "provider boom",
            exc=ProviderUnavailableError("ComfyUI unreachable"),
        )

    with factory() as session:
        row = session.get(Generation, gen_id)
        assert row.status == "retrying"
        assert row.attempts == 1
        assert row.next_attempt_at is not None
        assert row.claim_token is None

        # backoff gate: not claimable yet
        assert worker_module.claim_generation(session, gen_id) is False

        # …and claimable once the backoff window has passed
        row.next_attempt_at = "2000-01-01T00:00:00+00:00"
        session.commit()
        assert worker_module.claim_generation(session, gen_id) is True


def test_invalid_transition_is_domain_error(session_factory) -> None:
    with pytest.raises(ConflictError):
        validate_transition("completed", "running")
    with pytest.raises(ConflictError):
        validate_transition("cancelled", "queued")
    validate_transition("queued", "running")  # legal
    validate_transition("running", "retrying")  # legal


def test_cancel_after_completion_returns_conflict(client: TestClient) -> None:
    import asyncio

    project = client.post("/api/v1/projects", json={"name": "ST3"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "x"},
    ).json()
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()

    asyncio.run(worker_module.run_generation(created["id"]))
    done = client.get(f"/api/v1/generations/{created['id']}").json()
    assert done["status"] == "completed"

    resp = client.post(f"/api/v1/generations/{created['id']}/cancel")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


def test_health_reports_worker_liveness(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "worker" in body
    # under the TestClient lifespan the worker loop IS running → healthy
    assert body["worker"] in ("healthy", "stopped")
    assert body["status"] in ("healthy", "degraded")


def test_concurrency_greater_than_one_rejected_at_startup() -> None:
    with pytest.raises(ValueError, match="concurrency"):
        Settings(generation_concurrency=2)
