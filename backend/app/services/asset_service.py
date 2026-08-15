"""AssetService (backend-architecture §15, mvp-spec §27).

File storage layout (database-v0.1 §38-40):
  <data_dir>/projects/{project_id}/images/EP01_SC03_SH005_IMG_V001.png
DB stores ONLY relative paths — the whole project directory is portable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import Asset, Episode, Scene, Shot
from app.events.bus import EVENT_ASSET_CREATED, StudioEvent, bus
from app.repositories import SceneRepository, ShotRepository

logger = get_logger("assets")

THUMBNAIL_WIDTH = 240


def project_dir(project_id: str) -> Path:
    return settings.data_dir / "projects" / project_id


class AssetService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotRepository(session)
        self.scenes = SceneRepository(session)

    def register_asset(
        self,
        *,
        project_id: str,
        asset_type: str,
        source_path: str | Path,
        name: str | None = None,
        shot_id: str | None = None,
        generation_id: str | None = None,
        meta: dict | None = None,
        make_thumbnail: bool = True,
        commit: bool = True,
    ) -> Asset:
        """Copy a file into the project tree and register it (mvp-spec §71: ComfyUI output → Asset).

        commit=False lets the caller own the transaction (ADR-001 2.4: single-commit
        generation completion); events are only published after a commit by the caller.
        """
        source = Path(source_path)
        if not source.exists():
            raise NotFoundError("Source file does not exist.", {"path": str(source)})

        if shot_id is not None:
            rel_dir = self._shot_relative_dir(shot_id, asset_type)
        else:
            rel_dir = Path(asset_type)

        dest_dir = project_dir(project_id) / rel_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (name or source.name)
        content = source.read_bytes()
        dest.write_bytes(content)
        checksum = hashlib.sha256(content).hexdigest()

        width = height = None
        if asset_type == "image":
            try:
                with Image.open(dest) as img:
                    width, height = img.size
            except Exception:  # noqa: BLE001 — non-image content is expected
                logger.debug("asset %s has no image size (non-image content)", dest.name)

        thumbnail_rel = None
        if asset_type == "image" and make_thumbnail:
            thumbnail_rel = self.create_thumbnail(project_id, dest)

        asset = Asset(
            project_id=project_id,
            type=asset_type,
            name=dest.name,
            file_path=str(rel_dir / dest.name).replace("\\", "/"),
            thumbnail_path=thumbnail_rel,
            mime_type="image/png" if asset_type == "image" else None,
            width=width,
            height=height,
            file_size=dest.stat().st_size,
            meta_json=str(meta or {}),
            generation_id=generation_id,
            status="ready",
            source_type="generated",
            checksum=checksum,
        )
        self.session.add(asset)
        if commit:
            self.session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_ASSET_CREATED,
                    entity_type="asset",
                    entity_id=asset.id,
                    project_id=project_id,
                    payload={"type": asset.type, "shot_id": shot_id},
                )
            )
        return asset

    def create_thumbnail(self, project_id: str, image_path: Path) -> str | None:
        """Generate a small thumbnail next to the image; returns relative path or None."""
        try:
            with Image.open(image_path) as img:
                img.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH))
                thumb_path = image_path.with_name(image_path.stem + "_thumb" + image_path.suffix)
                img.save(thumb_path, "PNG")
            return str(thumb_path.relative_to(project_dir(project_id))).replace("\\", "/")
        except Exception as exc:  # noqa: BLE001
            logger.warning("thumbnail failed for %s: %s", image_path, exc)
            return None

    def get_asset(self, asset_id: str) -> Asset:
        """Fetch a live (non-deleted) asset — Router-safe lookup (P1-E4-T01)."""
        asset = self.session.get(Asset, asset_id)
        if asset is None or asset.deleted_at:
            raise NotFoundError("Asset does not exist.", {"asset_id": asset_id})
        return asset

    def absolute_path(self, asset: Asset) -> Path:
        if not asset.file_path:
            raise NotFoundError("Asset has no file.", {"asset_id": asset.id})
        return self._safe_path(asset, asset.file_path)

    def absolute_thumbnail_path(self, asset: Asset) -> Path | None:
        if not asset.thumbnail_path:
            return None
        return self._safe_path(asset, asset.thumbnail_path)

    def _safe_path(self, asset: Asset, relative: str) -> Path:
        """Resolve a stored relative path and verify it stays inside the project root (§127)."""
        path = project_dir(asset.project_id) / relative
        root = project_dir(asset.project_id).resolve()
        resolved = path.resolve()
        if root not in resolved.parents and resolved != root:
            raise NotFoundError("Asset path escapes project root.", {"asset_id": asset.id})
        if not resolved.exists():
            raise NotFoundError("Asset file is missing.", {"asset_id": asset.id, "path": relative})
        return resolved

    def _shot_relative_dir(self, shot_id: str, asset_type: str) -> Path:
        """EP01_SC03_SH005 → images/ (database-v0.1 §40 naming)."""
        shot = self.session.get(Shot, shot_id)
        scene = self.session.get(Scene, shot.scene_id) if shot else None
        episode = self.session.get(Episode, scene.episode_id) if scene else None
        if shot and scene and episode:
            shot_label = f"SH{shot.shot_number:03d}"
            scene_label = f"SC{scene.scene_number:02d}"
            episode_label = f"EP{episode.episode_number:02d}"
            return Path(f"{episode_label}_{scene_label}_{shot_label}") / asset_type
        return Path("misc") / asset_type
