"""Continuity Agent runner (P8-T018/T019; api-event-contract §142 Continuity).

A continuity_check run is a fast async task (202 + run_id): it reads the scene
continuity input (P8-A state when merged, shot base data for now), runs the rule
path + semantic LLM review, persists open warnings, and marks the run completed.
A continuity_fix run parks in WAITING_HUMAN with a Proposal (same P7 approval
flow) — it is created synchronously (no long task) since the proposal + human
decision is the async part already handled by ProposalService.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db import session as db_session_module
from app.db.models import AgentRun
from app.domain.agent import RUN_STATUS_COMPLETED, RUN_STATUS_FAILED
from app.events.bus import (
    EVENT_AGENT_RUN_COMPLETED,
    EVENT_AGENT_RUN_FAILED,
    StudioEvent,
    bus,
)
from app.services.continuity_service import ContinuityService

logger = get_logger("agent.continuity")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_run_id() -> str:
    return f"cont_{uuid.uuid4().hex[:10]}"


def _session():
    """Open a session through the test-overridable factory (conftest)."""
    return db_session_module.session_factory_provider()()


def create_check_run(scene_id: str) -> AgentRun:
    """Persist a continuity_check AgentRun (status=running) and spawn the task.

    The scene must exist (404 otherwise); the project is captured at creation for
    run bookkeeping. The check itself runs async (202 + run_id)."""
    from app.db.models import Scene

    run_id = _new_run_id()
    now = _now()
    with _session() as session:
        scene = session.get(Scene, scene_id)
        if scene is None or scene.deleted_at:
            raise NotFoundError("Scene does not exist or was deleted.", {"scene_id": scene_id})
        project_id = ContinuityService(session).project_id_for_scene(scene_id)
        run = AgentRun(
            id=run_id,
            project_id=project_id or "",
            run_type="continuity_check",
            status="running",
            input_json=json.dumps({"scene_id": scene_id}, ensure_ascii=False),
            current_stage="running",
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.commit()
    asyncio.create_task(_run_check(run_id, scene_id))
    return run


async def _run_check(run_id: str, scene_id: str) -> None:
    """Execute the continuity check and finalize the run (or fail it)."""
    import traceback

    from app.llm import factory as llm_factory

    try:
        llm = llm_factory.create_gateway()
        with _session() as session:
            service = ContinuityService(session)
            # resolve the real project for run bookkeeping
            project_id = service.project_id_for_scene(scene_id)
            created = await service.check_scene(scene_id, llm, run_id=run_id)
            if project_id is None:
                raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            run.project_id = project_id
            run.status = RUN_STATUS_COMPLETED
            run.current_stage = "completed"
            run.completed_at = _now()
            run.updated_at = _now()
            run.result_json = json.dumps(
                {"scene_id": scene_id, "warnings_created": len(created)},
                ensure_ascii=False,
            )
            session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_AGENT_RUN_COMPLETED,
                entity_type="agent_run",
                entity_id=run_id,
                project_id=project_id,
                payload={"result": {"scene_id": scene_id, "warnings_created": len(created)}},
            )
        )
        logger.info("continuity check run %s completed (%d warnings)", run_id, len(created))
    except Exception:  # noqa: BLE001
        logger.exception("continuity check run %s failed", run_id)
        with _session() as session:
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            run.status = RUN_STATUS_FAILED
            run.error_message = traceback.format_exc()
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
                payload={"error": "continuity check failed"},
            )
        )


def check_result(run_id: str) -> dict[str, Any]:
    """Load a continuity_check run's summarised result (warnings_created)."""
    with _session() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            raise NotFoundError("Agent run does not exist.", {"run_id": run_id})
        return {
            "run_id": run.id,
            "status": run.status,
            "result": json.loads(run.result_json) if run.result_json else None,
            "error": run.error_message,
            "run_type": run.run_type,
        }


def create_fix_run(warning_id: str, patch: dict | None = None) -> AgentRun:
    """Create a continuity_fix run: loads the warning, creates a pending Proposal
    through ProposalService, parks the run in WAITING_HUMAN (P8-T019). Returns the
    persisted run. Approve/reject reuse the P7 proposal API/resume."""
    from app.db.models import ContinuityWarning
    from app.services.proposal_service import ProposalService

    patch = patch or {}
    run_id = _new_run_id()
    now = _now()
    with _session() as session:
        warning = session.get(ContinuityWarning, warning_id)
        if warning is None:
            raise NotFoundError("Continuity warning does not exist.", {"warning_id": warning_id})
        run = AgentRun(
            id=run_id,
            project_id=warning.project_id,
            run_type="continuity_fix",
            status="running",
            input_json=json.dumps({"warning_id": warning_id, "patch": patch}, ensure_ascii=False),
            current_stage="proposing",
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.commit()
        ProposalService(session).create_continuity_fix_proposal(
            run,
            warning_id,
            warning.scene_id,
            warning.shot_id,
            patch,
        )
        return session.get(AgentRun, run_id)
