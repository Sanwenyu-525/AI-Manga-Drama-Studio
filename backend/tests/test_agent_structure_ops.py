"""Director shot-structure ops (slice A of tool-coverage gap #1).

create_shot (R1 auto + lifecycle ChangeSet, undo = delete), delete_shot (R3
proposal + guarded apply; undo refused honestly until restore lands) and
reorder_shots (R1 auto + order ChangeSet, undo = reorder back), plus the fake
batch planner (delete/create keywords, multi-number clauses) and per-op
shot_number:N resolution in the executor loop.
"""

import time

from fastapi.testclient import TestClient

from app.agents.fake_planner import parse_director_plan, parse_production_intent


# ---------- planner unit ----------

def test_planner_delete_single_number() -> None:
    plan = parse_director_plan("删除第9镜。", "shot_sel", "scene_1")
    assert not plan.requires_clarification
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "delete_shot"
    assert plan.steps[0].arguments["shot_id"] == "shot_number:9"


def test_planner_batch_update_plus_delete() -> None:
    plan = parse_director_plan("第8镜改成近景，删除第9镜。", "shot_sel", "scene_1")
    assert not plan.requires_clarification
    assert [op.tool for op in plan.steps] == ["update_shot", "delete_shot"]
    assert plan.steps[0].arguments == {"shot_id": "shot_number:8", "patch": {"shot_type": "close_up"}}
    assert plan.steps[1].arguments == {"shot_id": "shot_number:9"}


def test_planner_create_needs_scene() -> None:
    plan = parse_director_plan("新建一个近景镜头。", "shot_sel", "scene_1")
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "create_shot"
    assert plan.steps[0].arguments == {"scene_id": "scene_1", "shot": {"shot_type": "close_up"}}

    no_scene = parse_director_plan("新建一个近景镜头。", "shot_sel", None)
    assert no_scene.requires_clarification


def test_planner_compress_without_enumeration_asks() -> None:
    plan = parse_director_plan("把这场戏压缩一下。", "shot_sel", "scene_1")
    assert plan.requires_clarification
    assert plan.steps == []


def test_planner_single_update_unchanged() -> None:
    """Non-batch messages keep the legacy single-op path."""
    plan = parse_director_plan("把这个镜头改成近景。", "shot_sel", "scene_1")
    assert [op.tool for op in plan.steps] == ["update_shot"]


def test_intent_delete_and_create_mapping() -> None:
    delete = parse_production_intent("删除第9镜。", "shot_sel", "scene_1")
    assert delete.intent_type == "delete"
    assert delete.destructive is True
    assert delete.batch is False

    batch = parse_production_intent("第8镜改成近景，删除第9镜。", "shot_sel", "scene_1")
    assert batch.batch is True
    assert batch.destructive is True

    create = parse_production_intent("新建一个近景镜头。", "shot_sel", "scene_1")
    assert create.intent_type == "create"


# ---------- e2e helpers ----------

def _make_scene(client: TestClient, n: int = 3) -> dict:
    project = client.post("/api/v1/projects", json={"name": "PStructure"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}
    ).json()
    shots = [
        client.post(
            f"/api/v1/scenes/{scene['id']}/shots",
            json={"shot_type": "medium", "image_prompt": f"prompt {i}"},
        ).json()
        for i in range(n)
    ]
    return {"project_id": project["id"], "scene_id": scene["id"], "shots": shots}


def _wait_status(client: TestClient, run_id: str, statuses: set[str], timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not reach {statuses}")


def _run_director(client: TestClient, ctx: dict, message: str, shot: dict) -> str:
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": message,
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    assert resp.status_code == 202
    return resp.json()["id"]


def _live_shot_ids(client: TestClient, scene_id: str) -> list[str]:
    return [s["id"] for s in client.get(f"/api/v1/scenes/{scene_id}/shots").json()]


# ---------- e2e: create (R1 auto + undo) ----------

def test_director_create_shot_applies_and_undoes(client: TestClient) -> None:
    ctx = _make_scene(client, n=1)
    run_id = _run_director(client, ctx, "新建一个近景镜头。", ctx["shots"][0])
    done = _wait_status(client, run_id, {"completed", "failed"})
    assert done["status"] == "completed", done.get("result")

    live = _live_shot_ids(client, ctx["scene_id"])
    assert len(live) == 2
    created = next(s for s in client.get(f"/api/v1/scenes/{ctx['scene_id']}/shots").json() if s["id"] not in {ctx["shots"][0]["id"]})
    assert created["shot_type"] == "close_up"

    change_sets = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()
    assert len(change_sets) == 1
    assert change_sets[0]["tool"] == "create_shot"

    undone = client.post(
        f"/api/v1/agent/change-sets/{change_sets[0]['id']}/undo", json={"force": False}
    )
    assert undone.status_code == 200
    assert _live_shot_ids(client, ctx["scene_id"]) == [ctx["shots"][0]["id"]]


# ---------- e2e: delete (R3 proposal + guarded apply) ----------

def test_director_delete_shot_proposes_and_applies_on_approve(client: TestClient) -> None:
    ctx = _make_scene(client, n=3)
    victim = next(s for s in client.get(f"/api/v1/scenes/{ctx['scene_id']}/shots").json() if s["shot_number"] == 2)

    run_id = _run_director(client, ctx, "删除第2镜。", ctx["shots"][0])
    _wait_status(client, run_id, {"waiting_human", "waiting_approval"})
    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert len(proposals) == 1
    assert proposals[0]["tool"] == "delete_shot"
    assert proposals[0]["risk_level"] == "R3"

    resp = client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    assert resp.status_code == 200
    done = _wait_status(client, run_id, {"completed", "failed"})
    assert done["status"] == "completed", done.get("result")

    # resume re-run must not duplicate the proposal
    assert len(client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()) == 1
    assert victim["id"] not in _live_shot_ids(client, ctx["scene_id"])
    assert client.get(f"/api/v1/shots/{victim['id']}").status_code == 404


def test_director_delete_shot_reject_keeps_shot(client: TestClient) -> None:
    ctx = _make_scene(client, n=2)
    victim = next(s for s in client.get(f"/api/v1/scenes/{ctx['scene_id']}/shots").json() if s["shot_number"] == 2)

    run_id = _run_director(client, ctx, "删除第2镜。", ctx["shots"][0])
    _wait_status(client, run_id, {"waiting_human", "waiting_approval"})
    resp = client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "reject"})
    assert resp.status_code == 200
    done = _wait_status(client, run_id, {"completed", "failed"})
    assert done["status"] == "completed", done.get("result")
    assert victim["id"] in _live_shot_ids(client, ctx["scene_id"])


def test_undo_delete_restores_shot(client: TestClient) -> None:
    """P2-E2-T01: undo of a delete compensates via restore (no longer refused)."""
    ctx = _make_scene(client, n=2)
    victim = next(s for s in client.get(f"/api/v1/scenes/{ctx['scene_id']}/shots").json() if s["shot_number"] == 2)
    run_id = _run_director(client, ctx, "删除第2镜。", ctx["shots"][0])
    _wait_status(client, run_id, {"waiting_human", "waiting_approval"})
    client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    _wait_status(client, run_id, {"completed", "failed"})
    assert victim["id"] not in _live_shot_ids(client, ctx["scene_id"])

    change_sets = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()
    assert len(change_sets) == 1
    resp = client.post(
        f"/api/v1/agent/change-sets/{change_sets[0]['id']}/undo", json={"force": False}
    )
    assert resp.status_code == 200, resp.text
    assert victim["id"] in _live_shot_ids(client, ctx["scene_id"])


def test_undo_delete_conflicts_when_scene_gone(client: TestClient) -> None:
    """Restore conflicts surface as 409 with recovery (scene deleted since)."""
    ctx = _make_scene(client, n=2)
    run_id = _run_director(client, ctx, "删除第2镜。", ctx["shots"][0])
    _wait_status(client, run_id, {"waiting_human", "waiting_approval"})
    client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    _wait_status(client, run_id, {"completed", "failed"})
    client.delete(f"/api/v1/scenes/{ctx['scene_id']}")

    change_sets = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()
    resp = client.post(
        f"/api/v1/agent/change-sets/{change_sets[0]['id']}/undo", json={"force": False}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["recovery"] == "restore_scene"


# ---------- e2e: batch update + delete in one run ----------

def test_director_batch_update_and_delete(client: TestClient) -> None:
    ctx = _make_scene(client, n=3)
    by_number = {s["shot_number"]: s for s in client.get(f"/api/v1/scenes/{ctx['scene_id']}/shots").json()}

    run_id = _run_director(client, ctx, "第1镜改成近景，删除第3镜。", by_number[1])
    _wait_status(client, run_id, {"waiting_human", "waiting_approval"})
    # R1 update auto-applied before the R3 delete parked the run
    assert client.get(f"/api/v1/shots/{by_number[1]['id']}").json()["shot_type"] == "close_up"

    client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    done = _wait_status(client, run_id, {"completed", "failed"})
    assert done["status"] == "completed", done.get("result")
    assert by_number[3]["id"] not in _live_shot_ids(client, ctx["scene_id"])


# ---------- executor-level: reorder + ownership ----------

def test_executor_reorder_applies_and_undoes(session_factory) -> None:
    from sqlalchemy import select

    from app.agents.tools import ToolExecutor
    from app.db.models import AgentChangeSet, AgentRun
    from app.domain.agent import ToolOperation
    from app.domain.episode import EpisodeCreate
    from app.domain.project import ProjectCreate
    from app.domain.scene import SceneCreate
    from app.domain.shot import ShotCreate
    from app.services import EpisodeService, ProjectService, SceneService, ShotService
    from app.services.change_set_service import ChangeSetService

    factory, _ = session_factory
    session = factory()
    project = ProjectService(session).create_project(ProjectCreate(name="R"))
    episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
    scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
    shots = [ShotService(session).create_shot(scene.id, ShotCreate(shot_type="medium")) for _ in range(3)]
    session.commit()
    order_before = [s.id for s in ShotService(session).list_shots(scene.id)]
    assert [s.id for s in shots] == order_before

    run = AgentRun(id="run_reorder_1", project_id=project.id, status="running")
    session.add(run)
    session.commit()

    executor = ToolExecutor(session, project_id=project.id, run_id=run.id)
    reversed_ids = list(reversed(order_before))
    result = executor.execute(
        ToolOperation(tool="reorder_shots", arguments={"scene_id": scene.id, "ordered_ids": reversed_ids})
    )
    assert result.success is True, result.error
    assert [s.id for s in ShotService(session).list_shots(scene.id)] == reversed_ids

    # no-op reorder reports without recording
    again = executor.execute(
        ToolOperation(tool="reorder_shots", arguments={"scene_id": scene.id, "ordered_ids": reversed_ids})
    )
    assert again.success is True
    assert (again.data or {}).get("applied") is False

    # undo restores the original order
    rows = list(
        session.scalars(
            select(AgentChangeSet).where(AgentChangeSet.run_id == run.id)
        )
    )
    assert len(rows) == 1
    ChangeSetService(session).undo(rows[0].id)
    assert [s.id for s in ShotService(session).list_shots(scene.id)] == order_before
    session.close()


def test_executor_reorder_rejects_partial_set(session_factory) -> None:
    from app.agents.tools import ToolExecutor
    from app.db.models import AgentRun
    from app.domain.agent import ToolOperation
    from app.domain.episode import EpisodeCreate
    from app.domain.project import ProjectCreate
    from app.domain.scene import SceneCreate
    from app.domain.shot import ShotCreate
    from app.services import EpisodeService, ProjectService, SceneService, ShotService

    factory, _ = session_factory
    session = factory()
    project = ProjectService(session).create_project(ProjectCreate(name="R2"))
    episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
    scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
    shots = [ShotService(session).create_shot(scene.id, ShotCreate(shot_type="medium")) for _ in range(3)]
    session.commit()
    run = AgentRun(id="run_reorder_2", project_id=project.id, status="running")
    session.add(run)
    session.commit()

    executor = ToolExecutor(session, project_id=project.id, run_id=run.id)
    result = executor.execute(
        ToolOperation(
            tool="reorder_shots",
            arguments={"scene_id": scene.id, "ordered_ids": [shots[0].id, shots[1].id]},
        )
    )
    assert result.success is False
    session.close()


def test_executor_rejects_foreign_delete(session_factory) -> None:
    from app.agents.tools import ToolExecutor
    from app.db.models import AgentRun
    from app.domain.agent import ToolOperation
    from app.domain.episode import EpisodeCreate
    from app.domain.project import ProjectCreate
    from app.domain.scene import SceneCreate
    from app.domain.shot import ShotCreate
    from app.services import EpisodeService, ProjectService, SceneService, ShotService

    factory, _ = session_factory
    session = factory()

    def _chain(name: str):
        project = ProjectService(session).create_project(ProjectCreate(name=name))
        episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
        scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
        shot = ShotService(session).create_shot(scene.id, ShotCreate(shot_type="medium"))
        return project, shot

    project_a, _ = _chain("A")
    _, shot_b = _chain("B")
    run = AgentRun(id="run_del_foreign", project_id=project_a.id, status="running")
    session.add(run)
    session.commit()

    executor = ToolExecutor(session, project_id=project_a.id, run_id=run.id)
    result = executor.execute(ToolOperation(tool="delete_shot", arguments={"shot_id": shot_b.id}))
    assert result.success is False
    assert "project" in (result.error or "")
    assert ShotService(session).get_shot(shot_b.id).shot_type == "medium"
    session.close()
