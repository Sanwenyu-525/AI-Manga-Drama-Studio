"""Stage D / P2-E3 tests — Agent Scenario A/B/C (mvp-spec §97) with FakeLLM planner.

P2-E3-T02 risk semantics (supersedes P7's approve-everything):
- R1 update_shot AUTO-APPLIES through ShotService and records an undoable
  ChangeSet (P2-E3-T03) — no proposal, no WAITING_HUMAN.
- R2 generate_image REQUIRES approval: a pending Proposal (risk metadata + TTL)
  parks the run in WAITING_HUMAN; approve creates the Generation, reject skips.

Scenario A: selection=Shot05, "改成近景" → auto-applied (close_up, revision+1)
            + agent_change_sets row (undo restores the previous value).
Scenario B: "改成近景再生成" → update auto-applies; generate_image → R2 proposal
            → approve → Generation created.
Scenario C: no selection, "把这个改一下" → agent must NOT guess, asks for clarification.
"""

import time

from fastapi.testclient import TestClient

from app.agents.director.runner import _cancel_requested


def _wait_run(client: TestClient, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(0.05)
    raise TimeoutError(f"agent run {run_id} did not finish")


def _wait_status(client: TestClient, run_id: str, statuses: set[str], timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise TimeoutError(f"agent run {run_id} did not reach {statuses}")


def _wait_pending(client: TestClient, run_id: str) -> dict:
    return _wait_status(client, run_id, {"waiting_human", "waiting_approval"})


def _approve_run(client: TestClient, run_id: str) -> dict:
    """Wait until WAITING_HUMAN then approve all pending proposals via resume."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        run = _wait_status(client, run_id, {"waiting_human", "waiting_approval", "completed", "failed", "cancelled"})
        if run["status"] in ("waiting_human", "waiting_approval"):
            resp = client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
            if resp.status_code == 200:
                return resp.json()
            # transient race: re-poll to see if it settled to terminal meanwhile
            time.sleep(0.1)
            continue
        return run
    return client.get(f"/api/v1/agent/runs/{run_id}").json()


def _make_project_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "StageD"}).json()
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
        for i in range(3)
    ]
    return {"project_id": project["id"], "scene_id": scene["id"], "shots": shots}


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


# ---------- Scenario A: R1 auto-apply + ChangeSet ----------

def test_scenario_a_auto_applies_and_records_change_set(client: TestClient) -> None:
    """P2-E3-T02/T03: R1 update_shot applies directly (no approval fatigue) and
    leaves an undoable ChangeSet."""
    from app.events.bus import EVENT_AGENT_APPROVAL_REQUIRED

    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]  # "Shot 05"

    collected, cb = _subscribe_events({EVENT_AGENT_APPROVAL_REQUIRED})
    run_id = _run_director(client, ctx, "把这个镜头改成近景。", shot)

    done = _wait_run(client, run_id)
    assert done["status"] == "completed", done.get("result")
    _unsubscribe(cb)
    # R1 → no approval was ever requested
    assert collected == []

    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["shot_type"] == "close_up"
    assert updated["revision"] == 2

    # no proposal was created; the mutation is recorded as an undoable change set
    assert client.get(f"/api/v1/agent/runs/{run_id}/proposals").json() == []
    change_sets = client.get(
        "/api/v1/agent/change-sets", params={"run_id": run_id}
    ).json()
    assert len(change_sets) == 1
    cs = change_sets[0]
    assert cs["tool"] == "update_shot"
    assert cs["entity_id"] == shot["id"]
    assert cs["revision_before"] == 1
    assert cs["revision_after"] == 2
    assert cs["before"] == {"shot_type": "medium"}
    assert cs["after"] == {"shot_type": "close_up"}
    assert cs["undone"] is False


def test_scenario_a_undo_restores_previous_value(client: TestClient) -> None:
    """P2-E3-T03: undo applies the recorded before-values as a NEW compensating
    change — revision+1, history untouched."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    run_id = _run_director(client, ctx, "把这个镜头改成近景。", shot)
    _wait_run(client, run_id)

    cs_id = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()[0]["id"]
    undone = client.post(f"/api/v1/agent/change-sets/{cs_id}/undo", json={"force": False}).json()

    restored = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert restored["shot_type"] == "medium"
    assert restored["revision"] == 3  # 1 → agent 2 → undo 3

    # the compensating change set + the original's terminal undo state
    all_cs = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()
    assert undone["source"] == "undo"
    assert undone["before"] == {"shot_type": "close_up"}
    assert undone["after"] == {"shot_type": "medium"}
    original = next(c for c in all_cs if c["id"] == cs_id)
    assert original["undone"] is True
    assert original["undone_by_change_set_id"] == undone["id"]

    # undo is idempotent-terminal: second undo → 409
    again = client.post(f"/api/v1/agent/change-sets/{cs_id}/undo", json={"force": False})
    assert again.status_code == 409


# ---------- Scenario B: R1 apply + R2 approval + resume ----------

def test_scenario_b_approve_generation_then_complete(client: TestClient) -> None:
    """update auto-applies; generate_image parks for approval → resume approve →
    Generation created, run completed."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][2]
    run_id = _run_director(client, ctx, "改成近景然后重新生成。", shot)

    waiting = _wait_pending(client, run_id)
    assert waiting["status"] == "waiting_human"
    assert len(waiting["pending_proposals"]) == 1
    proposal = waiting["pending_proposals"][0]
    assert proposal["tool"] == "generate_image"

    # R2 red line: NO generation row exists before approval (P2-E3-T02)
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []

    # R1 part already applied while waiting
    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["shot_type"] == "close_up"

    client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    done = _wait_run(client, run_id)
    assert done["status"] == "completed", done.get("result")

    tools = [d["tool"] for d in done["result"]["details"]]
    assert "update_shot" in tools
    assert "generate_image" in tools
    assert done["result"]["generation_submitted"] == 1

    generations = client.get(f"/api/v1/shots/{shot['id']}/generations").json()
    assert len(generations) >= 1
    assert generations[0]["type"] == "image"


def test_reject_generation_proposal_no_generation(client: TestClient) -> None:
    """Scenario B + reject: the generation is never created."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]
    run_id = _run_director(client, ctx, "重新生成这个镜头。", shot)

    waiting = _wait_pending(client, run_id)
    assert len(waiting["pending_proposals"]) == 1

    client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "reject"})
    done = _wait_run(client, run_id)
    assert done["status"] == "completed"

    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []
    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert proposals[0]["status"] == "rejected"
    assert done["result"]["generation_submitted"] == 0


# ---------- R2 approval semantics ----------

def test_generate_image_requires_approval_r2(client: TestClient) -> None:
    """P2-E3-T02: R2 generate_image parks the run with a risk-graded proposal."""
    from app.events.bus import EVENT_AGENT_APPROVAL_REQUIRED, EVENT_AGENT_PROPOSAL_CREATED

    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    collected, cb = _subscribe_events({EVENT_AGENT_APPROVAL_REQUIRED, EVENT_AGENT_PROPOSAL_CREATED})
    run_id = _run_director(client, ctx, "重新生成第1镜。", shot)

    waiting = _wait_pending(client, run_id)
    assert waiting["status"] == "waiting_human"
    proposal = waiting["pending_proposals"][0]
    assert proposal["tool"] == "generate_image"
    assert proposal["base_revision"] == 1

    _unsubscribe(cb)
    prop_events = [e for e in collected if e["type"] == EVENT_AGENT_PROPOSAL_CREATED]
    approve_events = [e for e in collected if e["type"] == EVENT_AGENT_APPROVAL_REQUIRED]
    assert len(prop_events) == 1
    assert len(approve_events) >= 1
    payload = approve_events[0]["payload"]
    # structured risk metadata surfaces to the approval card (task AC)
    assert payload["risk_level"] == "R2"
    assert payload["estimated_tasks"] == 1
    assert payload["irreversible"] is False
    assert payload["expires_at"]

    # no generation created before approval
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []


def test_approve_generation_proposal_endpoint_creates_generation(client: TestClient) -> None:
    """Approve through the proposal endpoint (not resume): the Generation is created."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    run_id = _run_director(client, ctx, "重新生成第1镜。", shot)
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]

    approved = client.post(f"/api/v1/agent/proposals/{proposal_id}/approve").json()
    assert approved["status"] == "applied"
    assert approved["risk_level"] == "R2"

    generations = client.get(f"/api/v1/shots/{shot['id']}/generations").json()
    assert len(generations) == 1
    assert generations[0]["type"] == "image"


def test_base_revision_conflict_blocks_generation(client: TestClient) -> None:
    """P7-T016 (R2 form): a user edit between proposal and approve → conflict, no generation."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]
    run_id = _run_director(client, ctx, "重新生成这个镜头。", shot)
    waiting = _wait_pending(client, run_id)
    assert waiting["pending_proposals"][0]["base_revision"] == 1

    # user edits the shot while the proposal is pending (revision 1 → 2)
    client.patch(f"/api/v1/shots/{shot['id']}", json={"revision": 1, "patch": {"emotion": "tense"}})

    client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    _wait_run(client, run_id)

    # the agent did NOT create a generation over a changed shot
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []
    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert proposals[0]["status"] == "conflict"
    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["emotion"] == "tense"  # user edit preserved


def test_schema_invalid_proposal_rejected_422(client: TestClient) -> None:
    """P7-T014: illegal field in an update_shot patch fails structured validation."""
    from app.core.errors import ValidationError
    from app.services.proposal_service import ProposalService
    from app.db.models import AgentRun
    from app.agents.director.runner import _session

    with _session() as session:
        run = session.query(AgentRun).first()
        if run is None:
            import pytest

            pytest.skip("no agent run seeded")
        # simulate an agent patch with an illegal field
        from app.core.errors import StudioError

        service = ProposalService(session)
        try:
            service.validate_changes({"not_a_shot_field": 1})
        except (ValidationError, StudioError) as exc:
            assert exc.status_code == 422
        else:
            import pytest

            pytest.fail("expected 422 for illegal field")


# ---------- Scenario C: clarification ----------

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
    """Contract §79: explicit language > selection. R1 applies without approval."""
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
    run_id = resp.json()["id"]
    done = _wait_run(client, run_id)
    assert done["status"] == "completed", done.get("result")

    assert client.get(f"/api/v1/shots/{scene_a['shot']['id']}").json()["shot_type"] == "close_up"
    assert client.get(f"/api/v1/shots/{scene_b['shot']['id']}").json()["shot_type"] == "medium"


def test_concurrent_runs_do_not_cross_selection(client: TestClient) -> None:
    """P1-E3-T01: selection is run-local — two concurrent runs must target their own
    shots (regression for the old process-global _FAKE_SELECTION)."""
    _cancel_requested.clear()
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


def test_cancel_run(client: TestClient, monkeypatch) -> None:
    """P1-E3-T02: cancel is cooperative — status goes cancelling immediately, the
    graph observes the token and reaches the single terminal cancelled state."""
    from app.agents.director import graph as graph_module
    from app.llm.fake import FakeLLMGateway

    class SlowGateway(FakeLLMGateway):
        async def structured(self, schema, system, prompt):
            import asyncio

            await asyncio.sleep(0.3)  # keep the run cancellable while in flight
            return await super().structured(schema, system, prompt)

    monkeypatch.setattr(graph_module, "create_gateway", lambda task="default": SlowGateway())
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


def _subscribe_events(event_types: set[str]) -> tuple[list[dict], object]:
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
        bus._subscribers["*"].remove(callback)
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

    monkeypatch.setattr(graph_module, "create_gateway", lambda task="default": SlowGateway())
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

    # shot untouched (revision 1), no generation rows, no change sets
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["revision"] == 1
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []
    assert client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json() == []

    collected, cb = _subscribe_events(
        {EVENT_AGENT_RUN_CANCELLED, EVENT_AGENT_RUN_COMPLETED, EVENT_AGENT_TOOL_STARTED}
    )
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


def test_current_stage_updates_while_running(client: TestClient, monkeypatch) -> None:
    """P1-E3-T02: GET run exposes the real-time current_stage as the graph moves."""
    from app.agents.director import graph as graph_module
    from app.llm.fake import FakeLLMGateway

    _cancel_requested.clear()
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]

    class SlowGateway(FakeLLMGateway):
        async def structured(self, schema, system, prompt):
            import asyncio

            await asyncio.sleep(0.3)  # keep the understand stage observable
            return await super().structured(schema, system, prompt)

    monkeypatch.setattr(graph_module, "create_gateway", lambda task="default": SlowGateway())
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
        if run["status"] in ("waiting_human", "waiting_approval", "completed", "failed", "cancelled"):
            break
        time.sleep(0.02)

    # the LLM-slowed understand stage is observably reported; the R1 auto-apply
    # makes execute/review too fast to reliably catch between polls.
    assert "understand" in observed


def test_shot_updated_event_when_agent_applies(client: TestClient) -> None:
    """P7-T015 semantics (R1 auto-apply): the applied shot.updated carries
    source=agent and run_id (apply goes through ShotService, which emits the event)."""
    from app.events.bus import EVENT_SHOT_UPDATED

    _cancel_requested.clear()
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]

    collected, cb = _subscribe_events({EVENT_SHOT_UPDATED})
    run_id = _run_director(client, ctx, "把这个镜头改成近景。", shot)
    _wait_run(client, run_id)
    _unsubscribe(cb)

    shot_events = [e for e in collected if e["payload"].get("source") == "agent"]
    assert len(shot_events) == 1
    assert shot_events[0]["payload"]["run_id"] == run_id
    assert shot_events[0]["payload"]["changed_fields"] == ["shot_type"]
