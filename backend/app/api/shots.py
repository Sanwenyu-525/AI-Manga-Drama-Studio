"""Shot API (api-event-contract §19-21, §35, §91; mvp-spec §35)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.shot import ShotCreate, ShotRead, ShotUpdateRequest
from app.services import ShotService

router = APIRouter(tags=["shots"])


@router.get("/scenes/{scene_id}/shots", response_model=list[ShotRead])
def list_shots(scene_id: str, db: Session = Depends(get_db)) -> list[ShotRead]:
    return ShotService(db).list_shots(scene_id)


@router.post(
    "/scenes/{scene_id}/shots",
    response_model=ShotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_shot(scene_id: str, data: ShotCreate, db: Session = Depends(get_db)) -> ShotRead:
    return ShotService(db).create_shot(scene_id, data)


@router.get("/shots/{shot_id}", response_model=ShotRead)
def get_shot(shot_id: str, db: Session = Depends(get_db)) -> ShotRead:
    return ShotService(db).get_shot(shot_id)


@router.patch("/shots/{shot_id}", response_model=ShotRead)
def update_shot(shot_id: str, data: ShotUpdateRequest, db: Session = Depends(get_db)) -> ShotRead:
    """Optimistic concurrency (api-event-contract §21): body = {revision, patch}; 409 on mismatch."""
    return ShotService(db).update_shot(shot_id, data.revision, data.patch)


@router.delete("/shots/{shot_id}", status_code=status.HTTP_200_OK)
def delete_shot(shot_id: str, db: Session = Depends(get_db)) -> dict:
    ShotService(db).delete_shot(shot_id)
    return {"id": shot_id, "deleted": True}


@router.patch("/scenes/{scene_id}/shots/reorder", response_model=list[ShotRead])
def reorder_shots(scene_id: str, ordered_ids: list[str], db: Session = Depends(get_db)) -> list[ShotRead]:
    return ShotService(db).reorder_shots(scene_id, ordered_ids)
