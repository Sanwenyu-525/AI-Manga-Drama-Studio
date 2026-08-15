"""Costume API (database-v0.1 §8, api-event-contract §142/§143)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.costume import CostumeCreate, CostumeRead, CostumeUpdateRequest
from app.services import CostumeService

router = APIRouter(tags=["costumes"])


@router.get("/projects/{project_id}/costumes", response_model=list[CostumeRead])
def list_costumes(project_id: str, db: Session = Depends(get_db)) -> list[CostumeRead]:
    return CostumeService(db).list_costumes(project_id)


@router.post(
    "/projects/{project_id}/costumes",
    response_model=CostumeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_costume(project_id: str, data: CostumeCreate, db: Session = Depends(get_db)) -> CostumeRead:
    return CostumeService(db).create_costume(project_id, data)


@router.get("/costumes/{costume_id}", response_model=CostumeRead)
def get_costume(costume_id: str, db: Session = Depends(get_db)) -> CostumeRead:
    return CostumeService(db).get_costume(costume_id)


@router.patch("/costumes/{costume_id}", response_model=CostumeRead)
def update_costume(
    costume_id: str, data: CostumeUpdateRequest, db: Session = Depends(get_db)
) -> CostumeRead:
    """Optimistic concurrency: body = {revision, patch}; 409 on mismatch."""
    return CostumeService(db).update_costume(costume_id, data.revision, data.patch)


@router.delete("/costumes/{costume_id}", status_code=status.HTTP_200_OK)
def delete_costume(costume_id: str, db: Session = Depends(get_db)) -> dict:
    CostumeService(db).delete_costume(costume_id)
    return {"id": costume_id, "deleted": True}
