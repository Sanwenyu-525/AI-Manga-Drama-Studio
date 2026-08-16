"""ProposalService (P7-T012..T016) — create/validate/apply agent Proposals.

The Agent NEVER writes the domain directly. update_shot now produces an
AgentProposal (status=pending); the run parks in WAITING_HUMAN and emits
agent.approval.required. A human approves/rejects it via the API. On approve,
the change is applied through ShotService (never raw ORM) after a base_revision
optimistic-concurrency check (P7-T016): a mismatched revision becomes "conflict"
and is NOT applied, so a concurrent user edit is never overwritten.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import AgentProposal, AgentRun, Shot
from app.db.models.agent import SHOT_CHANGE_FIELDS
from app.domain.agent import (
    PROPOSAL_STATUS_APPLIED,
    PROPOSAL_STATUS_APPROVED,
    PROPOSAL_STATUS_CONFLICT,
    PROPOSAL_STATUS_PENDING,
    PROPOSAL_STATUS_REJECTED,
    RUN_STATUS_WAITING_HUMAN,
)
from app.domain.shot import ShotUpdate
from app.events.bus import (
    EVENT_AGENT_APPROVAL_REQUIRED,
    EVENT_AGENT_PROPOSAL_APPROVED,
    EVENT_AGENT_PROPOSAL_CONFLICT,
    EVENT_AGENT_PROPOSAL_CREATED,
    EVENT_AGENT_PROPOSAL_REJECTED,
    EVENT_AGENT_RUN_AWAITING_APPROVAL,
    StudioEvent,
    bus,
)
from app.services.shot_service import ShotService

logger = get_logger("agent.proposal")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ProposalService:
    """Domain service that owns the AgentProposal lifecycle (P7-T012..T016).
    Applies changes ONLY through ShotService — it never writes Shot ORM directly.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotService(session)

    # ---------- create (from the Agent update_shot tool) ----------

    def create_shot_proposal(
        self,
        run: AgentRun,
        target_id: str,
        base_revision: int,
        changes: dict,
    ) -> AgentProposal:
        """Record a pending shot-edit proposal and park the run in WAITING_HUMAN.
        Raises ValidationError for illegal fields/types (structured-output validation).
        """
        validated = self.validate_changes(changes)
        proposal = AgentProposal(
            run_id=run.id,
            tool="update_shot",
            target_type="shot",
            target_id=target_id,
            base_revision=base_revision,
            changes_json=json.dumps(validated, ensure_ascii=False),
            status=PROPOSAL_STATUS_PENDING,
            created_at=_now(),
        )
        self.session.add(proposal)
        run.status = RUN_STATUS_WAITING_HUMAN
        run.updated_at = _now()
        self.session.commit()

        project_id = run.project_id
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_PROPOSAL_CREATED,
            entity_type="agent_proposal",
            entity_id=proposal.id,
            project_id=project_id,
            payload={"run_id": run.id, "target_id": target_id, "base_revision": base_revision, "changes": validated},
        ))
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_RUN_AWAITING_APPROVAL,
            entity_type="agent_run",
            entity_id=run.id,
            project_id=project_id,
            payload={"status": RUN_STATUS_WAITING_HUMAN, "proposal_ids": [proposal.id]},
        ))
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_APPROVAL_REQUIRED,
            entity_type="agent_run",
            entity_id=run.id,
            project_id=project_id,
            payload={"proposal_id": proposal.id, "target_type": "shot", "target_id": target_id, "changes": validated},
        ))
        logger.info("proposal %s created (run %s, shot %s, base_rev %d)", proposal.id, run.id, target_id, base_revision)
        return proposal

    def validate_changes(self, changes: dict) -> dict:
        """Structured-output + domain validation of the proposed shot fields.
        Only whitelisted fields are allowed; values must type-check against the
        ShotUpdate schema. Returns the sanitized non-None field dict.
        """
        unknown = [k for k in changes if k not in SHOT_CHANGE_FIELDS]
        unknown = [k for k in changes if k not in SHOT_CHANGE_FIELDS]
        if unknown:
            raise ValidationError("Illegal update_shot field(s).", {"fields": unknown, "allowed": list(SHOT_CHANGE_FIELDS)})
        try:
            patch = ShotUpdate.model_validate(changes)
        except Exception as exc:  # noqa: BLE001 - pydantic error surfaced as 422
            raise ValidationError(
                "Proposal changes failed schema validation.",
                {"detail": str(exc)},
            ) from exc
        return {k: v for k, v in patch.model_dump().items() if v is not None}

    # ---------- create (from the Agent continuity_fix tool, P8-T019) ----------

    def create_continuity_fix_proposal(
        self,
        run: AgentRun,
        warning_id: str,
        scene_id: str,
        shot_id: str | None,
        patch: dict,
    ) -> AgentProposal:
        """Record a pending continuity-fix proposal and park the run in WAITING_HUMAN.

        target_type is "shot" when the fix addresses a specific shot (applied via
        ShotService.update_shot on approve), or "continuity" for a scene-level fix
        (apply = mark the warning fixed, no domain mutation). The originating
        warning id travels inside changes_json under the reserved "_warning" key.
        """
        from app.db.models import Shot

        if shot_id is not None:
            shot = self.session.get(Shot, shot_id)
            if shot is None or shot.deleted_at:
                raise NotFoundError("Fix target shot does not exist.", {"shot_id": shot_id})
            changes = self.validate_changes({k: v for k, v in patch.items() if k != "_warning"})
            changes["_warning"] = warning_id
            proposal = AgentProposal(
                run_id=run.id,
                tool="continuity_fix",
                target_type="shot",
                target_id=shot_id,
                base_revision=shot.revision,
                changes_json=json.dumps(changes, ensure_ascii=False),
                status=PROPOSAL_STATUS_PENDING,
                created_at=_now(),
            )
        else:
            changes = {"_warning": warning_id}
            proposal = AgentProposal(
                run_id=run.id,
                tool="continuity_fix",
                target_type="continuity",
                target_id=scene_id,
                base_revision=1,
                changes_json=json.dumps(changes, ensure_ascii=False),
                status=PROPOSAL_STATUS_PENDING,
                created_at=_now(),
            )
        self.session.add(proposal)
        run.status = RUN_STATUS_WAITING_HUMAN
        run.updated_at = _now()
        self.session.commit()

        project_id = run.project_id
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_PROPOSAL_CREATED,
            entity_type="agent_proposal",
            entity_id=proposal.id,
            project_id=project_id,
            payload={"run_id": run.id, "tool": "continuity_fix", "target_type": proposal.target_type, "target_id": proposal.target_id, "warning_id": warning_id},
        ))
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_RUN_AWAITING_APPROVAL,
            entity_type="agent_run",
            entity_id=run.id,
            project_id=project_id,
            payload={"status": RUN_STATUS_WAITING_HUMAN, "proposal_ids": [proposal.id]},
        ))
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_APPROVAL_REQUIRED,
            entity_type="agent_run",
            entity_id=run.id,
            project_id=project_id,
            payload={"proposal_id": proposal.id, "target_type": proposal.target_type, "target_id": proposal.target_id, "warning_id": warning_id},
        ))
        logger.info("continuity_fix proposal %s created (warning %s)", proposal.id, warning_id)
        return proposal

    # ---------- decide (human review) ----------

    def approve(self, proposal_id: str) -> AgentProposal:
        """Approve then apply. BaseRevision check first: a shot edited since the
        proposal was made becomes "conflict" and is NOT applied (P7-T016).
        Returns the proposal with its final status (applied | conflict).
        """
        proposal = self._get_proposal(proposal_id)
        if proposal.status != PROPOSAL_STATUS_PENDING:
            raise ConflictError("Proposal is not pending.", {"proposal_id": proposal_id, "status": proposal.status})
        proposal.status = PROPOSAL_STATUS_APPROVED
        proposal.decided_at = _now()

        # P8-T019: continuity_fix proposals apply through the continuity warning
        # lifecycle. A shot-scoped fix goes through ShotService.update_shot (same
        # base_revision guard), then the originating warning is marked fixed; a
        # scene-scoped (continuity-target) fix only marks the warning(s) fixed.
        if proposal.tool == "continuity_fix":
            return self._approve_continuity_fix(proposal)

        shot = self.session.get(Shot, proposal.target_id)
        if shot is None or shot.deleted_at:
            proposal.status = PROPOSAL_STATUS_CONFLICT
            proposal.conflict_reason = "Target shot no longer exists."
            proposal.error_message = "shot missing/deleted"
            self.session.commit()
            self._emit_conflict(proposal)
            return proposal
        if shot.revision != proposal.base_revision:
            proposal.status = PROPOSAL_STATUS_CONFLICT
            proposal.conflict_reason = "Shot revision changed since proposal."
            proposal.error_message = (
                "expected_revision=" + str(proposal.base_revision) + ", current_revision=" + str(shot.revision)
            )
            self.session.commit()
            self._emit_conflict(proposal)
            logger.info("proposal %s conflict: base_rev %d != shot rev %d", proposal.id, proposal.base_revision, shot.revision)
            return proposal

        changes = json.loads(proposal.changes_json) if proposal.changes_json else {}
        patch = ShotUpdate.model_validate(changes)
        try:
            self.shots.update_shot(
                proposal.target_id,
                shot.revision,
                patch,
                source="agent",
                run_id=proposal.run_id,
            )
            proposal.status = PROPOSAL_STATUS_APPLIED
        except ConflictError:
            proposal.status = PROPOSAL_STATUS_CONFLICT
            proposal.conflict_reason = "Shot revision changed while applying."
            self.session.commit()
            self._emit_conflict(proposal)
            return proposal
        self.session.commit()
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_PROPOSAL_APPROVED,
            entity_type="agent_proposal",
            entity_id=proposal.id,
            project_id=proposal_run_project(self.session, proposal),
            payload={"run_id": proposal.run_id, "status": PROPOSAL_STATUS_APPLIED, "target_id": proposal.target_id, "changes": changes},
        ))
        logger.info("proposal %s applied (shot %s)", proposal.id, proposal.target_id)
        return proposal

    def _approve_continuity_fix(self, proposal: AgentProposal) -> AgentProposal:
        """Apply a continuity_fix proposal (P8-T019).

        Shot-scoped (target_type="shot"): apply the shot patch through ShotService
        (base_revision guarded, same as update_shot), then mark the originating
        warning fixed. Scene-scoped (target_type="continuity", no shot mutation):
        just mark the warning(s) fixed. Never writes raw ORM beyond bookkeeping.
        """
        from app.db.models import Shot

        changes = json.loads(proposal.changes_json) if proposal.changes_json else {}
        warning_id = changes.get("_warning")
        patch = {k: v for k, v in changes.items() if k != "_warning"}

        if proposal.target_type == "shot":
            shot = self.session.get(Shot, proposal.target_id)
            if shot is None or shot.deleted_at:
                proposal.status = PROPOSAL_STATUS_CONFLICT
                proposal.conflict_reason = "Target shot no longer exists."
                proposal.error_message = "shot missing/deleted"
                proposal.decided_at = proposal.decided_at or _now()
                self.session.commit()
                self._emit_conflict(proposal)
                return proposal
            if shot.revision != proposal.base_revision:
                proposal.status = PROPOSAL_STATUS_CONFLICT
                proposal.conflict_reason = "Shot revision changed since proposal."
                proposal.error_message = (
                    "expected_revision=" + str(proposal.base_revision) + ", current_revision=" + str(shot.revision)
                )
                proposal.decided_at = proposal.decided_at or _now()
                self.session.commit()
                self._emit_conflict(proposal)
                return proposal
            if patch:
                shot_patch = ShotUpdate.model_validate(patch)
                try:
                    self.shots.update_shot(
                        proposal.target_id,
                        shot.revision,
                        shot_patch,
                        source="agent",
                        run_id=proposal.run_id,
                    )
                except ConflictError:
                    proposal.status = PROPOSAL_STATUS_CONFLICT
                    proposal.conflict_reason = "Shot revision changed while applying."
                    proposal.decided_at = proposal.decided_at or _now()
                    self.session.commit()
                    self._emit_conflict(proposal)
                    return proposal
            proposal.status = PROPOSAL_STATUS_APPLIED
            self.session.commit()
            if warning_id:
                self._mark_warnings_fixed(warning_id)
        else:
            # scene-scoped continuity fix: no domain mutation — just mark fixed.
            proposal.status = PROPOSAL_STATUS_APPLIED
            proposal.decided_at = proposal.decided_at or _now()
            self.session.commit()
            if warning_id:
                self._mark_warnings_fixed(warning_id)

        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_PROPOSAL_APPROVED,
            entity_type="agent_proposal",
            entity_id=proposal.id,
            project_id=proposal_run_project(self.session, proposal),
            payload={"run_id": proposal.run_id, "tool": "continuity_fix", "status": PROPOSAL_STATUS_APPLIED, "target_id": proposal.target_id, "warning_id": warning_id},
        ))
        logger.info("continuity_fix proposal %s applied (warning %s)", proposal.id, warning_id)
        return proposal

    def _mark_warnings_fixed(self, warning_id: str) -> None:
        """Mark a continuity warning fixed (within the same commit transaction)."""
        from app.services.continuity_service import ContinuityService

        try:
            ContinuityService(self.session).mark_fixed(warning_id)
        except NotFoundError:
            logger.warning("continuity warning %s not found while finalizing fix", warning_id)

    def reject(self, proposal_id: str) -> AgentProposal:
        """Reject a pending proposal — never applied, no domain mutation."""
        proposal = self._get_proposal(proposal_id)
        if proposal.status != PROPOSAL_STATUS_PENDING:
            raise ConflictError("Proposal is not pending.", {"proposal_id": proposal_id, "status": proposal.status})
        proposal.status = PROPOSAL_STATUS_REJECTED
        proposal.decided_at = _now()
        self.session.commit()
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_PROPOSAL_REJECTED,
            entity_type="agent_proposal",
            entity_id=proposal.id,
            project_id=proposal_run_project(self.session, proposal),
            payload={"run_id": proposal.run_id, "target_id": proposal.target_id},
        ))
        logger.info("proposal %s rejected", proposal.id)
        return proposal

    def conflict(self, proposal_id: str, reason: str) -> AgentProposal:
        """Explicitly mark a proposal as conflict (e.g. domain validation failed)."""
        proposal = self._get_proposal(proposal_id)
        proposal.status = PROPOSAL_STATUS_CONFLICT
        proposal.conflict_reason = reason
        proposal.decided_at = _now()
        self.session.commit()
        self._emit_conflict(proposal)
        return proposal

    def _get_proposal(self, proposal_id: str) -> AgentProposal:
        proposal = self.session.get(AgentProposal, proposal_id)
        if proposal is None:
            raise NotFoundError("Proposal does not exist.", {"proposal_id": proposal_id})
        return proposal

    def _emit_conflict(self, proposal: AgentProposal) -> None:
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_PROPOSAL_CONFLICT,
            entity_type="agent_proposal",
            entity_id=proposal.id,
            project_id=proposal_run_project(self.session, proposal),
            payload={
                "run_id": proposal.run_id,
                "target_id": proposal.target_id,
                "reason": proposal.conflict_reason or proposal.error_message or "",
            },
        ))

    # ---------- reads ----------

    def list_proposals(self, run_id: str | None = None, status: str | None = None) -> list[AgentProposal]:
        from sqlalchemy import select

        stmt = select(AgentProposal).order_by(AgentProposal.created_at)
        if run_id:
            stmt = stmt.where(AgentProposal.run_id == run_id)
        if status:
            stmt = stmt.where(AgentProposal.status == status)
        return list(self.session.scalars(stmt))


def proposal_run_project(session: Session, proposal: AgentProposal) -> str | None:
    run = session.get(AgentRun, proposal.run_id)
    return run.project_id if run else None
