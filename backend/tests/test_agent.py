"""Stage D tests — Agent Scenario A/B/C (mvp-spec §97) with FakeLLM planner.

Scenario A: selection=Shot05, "改成近景" → Shot05.shot_type = close_up
Scenario B: "改成近景再生成" → Shot Update + Generation Created
Scenario C: no selection, "把这个改一下" → agent must NOT guess, asks for clarification
"""

import time

from fastapi.testclient import TestClient

from app.agents.director.runner import _runs, _cancel_requested


def _wait_run(client: TestClient, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(0.05)
    raise TimeoutError(f"agent run {run_id} did not finish")


def _make_project_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "StageD"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shots = [
        client.post(
            f"/api/v1/scenes/{scene['id']}/shots",
            json={"shot_type": "medium", "image_prompt": f"prompt {i}"},
        ).json()
        for i in range(3)
    ]
    return {"project_id": project["id"], "scene_id": scene["id"], "shots": shots}


def test_scenario_a_modify_selected_shot(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]  # "Shot 05"

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "workspace": "storyboard", "scene_id": ctx["scene_id"]},
        },
    )
    assert resp.status_code == 202
    run_id = resp.json()["id"]

    done = _wait_run(client, run_id)
    assert done["status"] == "completed", done.get("result")

    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["shot_type"] == "close_up"
    assert updated["revision"] == 2  # revision bumped by agent mutation

    result = done["result"]
    assert result["tool_count"] == 1
    assert result["details"][0]["tool"] == "update_shot"


def test_scenario_b_modify_and_generate(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][2]

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "改成近景然后重新生成。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    done = _wait_run(client, run_id)
    assert done["status"] == "completed"

    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["shot_type"] == "close_up"

    tools = [d["tool"] for d in done["result"]["details"]]
    assert "update_shot" in tools
    assert "generate_image" in tools
    assert done["result"]["generation_submitted"] == 1

    # generation actually queued in the DB (worker may have completed it already — that's fine)
    generations = client.get(f"/api/v1/shots/{shot['id']}/generations").json()
    assert len(generations) >= 1
    assert generations[0]["type"] == "image"


def test_scenario_c_no_selection_requires_clarification(client: TestClient) -> None:
    ctx = _make_project_shot(client)

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个改一下。",
            "selection": {"shot_ids": [], "workspace": "storyboard"},
        },
    )
    run_id = resp.json()["id"]
    done = _wait_run(client, run_id)
    assert done["status"] == "completed"
    assert done["result"]["clarification"] is not None  # agent asked instead of guessing
    assert done["result"]["tool_count"] == 0

    # nothing was modified
    first = client.get(f"/api/v1/scenes/{ctx['scene_id']}/shots").json()
    assert all(s["shot_type"] == "medium" for s in first)


def test_scenario_a_explicit_shot_number_wins_over_selection(client: TestClient) -> None:
    """Contract §79: explicit language > selection."""
    ctx = _make_project_shot(client)
    selected = ctx["shots"][0]
    target = ctx["shots"][2]  # "第3镜"

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把第3镜改成近景。",
            "selection": {"shot_ids": [selected["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    done = _wait_run(client, run_id)
    assert done["status"] == "completed"

    assert client.get(f"/api/v1/shots/{target['id']}").json()["shot_type"] == "close_up"
    assert client.get(f"/api/v1/shots/{selected['id']}").json()["shot_type"] == "medium"


def test_cancel_run(client: TestClient) -> None:
    # isolate global runner state (parallel background tasks may still be settling)
    _runs.clear()
    _cancel_requested.clear()

    ctx = _make_project_shot(client)
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "改成近景。",
            "selection": {"shot_ids": [ctx["shots"][0]["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    cancelled = client.post(f"/api/v1/agent/runs/{run_id}/cancel").json()
    assert cancelled["status"] == "cancelled"

    # cancel again → 409
    again = client.post(f"/api/v1/agent/runs/{run_id}/cancel")
    assert again.status_code == 409

    # resume without approval → 409
    resume = client.post(f"/api/v1/agent/runs/{run_id}/resume")
    assert resume.status_code == 409
