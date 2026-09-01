"""Generation API (api-event-contract §35-41, mvp-spec §70)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.domain.generation import (
    AssetVersionRead,
    GenerationCreate,
    GenerationRead,
    GenerationReferenceRead,
    ShotReferenceRead,
    VoiceoverBatchResult,
    VoiceoverGenerateRequest,
)
from app.generations.worker import cancel_running, pause_queue, queue_status, resume_queue
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
        prompt_version_id=g.prompt_version_id,
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


@router.post(
    "/timeline-clips/{clip_id}/generate-voiceover",
    response_model=GenerationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_voiceover(clip_id: str, data: VoiceoverGenerateRequest, db: Session = Depends(get_db)) -> GenerationRead:
    """TASK-012: queue TTS voiceover for a VOICE-track clip (202 + type="audio" generation)."""
    from app.services.audio_service import AudioService

    return _to_read(AudioService(db).create_voiceover_generation(clip_id, data))


@router.post(
    "/timelines/{timeline_id}/generate-voiceovers",
    response_model=VoiceoverBatchResult,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_voiceovers_batch(timeline_id: str, db: Session = Depends(get_db)) -> VoiceoverBatchResult:
    """C1 整轨批量配音: queue a voiceover for every VOICE-track clip with text.

    Returns which clips were queued, skipped (no text) or already bound to an
    AUDIO asset. Each submission is a separate type="audio" generation (202 path).
    """
    from app.services.audio_service import AudioService

    return AudioService(db).create_voiceover_batch(timeline_id)


@router.get("/generations/recent", response_model=list[GenerationRead])
def recent_generations(db: Session = Depends(get_db)) -> list[GenerationRead]:
    """Recent generations across all shots (bottom dock history).

    NOTE: registered BEFORE /generations/{generation_id} — static route must win
    (P1-E4-T01 route conflict regression)."""
    return [_to_read(g) for g in GenerationService(db).list_recent()]


# --- queue-level control (P5-T013/T014), registered before the {generation_id}
# param route so the static paths win (same rule as /generations/recent). These are
# thin routers — all logic lives in the worker module. ---

@router.post("/generations/pause")
def pause_queue_endpoint() -> dict:
    """Pause scheduling of NEW generation tasks; running ones continue."""
    pause_queue()
    return {"paused": True}


@router.post("/generations/resume")
def resume_queue_endpoint() -> dict:
    """Resume scheduling of new generation tasks."""
    resume_queue()
    return {"paused": False}


@router.get("/generations/queue-status")
def generations_queue_status() -> dict:
    """Queue-level status (paused flag + pending/running counts)."""
    return queue_status()


@router.get("/shots/{shot_id}/reference-images", response_model=list[ShotReferenceRead])
def preview_shot_references(shot_id: str, db: Session = Depends(get_db)) -> list[ShotReferenceRead]:
    """M1 + 自主迭代 03 前端闭环：预览该镜头生成「自动模式」将注入的角色 + 场景地点
    MASTER 参考图。

    与 create_generation 的自动解析同源（生成前可见），供 ShotInspector
    生成面板展示缩略图；手动覆盖走 GenerationCreate.reference_asset_ids。
    """
    refs = GenerationService(db).preview_references(shot_id)
    return [
        ShotReferenceRead(
            character_id=r.get("character_id"),
            character_name=r.get("character_name"),
            location_id=r.get("location_id"),
            location_name=r.get("location_name"),
            version_id=r.get("version_id"),
            asset_id=r["asset_id"],
        )
        for r in refs
    ]


@router.get("/generations/{generation_id}", response_model=GenerationRead)
def get_generation(generation_id: str, db: Session = Depends(get_db)) -> GenerationRead:
    """单条明细（含参考图溯源）：references 仅在此端点填充。

    列表端点（recent / per-shot）保持 references=None，避免 N+1。
    """
    service = GenerationService(db)
    read = _to_read(service.get_generation(generation_id))
    read.references = [
        GenerationReferenceRead(
            character_id=r.get("character_id"),
            character_name=r.get("character_name"),
            location_id=r.get("location_id"),
            location_name=r.get("location_name"),
            version_id=r.get("version_id"),
            asset_id=r["asset_id"],
            source=r.get("source") or "auto",
        )
        for r in service.generation_references(generation_id)
    ]
    return read


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


MEDIA_TYPES = ("image", "video")


def _to_version_read(asset, shot_id: str, media_type: str, is_active: bool) -> AssetVersionRead:
    return AssetVersionRead(
        id=asset.id,
        shot_id=shot_id,
        asset_id=asset.id,
        media_type=media_type,
        version_number=asset.version_number or 0,
        generation_id=asset.generation_id,
        is_active=is_active,
        status=asset.status,
        notes=None,
        created_at=asset.created_at,
    )


def _list_versions(shot_id: str, db: Session) -> list[AssetVersionRead]:
    """All versions of a shot across image+video purposes (ADR-001)."""
    service = VersionService(db)
    shot = service.shots.get(shot_id)
    if shot is None:
        raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
    rows: list[AssetVersionRead] = []
    for media_type in MEDIA_TYPES:
        active_id = getattr(shot, f"active_{media_type}_asset_id")
        for asset in service.list_shot_versions(shot_id, media_type):
            rows.append(_to_version_read(asset, shot_id, media_type, asset.id == active_id))
    return rows


@router.get("/shots/{shot_id}/versions", response_model=list[AssetVersionRead])
def list_versions(shot_id: str, db: Session = Depends(get_db)) -> list[AssetVersionRead]:
    return _list_versions(shot_id, db)


@router.get("/shots/{shot_id}/image-versions", response_model=list[AssetVersionRead])
def list_image_versions(shot_id: str, db: Session = Depends(get_db)) -> list[AssetVersionRead]:
    return _list_versions(shot_id, db)


@router.get("/shots/{shot_id}/video-versions", response_model=list[AssetVersionRead])
def list_video_versions(shot_id: str, db: Session = Depends(get_db)) -> list[AssetVersionRead]:
    return _list_versions(shot_id, db)


@router.post("/media-versions/{asset_id}/activate", response_model=AssetVersionRead)
def activate_version(asset_id: str, db: Session = Depends(get_db)) -> AssetVersionRead:
    """Legacy path kept for the current frontend: version_id IS the asset id (ADR-001)."""
    asset = VersionService(db).set_active_asset(asset_id)
    shot_id = asset.version_group_id.split(":")[2] if asset.version_group_id else ""
    media_type = "image" if asset.version_group_id.endswith(":SHOT_IMAGE") else "video"
    return _to_version_read(asset, shot_id, media_type, True)


@router.post("/shots/{shot_id}/image-versions/{asset_id}/activate", response_model=AssetVersionRead)
def activate_image_version(shot_id: str, asset_id: str, db: Session = Depends(get_db)) -> AssetVersionRead:
    asset = VersionService(db).set_active_asset(asset_id)
    return _to_version_read(asset, shot_id, "image", True)


@router.post("/shots/{shot_id}/video-versions/{asset_id}/activate", response_model=AssetVersionRead)
def activate_video_version(shot_id: str, asset_id: str, db: Session = Depends(get_db)) -> AssetVersionRead:
    asset = VersionService(db).set_active_asset(asset_id)
    return _to_version_read(asset, shot_id, "video", True)
