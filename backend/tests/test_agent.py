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


def _make_two_scene_project(client: TestClient) -> dict:
    """Project with two scenes, each holding a shot numbered 1 (ambiguous numbers)."""
    project = client.post("/api/v1/projects", json={"name": "StageD-amb"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scenes = []
    for i in range(2):
        scene = client.post(
            f"/api/v1/episodes/{episode['id']}/scenes", json={"name": f"S{i + 1}"}
        ).json()
        shot = client.post(
            f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "medium"}
        ).json()
        scenes.append({"scene_id": scene["id"], "shot": shot})
    return {"project_id": project["id"], "episode_id": episode["id"], "scenes": scenes}


def test_foreign_shot_id_rejected_before_tools(client: TestClient) -> None:
    """P1-E3-T01: selection pointing at another project's shot must fail before any
    tool runs — no cross-project mutation, clarification instead of guessing."""
    ctx_a = _make_project_shot(client)
    ctx_b = _make_project_shot(client)
    foreign = ctx_b["shots"][0]

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx_a["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [foreign["id"]], "scene_id": ctx_a["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    done = _wait_run(client, run_id)
    assert done["status"] == "completed"
    assert done["result"]["clarification"] is not None
    assert done["result"]["tool_count"] == 0

    # foreign shot untouched
    fetched = client.get(f"/api/v1/shots/{foreign['id']}").json()
    assert fetched["shot_type"] == "medium"


def test_deleted_shot_rejected_before_tools(client: TestClient) -> None:
    """P1-E3-T01: selection pointing at a soft-deleted shot → clarification, no tools."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    client.delete(f"/api/v1/shots/{shot['id']}")

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    done = _wait_run(client, resp.json()["id"])
    assert done["status"] == "completed"
    assert done["result"]["clarification"] is not None
    assert done["result"]["tool_count"] == 0


def test_ambiguous_shot_number_requires_clarification(client: TestClient) -> None:
    """P1-E3-T01: same shot_number across the project without a selected scene →
    clarification, never a silent first pick."""
    ctx = _make_two_scene_project(client)

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把第1镜改成近景。",
            "selection": {"shot_ids": [], "workspace": "storyboard"},
        },
    )
    done = _wait_run(client, resp.json()["id"])
    assert done["status"] == "completed"
    assert done["result"]["clarification"] is not None
    assert done["result"]["tool_count"] == 0

    # neither scene's shot was modified
    for entry in ctx["scenes"]:
        fetched = client.get(f"/api/v1/shots/{entry['shot']['id']}").json()
        assert fetched["shot_type"] == "medium"


def test_ambiguous_shot_number_resolved_by_selected_scene(client: TestClient) -> None:
    """P1-E3-T01: the same ambiguous number resolves inside the selected scene."""
    ctx = _make_two_scene_project(client)
    scene_a = ctx["scenes"][0]
    scene_b = ctx["scenes"][1]

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把第1镜改成近景。",
            "selection": {"shot_ids": [], "scene_id": scene_a["scene_id"]},
        },
    )
    done = _wait_run(client, resp.json()["id"])
    assert done["status"] == "completed", done.get("result")

    assert client.get(f"/api/v1/shots/{scene_a['shot']['id']}").json()["shot_type"] == "close_up"
    assert client.get(f"/api/v1/shots/{scene_b['shot']['id']}").json()["shot_type"] == "medium"


def test_concurrent_runs_do_not_cross_selection(client: TestClient) -> None:
    """P1-E3-T01: selection is run-local — two concurrent runs must target their own
    shots (regression for the old process-global _FAKE_SELECTION)."""
    ctx = _make_project_shot(client)
    shot_a = ctx["shots"][0]
    shot_b = ctx["shots"][1]

    r1 = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot_a["id"]], "scene_id": ctx["scene_id"]},
        },
    ).json()
    r2 = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot_b["id"]], "scene_id": ctx["scene_id"]},
        },
    ).json()

    done1 = _wait_run(client, r1["id"])
    done2 = _wait_run(client, r2["id"])
    assert done1["status"] == "completed" and done2["status"] == "completed"

    # each run resolved its OWN selection (no cross-talk)
    arg1 = done1["result"]["details"][0]["arguments"]["shot_id"]
    arg2 = done2["result"]["details"][0]["arguments"]["shot_id"]
    assert arg1 == shot_a["id"]
    assert arg2 == shot_b["id"]

    # both shots updated by their own runs
    assert client.get(f"/api/v1/shots/{shot_a['id']}").json()["shot_type"] == "close_up"
    assert client.get(f"/api/v1/shots/{shot_b['id']}").json()["shot_type"] == "close_up"


def test_cancel_run(client: TestClient) -> None:
    """P1-E3-T02: cancel is cooperative — status goes cancelling immediately, the
    graph observes the token and reaches the single terminal cancelled state."""
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
    cancelling = client.post(f"/api/v1/agent/runs/{run_id}/cancel").json()
    assert cancelling["status"] == "cancelling"

    done = _wait_run(client, run_id)  # polls until the graph reaches terminal state
    assert done["status"] == "cancelled"

    # cancel again → 409 (already finished / being cancelled)
    again = client.post(f"/api/v1/agent/runs/{run_id}/cancel")
    assert again.status_code == 409

    # resume without approval → 409
    resume = client.post(f"/api/v1/agent/runs/{run_id}/resume")
    assert resume.status_code == 409


def _subscribe_events(event_types: set[str]) -> list[dict]:
    """Subscribe to the in-process bus and collect matching events (test helper)."""
    from app.events.bus import bus

    collected: list[dict] = []

    def _on(event) -> None:
        if event.event_type in event_types:
            collected.append(
                {"type": event.event_type, "entity_id": event.entity_id, "payload": event.payload}
            )

    bus.subscribe("*", _on)
    return collected, _on


def _unsubscribe(callback) -> None:
    from app.events.bus import bus

    try:
        bus._subscribers["*"].remove(callback)  # noqa: SLF001 — test-only cleanup
    except (KeyError, ValueError):
        pass


def test_cancel_before_graph_stops_everything(client: TestClient, monkeypatch) -> None:
    """P1-E3-T02: cancel while the first node is in flight → the next node boundary
    stops the run: no tool, no side effect, exactly one terminal cancelled event,
    never a completed event."""
    from app.agents.director import graph as graph_module
    from app.events.bus import (
        EVENT_AGENT_RUN_CANCELLED,
        EVENT_AGENT_RUN_COMPLETED,
        EVENT_AGENT_TOOL_STARTED,
    )
    from app.llm.fake import FakeLLMGateway

    class SlowGateway(FakeLLMGateway):
        async def structured(self, schema, system, prompt):
            import asyncio

            await asyncio.sleep(0.3)  # keep the understand node in flight
            return await super().structured(schema, system, prompt)

    monkeypatch.setattr(graph_module, "create_gateway", lambda: SlowGateway())

    _runs.clear()
    _cancel_requested.clear()
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    client.post(f"/api/v1/agent/runs/{run_id}/cancel")
    done = _wait_run(client, run_id)
    assert done["status"] == "cancelled"

    # shot untouched (revision 1), no generation rows
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["revision"] == 1
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []

    collected, cb = _subscribe_events(
        {EVENT_AGENT_RUN_CANCELLED, EVENT_AGENT_RUN_COMPLETED, EVENT_AGENT_TOOL_STARTED}
    )
    # note: events of THIS run were already published before subscription —
    # re-run the same flow to observe the single-cancelled-event guarantee
    _runs.clear()
    _cancel_requested.clear()
    ctx2 = _make_project_shot(client)
    resp2 = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx2["project_id"],
            "message": "改成近景。",
            "selection": {"shot_ids": [ctx2["shots"][0]["id"]], "scene_id": ctx2["scene_id"]},
        },
    )
    run2 = resp2.json()["id"]
    client.post(f"/api/v1/agent/runs/{run2}/cancel")
    _wait_run(client, run2)

    cancelled_events = [e for e in collected if e["type"] == EVENT_AGENT_RUN_CANCELLED]
    completed_events = [e for e in collected if e["type"] == EVENT_AGENT_RUN_COMPLETED]
    tool_events = [e for e in collected if e["type"] == EVENT_AGENT_TOOL_STARTED]
    assert len(cancelled_events) == 1
    assert cancelled_events[0]["entity_id"] == run2
    assert completed_events == []
    assert tool_events == []
    _unsubscribe(cb)


def test_cancel_between_tools_skips_remaining(client: TestClient, monkeypatch) -> None:
    """P1-E3-T02: cancel at the tool boundary — the FIRST tool may commit, the
    remaining tools must NOT run (no Generation created after cancel)."""
    from app.agents.tools import ToolExecutor
    from app.agents.director.runner import _cancel_requested as cancel_set
    from app.events.bus import (
        EVENT_AGENT_RUN_CANCELLED,
        EVENT_AGENT_RUN_COMPLETED,
        EVENT_GENERATION_CREATED,
    )

    _runs.clear()
    _cancel_requested.clear()
    ctx = _make_project_shot(client)
    shot = ctx["shots"][2]

    original_update = ToolExecutor._update_shot
    cancelled_run_id = {"id": None}

    def update_then_cancel(self, args):
        result = original_update(self, args)
        cancel_set.add(self.run_id)  # simulate user cancel right after the first tool
        cancelled_run_id["id"] = self.run_id
        return result

    monkeypatch.setattr(ToolExecutor, "_update_shot", update_then_cancel)

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
    assert done["status"] == "cancelled"

    # the first (update_shot) tool committed…
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["shot_type"] == "close_up"
    # …but the second (generate_image) tool never ran — no Generation, no Version
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []


def test_current_stage_updates_while_running(client: TestClient, monkeypatch) -> None:
    """P1-E3-T02: GET run exposes the real-time current_stage as the graph moves."""
    from app.agents.director import graph as graph_module
    from app.llm.fake import FakeLLMGateway

    _runs.clear()
    _cancel_requested.clear()
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]

    class SlowGateway(FakeLLMGateway):
        async def structured(self, schema, system, prompt):
            import asyncio

            await asyncio.sleep(0.3)  # keep the understand stage observable
            return await super().structured(schema, system, prompt)

    monkeypatch.setattr(graph_module, "create_gateway", lambda: SlowGateway())
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]

    observed: set[str] = set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["current_stage"]:
            observed.add(run["current_stage"])
        if run["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.02)

    # "understand" is kept observable by the slow gateway; "review" is the final
    # stage. Fast intermediate stages are not guaranteed to be sampled.
    assert "understand" in observed
    assert "review" in observed


def test_shot_updated_event_carries_agent_source_and_run_id(client: TestClient) -> None:
    """P1-E3-T02: shot.updated distinguishes user vs agent and links run_id."""
    from app.events.bus import EVENT_SHOT_UPDATED

    _runs.clear()
    _cancel_requested.clear()
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]

    collected, cb = _subscribe_events({EVENT_SHOT_UPDATED})
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    _wait_run(client, run_id)
    _unsubscribe(cb)

    shot_events = [e for e in collected if e["payload"].get("source") == "agent"]
    assert len(shot_events) == 1
    assert shot_events[0]["payload"]["run_id"] == run_id
    assert shot_events[0]["payload"]["changed_fields"] == ["shot_type"]

    # a user edit carries source=user (default) and no run_id
    collected2, cb2 = _subscribe_events({EVENT_SHOT_UPDATED})
    client.patch(
        f"/api/v1/shots/{shot['id']}",
        json={"revision": 2, "patch": {"emotion": "tense"}},
    )
    _unsubscribe(cb2)
    user_events = [e for e in collected2 if e["type"] == EVENT_SHOT_UPDATED]
    assert len(user_events) == 1
    assert user_events[0]["payload"]["source"] == "user"
    assert user_events[0]["payload"].get("run_id") is None
