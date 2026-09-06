"""Asset API (api-event-contract §44-46, P3-T003/T005, P6-B).

- GET /projects/{id}/assets          — P6-B: paginated/filtered project list ({total, items})
- GET /assets/{id}                   — P6-B: single-asset detail (Inspector)
- GET /assets/{id}/content · /assets/{id}/thumbnail  — content serving (§127 path safety)
- POST /projects/{id}/assets/import       — P3-T003: external file → project-scope Asset
- POST /projects/{id}/assets/check-missing — P3-T005: ready→missing detection summary

Router stays thin (AGENTS.md §3.6): all business logic lives in AssetService.
"""

import json
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.asset import AssetDetailRead, AssetListRead, AssetListItemRead, AssetMissingCheckRead, AssetRead
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


def _thumbnail_url(asset_id: str) -> str:
    return f"/api/v1/assets/{asset_id}/thumbnail"


def _asset_dimensions(asset) -> tuple[int | None, int | None]:
    """width/height from columns, falling back to meta_json when unset (P6-B)."""
    width, height = asset.width, asset.height
    if width is None or height is None:
        try:
            meta = json.loads(asset.meta_json) if asset.meta_json else None
        except (ValueError, TypeError):
            meta = None
        if isinstance(meta, dict):
            width = width if width is not None else meta.get("width") or meta.get("Width")
            height = height if height is not None else meta.get("height") or meta.get("Height")
    return width, height


def _shot_ref(asset) -> str | None:
    """Reference summary: shot_id carried in version_group_id (vg:shot:{id}:{PURPOSE})."""
    if not asset.version_group_id or not asset.version_group_id.startswith("vg:shot:"):
        return None
    parts = asset.version_group_id.split(":")
    return parts[2] if len(parts) >= 3 else None


def _to_asset_list_item(asset) -> AssetListItemRead:
    width, height = _asset_dimensions(asset)
    return AssetListItemRead(
        id=asset.id,
        type=asset.type,
        status=asset.status,
        name=asset.name,
        source_type=asset.source_type,
        version_group_id=asset.version_group_id,
        version_number=asset.version_number,
        checksum=asset.checksum,
        file_size=asset.file_size,
        width=width,
        height=height,
        created_at=asset.created_at,
        file_path=asset.file_path,
        thumbnail_url=_thumbnail_url(asset.id) if asset.thumbnail_path else None,
    )


def _to_asset_detail(asset) -> AssetDetailRead:
    width, height = _asset_dimensions(asset)
    return AssetDetailRead(
        id=asset.id,
        project_id=asset.project_id,
        type=asset.type,
        status=asset.status,
        version_group_id=asset.version_group_id,
        version_number=asset.version_number,
        checksum=asset.checksum,
        file_size=asset.file_size,
        width=width,
        height=height,
        created_at=asset.created_at,
        file_path=asset.file_path,
        thumbnail_url=_thumbnail_url(asset.id) if asset.thumbnail_path else None,
        meta_json=asset.meta_json,
        generation_id=asset.generation_id,
        parent_asset_id=asset.parent_asset_id,
        shot_id=_shot_ref(asset),
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
    shot_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> AssetRead:
    """P3-T003: import a single file as a project-scope Asset (multipart).

    FastAPI validates the form fields (an invalid asset_type is a 422 through
    the standard RequestValidationError handler); AssetService owns the rest.

    P2-E2-T02: optional `shot_id` links the import to a shot (meta-only, no
    version-group ownership); unknown shot → 404, cross-project shot → 422.
    """
    suffix = Path(file.filename or "").suffix
    # Stream to the temp file in chunks — the multipart body must never be fully
    # loaded into RAM before the service-side 50 MB check runs.
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while chunk := file.file.read(1024 * 1024):
            tmp.write(chunk)
        tmp_path = Path(tmp.name)
    try:
        asset = AssetService(db).import_asset(
            project_id=project_id,
            asset_type=asset_type,
            source_path=tmp_path,
            purpose=purpose,
            source_name=source_name or (file.filename or None),
            shot_id=shot_id,
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


@project_assets.get("/{project_id}/assets", response_model=AssetListRead)
def list_project_assets(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    asset_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    source: str | None = Query(default=None),
    shot_id: str | None = Query(default=None),
    scene_id: str | None = Query(default=None),
    created_from: str | None = Query(default=None),
    created_to: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AssetListRead:
    """P6-B: paginated, filtered project-scope asset list ({total, items}).

    Live (non-deleted) rows only by default; filters are validated in
    AssetService (invalid type/status/source → 422). Order: created_at DESC.

    P2-E2-T02: keyset cursor pagination (opaque `cursor` + `next_cursor`,
    mutually exclusive with offset) + source/shot/scene/created_at filters.
    `asset_type` 即 AC 所说 media_type；shot/scene 跨项目 → 422，不存在 → 404。
    """
    service = AssetService(db)
    total, rows, next_cursor = service.list_assets(
        project_id=project_id,
        limit=limit,
        offset=offset,
        asset_type=asset_type,
        status=status,
        include_deleted=include_deleted,
        source=source,
        shot_id=shot_id,
        scene_id=scene_id,
        created_from=created_from,
        created_to=created_to,
        cursor=cursor,
    )
    return AssetListRead(
        total=total, items=[_to_asset_list_item(a) for a in rows], next_cursor=next_cursor
    )


@router.get("/{asset_id}", response_model=AssetDetailRead)
def get_asset_detail(asset_id: str, db: Session = Depends(get_db)) -> AssetDetailRead:
    """P6-B: single-asset full detail (Inspector). 404 when absent or soft-deleted."""
    asset = AssetService(db).get_asset(asset_id)
    return _to_asset_detail(asset)
