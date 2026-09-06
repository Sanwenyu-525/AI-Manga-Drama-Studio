"""Shot API (api-event-contract §19-21, §35, §91; mvp-spec §35)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.shot import (
    ShotBatchDeleteRequest,
    ShotBatchResult,
    ShotBatchUpdateRequest,
    ShotCreate,
    ShotRead,
    ShotUpdateRequest,
)
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


@router.post("/shots/{shot_id}/restore", response_model=ShotRead)
def restore_shot(shot_id: str, db: Session = Depends(get_db)) -> ShotRead:
    """P2-E2-T01: restore a soft-deleted shot (409 when the parent scene is
    deleted or a live sibling reuses the number/order)."""
    return ShotService(db).restore_shot(shot_id)


@router.patch("/scenes/{scene_id}/shots/reorder", response_model=list[ShotRead])
def reorder_shots(scene_id: str, ordered_ids: list[str], db: Session = Depends(get_db)) -> list[ShotRead]:
    return ShotService(db).reorder_shots(scene_id, ordered_ids)


@router.post("/scenes/{scene_id}/shots/batch-update", response_model=ShotBatchResult)
def batch_update_shots(
    scene_id: str, data: ShotBatchUpdateRequest, db: Session = Depends(get_db)
) -> ShotBatchResult:
    """Bulk apply one patch to selected shots (autonomous-iteration-02).
    Per-item results; 200 even on partial failure (mirrors ChangeSet undo)."""
    return ShotService(db).batch_update_shots(scene_id, data.shot_ids, data.patch)


@router.post("/scenes/{scene_id}/shots/batch-delete", response_model=ShotBatchResult)
def batch_delete_shots(
    scene_id: str, data: ShotBatchDeleteRequest, db: Session = Depends(get_db)
) -> ShotBatchResult:
    """Bulk soft-delete selected shots. Per-item results; 200 even on partial failure."""
    return ShotService(db).batch_delete_shots(scene_id, data.shot_ids)
