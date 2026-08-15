"""Character API (database-v0.1 §7, api-event-contract §20/§88-89: revision + soft delete)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.character import CharacterCreate, CharacterRead, CharacterUpdateRequest
from app.services import CharacterService

router = APIRouter(tags=["characters"])


@router.get("/projects/{project_id}/characters", response_model=list[CharacterRead])
def list_characters(project_id: str, db: Session = Depends(get_db)) -> list[CharacterRead]:
    return CharacterService(db).list_characters(project_id)


@router.post(
    "/projects/{project_id}/characters",
    response_model=CharacterRead,
    status_code=status.HTTP_201_CREATED,
)
def create_character(project_id: str, data: CharacterCreate, db: Session = Depends(get_db)) -> CharacterRead:
    return CharacterService(db).create_character(project_id, data)


@router.get("/characters/{character_id}", response_model=CharacterRead)
def get_character(character_id: str, db: Session = Depends(get_db)) -> CharacterRead:
    return CharacterService(db).get_character(character_id)


@router.patch("/characters/{character_id}", response_model=CharacterRead)
def update_character(
    character_id: str, data: CharacterUpdateRequest, db: Session = Depends(get_db)
) -> CharacterRead:
    """Optimistic concurrency (§21/§88): body = {revision, patch}; 409 on mismatch."""
    return CharacterService(db).update_character(character_id, data.revision, data.patch)


@router.delete("/characters/{character_id}", status_code=status.HTTP_200_OK)
def delete_character(character_id: str, db: Session = Depends(get_db)) -> dict:
    CharacterService(db).delete_character(character_id)
    return {"id": character_id, "deleted": True}
