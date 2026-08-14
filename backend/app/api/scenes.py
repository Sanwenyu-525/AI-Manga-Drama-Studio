"""Scene API (api-event-contract §16-18, mvp-spec §34/§36)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.scene import SceneCreate, SceneRead, SceneUpdate
from app.domain.shot import StoryboardRead
from app.services import SceneService, ShotService

router = APIRouter(tags=["scenes"])


@router.get("/episodes/{episode_id}/scenes", response_model=list[SceneRead])
def list_scenes(episode_id: str, db: Session = Depends(get_db)) -> list[SceneRead]:
    return SceneService(db).list_scenes(episode_id)


@router.post(
    "/episodes/{episode_id}/scenes",
    response_model=SceneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_scene(episode_id: str, data: SceneCreate, db: Session = Depends(get_db)) -> SceneRead:
    return SceneService(db).create_scene(episode_id, data)


@router.get("/scenes/{scene_id}", response_model=SceneRead)
def get_scene(scene_id: str, db: Session = Depends(get_db)) -> SceneRead:
    return SceneService(db).get_scene(scene_id)


@router.patch("/scenes/{scene_id}", response_model=SceneRead)
def update_scene(scene_id: str, data: SceneUpdate, db: Session = Depends(get_db)) -> SceneRead:
    return SceneService(db).update_scene(scene_id, data)


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_200_OK)
def delete_scene(scene_id: str, db: Session = Depends(get_db)) -> dict:
    """Soft delete (api-event-contract §89): returns {id, deleted: true}."""
    SceneService(db).delete_scene(scene_id)
    return {"id": scene_id, "deleted": True}


@router.get("/scenes/{scene_id}/storyboard", response_model=StoryboardRead)
def get_storyboard(scene_id: str, db: Session = Depends(get_db)) -> StoryboardRead:
    """Aggregate endpoint (api-event-contract §101): scene + shot summaries in one call."""
    return ShotService(db).get_storyboard(scene_id)
