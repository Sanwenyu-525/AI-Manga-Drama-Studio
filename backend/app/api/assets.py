"""Asset API (api-event-contract §44-46, P3-T003/T005).

- GET /assets/{id}/content · /assets/{id}/thumbnail  — content serving (§127 path safety)
- POST /projects/{id}/assets/import       — P3-T003: external file → project-scope Asset
- POST /projects/{id}/assets/check-missing — P3-T005: ready→missing detection summary

Router stays thin (AGENTS.md §3.6): all business logic lives in AssetService.
"""

import json
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.asset import AssetMissingCheckRead, AssetRead
from app.services.asset_service import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])
project_assets = APIRouter(prefix="/projects", tags=["assets"])


def _to_asset_read(asset) -> AssetRead:
    meta = None
    if asset.meta_json:
        try:
            meta = json.loads(asset.meta_json)
        except (ValueError, TypeError):
            meta = None
    return AssetRead(
        id=asset.id,
        project_id=asset.project_id,
        type=asset.type,
        name=asset.name,
        file_path=asset.file_path,
        thumbnail_path=asset.thumbnail_path,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        duration=asset.duration,
        file_size=asset.file_size,
        meta=meta,
        version_group_id=asset.version_group_id,
        version_number=asset.version_number,
        status=asset.status,
        source_type=asset.source_type,
        checksum=asset.checksum,
        generation_id=asset.generation_id,
        parent_asset_id=asset.parent_asset_id,
        created_at=asset.created_at,
    )


@router.get("/{asset_id}/content")
def asset_content(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    service = AssetService(db)
    asset = service.get_asset(asset_id)
    return FileResponse(service.absolute_path(asset), media_type=asset.mime_type or "application/octet-stream")


@router.get("/{asset_id}/thumbnail")
def asset_thumbnail(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    service = AssetService(db)
    asset = service.get_asset(asset_id)
    thumb = service.absolute_thumbnail_path(asset)
    if thumb is not None:
        return FileResponse(thumb, media_type="image/png")
    return asset_content(asset_id, db)


@project_assets.post(
    "/{project_id}/assets/import",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
)
def import_asset(
    project_id: str,
    file: UploadFile = File(...),
    asset_type: Literal["image", "video"] = Form(...),
    purpose: str | None = Form(default=None),
    source_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> AssetRead:
    """P3-T003: import a single file as a project-scope Asset (multipart).

    FastAPI validates the form fields (an invalid asset_type is a 422 through
    the standard RequestValidationError handler); AssetService owns the rest.
    """
    suffix = Path(file.filename or "").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = Path(tmp.name)
    try:
        asset = AssetService(db).import_asset(
            project_id=project_id,
            asset_type=asset_type,
            source_path=tmp_path,
            purpose=purpose,
            source_name=source_name or (file.filename or None),
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    return _to_asset_read(asset)


@project_assets.post(
    "/{project_id}/assets/check-missing",
    response_model=AssetMissingCheckRead,
)
def check_missing(project_id: str, db: Session = Depends(get_db)) -> AssetMissingCheckRead:
    """P3-T005: scan all assets of a project; returns {checked, missing} summary."""
    checked, missing = AssetService(db).check_missing_assets(project_id)
    return AssetMissingCheckRead(checked=checked, missing=missing)
