"""ProposalService (P7-T012..T016 + P2-E3-T02/T03) — create/validate/decide/apply
agent Proposals with risk grading and expiry.

The Agent NEVER writes the domain directly. Tools that require approval per the
risk policy (R2 generate_image by default, R3 always) produce a pending
AgentProposal carrying structured risk metadata (level, reason, estimated
tasks/cost, irreversibility) and an expiry timestamp; the run parks in
WAITING_HUMAN and emits agent.approval.required. R1 update_shot auto-applies per
policy and records an undoable ChangeSet instead (risk.py).

On approve the change is applied through ShotService / GenerationService (never
raw ORM) after a base_revision optimistic-concurrency check (P7-T016): a
mismatched revision becomes "conflict" and is NOT applied. Proposals past their
TTL become "expired" (terminal, never applied) — decided lazily on read/decide.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import AgentProposal, AgentRun, Shot
from app.db.models.agent import SHOT_CHANGE_FIELDS
from app.domain.agent import (
    PROPOSAL_STATUS_APPLIED,
    PROPOSAL_STATUS_APPROVED,
    PROPOSAL_STATUS_CONFLICT,
    PROPOSAL_STATUS_EXPIRED,
    PROPOSAL_STATUS_PENDING,
    PROPOSAL_STATUS_REJECTED,
    RISK_R1,
    RUN_STATUS_FAILED,
    RUN_STATUS_WAITING_HUMAN,
    RiskAssessment,
)
from app.domain.generation import GenerationCreate
from app.domain.shot import ShotUpdate
from app.events.bus import (
    EVENT_AGENT_APPROVAL_REQUIRED,
    EVENT_AGENT_PROPOSAL_APPROVED,
    EVENT_AGENT_PROPOSAL_CONFLICT,
    EVENT_AGENT_PROPOSAL_CREATED,
    EVENT_AGENT_PROPOSAL_EXPIRED,
    EVENT_AGENT_PROPOSAL_REJECTED,
    EVENT_AGENT_RUN_AWAITING_APPROVAL,
    EVENT_AGENT_RUN_FAILED,
    StudioEvent,
    bus,
)
from app.services.change_set_service import ChangeSetService
from app.services.generation_service import GenerationService
from app.services.shot_service import ShotService

logger = get_logger("agent.proposal")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _expiry_from_now() -> str:
    return (datetime.now(UTC) + timedelta(hours=settings.agent_proposal_ttl_hours)).isoformat()


def _is_expired(proposal: AgentProposal) -> bool:
    if proposal.expires_at is None:
        return False
    try:
        return datetime.fromisoformat(proposal.expires_at) <= datetime.now(UTC)
    except ValueError:
        return False


class ProposalService:
    """Domain service that owns the AgentProposal lifecycle (P7-T012..T016).
    Applies changes ONLY through Services — it never writes Shot ORM directly.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotService(session)
        self.generations = GenerationService(session)
        self.change_sets = ChangeSetService(session)

    # ---------- create (generic core, P2-E3-T02) ----------

    def _create_proposal(
        self,
        run: AgentRun,
        *,
        tool: str,
        target_type: str,
        target_id: str,
        base_revision: int,
        changes: dict,
        assessment: RiskAssessment,
    ) -> AgentProposal:
        proposal = AgentProposal(
            run_id=run.id,
            tool=tool,
            target_type=target_type,
            target_id=target_id,
            base_revision=base_revision,
            changes_json=json.dumps(changes, ensure_ascii=False),
            status=PROPOSAL_STATUS_PENDING,
            risk_level=assessment.risk_level,
            reason=assessment.reason,
            estimated_tasks=assessment.estimated_tasks,
            estimated_cost=assessment.estimated_cost,
            irreversible=assessment.irreversible,
            expires_at=_expiry_from_now(),
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
            payload={
                "run_id": run.id,
                "tool": tool,
                "target_type": target_type,
                "target_id": target_id,
                "base_revision": base_revision,
                "changes": changes,
                "risk_level": assessment.risk_level,
                "reason": assessment.reason,
                "estimated_tasks": assessment.estimated_tasks,
                "estimated_cost": assessment.estimated_cost,
                "irreversible": assessment.irreversible,
                "expires_at": proposal.expires_at,
            },
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
            payload={
                "proposal_id": proposal.id,
                "tool": tool,
                "target_type": target_type,
                "target_id": target_id,
                "changes": changes,
                "risk_level": assessment.risk_level,
                "reason": assessment.reason,
                "estimated_tasks": assessment.estimated_tasks,
                "estimated_cost": assessment.estimated_cost,
                "irreversible": assessment.irreversible,
                "expires_at": proposal.expires_at,
            },
        ))
        logger.info(
            "proposal %s created (run %s, tool %s, target %s, risk %s, base_rev %d)",
            proposal.id, run.id, tool, target_id, assessment.risk_level, base_revision,
        )
        return proposal

    def create_shot_proposal(
        self,
        run: AgentRun,
        target_id: str,
        base_revision: int,
        changes: dict,
        assessment: RiskAssessment | None = None,
    ) -> AgentProposal:
        """Record a pending shot-edit proposal and park the run in WAITING_HUMAN.
        Raises ValidationError for illegal fields/types (structured-output validation).
        """
        validated = self.validate_changes(changes)
        if assessment is None:
            assessment = RiskAssessment(
                risk_level=RISK_R1,
                reason="可逆编辑：通过 ChangeSet 记录，可撤销。",
                affected_entities=[target_id],
                estimated_tasks=1,
            )
        return self._create_proposal(
            run,
            tool="update_shot",
            target_type="shot",
            target_id=target_id,
            base_revision=base_revision,
            changes=validated,
            assessment=assessment,
        )

    def create_generation_proposal(
        self,
        run: AgentRun,
        shot_id: str,
        base_revision: int,
        args: dict,
        assessment: RiskAssessment,
    ) -> AgentProposal:
        """R2 (P2-E3-T02): a generation task is expensive — no Generation row is
        created before a human approves this proposal. args are the
        GenerateImageArgs fields (prompt/seed/width/height)."""
        changes = {k: v for k, v in args.items() if k in ("prompt", "seed", "width", "height") and v is not None}
        return self._create_proposal(
            run,
            tool="generate_image",
            target_type="shot",
            target_id=shot_id,
            base_revision=base_revision,
            changes=changes,
            assessment=assessment,
        )

    def validate_changes(self, changes: dict) -> dict:
        """Structured-output + domain validation of the proposed shot fields.
        Only whitelisted fields are allowed; values must type-check against the
        ShotUpdate schema. Returns the sanitized non-None field dict.
        """
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
        if shot_id is not None:
            shot = self.session.get(Shot, shot_id)
            if shot is None or shot.deleted_at:
                raise NotFoundError("Fix target shot does not exist.", {"shot_id": shot_id})
            changes = self.validate_changes({k: v for k, v in patch.items() if k != "_warning"})
            changes["_warning"] = warning_id
            base_revision = shot.revision
        else:
            changes = {"_warning": warning_id}
            base_revision = 1
        assessment = RiskAssessment(
            risk_level=RISK_R1,
            reason="可逆修复：走 Proposal 审批，可撤销。",
            affected_entities=[shot_id or scene_id],
            estimated_tasks=1,
        )
        return self._create_proposal(
            run,
            tool="continuity_fix",
            target_type="shot" if shot_id is not None else "continuity",
            target_id=shot_id if shot_id is not None else scene_id,
            base_revision=base_revision,
            changes=changes,
            assessment=assessment,
        )

    # ---------- decide (human review) ----------

    def approve(self, proposal_id: str) -> AgentProposal:
        """Approve then apply. Expired proposals are terminated (409). The
        base_revision check runs first: a shot edited since the proposal was made
        becomes "conflict" and is NOT applied (P7-T016). generate_image proposals
        create the Generation only here (R2: nothing queued before approval).
        Returns the proposal with its final status (applied | conflict).
        """
        proposal = self._get_proposal(proposal_id)
        self._require_pending(proposal)
        proposal.status = PROPOSAL_STATUS_APPROVED
        proposal.decided_at = _now()

        if proposal.tool == "continuity_fix":
            return self._approve_continuity_fix(proposal)
        if proposal.tool == "generate_image":
            return self._approve_generation(proposal)

        shot = self.session.get(Shot, proposal.target_id)
        if shot is None or shot.deleted_at:
            return self._conflict(proposal, "Target shot no longer exists.", "shot missing/deleted")
        if shot.revision != proposal.base_revision:
            return self._conflict(
                proposal,
                "Shot revision changed since proposal.",
                f"expected_revision={proposal.base_revision}, current_revision={shot.revision}",
            )

        changes = json.loads(proposal.changes_json) if proposal.changes_json else {}
        patch = ShotUpdate.model_validate(changes)
        before = self.shots.get_shot(shot.id)  # user-visible before values (read DTO)
        try:
            updated = self.shots.update_shot(
                proposal.target_id,
                shot.revision,
                patch,
                source="agent",
                run_id=proposal.run_id,
            )
        except ConflictError:
            return self._conflict(proposal, "Shot revision changed while applying.", None)
        proposal.status = PROPOSAL_STATUS_APPLIED
        run = self.session.get(AgentRun, proposal.run_id)
        # P2-E3-T03: record the undoable change set (minimal before/after patch).
        fields = [k for k in changes if not k.startswith("_")]
        if fields and run is not None:
            self.change_sets.record_shot_patch(
                project_id=run.project_id,
                run_id=proposal.run_id,
                tool="update_shot",
                shot_id=proposal.target_id,
                before={f: getattr(before, f, None) for f in fields},
                after={f: getattr(updated, f, None) for f in fields},
                revision_before=before.revision,
                revision_after=updated.revision,
            )
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

    def _approve_generation(self, proposal: AgentProposal) -> AgentProposal:
        """R2 apply (P2-E3-T02): create the Generation only after approval."""
        shot = self.session.get(Shot, proposal.target_id)
        if shot is None or shot.deleted_at:
            return self._conflict(proposal, "Target shot no longer exists.", "shot missing/deleted")
        if shot.revision != proposal.base_revision:
            return self._conflict(
                proposal,
                "Shot revision changed since proposal.",
                f"expected_revision={proposal.base_revision}, current_revision={shot.revision}",
            )
        changes = json.loads(proposal.changes_json) if proposal.changes_json else {}
        try:
            generation = self.generations.create_generation(
                proposal.target_id,
                GenerationCreate(
                    type="image",
                    prompt=changes.get("prompt"),
                    seed=changes.get("seed"),
                    width=changes.get("width"),
                    height=changes.get("height"),
                ),
                run_id=proposal.run_id,
            )
        except ValidationError as exc:
            return self._conflict(proposal, "Generation could not be created.", exc.message)
        proposal.status = PROPOSAL_STATUS_APPLIED
        self.session.commit()
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_PROPOSAL_APPROVED,
            entity_type="agent_proposal",
            entity_id=proposal.id,
            project_id=proposal_run_project(self.session, proposal),
            payload={
                "run_id": proposal.run_id,
                "tool": "generate_image",
                "status": PROPOSAL_STATUS_APPLIED,
                "target_id": proposal.target_id,
                "generation_id": generation.id,
                "changes": changes,
            },
        ))
        logger.info("proposal %s applied (generation %s created)", proposal.id, generation.id)
        return proposal

    def _approve_continuity_fix(self, proposal: AgentProposal) -> AgentProposal:
        """Apply a continuity_fix proposal (P8-T019).

        Shot-scoped (target_type="shot"): apply the shot patch through ShotService
        (base_revision guarded, same as update_shot) and record a ChangeSet, then
        mark the originating warning fixed. Scene-scoped (target_type="continuity",
        no shot mutation): just mark the warning(s) fixed. Never writes raw ORM
        beyond bookkeeping.
        """
        changes = json.loads(proposal.changes_json) if proposal.changes_json else {}
        warning_id = changes.get("_warning")
        patch = {k: v for k, v in changes.items() if not k.startswith("_")}

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
            before = self.shots.get_shot(shot.id) if patch else None
            if patch:
                shot_patch = ShotUpdate.model_validate(patch)
                try:
                    updated = self.shots.update_shot(
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
            run = self.session.get(AgentRun, proposal.run_id)
            if patch and before is not None and run is not None:
                self.change_sets.record_shot_patch(
                    project_id=run.project_id,
                    run_id=proposal.run_id,
                    tool="continuity_fix",
                    shot_id=proposal.target_id,
                    before={f: getattr(before, f, None) for f in patch},
                    after={f: getattr(updated, f, None) for f in patch},
                    revision_before=before.revision,
                    revision_after=updated.revision,
                )
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
        self._require_pending(proposal)
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

    # ---------- expiry (P2-E3-T02) ----------

    def _require_pending(self, proposal: AgentProposal) -> None:
        """Terminal-state guard: only pending proposals can be decided — an
        expired proposal is terminated like any other non-pending state."""
        if proposal.status == PROPOSAL_STATUS_PENDING and _is_expired(proposal):
            self._expire(proposal)
        if proposal.status != PROPOSAL_STATUS_PENDING:
            raise ConflictError(
                "Proposal is not pending.",
                {"proposal_id": proposal.id, "status": proposal.status},
            )

    def _expire(self, proposal: AgentProposal) -> AgentProposal:
        proposal.status = PROPOSAL_STATUS_EXPIRED
        proposal.decided_at = _now()
        self.session.commit()
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_PROPOSAL_EXPIRED,
            entity_type="agent_proposal",
            entity_id=proposal.id,
            project_id=proposal_run_project(self.session, proposal),
            payload={"run_id": proposal.run_id, "target_id": proposal.target_id, "tool": proposal.tool},
        ))
        logger.info("proposal %s expired (run %s)", proposal.id, proposal.run_id)
        self._fail_run_if_no_pending(proposal.run_id)
        return proposal

    def _fail_run_if_no_pending(self, run_id: str) -> None:
        """A WAITING_HUMAN run whose pending proposals are all gone (expired) can
        never be resumed — fail it so it does not hang forever."""
        run = self.session.get(AgentRun, run_id)
        if run is None or run.status not in (RUN_STATUS_WAITING_HUMAN, "waiting_approval"):
            return
        still_pending = self.session.scalar(
            select(AgentProposal.id).where(
                AgentProposal.run_id == run_id,
                AgentProposal.status == PROPOSAL_STATUS_PENDING,
            ).limit(1)
        )
        if still_pending is not None:
            return
        run.status = RUN_STATUS_FAILED
        run.error_message = "All pending approvals expired."
        run.completed_at = _now()
        run.updated_at = _now()
        self.session.commit()
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_RUN_FAILED,
            entity_type="agent_run",
            entity_id=run.id,
            project_id=run.project_id,
            payload={"error": "All pending approvals expired."},
        ))

    def expire_stale_proposals(self, run_id: str) -> int:
        """Lazy TTL sweep for one run: mark overdue pending proposals expired; if
        the run is WAITING_HUMAN with no pending proposals left, fail it so it
        never hangs forever. Returns the number of proposals expired."""
        run = self.session.get(AgentRun, run_id)
        if run is None:
            return 0
        pending = list(
            self.session.scalars(
                select(AgentProposal).where(
                    AgentProposal.run_id == run_id,
                    AgentProposal.status == PROPOSAL_STATUS_PENDING,
                )
            )
        )
        expired = [p for p in pending if _is_expired(p)]
        for proposal in expired:
            self._expire(proposal)
        return len(expired)

    # ---------- helpers ----------

    def _conflict(self, proposal: AgentProposal, reason: str, error_message: str | None) -> AgentProposal:
        proposal.status = PROPOSAL_STATUS_CONFLICT
        proposal.conflict_reason = reason
        proposal.error_message = error_message
        proposal.decided_at = proposal.decided_at or _now()
        self.session.commit()
        self._emit_conflict(proposal)
        logger.info("proposal %s conflict: %s", proposal.id, reason)
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
        stmt = select(AgentProposal).order_by(AgentProposal.created_at)
        if run_id:
            stmt = stmt.where(AgentProposal.run_id == run_id)
        if status:
            stmt = stmt.where(AgentProposal.status == status)
        return list(self.session.scalars(stmt))


def proposal_run_project(session: Session, proposal: AgentProposal) -> str | None:
    run = session.get(AgentRun, proposal.run_id)
    return run.project_id if run else None
