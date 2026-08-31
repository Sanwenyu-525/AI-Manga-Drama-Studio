"""P7/P2-E3 proposal system + persistence + checkpointer tests.

P2-E3-T02 semantics (supersedes P7's approve-everything):
- update_shot (R1) auto-applies and records a ChangeSet — NO proposal (test_agent.py).
- generate_image (R2) produces a pending Proposal (risk metadata + TTL);
  the run parks in WAITING_HUMAN and emits agent.approval.required.
- approve → the Generation is created only here (base_revision guarded);
  reject → nothing is created.
- Expired proposals are terminal: approve → 409 + status=expired; a fully
  expired WAITING_HUMAN run fails (never hangs).
- checkpointer: interrupt then resume continues (deterministic fake path).
- run persistence: a new runner session can read the run back.
"""

import time
from datetime import UTC, datetime, timedelta

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


def _run_generation_request(client: TestClient, ctx: dict, shot: dict, message: str) -> str:
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


def test_generate_image_proposal_and_waiting_human(client: TestClient) -> None:
    """R2 baseline: pending proposal + run WAITING_HUMAN + approval event."""
    from app.events.bus import EVENT_AGENT_APPROVAL_REQUIRED, EVENT_AGENT_PROPOSAL_CREATED

    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]

    collected, cb = _subscribe_events({EVENT_AGENT_APPROVAL_REQUIRED, EVENT_AGENT_PROPOSAL_CREATED})
    run_id = _run_generation_request(client, ctx, shot, "重新生成这个镜头。")
    waiting = _wait_pending(client, run_id)
    assert waiting["status"] == "waiting_human"
    assert len(waiting["pending_proposals"]) == 1

    # shot NOT mutated, NO generation created
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["revision"] == 1
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []

    _unsubscribe(cb)
    prop_events = [e for e in collected if e["type"] == EVENT_AGENT_PROPOSAL_CREATED]
    approve_events = [e for e in collected if e["type"] == EVENT_AGENT_APPROVAL_REQUIRED]
    assert len(prop_events) == 1
    assert prop_events[0]["payload"]["target_id"] == shot["id"]
    assert prop_events[0]["payload"]["risk_level"] == "R2"
    assert len(approve_events) >= 1
    assert approve_events[0]["payload"]["proposal_id"] == waiting["pending_proposals"][0]["id"]
    assert approve_events[0]["payload"]["risk_level"] == "R2"


def test_approve_creates_generation_via_service(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    run_id = _run_generation_request(client, ctx, shot, "重新生成这个镜头。")
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]

    approved = client.post(f"/api/v1/agent/proposals/{proposal_id}/approve").json()
    assert approved["status"] == "applied"

    generations = client.get(f"/api/v1/shots/{shot['id']}/generations").json()
    assert len(generations) == 1
    assert generations[0]["type"] == "image"

    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert proposals[0]["status"] == "applied"
    assert proposals[0]["risk_level"] == "R2"
    assert proposals[0]["expires_at"]


def test_reject_does_not_create_generation(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]
    run_id = _run_generation_request(client, ctx, shot, "重新生成这个镜头。")
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]

    rejected = client.post(f"/api/v1/agent/proposals/{proposal_id}/reject").json()
    assert rejected["status"] == "rejected"

    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["revision"] == 1

    # approve after reject → 409 (terminal, idempotent)
    again = client.post(f"/api/v1/agent/proposals/{proposal_id}/approve")
    assert again.status_code == 409


def test_proposal_expired_is_terminal(client: TestClient) -> None:
    """P2-E3-T02: an overdue proposal cannot be decided — 409 + status=expired;
    the waiting run fails (never hangs forever)."""
    from app.events.bus import EVENT_AGENT_PROPOSAL_EXPIRED

    ctx = _make_project_shot(client)
    shot = ctx["shots"][2]
    run_id = _run_generation_request(client, ctx, shot, "重新生成这个镜头。")
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]

    collected, cb = _subscribe_events({EVENT_AGENT_PROPOSAL_EXPIRED})

    # backdate the expiry (simulates TTL elapsed)
    from app.agents.director.runner import _session
    from app.db.models import AgentProposal

    with _session() as session:
        proposal = session.get(AgentProposal, proposal_id)
        proposal.expires_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        session.commit()

    # approve → 409, proposal terminal=expired, nothing created
    resp = client.post(f"/api/v1/agent/proposals/{proposal_id}/approve")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["status"] == "expired"
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []

    # reject on the expired proposal → also 409 (terminal)
    resp2 = client.post(f"/api/v1/agent/proposals/{proposal_id}/reject")
    assert resp2.status_code == 409

    # GET run (lazy sweep) → run failed, no pending proposals left
    run = client.get(f"/api/v1/agent/runs/{run_id}").json()
    assert run["status"] == "failed"
    assert run["pending_proposals"] == []
    _unsubscribe(cb)
    assert len(collected) >= 1

    # resume on the failed run → 409
    resp3 = client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    assert resp3.status_code == 409


def test_expired_proposal_via_list_sweep(client: TestClient) -> None:
    """The proposals list also sweeps: an overdue pending proposal shows expired."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    run_id = _run_generation_request(client, ctx, shot, "重新生成这个镜头。")
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]

    from app.agents.director.runner import _session
    from app.db.models import AgentProposal

    with _session() as session:
        proposal = session.get(AgentProposal, proposal_id)
        proposal.expires_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        session.commit()

    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert proposals[0]["status"] == "expired"


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


def test_get_shot_and_update_shot_produce_no_proposal(client: TestClient) -> None:
    """R0/R1 tools do not produce proposals (update auto-applies + ChangeSet)."""
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
    done = _wait_run(client, run_id)  # completes directly (no waiting_human)
    assert done["status"] == "completed"
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["shot_type"] == "close_up"
    assert client.get(f"/api/v1/agent/runs/{run_id}/proposals").json() == []


def test_run_persists_across_new_store(client: TestClient) -> None:
    """P7-T001: the run lives in the DB — a fresh runner session still reads it back."""
    from app.agents.director.runner import get_run

    ctx = _make_project_shot(client)
    run_id = _run_generation_request(client, ctx, ctx["shots"][0], "重新生成这个镜头。")
    _wait_pending(client, run_id)
    # a brand-new get_run call (fresh session) reads it from the DB
    reloaded = get_run(run_id)
    assert reloaded.id == run_id
    assert reloaded.status == "waiting_human"
    assert len(reloaded.pending_proposals) == 1


def test_proposals_endpoint_lists_decided(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][2]
    run_id = _run_generation_request(client, ctx, shot, "重新生成这个镜头。")
    waiting = _wait_pending(client, run_id)
    proposal_id = waiting["pending_proposals"][0]["id"]
    client.post(f"/api/v1/agent/proposals/{proposal_id}/approve")
    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert proposals[0]["status"] == "applied"
    assert proposals[0]["tool"] == "generate_image"


def test_resume_continue_after_approve_creates_generation(client: TestClient) -> None:
    """Scenario B: approve via resume → generation created, run completes."""
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


def test_resume_reject_does_not_repropose(client: TestClient) -> None:
    """Resume re-executes the node; a rejected proposal must not be re-created —
    the run completes with zero generations."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    run_id = _run_generation_request(client, ctx, shot, "重新生成这个镜头。")
    _wait_pending(client, run_id)

    client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "reject"})
    done = _wait_run(client, run_id)
    assert done["status"] == "completed"

    # exactly ONE proposal for the run (no re-proposal after resume re-run)
    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert len(proposals) == 1
    assert proposals[0]["status"] == "rejected"
    assert client.get(f"/api/v1/shots/{shot['id']}/generations").json() == []


def test_interrupt_restart_resume_scenario(client: TestClient) -> None:
    """P2-E3-T02 AC: interrupt → (simulated) restart → resume still works — the
    run/proposals live in the DB and the checkpointer holds the graph state."""
    from app.agents.director.runner import get_run

    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]
    run_id = _run_generation_request(client, ctx, shot, "重新生成这个镜头。")
    _wait_pending(client, run_id)

    # simulated restart: read everything back through fresh sessions only
    reloaded = get_run(run_id)
    assert reloaded.status == "waiting_human"
    proposal_id = reloaded.pending_proposals[0]["id"]

    resp = client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
    assert resp.status_code == 200
    done = _wait_run(client, run_id)
    assert done["status"] == "completed"

    proposals = client.get(f"/api/v1/agent/runs/{run_id}/proposals").json()
    assert proposals[0]["id"] == proposal_id
    assert proposals[0]["status"] == "applied"
    assert len(client.get(f"/api/v1/shots/{shot['id']}/generations").json()) == 1


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
