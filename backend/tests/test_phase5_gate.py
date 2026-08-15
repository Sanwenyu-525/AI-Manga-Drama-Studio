"""P5 Gate acceptance (roadmap §33-38; mvp-spec Phase 5 / P5-E1..E5).

Synchronous-drive pattern (mirrors test_phase3_gate): the scheduler/worker background
loops are disabled, and generation execution is driven by asyncio.run(run_generation)
while job advancement is driven by job_scheduler.advance_job — the same DB is the only
state, so restart recovery is native.

Scenarios:
  - 20 shots → create_scene_job → all tasks complete, progress=100, generation + asset
    persisted per task.
  - Partial failure: one shot's provider raises → that task failed, the other 19 complete
    (failure does not block siblings); job ends completed with error_summary.
  - Dependency skip: a task whose dependency failed → dependency_failed, no generation.
  - Control: pause (scheduler skips) / resume / cancel (no new generations) / retry.
  - DAG validator: cycle / unknown reference → 422.
  - Restart recovery: re-advancing a partially-advanced job is idempotent (no duplicate
    generations).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.errors import ProviderUnavailableError, ValidationError
from app.db import models  # noqa: F401
from app.db.models import Generation, JobTask, TaskDependency
from app.domain.episode import EpisodeCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate
from app.generations import worker as worker_module
from app.generations.worker import run_generation
from app.jobs import scheduler as job_scheduler
from app.services import (
    EpisodeService,
    JobService,
    ProjectService,
    SceneService,
    ShotService,
)


@pytest.fixture()
def disable_background(client, session_factory):
    """Stop the lifespan background scheduler + worker from racing the synchronous drive.

    We still want the TestClient app mounted (API calls + DB override), but job scheduling
    and generation execution are driven manually so every assertion is deterministic.
    """
    job_scheduler.set_enabled(False)
    worker_module.reset_worker_state()
    worker_module.pause_queue()  # background worker must not claim queued generations
    yield
    job_scheduler.set_enabled(True)
    worker_module.resume_queue()


def _make_scene_shots(client: TestClient, scene_id: str, count: int) -> list[str]:
    """Create N shots (with image prompts) in the scene; returns shot ids ordered by order."""
    ids: list[str] = []
    for i in range(1, count + 1):
        shot = client.post(
            f"/api/v1/scenes/{scene_id}/shots",
            json={"shot_type": "medium", "image_prompt": f"manga, frame {i}"},
        ).json()
        ids.append(shot["id"])
    return ids


def _create_job_fixture(client: TestClient, scene_id: str) -> dict:
    resp = client.post(
        f"/api/v1/projects/{_project_of_scene(client, scene_id)}/jobs",
        json={"scene_id": scene_id, "name": "gate scene"},
    )
    assert resp.status_code == 201
    return resp.json()


def _project_of_scene(client: TestClient, scene_id: str) -> str:
    # fetch via scene → episode → project chain through the API/DB. Simplest: the test
    # builds the tree and remembers the project id; this helper is used by tests that
    # already know it. Fallback: read relational ids from the DB.
    from app.db import session as db_session_module

    factory = db_session_module.session_factory_provider()
    with factory() as s:
        from app.db.models import Episode, Scene

        scene = s.get(Scene, scene_id)
        ep = s.get(Episode, scene.episode_id)
        return ep.project_id


def _set_route_to_client_factory(client: TestClient, session_factory):
    """The client fixture already overrides session_factory_provider to the test factory;
    this is a no-op reminder of the invariant (worker + scheduler read the same DB)."""
    return session_factory


def _generation_status(factory, generation_id: str) -> str:
    with factory() as s:
        g = s.get(Generation, generation_id)
        return g.status if g else "missing"


def _tasks_for_job(factory, job_id: str) -> list:
    with factory() as s:
        return list(s.scalars(select(JobTask).where(JobTask.job_id == job_id)))


def _drive_job_to_terminal(factory, job_id: str, max_steps: int = 200) -> str:
    """Advance the job (creating generations) AND run every pending generation to
    completion/failure, until the job reaches a terminal state.

    Returns the final job status.
    """
    for _ in range(max_steps):
        status = job_scheduler.advance_job(job_id, factory)
        # drive any queued/retrying generations linked to this job
        tasks = _tasks_for_job(factory, job_id)
        for task in tasks:
            if not task.generation_id:
                continue
            gstatus = _generation_status(factory, task.generation_id)
            if gstatus in ("queued", "retrying"):
                asyncio.run(run_generation(task.generation_id))
        if status in ("completed", "failed", "cancelled"):
            return status
    raise TimeoutError(f"job {job_id} did not reach a terminal state")


def _make_tree(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P5Gate"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return {"project_id": project["id"], "episode_id": episode["id"], "scene_id": scene["id"]}


# ================= 20-shot end-to-end =================

def test_scene_job_20_shots_all_complete(client: TestClient, disable_background, session_factory):
    tree = _make_tree(client)
    shot_ids = _make_scene_shots(client, tree["scene_id"], 20)
    assert len(shot_ids) == 20

    job = _create_job_fixture(client, tree["scene_id"])
    assert job["job_type"] == "SCENE_IMAGE"
    assert job["task_count"] == 20
    assert job["status"] in ("queued", "running")

    factory, _ = session_factory
    final = _drive_job_to_terminal(factory, job["id"])
    assert final == "completed"

    body = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert body["status"] == "completed"
    assert body["progress"] == 100
    assert len(body["tasks"]) == 20
    assert all(t["status"] == "completed" for t in body["tasks"])
    assert all(t["generation_id"] for t in body["tasks"])

    # every generation produced a persisted asset (generation completed → output_asset_id)
    with factory() as s:
        for task in s.scalars(select(JobTask).where(JobTask.job_id == job["id"])):
            gen = s.get(Generation, task.generation_id)
            assert gen is not None
            assert gen.status == "completed"
            assert gen.output_asset_id is not None
            assert gen.output_asset_id.startswith("") or len(gen.output_asset_id) > 0
    # each shot gained an image V1 (asset + version + activate), asserted via versions API
    for shot_id in shot_ids:
        versions = client.get(f"/api/v1/shots/{shot_id}/versions").json()
        assert any(v["media_type"] == "image" and v["is_active"] for v in versions), shot_id


# ================= partial failure =================

@pytest.fixture()
def failing_provider_for_shot(disable_background, monkeypatch):
    """Patch the worker's image provider so generation for a specific shot id raises
    ProviderUnavailableError (retryable → non-deterministic failure is retried until the
    attempt budget is exhausted → 'failed'); every other shot uses the real mock provider.
    We target the task with max_attempts=1 so a single retryable raise ends in 'failed'.
    """

    def _install(target_shot_id: str) -> None:

        real_get = worker_module.get_image_provider

        class _FailingMock:
            name = "mock"

            async def generate(self, request, on_progress):
                if request.metadata.get("shot_id") == target_shot_id:
                    if request.metadata.get("_fail") is not None and request.metadata["_fail"]:
                        pass
                    raise ProviderUnavailableError("ComfyUI unreachable for this shot (injected).")
                provider = real_get("mock")
                return await provider.generate(request, on_progress)

            async def cancel(self, provider_ref):
                provider = real_get("mock")
                await provider.cancel(provider_ref)

        monkeypatch.setattr(worker_module, "get_image_provider", lambda pid=None: _FailingMock())

    return _install


def test_partial_failure_one_task_fails_others_complete(
    client: TestClient, disable_background, session_factory, failing_provider_for_shot, monkeypatch
):
    # make all generations single-attempt so the injected retryable failure → 'failed'
    monkeypatch.setattr("app.core.config.settings.generation_max_attempts", 1)

    tree = _make_tree(client)
    shot_ids = _make_scene_shots(client, tree["scene_id"], 20)
    job = _create_job_fixture(client, tree["scene_id"])

    factory, _ = session_factory
    # install the failing provider for the FIRST shot before advancing (target shot 0)
    failing_provider_for_shot(shot_ids[0])

    final = _drive_job_to_terminal(factory, job["id"])
    # partial failure → the job still ends 'completed' with error_summary (failure does
    # not block siblings), per P5-E4 design.
    assert final == "completed"

    body = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert body["status"] == "completed"
    assert len(body["tasks"]) == 20
    statuses = {t["status"] for t in body["tasks"]}
    assert "failed" in statuses
    assert "completed" in statuses
    # exactly one failure, exactly 19 completed
    from collections import Counter

    counts = Counter(t["status"] for t in body["tasks"])
    assert counts["failed"] == 1
    assert counts["completed"] == 19
    assert body["progress"] == 95  # round(19/20*100)
    assert body["error_summary"]
    assert body["error_summary"].find("did not complete") != -1

    # the failed task's generation was failed with an error
    failed_task = next(t for t in body["tasks"] if t["status"] == "failed")
    with factory() as s:
        gen = s.get(Generation, failed_task["generation_id"])
        assert gen.status == "failed"
        assert gen.error_message


# ================= dependency skip / DAG =================

def test_dependency_failed_blocks_downstream_without_generation(
    client: TestClient, disable_background, session_factory, failing_provider_for_shot, monkeypatch
):
    monkeypatch.setattr("app.core.config.settings.generation_max_attempts", 1)
    tree = _make_tree(client)
    shot_ids = _make_scene_shots(client, tree["scene_id"], 3)  # A, B, C
    job = _create_job_fixture(client, tree["scene_id"])
    factory, _ = session_factory

    # Build a DAG: B depends on A, C depends on B (A → B → C).
    with factory() as s:
        tasks = list(s.scalars(select(JobTask).where(JobTask.job_id == job["id"]).order_by(JobTask.priority)))
        a, b, c = tasks  # priority = shot_order 1,2,3
        s.add(TaskDependency(task_id=b.id, depends_on_task_id=a.id))
        s.add(TaskDependency(task_id=c.id, depends_on_task_id=b.id))
        s.commit()

    # Fail A (the root). B and C must become dependency_failed with NO generation created.
    failing_provider_for_shot(shot_ids[0])  # shot A
    final = _drive_job_to_terminal(factory, job["id"])
    assert final == "completed"

    body = client.get(f"/api/v1/jobs/{job['id']}").json()
    statuses = {t["status"] for t in body["tasks"]}
    assert "failed" in statuses
    assert "dependency_failed" in statuses
    by_status = {t["status"]: t for t in body["tasks"]}
    assert by_status["failed"]["target_id"] == shot_ids[0]  # A failed
    # downstream B + C are dependency_failed and did NOT create a generation
    for t in body["tasks"]:
        if t["status"] == "dependency_failed":
            assert t["generation_id"] is None


def test_dag_cycle_rejected_422(session_factory, disable_background):
    factory, _ = session_factory
    with factory() as s:
        project = ProjectService(s).create_project(ProjectCreate(name="P5Dag"))
        episode = EpisodeService(s).create_episode(project.id, EpisodeCreate(title="E1"))
        scene = SceneService(s).create_scene(episode.id, SceneCreate(name="S1"))
        ShotService(s).create_shot(scene.id, ShotCreate(image_prompt="a"))
        ShotService(s).create_shot(scene.id, ShotCreate(image_prompt="b"))
        job = JobService(s).create_scene_job(scene.id, None)
        tasks = list(s.scalars(select(JobTask).where(JobTask.job_id == job.id)))
    t1, t2 = tasks[0].id, tasks[1].id
    with pytest.raises(ValidationError) as exc:
        JobService(s).validate_dependencies([t1, t2], [(t1, t2), (t2, t1)])
    assert exc.value.status_code == 422
    assert "cycle" in exc.value.message.lower()
    # unknown reference also 422
    with pytest.raises(ValidationError) as exc2:
        JobService(s).validate_dependencies([t1, t2], [(t1, "no-such-task")])
    assert exc2.value.status_code == 422
    assert "unknown" in exc2.value.message.lower()


# ================= control =================

def test_pause_resume(client: TestClient, disable_background, session_factory):
    tree = _make_tree(client)
    _make_scene_shots(client, tree["scene_id"], 5)
    job = _create_job_fixture(client, tree["scene_id"])
    factory, _ = session_factory

    paused = client.post(f"/api/v1/jobs/{job['id']}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    # scheduler must skip a paused job (no generation created, no task advanced)
    status = job_scheduler.advance_job(job["id"], factory)
    assert status == "paused"
    tasks = _tasks_for_job(factory, job["id"])
    assert all(t.generation_id is None for t in tasks)

    resumed = client.post(f"/api/v1/jobs/{job['id']}/resume")
    assert resumed.json()["status"] == "queued"
    final = _drive_job_to_terminal(factory, job["id"])
    assert final == "completed"


def test_cancel_no_new_generations(client: TestClient, disable_background, session_factory):
    tree = _make_tree(client)
    _make_scene_shots(client, tree["scene_id"], 5)
    job = _create_job_fixture(client, tree["scene_id"])
    factory, _ = session_factory

    # advance once → some generations created
    job_scheduler.advance_job(job["id"], factory)
    with factory() as s:
        n_before = len(list(s.scalars(select(Generation).where(Generation.shot_id.in_(
            [t.target_id for t in s.scalars(select(JobTask).where(JobTask.job_id == job["id"]))]
        )))))

    cancelled = client.post(f"/api/v1/jobs/{job['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert all(t["status"] == "cancelled" for t in cancelled.json()["tasks"])

    # after cancel no further scheduling and no new generations
    status = job_scheduler.advance_job(job["id"], factory)
    assert status == "cancelled"
    with factory() as s:
        n_after = len(list(s.scalars(select(Generation).where(Generation.shot_id.in_(
            [t.target_id for t in s.scalars(select(JobTask).where(JobTask.job_id == job["id"]))]
        )))))
    assert n_after == n_before


def test_retry_requeues_failed_and_completes(
    client: TestClient, disable_background, session_factory, failing_provider_for_shot, monkeypatch
):
    monkeypatch.setattr("app.core.config.settings.generation_max_attempts", 1)
    tree = _make_tree(client)
    shot_ids = _make_scene_shots(client, tree["scene_id"], 2)
    job = _create_job_fixture(client, tree["scene_id"])
    factory, _ = session_factory

    # First run: fail shot 0, complete shot 1
    failing_provider_for_shot(shot_ids[0])
    assert job_scheduler.advance_job(job["id"], factory) in ("queued", "running")
    # drive all pending generations (shot1 mock, shot0 failing) then reflect
    final = _drive_job_to_terminal(factory, job["id"])
    assert final == "completed"
    body = client.get(f"/api/v1/jobs/{job['id']}").json()
    statuses = {t["status"]: t for t in body["tasks"]}
    assert statuses["failed"]["target_id"] == shot_ids[0]

    # retry: the failed task must be requeued (cleared generation ref), then complete.
    retried = client.post(f"/api/v1/jobs/{job['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    retried_failed = next(t for t in retried.json()["tasks"] if t["target_id"] == shot_ids[0])
    assert retried_failed["status"] == "queued"
    assert retried_failed["generation_id"] is None
    completed_survivor = next(t for t in retried.json()["tasks"] if t["target_id"] == shot_ids[1])
    assert completed_survivor["status"] == "completed"  # completed tasks stay completed

    # clear the failure injection so the retried task can complete
    monkeypatch.undo()
    final2 = _drive_job_to_terminal(factory, job["id"])
    assert final2 == "completed"
    body2 = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert all(t["status"] == "completed" for t in body2["tasks"])
    assert body2["progress"] == 100


# ================= restart recovery =================

def test_restart_recovery_idempotent_no_duplicate_generations(
    client: TestClient, disable_background, session_factory
):
    tree = _make_tree(client)
    _make_scene_shots(client, tree["scene_id"], 4)
    job = _create_job_fixture(client, tree["scene_id"])
    factory, _ = session_factory

    # "process dies" after creating some generations but before completing them:
    job_scheduler.advance_job(job["id"], factory)  # creates 4 generations
    with factory() as s:
        tasks = list(s.scalars(select(JobTask).where(JobTask.job_id == job["id"])))
        gen_ids_first = {t.generation_id for t in tasks}
    assert all(gen_ids_first)

    # a "fresh process" advances the SAME job again — must NOT create duplicate generations
    job_scheduler.advance_job(job["id"], factory)
    with factory() as s:
        tasks2 = list(s.scalars(select(JobTask).where(JobTask.job_id == job["id"])))
        gen_ids_second = {t.generation_id for t in tasks2}
    assert gen_ids_second == gen_ids_first  # same generation rows, no duplicates
    assert len(gen_ids_second) == 4

    # finish all generations and drive to terminal — works from DB alone
    final = _drive_job_to_terminal(factory, job["id"])
    assert final == "completed"
    body = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert body["progress"] == 100
