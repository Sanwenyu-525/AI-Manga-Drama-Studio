"""Asset API (api-event-contract §44-46): content/thumbnail serving with path safety (§127)."""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.db.models import Asset
from app.services.asset_service import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])


def _get_asset(db: Session, asset_id: str) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.deleted_at:
        raise NotFoundError("Asset does not exist.", {"asset_id": asset_id})
    return asset


@router.get("/{asset_id}/content")
def asset_content(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = _get_asset(db, asset_id)
    path = AssetService(db).absolute_path(asset)
    return FileResponse(path, media_type=asset.mime_type or "application/octet-stream")


@router.get("/{asset_id}/thumbnail")
def asset_thumbnail(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = _get_asset(db, asset_id)
    thumb = AssetService(db).absolute_thumbnail_path(asset)
    if thumb is not None:
        return FileResponse(thumb, media_type="image/png")
    # fallback to the full image
    return asset_content(asset_id, db)
