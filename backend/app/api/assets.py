"""Asset API (api-event-contract §44-46): content/thumbnail serving with path safety (§127)."""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.asset_service import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/{asset_id}/content")
def asset_content(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = AssetService(db).get_asset(asset_id)
    path = AssetService(db).absolute_path(asset)
    return FileResponse(path, media_type=asset.mime_type or "application/octet-stream")


@router.get("/{asset_id}/thumbnail")
def asset_thumbnail(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = AssetService(db).get_asset(asset_id)
    thumb = AssetService(db).absolute_thumbnail_path(asset)
    if thumb is not None:
        return FileResponse(thumb, media_type="image/png")
    # fallback to the full image
    return asset_content(asset_id, db)
