"""Agent API (api-event-contract §23-31, §52-54; mvp-spec §82) + P7 proposal APIs.

All agent entry points go through the AgentGateway (P7-T002), never LangGraph
internals directly. P7 additions: resume with a human decision (T017/T018),
proposal listing + approve/reject (T012/T015).
"""

from fastapi import APIRouter, Query, status

from app.agents.gateway import gateway
from app.agents.director.runner import get_run, resume_run
from app.domain.agent import (
    AgentProposalRead,
    AgentRunCreate,
    AgentRunRead,
    ChangeSetRead,
    ProposalResumeRequest,
    UndoBatchRequest,
    UndoRequest,
)
from app.domain.continuity import ContinuityCheckRequest, ContinuityFixRequest

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/director/runs", response_model=AgentRunRead, status_code=status.HTTP_202_ACCEPTED)
async def create_director_run(data: AgentRunCreate) -> AgentRunRead:
    """202 + run_id; the graph executes in the background, events stream over WS (contract §24).

    NOTE: must be async — create_task needs the running event loop (sync routes run in a threadpool).
    """
    return gateway.create_run(data)


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(run_id: str) -> AgentRunRead:
    return get_run(run_id)


@router.post("/runs/{run_id}/resume", response_model=AgentRunRead)
async def resume_agent_run(run_id: str, body: ProposalResumeRequest | None = None) -> AgentRunRead:
    """P7-T017/T018: resume a WAITING_HUMAN run with a human decision.

    Body is optional and backwards compatible: an omitted/empty body defaults to
    approve-all-pending. decision=approve applies proposals through ShotService and
    continues the interrupted graph; decision=reject marks them rejected.
    """
    if body is None:
        return resume_run(run_id)
    return gateway.resume_run(run_id, decision=body.decision, proposal_ids=body.proposal_ids)


@router.post("/runs/{run_id}/cancel", response_model=AgentRunRead)
def cancel_agent_run(run_id: str) -> AgentRunRead:
    """Cancels the Agent Run only — NOT already-created generations (contract §31, §54)."""
    return gateway.cancel_run(run_id)


# ---------- P7: proposals ----------

@router.get("/runs/{run_id}/proposals", response_model=list[AgentProposalRead])
def list_run_proposals(run_id: str) -> list[AgentProposalRead]:
    """List proposals for a run (P7-T012)."""
    return gateway.list_proposals(run_id=run_id)


@router.post("/proposals/{proposal_id}/approve", response_model=AgentProposalRead)
def approve_proposal(proposal_id: str) -> AgentProposalRead:
    """Approve a pending proposal: apply through ShotService + publish events (P7-T015)."""
    return gateway.approve_proposal(proposal_id)


@router.post("/proposals/{proposal_id}/reject", response_model=AgentProposalRead)
def reject_proposal(proposal_id: str) -> AgentProposalRead:
    """Reject a pending proposal: never applied, marked rejected (P7-T015)."""
    return gateway.reject_proposal(proposal_id)


# ---------- P2-E3-T03: change sets / undo ----------

@router.get("/change-sets", response_model=list[ChangeSetRead])
def list_change_sets(
    project_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    undone: bool | None = Query(default=None),
) -> list[ChangeSetRead]:
    """List recorded agent mutations (minimal before/after patches), newest first.

    Filter by project / run / target entity; undone=true|false filters the undo state.
    """
    return gateway.list_change_sets(
        project_id=project_id, run_id=run_id, entity_id=entity_id, undone=undone
    )


@router.post("/change-sets/{change_set_id}/undo", response_model=ChangeSetRead)
def undo_change_set(change_set_id: str, body: UndoRequest | None = None) -> ChangeSetRead:
    """Undo one agent mutation: applies the recorded before-values as a NEW
    compensating change (revision+1, history untouched). 409 with recovery details
    when a later edit overwrote the same fields — force=true restores anyway."""
    return gateway.undo_change_set(change_set_id, force=bool(body.force) if body else False)


@router.post("/runs/{run_id}/change-sets/undo")
def undo_run_change_sets(run_id: str, body: UndoBatchRequest | None = None) -> list[dict]:
    """Undo all agent change sets of a run (newest first). Returns per-item
    results: undone | conflict | skipped — never a half-silent batch."""
    return gateway.undo_run_change_sets(run_id, force=bool(body.force) if body else False)


# ---------- P8-T018/T019: Continuity Agent ----------

@router.post("/continuity/check", status_code=status.HTTP_202_ACCEPTED)
async def continuity_check(body: ContinuityCheckRequest) -> dict:
    """202 + run_id: run the Continuity Agent semantic check for a scene (P8-T018).

    The check runs in the background; rules + LLM semantic warnings are persisted to
    continuity_warnings and streamed via continuity.warning.created over WS. The
    run is pollable via GET /agent/runs/{run_id}.
    """
    from app.agents.continuity.runner import create_check_run

    run = create_check_run(body.scene_id)
    return {"run_id": run.id, "status": "running"}


@router.get("/continuity/runs/{run_id}")
def get_continuity_check_run(run_id: str) -> dict:
    """Load a continuity run's status/result (continuity_check or continuity_fix)."""
    from app.agents.continuity.runner import check_result

    return check_result(run_id)


@router.post("/continuity/fix", response_model=AgentRunRead)
def continuity_fix(body: ContinuityFixRequest) -> AgentRunRead:
    """Trigger a fix for ONE continuity warning (P8-T019).

    Creates a continuity_fix run with a pending Proposal; the run parks in
    WAITING_HUMAN awaiting human approval. Approve/reject reuse the P7 proposal API
    (POST /agent/proposals/{id}/approve|reject). This is the "separate" design: the
    frontend first runs a check, then issues a fix per warning.
    """
    from app.agents.continuity.runner import create_fix_run
    from app.agents.director.runner import get_run

    run = create_fix_run(body.warning_id, body.patch)
    return get_run(run.id)
