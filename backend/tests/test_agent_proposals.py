"""P7 proposal system + persistence + checkpointer tests.

Covers:
- Scenario A: update_shot → pending Proposal + WAITING_HUMAN + agent.approval.required
- approve → ShotService applies (shot field + revision+1) + proposal applied
- reject → not applied + proposal rejected
- BaseRevision conflict (user edit before approve) → conflict, not overwritten
- Schema validation: illegal field → 422
- proposals list endpoint; generate_image / get_shot produce no proposal
- checkpointer: interrupt then resume continues (deterministic fake path)
- run persistence: a new runner session can read the run back
"""

import time

from fastapi.testclient import TestClient


def _make_project_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P7Proposal"}).json()
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


def _wait_status(client, run_id, statuses, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not reach {statuses}")


def _wait_run(client, run_id, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not finish")


def _wait_pending(client, run_id):
    return _wait_status(client, run_id, {"waiting_human", "waiting_approval"})


def test_update_shot_produces_proposal_and_waiting_human(client: TestClient) -> None:
    """Scenario A baseline: pending proposal + run WAITING_HUMAN + approval event."""
    from app.events.bus import EVENT_AGENT_APPROVAL_REQUIRED, EVENT_AGENT_PROPOSAL_CREATED

    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]

    collected, cb = _subscribe_events({EVENT_AGENT_APPROVAL_REQUIRED, EVENT_AGENT_PROPOSAL_CREATED})

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    waiting = _wait_pending(client, run_id)
    assert waiting["status"] == "waiting_human"
    assert len(waiting["pending_proposals"]) == 1

    # shot NOT mutated yet
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["revision"] == 1

    _unsubscribe(cb)
    prop_events = [e for e in collected if e["type"] == EVENT_AGENT_PROPOSAL_CREATED]
    approve_events = [e for e in collected if e["type"] == EVENT_AGENT_APPROVAL_REQUIRED]
    assert len(prop_events) == 1
    assert prop_events[0]["payload"]["target_id"] == shot["id"]
    assert len(approve_events) >= 1
    assert approve_events[0]["payload"]["proposal_id"] == waiting["pending_proposals"][0]["id"]
    assert approve_events[0]["payload"]["changes"] == {"shot_type": "close_up"}


def test_approve_applies_shot_via_service(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]

    approved = client.post(f"/api/v1/agent/proposals/{proposal_id}/approve").json()
    assert approved["status"] == "applied"

    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["shot_type"] == "close_up"
    assert updated["revision"] == 2

    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert proposals[0]["status"] == "applied"


def test_reject_does_not_apply(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]

    rejected = client.post(f"/api/v1/agent/proposals/{proposal_id}/reject").json()
    assert rejected["status"] == "rejected"

    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["shot_type"] == "medium"
    assert updated["revision"] == 1


def test_base_revision_conflict_not_overwritten(client: TestClient) -> None:
    """P7-T016: user edits the shot while a proposal is pending → approve = conflict."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    waiting = _wait_pending(client, run_id)
    proposal = waiting["pending_proposals"][0]
    assert proposal["base_revision"] == 1

    # user edits → revision 2
    client.patch(f"/api/v1/shots/{shot['id']}", json={"revision": 1, "patch": {"emotion": "tense"}})
    current = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert current["revision"] == 2

    approved = client.post(f"/api/v1/agent/proposals/{proposal['id']}/approve").json()
    assert approved["status"] == "conflict"

    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["revision"] == 2
    assert updated["emotion"] == "tense"
    assert updated["shot_type"] == "medium"  # agent change NOT applied


def test_schema_invalid_field_raises_422(client: TestClient) -> None:
    from app.core.errors import StudioError, ValidationError
    from app.agents.director.runner import _session
    from app.services.proposal_service import ProposalService

    with _session() as session:
        service = ProposalService(session)
        try:
            service.validate_changes({"bogus_field": 1})
        except (ValidationError, StudioError) as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError("expected 422 for illegal field")


def test_generate_image_and_get_shot_no_proposal(client: TestClient) -> None:
    """generate_image / get_shot do not produce proposals and don't need approval."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "重新生成这个镜头。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    done = _wait_run(client, run_id)  # completes directly (no waiting_human)
    assert done["status"] == "completed"
    assert done["result"]["generation_submitted"] == 1
    assert client.get(f"/api/v1/agent/runs/{run_id}/proposals").json() == []


def test_run_persists_across_new_store(client: TestClient) -> None:
    """P7-T001: the run lives in the DB — a fresh runner session still reads it back."""
    from app.agents.director.runner import get_run

    ctx = _make_project_shot(client)
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [ctx["shots"][0]["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    _wait_pending(client, run_id)
    # a brand-new get_run call (fresh session) reads it from the DB
    reloaded = get_run(run_id)
    assert reloaded.id == run_id
    assert reloaded.status == "waiting_human"
    assert len(reloaded.pending_proposals) == 1


def test_proposals_endpoint_lists_decided(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][2]
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]
    client.post(f"/api/v1/agent/proposals/{proposal_id}/approve")
    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert proposals[0]["status"] == "applied"
    assert proposals[0]["changes"] == {"shot_type": "close_up"}


def test_resume_continue_generation_after_approve(client: TestClient) -> None:
    """Scenario B: approve via resume → update applies AND generate_image runs."""
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
    waiting = _wait_pending(client, run_id)
    assert len(waiting["pending_proposals"]) == 1
    client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    done = _wait_run(client, run_id)
    assert done["status"] == "completed", done.get("result")
    tools = [d["tool"] for d in done["result"]["details"]]
    assert "update_shot" in tools and "generate_image" in tools
    assert done["result"]["generation_submitted"] == 1
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["revision"] == 2


def test_checkpointer_interrupt_resume_continues() -> None:
    """P7-T004: the sqlite checkpointer persists an interrupt and resume continues."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    from app.agents.checkpointers.sqlite_saver import SqliteCheckpointSaver

    class State(TypedDict, total=False):
        value: str

    def node(state):
        decision = interrupt({"ask": "proceed?"})
        state["value"] = "decided:" + str((decision or {}).get("decision") if isinstance(decision, dict) else decision)
        return state

    builder = StateGraph(State)
    builder.add_node("n", node)
    builder.add_edge(START, "n")
    builder.add_edge("n", END)
    saver = SqliteCheckpointSaver()  # in-memory
    app = builder.compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "ckpt-1"}}

    first = app.invoke({}, cfg)
    assert "value" not in first  # interrupted, no value yet
    # state persisted
    snap = app.get_state(cfg)
    assert any(i for t in snap.tasks for i in t.interrupts)

    resumed = app.invoke(Command(resume={"decision": "approve"}), cfg)
    assert resumed["value"] == "decided:approve"
    saver.close()


def _subscribe_events(event_types: set[str]):
    from app.events.bus import bus

    collected = []

    def _on(event):
        if event.event_type in event_types:
            collected.append({"type": event.event_type, "entity_id": event.entity_id, "payload": event.payload})

    bus.subscribe("*", _on)
    return collected, _on


def _unsubscribe(cb) -> None:
    from app.events.bus import bus

    try:
        bus._subscribers["*"].remove(cb)
    except (KeyError, ValueError):
        pass
