"""Pipeline API (C2 一键成片, api-event-contract §15.1, mvp-spec DOC-C2).

Long LLM stages (run_analysis / confirm / resume) return 202 + operation_id
(Operation mechanism — same as episode analysis); the frontend polls the
operation then reads GET /episodes/{id}/pipeline/latest. finalize is synchronous
(timeline sequence + render queue are fast local writes).
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_script_llm
from app.domain.pipeline import PipelineRead, PipelineRunRead
from app.llm.gateway import LLMGateway
from app.operations.store import operation_store
from app.services import PipelineService

router = APIRouter(tags=["pipelines"])


class ConfirmRequest(BaseModel):
    snapshot_id: str | None = None


@router.post(
    "/episodes/{episode_id}/pipeline/run",
    status_code=status.HTTP_202_ACCEPTED,
)
async def pipeline_run(
    episode_id: str,
    db: Session = Depends(get_db),
    llm: LLMGateway = Depends(get_script_llm),
) -> dict:
    """Analysis preview → waiting_confirm (202 + operation; poll then read latest)."""
    project_id = _project_id_of(db, episode_id)
    op = operation_store.create("pipeline_analysis", project_id=project_id)

    async def job() -> dict:
        from app.db.session import session_factory_provider

        async with operation_store.lock_for(f"pipeline:{episode_id}"):
            factory = session_factory_provider()
            with factory() as session:
                result = await PipelineService(session).run_analysis(episode_id, llm)
                return result.model_dump()

    operation_store.start(op["id"], job)
    return {"operation_id": op["id"], "status": op["status"]}


@router.post(
    "/episodes/{episode_id}/pipeline/{pipeline_id}/confirm",
    status_code=status.HTTP_202_ACCEPTED,
)
async def pipeline_confirm(
    episode_id: str,
    pipeline_id: str,
    body: ConfirmRequest | None = None,
    db: Session = Depends(get_db),
    llm: LLMGateway = Depends(get_script_llm),
) -> dict:
    """Confirm the reviewed plans → scenes → shots → queue images (202 + operation)."""
    project_id = _project_id_of(db, episode_id)
    op = operation_store.create("pipeline_confirm", project_id=project_id)
    snapshot_id = (body.snapshot_id or "").strip() if body is not None else None

    async def job() -> dict:
        from app.db.session import session_factory_provider

        async with operation_store.lock_for(f"pipeline:{episode_id}"):
            factory = session_factory_provider()
            with factory() as session:
                result = await PipelineService(session).confirm(pipeline_id, snapshot_id, llm)
                return result.model_dump()

    operation_store.start(op["id"], job)
    return {"operation_id": op["id"], "status": op["status"]}


@router.post(
    "/episodes/{episode_id}/pipeline/{pipeline_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
)
async def pipeline_resume(
    episode_id: str,
    pipeline_id: str,
    db: Session = Depends(get_db),
    llm: LLMGateway = Depends(get_script_llm),
) -> dict:
    """Continue from the first non-done stage (crash/mid-run recovery)."""
    project_id = _project_id_of(db, episode_id)
    op = operation_store.create("pipeline_resume", project_id=project_id)

    async def job() -> dict:
        from app.db.session import session_factory_provider

        async with operation_store.lock_for(f"pipeline:{episode_id}"):
            factory = session_factory_provider()
            with factory() as session:
                result = await PipelineService(session).resume(pipeline_id, llm)
                return result.model_dump()

    operation_store.start(op["id"], job)
    return {"operation_id": op["id"], "status": op["status"]}


@router.post(
    "/episodes/{episode_id}/pipeline/{pipeline_id}/finalize",
    response_model=PipelineRunRead,
)
def pipeline_finalize(
    episode_id: str,
    pipeline_id: str,
    db: Session = Depends(get_db),
) -> PipelineRunRead:
    """Create/sequence timeline + queue render → completed (synchronous)."""
    return PipelineService(db).finalize(pipeline_id)


@router.get("/episodes/{episode_id}/pipeline/latest", response_model=PipelineRead | None)
def pipeline_latest(episode_id: str, db: Session = Depends(get_db)) -> PipelineRead | None:
    return PipelineService(db).latest(episode_id)


def _project_id_of(db: Session, episode_id: str) -> str | None:
    from app.db.models import Episode

    episode = db.get(Episode, episode_id)
    return episode.project_id if episode is not None else None
