"""Episode API (api-event-contract §13-15, §18; mvp-spec §33, §59)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_llm
from app.domain.analysis import ScenePlan
from app.domain.episode import EpisodeCreate, EpisodeRead, EpisodeUpdate
from app.llm.gateway import LLMGateway
from app.operations.store import operation_store
from app.services import EpisodeService
from app.services.script_service import ScriptService

router = APIRouter(tags=["episodes"])


@router.post(
    "/projects/{project_id}/episodes",
    response_model=EpisodeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_episode(project_id: str, data: EpisodeCreate, db: Session = Depends(get_db)) -> EpisodeRead:
    return EpisodeService(db).create_episode(project_id, data)


@router.get("/projects/{project_id}/episodes", response_model=list[EpisodeRead])
def list_episodes(project_id: str, db: Session = Depends(get_db)) -> list[EpisodeRead]:
    return EpisodeService(db).list_episodes(project_id)


@router.get("/episodes/{episode_id}", response_model=EpisodeRead)
def get_episode(episode_id: str, db: Session = Depends(get_db)) -> EpisodeRead:
    return EpisodeService(db).get_episode(episode_id)


@router.patch("/episodes/{episode_id}", response_model=EpisodeRead)
def update_episode(episode_id: str, data: EpisodeUpdate, db: Session = Depends(get_db)) -> EpisodeRead:
    return EpisodeService(db).update_episode(episode_id, data)


@router.delete("/episodes/{episode_id}", status_code=status.HTTP_200_OK)
def delete_episode(episode_id: str, db: Session = Depends(get_db)) -> dict:
    """Soft-delete the episode and its scene/shot tree."""
    EpisodeService(db).delete_episode(episode_id)
    return {"id": episode_id, "deleted": True}


@router.post("/episodes/{episode_id}/analyze/preview", response_model=list[ScenePlan])
async def preview_analysis(
    episode_id: str,
    db: Session = Depends(get_db),
    llm: LLMGateway = Depends(get_llm),
) -> list[ScenePlan]:
    """AI analysis WITHOUT persisting — Review-before-commit UX (mvp-spec §60)."""
    return await ScriptService(db, llm).preview_analysis(episode_id)


@router.post(
    "/episodes/{episode_id}/analyze",
    status_code=status.HTTP_202_ACCEPTED,
)
async def analyze_episode(
    episode_id: str,
    db: Session = Depends(get_db),
    llm: LLMGateway = Depends(get_llm),
) -> dict:
    """202 + operation_id; the job persists scenes when finished (contract §14-15)."""
    episode = EpisodeService(db).get_episode(episode_id)
    op = operation_store.create("episode_analysis", project_id=episode.project_id)

    async def job() -> dict:
        from app.db.session import session_factory_provider

        async with operation_store.lock_for(f"analyze:{episode_id}"):
            factory = session_factory_provider()
            with factory() as session:
                result = await ScriptService(session, llm).analyze_episode(episode_id)
                return result.model_dump()

    operation_store.start(op["id"], job)
    return {"operation_id": op["id"], "status": op["status"]}
