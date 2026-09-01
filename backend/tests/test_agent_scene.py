"""自主迭代 07 — AI Director update_scene 工具测试。

覆盖：场景级指令 → update_scene 自动应用（R1）+ scene ChangeSet 可撤销 +
P8-T017 连续性重算；风险分级；planner 场景意图（无场景澄清 / 无值澄清）。
"""

import time

from fastapi.testclient import TestClient

from app.agents.risk import classify_tool_operation, requires_approval


def _wait_run(client: TestClient, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(0.05)
    raise TimeoutError(f"agent run {run_id} did not finish")


def _make_scene(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "SceneAgent"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "天台"}).json()
    return {"project_id": project["id"], "scene_id": scene["id"]}


def _run_director(client: TestClient, ctx: dict, message: str) -> str:
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": message,
            "selection": {"scene_id": ctx["scene_id"], "shot_ids": []},
        },
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["id"]


def test_update_scene_applies_env_and_records_change_set(client: TestClient) -> None:
    """Scenario：把这场戏改成夜晚 → update_scene 自动应用（R1）+ scene ChangeSet。"""
    ctx = _make_scene(client)
    scene = client.get(f"/api/v1/scenes/{ctx['scene_id']}").json()
    assert scene["revision"] == 1

    run_id = _run_director(client, ctx, "把这场戏改成夜晚。")
    done = _wait_run(client, run_id)
    assert done["status"] == "completed", done.get("result")
    assert done["result"]["summary"], done.get("result")

    updated = client.get(f"/api/v1/scenes/{ctx['scene_id']}").json()
    assert updated["time_of_day"] == "夜晚", updated
    assert updated["revision"] == 2, updated

    # scene ChangeSet 已记录（entity_type=scene, tool=update_scene）
    change_sets = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()
    scene_cs = [cs for cs in change_sets if cs["entity_type"] == "scene" and cs["tool"] == "update_scene"]
    assert len(scene_cs) == 1, change_sets
    assert scene_cs[0]["before"] == {"time_of_day": None}
    assert scene_cs[0]["after"] == {"time_of_day": "夜晚"}


def test_update_scene_undo_restores_previous_value(client: TestClient) -> None:
    ctx = _make_scene(client)
    # 先手动把时段设为「白天」（revision 1→2）——Agent 修改的是已设置字段，撤销才有明确恢复目标。
    scene = client.get(f"/api/v1/scenes/{ctx['scene_id']}").json()
    resp = client.patch(
        f"/api/v1/scenes/{ctx['scene_id']}",
        json={"revision": scene["revision"], "patch": {"time_of_day": "白天"}},
    )
    assert resp.status_code == 200, resp.text
    # Agent 把这场戏改成夜晚（revision 2→3）
    run_id = _run_director(client, ctx, "把这场戏改成夜晚。")
    _wait_run(client, run_id)
    assert client.get(f"/api/v1/scenes/{ctx['scene_id']}").json()["time_of_day"] == "夜晚"
    change_sets = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()
    cs = next(c for c in change_sets if c["entity_type"] == "scene")
    assert cs["before"] == {"time_of_day": "白天"}

    resp = client.post(f"/api/v1/agent/change-sets/{cs['id']}/undo")
    assert resp.status_code == 200, resp.text
    updated = client.get(f"/api/v1/scenes/{ctx['scene_id']}").json()
    assert updated["time_of_day"] == "白天", updated  # 撤销恢复到修改前


def test_update_scene_is_r1_no_approval() -> None:
    assessment = classify_tool_operation("update_scene", {"scene_id": "sc_1", "patch": {"time_of_day": "夜晚"}})
    assert assessment.risk_level == "R1"
    assert requires_approval(assessment) is False


def test_update_scene_triggers_continuity_recompute(client: TestClient) -> None:
    """P8-T017：场景环境变更 → 连续性基准重算并传播。"""
    ctx = _make_scene(client)
    client.post(f"/api/v1/scenes/{ctx['scene_id']}/continuity/recompute")
    run_id = _run_director(client, ctx, "把这场戏的氛围改成紧张。")
    _wait_run(client, run_id)
    continuity = client.get(f"/api/v1/scenes/{ctx['scene_id']}/continuity").json()
    env = (continuity.get("base_state") or {}).get("environment") or {}
    assert env.get("mood") == "紧张", env


def test_planner_scene_intent_requires_scene_or_value() -> None:
    from app.agents.fake_planner import parse_director_plan

    # 场景目标 + 环境值 → update_scene
    plan = parse_director_plan("把这场戏改成夜晚。", None, "sc_1")
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "update_scene"
    assert plan.steps[0].arguments == {"scene_id": "sc_1", "patch": {"time_of_day": "夜晚"}}

    # 场景目标但无环境值 → 澄清
    plan = parse_director_plan("改一下这个场景。", None, "sc_1")
    assert plan.requires_clarification is True

    # 场景目标但无选中场景 → 澄清
    plan = parse_director_plan("把这场戏改成夜晚。", None, None)
    assert plan.requires_clarification is True
