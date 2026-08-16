"""Agent API (api-event-contract §23-31, §52-54; mvp-spec §82) + P7 proposal APIs.

All agent entry points go through the AgentGateway (P7-T002), never LangGraph
internals directly. P7 additions: resume with a human decision (T017/T018),
proposal listing + approve/reject (T012/T015).
"""

from fastapi import APIRouter, status

from app.agents.gateway import gateway
from app.agents.director.runner import get_run, resume_run
from app.domain.agent import (
    AgentProposalRead,
    AgentRunCreate,
    AgentRunRead,
    ProposalResumeRequest,
)

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
