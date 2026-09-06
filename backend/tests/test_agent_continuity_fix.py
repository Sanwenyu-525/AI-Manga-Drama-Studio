"""Director continuity_fix planning (agent-director §78 third must-pass case).

The planner previously never emitted continuity_fix (fake rules had no continuity
branch; ToolOperation rejected the tool), so "第八镜和第九镜接不上" fell back to
a read-only get_shot. Now:
- fake planner emits continuity_fix with just a shot_id (warning resolved by executor);
- the executor falls back to the latest open warning for that shot, fails
  structurally (NO_OPEN_WARNING) when there is none, and rejects cross-project
  warnings (P1-E3-T01 defense in depth);
- the full run parks in WAITING_HUMAN and marks the warning fixed on approve.
"""

import time

from fastapi.testclient import TestClient

from app.agents.fake_planner import parse_director_plan, parse_production_intent


# ---------- planner unit ----------

def test_planner_emits_continuity_fix_for_seam_issue() -> None:
    plan = parse_director_plan("第8镜和第9镜接不上。", "shot_sel", "scene_1")
    assert not plan.requires_clarification
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "continuity_fix"
    assert plan.steps[0].arguments["shot_id"] == "shot_number:8"
    assert plan.steps[0].arguments["patch"] == {}


def test_planner_continuity_fix_carries_shot_patch() -> None:
    plan = parse_director_plan("把这个镜头改成近景修复连续性。", "shot_sel", "scene_1")
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "continuity_fix"
    assert plan.steps[0].arguments["patch"] == {"shot_type": "close_up"}


def test_planner_continuity_fix_then_regenerate() -> None:
    plan = parse_director_plan("第八镜接不上，修好后重新生成。", "shot_sel", "scene_1")
    assert [op.tool for op in plan.steps] == ["continuity_fix", "generate_image"]


def test_planner_continuity_without_target_asks() -> None:
    plan = parse_director_plan("检查一下连续性。", None, "scene_1")
    assert plan.requires_clarification
    assert plan.steps == []


def test_production_intent_maps_continuity_fix_to_review() -> None:
    intent = parse_production_intent("第八镜和第九镜接不上。", "shot_sel", "scene_1")
    assert intent.intent_type == "review"
    assert intent.target_type == "shot"


# ---------- e2e helpers ----------

def _make_scene(client: TestClient, n: int = 2) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P8DirectorFix"}).json()
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


def _wait_warnings(client: TestClient, scene_id: str, timeout: float = 15.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        warnings = client.get(f"/api/v1/scenes/{scene_id}/continuity-warnings").json()
        if warnings:
            return warnings
        time.sleep(0.1)
    raise TimeoutError("no continuity warnings appeared")


def _make_open_warning(client: TestClient, ctx: dict):
    """Emotion flip tense→calm yields a semantic action_logic warning on shots[1]."""
    shot0, shot1 = ctx["shots"]
    for shot, emotion in ((shot0, "tense"), (shot1, "calm")):
        resp = client.patch(
            f"/api/v1/shots/{shot['id']}", json={"revision": 1, "patch": {"emotion": emotion}}
        )
        assert resp.status_code == 200
    resp = client.post("/api/v1/agent/continuity/check", json={"scene_id": ctx["scene_id"]})
    assert resp.status_code == 202
    warnings = _wait_warnings(client, ctx["scene_id"])
    sem = next(w for w in warnings if w.get("shot_id") == shot1["id"] and w["status"] == "open")
    return shot1, sem


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


# ---------- e2e ----------

def test_director_continuity_fix_proposes_and_marks_fixed_on_approve(client: TestClient) -> None:
    ctx = _make_scene(client)
    shot1, warning = _make_open_warning(client, ctx)

    run_id = _run_director(client, ctx, "这个镜头接不上，修一下。", shot1)
    _wait_status(client, run_id, {"waiting_human", "waiting_approval"})
    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert len(proposals) == 1
    assert proposals[0]["tool"] == "continuity_fix"
    assert proposals[0]["changes"].get("_warning") == warning["id"]

    resp = client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    assert resp.status_code == 200
    done = _wait_status(client, run_id, {"completed", "failed"})
    assert done["status"] == "completed", done.get("result")

    # resume re-run must not duplicate the proposal; approve applied it
    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert len(proposals) == 1
    assert proposals[0]["status"] == "applied"
    # fixed warnings leave the open list
    warnings = client.get(f"/api/v1/scenes/{ctx['scene_id']}/continuity-warnings").json()
    assert warning["id"] not in {w["id"] for w in warnings}


def test_director_continuity_fix_without_open_warning_fails_structured(client: TestClient) -> None:
    ctx = _make_scene(client)
    shot = ctx["shots"][0]

    run_id = _run_director(client, ctx, "这个镜头接不上，修一下。", shot)
    done = _wait_status(client, run_id, {"completed", "failed"})
    assert done["status"] == "failed"
    details = (done.get("result") or {}).get("details") or []
    assert details and details[0]["result"]["data"]["code"] == "NO_OPEN_WARNING"


# ---------- executor defense in depth ----------

def test_executor_rejects_foreign_warning(session_factory) -> None:
    from app.agents.tools import ToolExecutor
    from app.db.models import AgentRun, ContinuityWarning
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
        return project, scene, shot

    project_a, _, _ = _chain("A")
    project_b, scene_b, shot_b = _chain("B")
    warning_b = ContinuityWarning(
        project_id=project_b.id,
        scene_id=scene_b.id,
        shot_id=shot_b.id,
        category="costume",
        message="foreign",
        status="open",
    )
    session.add(warning_b)
    run_a = AgentRun(id="run_foreign_warn", project_id=project_a.id, status="running")
    session.add(run_a)
    session.commit()

    executor = ToolExecutor(session, project_id=project_a.id, run_id=run_a.id)
    result = executor.execute(
        ToolOperation(tool="continuity_fix", arguments={"warning_id": warning_b.id})
    )
    assert result.success is False
    assert "project" in (result.error or "")
    session.close()
