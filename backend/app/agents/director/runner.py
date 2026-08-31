"""AgentRun persistence + runner (P7-T001, api-event-contract §23-31, §52-54).

The Stage D AgentRunStore was in-process (process-global dict). P7 migrates it to
the SQLAlchemy agent_runs table so run records survive restarts and resume can
continue a run (each run's LangGraph thread_id == run_id via the custom
SqliteCheckpointSaver, P7-T004).

Runs execute the LangGraph Director in an asyncio task; events stream via the
EventBus → WS gateway. A run parks in WAITING_HUMAN when update_shot emits a
Proposal (P7-T012) and resumes on human approve/reject (P7-T017/T018).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db import session as db_session_module
from app.db.models import AgentProposal, AgentRun
from app.domain.agent import (
    AgentRunCreate,
    AgentRunRead,
    DirectorPlan,
    PROPOSAL_STATUS_PENDING,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_CANCELLING,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING_HUMAN,
)
from app.events.bus import (
    EVENT_AGENT_RUN_CANCELLED,
    EVENT_AGENT_RUN_COMPLETED,
    EVENT_AGENT_RUN_FAILED,
    EVENT_AGENT_RUN_STARTED,
    StudioEvent,
    bus,
)
from app.services.proposal_service import ProposalService

logger = get_logger("agent.runner")

# stage names mirror the graph nodes (contract §25 current_stage)
STAGES = ("understand", "load_context", "plan", "execute", "review")

# run_id → in-flight lane guard (prevent double-start) + cancel token (runtime-only).
_running: set[str] = set()
_cancel_requested: set[str] = set()

try:  # langgraph.errors.GraphInterrupt — raised when a node calls interrupt()
    from langgraph.errors import GraphInterrupt as _GRAPH_INTERRUPT  # type: ignore
except ImportError:  # pragma: no cover
    _GRAPH_INTERRUPT = Exception


def _mark_waiting_human(run_id: str) -> None:
    """Ensure a run that interrupted is db-marked waiting_human (no terminal event)."""
    from app.domain.agent import RUN_STATUS_WAITING_HUMAN

    with _session() as session:
        run = session.get(AgentRun, run_id)
        if run is not None and run.status not in ("completed", "failed", "cancelled", "cancelling"):
            run.status = RUN_STATUS_WAITING_HUMAN
            run.updated_at = _now()
            session.commit()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:10]}"


def _session():
    """Open a session through the test-overridable factory (conftest)."""
    return db_session_module.session_factory_provider()()


def set_run_stage(run_id: str, stage: str) -> None:
    """Real-time current_stage for GET run (P1-E3-T02) — called by graph nodes."""
    with _session() as session:
        run = session.get(AgentRun, run_id)
        if run is not None:
            run.current_stage = stage
            run.updated_at = _now()
            session.commit()


def is_cancel_requested(run_id: str) -> bool:
    """Cancel token check — graph nodes/tool boundaries consult this (P1-E3-T02)."""
    return run_id in _cancel_requested


def create_run(data: AgentRunCreate) -> AgentRunRead:
    """Persist a new AgentRun row (status=created). API-compatible with Stage D."""
    run_id = _new_run_id()
    now = _now()
    with _session() as session:
        run = AgentRun(
            id=run_id,
            project_id=data.project_id,
            run_type="director",
            status="created",
            input_json=json.dumps(
                {"message": data.message, "selection": data.selection.model_dump()},
                ensure_ascii=False,
            ),
            started_at=None,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.commit()
        return _to_read(session, run)


def start_run(run_id: str) -> None:
    """Mark running, publish run.started, and spawn the graph task (guarded)."""
    with _session() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            raise NotFoundError("Agent run does not exist.", {"run_id": run_id})
        if run_id in _running:
            raise ConflictError("Agent run is already started.", {"run_id": run_id})
        _running.add(run_id)
        run.status = RUN_STATUS_RUNNING
        run.started_at = _now()
        run.updated_at = _now()
        project_id = run.project_id
        session.commit()
    bus.publish(
        StudioEvent(
            event_type=EVENT_AGENT_RUN_STARTED,
            entity_type="agent_run",
            entity_id=run_id,
            project_id=project_id,
            payload={"status": RUN_STATUS_RUNNING},
        )
    )
    asyncio.create_task(_run_graph(run_id))


async def _run_graph(run_id: str) -> None:
    """Invoke the Director graph with the checkpointer (thread_id = run_id).

    The graph may return while the run is suspended (WAITING_HUMAN after a
    proposal was emitted via LangGraph interrupt). In that case we leave the run
    parked and publish nothing; a later resume_run() continues the graph and
    finalizes it.
    """
    import traceback

    from app.agents.director.graph import director_graph

    with _session() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            return
        meta = _load_input(run)
        project_id = run.project_id

    initial_state = {
        "run_id": run_id,
        "project_id": project_id,
        "session_id": run_id,
        "user_message": meta["message"],
        "selection": meta["selection"],
        "tool_results": [],
    }
    config = {"configurable": {"thread_id": run_id}}
    try:
        final = await director_graph.ainvoke(initial_state, config)
        with _session() as session:
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            if run.status == RUN_STATUS_WAITING_HUMAN:
                # suspended awaiting human approval — no terminal event yet
                return
            _finalize(session, run, final, cancelled=run_id in _cancel_requested)
    except _GRAPH_INTERRUPT:
        # A proposal-based interrupt escaped ainvoke — the run is WAITING_HUMAN.
        _mark_waiting_human(run_id)
        logger.info("agent run %s interrupted awaiting human approval", run_id)
    except Exception:  # noqa: BLE001
        logger.exception("agent run %s graph failed", run_id)
        with _session() as session:
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.result_json = json.dumps({"error": str(traceback.format_exc())})
            run.completed_at = _now()
            run.updated_at = _now()
            project_id = run.project_id
            session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_AGENT_RUN_FAILED,
                entity_type="agent_run",
                entity_id=run_id,
                project_id=project_id,
                payload={"error": "agent run failed"},
            )
        )
    finally:
        _running.discard(run_id)


def _finalize(session, run: AgentRun, final: dict, *, cancelled: bool) -> None:
    """Persist the terminal status/plan/result and publish the ONE terminal event."""
    status = final.get("status", RUN_STATUS_COMPLETED)
    plan = final.get("plan")
    result = final.get("final_result")
    if plan is not None:
        run.plan_json = json.dumps(plan, ensure_ascii=False)
    if result is not None:
        run.result_json = json.dumps(result, ensure_ascii=False)
    run.completed_at = _now()
    run.updated_at = _now()
    project_id = run.project_id
    if cancelled:
        run.status = RUN_STATUS_CANCELLED
        session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_AGENT_RUN_CANCELLED,
                entity_type="agent_run",
                entity_id=run.id,
                project_id=project_id,
            )
        )
        return
    run.status = status
    session.commit()
    event_type = EVENT_AGENT_RUN_COMPLETED if status == RUN_STATUS_COMPLETED else EVENT_AGENT_RUN_FAILED
    bus.publish(
        StudioEvent(
            event_type=event_type,
            entity_type="agent_run",
            entity_id=run.id,
            project_id=project_id,
            payload={"result": result},
        )
    )
    logger.info("agent run %s -> %s", run.id, status)


def get_run(run_id: str) -> AgentRunRead:
    """Load a run from the DB. When WAITING_HUMAN, run the lazy TTL sweep first
    (P2-E3-T02) so overdue proposals surface as expired and a fully-expired run
    fails instead of hanging forever, then attach pending proposal summaries."""
    with _session() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            raise NotFoundError("Agent run does not exist.", {"run_id": run_id})
        if run.status in (RUN_STATUS_WAITING_HUMAN, "waiting_approval"):
            ProposalService(session).expire_stale_proposals(run_id)
            session.refresh(run)
        return _to_read(session, run)


def cancel_run(run_id: str) -> AgentRunRead:
    """Cooperative cancel (P1-E3-T02): status → cancelling immediately; the graph
    observes the token at the next node/tool boundary and stops producing side
    effects; the SINGLE terminal agent.run.cancelled event is published by the
    runner once the graph has actually stopped (no contradictory events)."""
    with _session() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            raise NotFoundError("Agent run does not exist.", {"run_id": run_id})
        if run.status in ("completed", "failed", "cancelled", "cancelling"):
            raise ConflictError(
                "Agent run already finished or is being cancelled.",
                {"run_id": run_id, "status": run.status},
            )
        _cancel_requested.add(run_id)
        run.status = RUN_STATUS_CANCELLING
        run.updated_at = _now()
        session.commit()
        logger.info("agent run %s cancel requested (cancelling)", run_id)
        return _to_read(session, run)


def active_run_count(project_id: str) -> int:
    """In-flight runs for a project (bootstrap payload, contract §103)."""
    from sqlalchemy import select

    with _session() as session:
        return len(
            list(
                session.scalars(
                    select(AgentRun.id).where(
                        AgentRun.project_id == project_id,
                        AgentRun.status.in_(("created", "running", "waiting_approval", "waiting_human", "cancelling")),
                    )
                )
            )
        )


def resume_run(run_id: str, decision: str = "approve", proposal_ids: list[str] | None = None) -> AgentRunRead:
    """P7-T017/T018: resume a WAITING_HUMAN run with a human decision.

    decision="approve" → apply the (specified or all pending) proposals through
    ShotService, then continue the interrupted graph (e.g. run remaining steps);
    decision="reject" → mark them rejected (nothing applied) and continue.

    Backwards compatible: a bare resume (no body) defaults to approve-all-pending.
    """
    from langgraph.types import Command

    with _session() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            raise NotFoundError("Agent run does not exist.", {"run_id": run_id})
        if run.status not in ("waiting_human", "waiting_approval"):
            raise ConflictError(
                "Run has no pending human approval to resume.",
                {"run_id": run_id, "status": run.status},
            )
        # P2-E3-T02: lazily expire overdue proposals first — an expired proposal
        # is terminal and must not be decided by this resume.
        ProposalService(session).expire_stale_proposals(run_id)
        session.refresh(run)
        pending = _pending_proposals(session, run_id, proposal_ids)
        if not pending:
            raise ConflictError("No pending proposals to decide.", {"run_id": run_id})

        proposal_service = ProposalService(session)
        if decision == "approve":
            for proposal in pending:
                proposal_service.approve(proposal.id)
        else:
            for proposal in pending:
                proposal_service.reject(proposal.id)
        session.commit()

    config = {"configurable": {"thread_id": run_id}}
    asyncio.create_task(_continue_graph(run_id, config, Command(resume={"decision": decision})))

    return get_run(run_id)


async def _continue_graph(run_id: str, config: dict, command) -> None:
    """Resume a suspended graph after a human decision, then finalize the run."""
    import traceback

    from app.agents.director.graph import director_graph

    _running.add(run_id)
    try:
        final = await director_graph.ainvoke(command, config)
        with _session() as session:
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            # This is a resumed execution after a human decision — finalize it.
            _finalize(session, run, final, cancelled=run_id in _cancel_requested)
    except _GRAPH_INTERRUPT:
        # Resume surfaced another interrupt (another proposal) — stay waiting_human.
        _mark_waiting_human(run_id)
        logger.info("agent run %s re-interrupted awaiting human approval", run_id)
    except Exception:  # noqa: BLE001
        logger.exception("agent run %s resume failed", run_id)
        with _session() as session:
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.error_message = str(traceback.format_exc())
            run.completed_at = _now()
            run.updated_at = _now()
            project_id = run.project_id
            session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_AGENT_RUN_FAILED,
                entity_type="agent_run",
                entity_id=run_id,
                project_id=project_id,
                payload={"error": "agent run resume failed"},
            )
        )
    finally:
        _running.discard(run_id)


def _pending_proposals(session, run_id: str, proposal_ids: list[str] | None) -> list[AgentProposal]:
    q = session.query(AgentProposal).filter(
        AgentProposal.run_id == run_id,
        AgentProposal.status == PROPOSAL_STATUS_PENDING,
    )
    if proposal_ids:
        q = q.filter(AgentProposal.id.in_(proposal_ids))
    return list(q.all())


def _load_input(run: AgentRun) -> dict:
    data = json.loads(run.input_json) if run.input_json else {}
    return {"message": data.get("message", ""), "selection": data.get("selection") or {}}


def _to_read(session, run: AgentRun) -> AgentRunRead:
    pending: list[AgentProposal]
    if run.status in ("waiting_human", "waiting_approval"):
        pending = _pending_proposals(session, run.id, None)
    else:
        pending = []
    return AgentRunRead(
        id=run.id,
        project_id=run.project_id,
        status=run.status,
        current_stage=run.current_stage,
        plan=DirectorPlan.model_validate(json.loads(run.plan_json)) if run.plan_json else None,
        approval=None,
        change_set_id=None,
        result=json.loads(run.result_json) if run.result_json else None,
        pending_proposals=[_proposal_summary(p) for p in pending],
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _proposal_summary(p: AgentProposal) -> dict:
    return {
        "id": p.id,
        "tool": p.tool,
        "target_type": p.target_type,
        "target_id": p.target_id,
        "base_revision": p.base_revision,
        "changes": json.loads(p.changes_json) if p.changes_json else {},
        "status": p.status,
        # P2-E3-T02: risk metadata on the approval card (matches AgentProposalRead).
        "risk_level": p.risk_level,
        "reason": p.reason,
        "estimated_tasks": p.estimated_tasks,
        "estimated_cost": p.estimated_cost,
        "irreversible": p.irreversible,
        "expires_at": p.expires_at,
    }
