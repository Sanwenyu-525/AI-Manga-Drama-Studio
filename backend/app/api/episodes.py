"""Episode API (api-event-contract §13-15, mvp-spec §33)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.episode import EpisodeCreate, EpisodeRead, EpisodeUpdate
from app.services import EpisodeService

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
