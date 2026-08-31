"""AgentGateway (P7-T002) — the single formal entry point for the agent runtime.

Core business (API routers, future workflow engine) talks ONLY to this facade — it
never touches LangGraph internals directly. It owns create/cancel/resume/approve/
reject orchestration and isolates the Director graph + checkpointer + proposal
lifecycle behind one stable interface (agent-director §architecture).

Red line: the gateway still routes domain mutations through Services (ShotService/
ProposalService) — it never writes ORM directly beyond run bookkeeping.
"""

from __future__ import annotations

from app.agents.director import runner
from app.domain.agent import AgentRunCreate, AgentRunRead, AgentProposalRead, ChangeSetRead
from app.services.proposal_service import ProposalService


class AgentGateway:
    """Formal interface between Studio core and the AI Director runtime (P7-T002)."""

    def __init__(self) -> None:
        self._runner = runner

    # ---- runs ----

    def create_run(self, data: AgentRunCreate) -> AgentRunRead:
        """Create + start a run (202); the graph executes in the background."""
        run = self._runner.create_run(data)
        self._runner.start_run(run.id)
        return run

    def get_run(self, run_id: str) -> AgentRunRead:
        return self._runner.get_run(run_id)

    def cancel_run(self, run_id: str) -> AgentRunRead:
        return self._runner.cancel_run(run_id)

    def resume_run(
        self,
        run_id: str,
        decision: str = "approve",
        proposal_ids: list[str] | None = None,
    ) -> AgentRunRead:
        """Resume a WAITING_HUMAN run with a human decision (P7-T017/T018)."""
        return self._runner.resume_run(run_id, decision=decision, proposal_ids=proposal_ids)

    def active_run_count(self, project_id: str) -> int:
        return self._runner.active_run_count(project_id)

    # ---- proposals ----

    def list_proposals(self, run_id: str | None = None, status: str | None = None) -> list[AgentProposalRead]:
        from .director.runner import _session

        with _session() as session:
            if run_id:
                # P2-E3-T02: lazy TTL sweep so the list never shows stale pending.
                ProposalService(session).expire_stale_proposals(run_id)
            proposals = ProposalService(session).list_proposals(run_id, status)
            return [_proposal_read(p) for p in proposals]

    def approve_proposal(self, proposal_id: str) -> AgentProposalRead:
        """Approve a pending proposal: apply through ShotService / create the
        Generation (R2) + publish events. The parent run's graph continuation is
        driven by resume_run — this endpoint only finalizes the proposal decision."""
        from .director.runner import _session

        with _session() as session:
            proposal = ProposalService(session).approve(proposal_id)
            return _proposal_read(proposal)

    def reject_proposal(self, proposal_id: str) -> AgentProposalRead:
        from .director.runner import _session

        with _session() as session:
            proposal = ProposalService(session).reject(proposal_id)
            return _proposal_read(proposal)

    def get_proposal(self, proposal_id: str) -> AgentProposalRead:
        from .director.runner import _session

        with _session() as session:
            proposal = ProposalService(session)._get_proposal(proposal_id)
            return _proposal_read(proposal)

    # ---- change sets (P2-E3-T03) ----

    def list_change_sets(
        self,
        project_id: str | None = None,
        run_id: str | None = None,
        entity_id: str | None = None,
        undone: bool | None = None,
    ) -> list[ChangeSetRead]:
        from .director.runner import _session
        from app.services.change_set_service import ChangeSetService, to_read

        with _session() as session:
            rows = ChangeSetService(session).list_change_sets(
                project_id=project_id, run_id=run_id, entity_id=entity_id, undone=undone
            )
            return [to_read(cs) for cs in rows]

    def undo_change_set(self, change_set_id: str, *, force: bool = False) -> ChangeSetRead:
        """Undo one change set: a NEW compensating change (history untouched)."""
        from .director.runner import _session
        from app.services.change_set_service import ChangeSetService, to_read

        with _session() as session:
            compensating = ChangeSetService(session).undo(change_set_id, force=force)
            return to_read(compensating)

    def undo_run_change_sets(self, run_id: str, *, force: bool = False) -> list[dict]:
        """Undo all agent change sets of a run — per-item results, never half-silent."""
        from .director.runner import _session
        from app.services.change_set_service import ChangeSetService

        with _session() as session:
            return ChangeSetService(session).undo_run(run_id, force=force)


def _proposal_read(p) -> AgentProposalRead:
    import json

    return AgentProposalRead(
        id=p.id,
        run_id=p.run_id,
        tool=p.tool,
        target_type=p.target_type,
        target_id=p.target_id,
        base_revision=p.base_revision,
        changes=json.loads(p.changes_json) if p.changes_json else {},
        status=p.status,
        conflict_reason=p.conflict_reason,
        error_message=p.error_message,
        created_at=p.created_at,
        decided_at=p.decided_at,
        risk_level=p.risk_level,
        reason=p.reason,
        estimated_tasks=p.estimated_tasks,
        estimated_cost=p.estimated_cost,
        irreversible=p.irreversible,
        expires_at=p.expires_at,
    )


gateway = AgentGateway()
