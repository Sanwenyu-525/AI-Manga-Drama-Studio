"""AgentRunStore + runner (api-event-contract §23-31, §53): create/query/cancel agent runs.

Runs execute the LangGraph Director in an asyncio task; events stream via the
EventBus → WS gateway (agent events, contract §59-63). In-memory store for MVP
(Agent messages table + checkpointer come later).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.domain.agent import AgentRunCreate, AgentRunRead, DirectorPlan
from app.events.bus import (
    EVENT_AGENT_RUN_COMPLETED,
    EVENT_AGENT_RUN_FAILED,
    EVENT_AGENT_RUN_STARTED,
    StudioEvent,
    bus,
)

logger = get_logger("agent.runner")

# stage names mirror the graph nodes (contract §25 current_stage)
STAGES = ("understand", "load_context", "plan", "execute", "review")

_runs: dict[str, dict] = {}
_cancel_requested: set[str] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run(data: AgentRunCreate) -> AgentRunRead:
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    run = {
        "id": run_id,
        "project_id": data.project_id,
        "message": data.message,
        "selection": data.selection.model_dump(),
        "status": "created",
        "current_stage": None,
        "plan": None,
        "approval": None,
        "change_set_id": None,
        "result": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _runs[run_id] = run
    return _to_read(run)


def start_run(run_id: str) -> None:
    run = _runs[run_id]
    run["status"] = "running"
    run["updated_at"] = _now()
    bus.publish(
        StudioEvent(
            event_type=EVENT_AGENT_RUN_STARTED,
            entity_type="agent_run",
            entity_id=run_id,
            project_id=run["project_id"],
            payload={"status": "running"},
        )
    )
    asyncio.create_task(_run_graph(run_id))


async def _run_graph(run_id: str) -> None:
    from app.agents.director.graph import director_graph

    run = _runs.get(run_id)
    if run is None:
        return
    project_id = run["project_id"]

    initial_state = {
        "run_id": run_id,
        "project_id": project_id,
        "session_id": run_id,
        "user_message": run["message"],
        "selection": run["selection"],
        "tool_results": [],
    }

    try:
        final = await director_graph.ainvoke(initial_state)
        if run_id in _cancel_requested:
            run["status"] = "cancelled"
            bus.publish(
                StudioEvent(
                    event_type="agent.run.cancelled",
                    entity_type="agent_run",
                    entity_id=run_id,
                    project_id=project_id,
                )
            )
        else:
            run["status"] = final.get("status", "completed")
            run["current_stage"] = "review"
            run["plan"] = final.get("plan")
            run["result"] = final.get("final_result")
            bus.publish(
                StudioEvent(
                    event_type=EVENT_AGENT_RUN_COMPLETED if run["status"] == "completed" else EVENT_AGENT_RUN_FAILED,
                    entity_type="agent_run",
                    entity_id=run_id,
                    project_id=project_id,
                    payload={"result": run["result"]},
                )
            )
            logger.info("agent run %s -> %s", run_id, run["status"])
    except Exception as exc:  # noqa: BLE001 — graph failures are reported, not raised
        logger.exception("agent run %s failed", run_id)
        run["status"] = "failed"
        run["result"] = {"error": str(exc)}
        bus.publish(
            StudioEvent(
                event_type=EVENT_AGENT_RUN_FAILED,
                entity_type="agent_run",
                entity_id=run_id,
                project_id=project_id,
                payload={"error": str(exc)},
            )
        )
    finally:
        run["updated_at"] = _now()


def get_run(run_id: str) -> AgentRunRead:
    run = _runs.get(run_id)
    if run is None:
        raise NotFoundError("Agent run does not exist.", {"run_id": run_id})
    return _to_read(run)


def cancel_run(run_id: str) -> AgentRunRead:
    run = _runs.get(run_id)
    if run is None:
        raise NotFoundError("Agent run does not exist.", {"run_id": run_id})
    if run["status"] in ("completed", "failed", "cancelled"):
        raise ConflictError("Agent run already finished.", {"run_id": run_id, "status": run["status"]})
    _cancel_requested.add(run_id)
    run["status"] = "cancelled"
    run["updated_at"] = _now()
    bus.publish(
        StudioEvent(
            event_type="agent.run.cancelled",
            entity_type="agent_run",
            entity_id=run_id,
            project_id=run["project_id"],
        )
    )
    return _to_read(run)


def active_run_count(project_id: str) -> int:
    """In-flight runs for a project (bootstrap payload, contract §103)."""
    return sum(
        1
        for run in _runs.values()
        if run["project_id"] == project_id and run["status"] in ("created", "running", "waiting_approval")
    )


def resume_run(run_id: str) -> AgentRunRead:
    """MVP has no interrupt/approval flow yet — resume exists for contract compatibility."""
    run = _runs.get(run_id)
    if run is None:
        raise NotFoundError("Agent run does not exist.", {"run_id": run_id})
    if run["status"] != "waiting_approval":
        raise ConflictError(
            "Run has no pending approval to resume.",
            {"run_id": run_id, "status": run["status"]},
        )
    return _to_read(run)


def _to_read(run: dict) -> AgentRunRead:
    return AgentRunRead(
        id=run["id"],
        project_id=run["project_id"],
        status=run["status"],
        current_stage=run.get("current_stage"),
        plan=DirectorPlan.model_validate(run["plan"]) if run.get("plan") else None,
        approval=run.get("approval"),
        change_set_id=run.get("change_set_id"),
        result=run.get("result"),
        created_at=run["created_at"],
        updated_at=run["updated_at"],
    )
