"""Generation API (api-event-contract §35-41, mvp-spec §70)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.generation import GenerationCreate, GenerationRead, MediaVersionRead
from app.generations.worker import cancel_running
from app.services import GenerationService, VersionService

router = APIRouter(tags=["generations"])

# local serializers (avoids leaking ORM objects)
def _to_read(g) -> GenerationRead:
    return GenerationRead(
        id=g.id,
        project_id=g.project_id,
        shot_id=g.shot_id,
        type=g.type,
        provider=g.provider,
        model=g.model,
        workflow_id=g.workflow_id,
        status=g.status,
        progress=g.progress,
        stage=g.stage,
        output_asset_id=g.output_asset_id,
        error_message=g.error_message,
        retry_of=g.retry_of,
        created_at=g.created_at,
        started_at=g.started_at,
        completed_at=g.completed_at,
    )


@router.post("/shots/{shot_id}/generations", response_model=GenerationRead, status_code=status.HTTP_202_ACCEPTED)
def create_generation(shot_id: str, data: GenerationCreate, db: Session = Depends(get_db)) -> GenerationRead:
    return _to_read(GenerationService(db).create_generation(shot_id, data))


@router.get("/generations/recent", response_model=list[GenerationRead])
def recent_generations(db: Session = Depends(get_db)) -> list[GenerationRead]:
    """Recent generations across all shots (bottom dock history).

    NOTE: registered BEFORE /generations/{generation_id} — static route must win
    (P1-E4-T01 route conflict regression)."""
    return [_to_read(g) for g in GenerationService(db).list_recent()]


@router.get("/generations/{generation_id}", response_model=GenerationRead)
def get_generation(generation_id: str, db: Session = Depends(get_db)) -> GenerationRead:
    return _to_read(GenerationService(db).get_generation(generation_id))


@router.get("/shots/{shot_id}/generations", response_model=list[GenerationRead])
def list_generations(shot_id: str, db: Session = Depends(get_db)) -> list[GenerationRead]:
    return [_to_read(g) for g in GenerationService(db).list_generations(shot_id=shot_id)]


@router.post("/generations/{generation_id}/retry", response_model=GenerationRead, status_code=status.HTTP_202_ACCEPTED)
def retry_generation(generation_id: str, db: Session = Depends(get_db)) -> GenerationRead:
    return _to_read(GenerationService(db).retry_generation(generation_id))


@router.post("/generations/{generation_id}/cancel", response_model=GenerationRead)
async def cancel_generation(generation_id: str, db: Session = Depends(get_db)) -> GenerationRead:
    service = GenerationService(db)
    generation = service.cancel_generation(generation_id)
    await cancel_running(generation_id)
    return _to_read(generation)


@router.get("/shots/{shot_id}/versions", response_model=list[MediaVersionRead])
def list_versions(shot_id: str, db: Session = Depends(get_db)) -> list[MediaVersionRead]:
    versions = VersionService(db).list_shot_versions(shot_id)
    return [
        MediaVersionRead(
            id=v.id,
            shot_id=v.shot_id,
            asset_id=v.asset_id,
            media_type=v.media_type,
            version_number=v.version_number,
            generation_id=v.generation_id,
            is_active=bool(v.is_active),
            notes=v.notes,
            created_at=v.created_at,
        )
        for v in versions
    ]


@router.post("/media-versions/{version_id}/activate", response_model=MediaVersionRead)
def activate_version(version_id: str, db: Session = Depends(get_db)) -> MediaVersionRead:
    v = VersionService(db).set_active_version(version_id)
    return MediaVersionRead(
        id=v.id,
        shot_id=v.shot_id,
        asset_id=v.asset_id,
        media_type=v.media_type,
        version_number=v.version_number,
        generation_id=v.generation_id,
        is_active=True,
        notes=v.notes,
        created_at=v.created_at,
    )
