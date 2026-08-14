"""Agent API (api-event-contract §23-31, §52-54; mvp-spec §82)."""

from fastapi import APIRouter, Depends, status

from app.agents.director.runner import cancel_run, create_run, get_run, resume_run, start_run
from app.domain.agent import AgentRunCreate, AgentRunRead

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/director/runs", response_model=AgentRunRead, status_code=status.HTTP_202_ACCEPTED)
async def create_director_run(data: AgentRunCreate) -> AgentRunRead:
    """202 + run_id; the graph executes in the background, events stream over WS (contract §24).

    NOTE: must be async — create_task needs the running event loop (sync routes run in a threadpool).
    """
    run = create_run(data)
    start_run(run.id)
    return run


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(run_id: str) -> AgentRunRead:
    return get_run(run_id)


@router.post("/runs/{run_id}/resume", response_model=AgentRunRead)
def resume_agent_run(run_id: str) -> AgentRunRead:
    return resume_run(run_id)


@router.post("/runs/{run_id}/cancel", response_model=AgentRunRead)
def cancel_agent_run(run_id: str) -> AgentRunRead:
    """Cancels the Agent Run only — NOT already-created generations (contract §31, §54)."""
    return cancel_run(run_id)
