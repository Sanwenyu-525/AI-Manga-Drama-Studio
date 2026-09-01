"""AssetService (backend-architecture §15, mvp-spec §27; P3-T003/T005).

File storage layout (database-v0.1 §38-40):
  <data_dir>/projects/{project_id}/images/EP01_SC03_SH005_IMG_V001.png
  <data_dir>/projects/{project_id}/imported/{PROJECT_ID}_IMP_001.png
DB stores ONLY relative paths — the whole project directory is portable.

P3-T003 (import): external files become project-scope Assets (source_type=imported,
no shot / version-group ownership). P3-T005 (missing): a ready asset whose file
disappears is marked "missing"; the record and any file are preserved.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import uuid
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Asset, Episode, Project, Scene, Shot
from app.db.models.asset import ASSET_STATUSES, ASSET_TYPES
from app.events.bus import EVENT_ASSET_CREATED, StudioEvent, bus
from app.repositories import SceneRepository, ShotRepository

logger = get_logger("assets")

THUMBNAIL_WIDTH = 240
IMPORT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB (P3-T003 validation)
IMPORTED_SUBDIR = "imported"
_STREAM_CHUNK = 1024 * 1024

_IMAGE_MIME_BY_FORMAT = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}

# Fallback when the real file gives no detectable MIME (P1-E2-T03: MIME always
# comes from the actual file — extension first, content for images).
_FALLBACK_MIME = {"image": "image/png", "video": "video/mp4", "audio": "audio/mpeg"}


def project_dir(project_id: str) -> Path:
    return settings.data_dir / "projects" / project_id


def _import_suffix(asset_type: str, original_name: str) -> str:
    """Best-effort file extension for the imported copy (database-v0.1 §40)."""
    if asset_type == "video":
        return ".mp4"
    suffix = Path(original_name).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return suffix
    return ".png"


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
        staged_files: list[Path] | None = None,
    ) -> Asset:
        """Copy a file into the project tree and register it (mvp-spec §71: ComfyUI output → Asset).

        commit=False lets the caller own the transaction (ADR-001 2.4: single-commit
        generation completion); events are only published after a commit by the caller.

        P1-E2-T03 (atomic completion chain):
        - streamed copy through a unique temp file + `os.replace` — large files never
          load into memory and the final path never exposes a partial write;
        - checksum streams with the copy (single read of the source);
        - `meta_json` is valid JSON (the old `str(dict)` was Python repr);
        - MIME is derived from the real file (image content via PIL, else extension);
        - every file written is appended to `staged_files` so the caller can
          compensate (delete) them when its DB transaction rolls back.
        """
        source = Path(source_path)
        if not source.exists():
            raise NotFoundError("Source file does not exist.", {"path": str(source)})

        # Write-side path guard: `name` is concatenated into the destination path —
        # reject anything that could escape the project directory (defense in depth;
        # the read side already enforces this via _safe_path).
        if name is not None:
            if not name or "/" in name or "\\" in name or ".." in name or name in (".", ".."):
                raise ValidationError("Invalid asset name.", {"name": name})

        if shot_id is not None:
            rel_dir = self._shot_relative_dir(shot_id, asset_type)
        else:
            rel_dir = Path(asset_type)

        dest_dir = project_dir(project_id) / rel_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (name or source.name)

        tmp_dest = dest_dir / f".{dest.name}.{uuid.uuid4().hex}.tmp"
        checksum = hashlib.sha256()
        try:
            with source.open("rb") as src, tmp_dest.open("wb") as out:
                for chunk in iter(lambda: src.read(_STREAM_CHUNK), b""):
                    out.write(chunk)
                    checksum.update(chunk)
            os.replace(tmp_dest, dest)  # atomic on the same volume
        finally:
            tmp_dest.unlink(missing_ok=True)  # no-op after a successful replace
        if staged_files is not None:
            staged_files.append(dest)

        width = height = None
        mime_type: str | None = None
        if asset_type == "image":
            try:
                with Image.open(dest) as img:
                    width, height = img.size
                    mime_type = _IMAGE_MIME_BY_FORMAT.get((img.format or "").lower())
            except Exception:  # noqa: BLE001 — non-image content is expected
                logger.debug("asset %s has no image size (non-image content)", dest.name)
        if mime_type is None:
            mime_type = mimetypes.guess_type(dest.name)[0] or _FALLBACK_MIME.get(asset_type)

        thumbnail_rel = None
        if asset_type == "image" and make_thumbnail:
            thumbnail_rel = self.create_thumbnail(project_id, dest)
            if thumbnail_rel and staged_files is not None:
                staged_files.append(project_dir(project_id) / thumbnail_rel)

        asset = Asset(
            project_id=project_id,
            type=asset_type,
            name=dest.name,
            file_path=str(rel_dir / dest.name).replace("\\", "/"),
            thumbnail_path=thumbnail_rel,
            mime_type=mime_type,
            width=width,
            height=height,
            file_size=dest.stat().st_size,
            meta_json=json.dumps(meta or {}, ensure_ascii=False),
            generation_id=generation_id,
            status="ready",
            source_type="generated",
            checksum=checksum.hexdigest(),
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

    def import_asset(
        self,
        *,
        project_id: str,
        asset_type: str,
        source_path: str | Path,
        purpose: str | None = None,
        source_name: str | None = None,
    ) -> Asset:
        """P3-T003: bring an external file into the project and register it as a
        project-scope Asset (no shot / version-group ownership).

        - Naming (database-v0.1 §40): projects are portable, so imported assets
          live under <proj>/imported/ with the scheme {PROJECT_ID}_IMP_{seq} —
          distinct from generated EP_SC_SH_IMG_V assets.
        - SHA-256 checksum (same hash as register_asset).
        - Metadata from MediaProbeService (pure stdlib; never errors).
        - Owns its own transaction: commit then publish asset.created.
        """
        from app.services.media_probe_service import probe

        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        allowed = ("image", "video")
        if asset_type not in allowed:
            raise ValidationError(
                "Unsupported asset_type for import.",
                {"asset_type": asset_type, "supported": list(allowed)},
            )

        source = Path(source_path)
        if not source.is_file():
            raise NotFoundError("Source file does not exist.", {"path": str(source)})

        size = source.stat().st_size
        if size > IMPORT_MAX_BYTES:
            raise ValidationError(
                "Imported asset exceeds the 50 MB limit.",
                {"size": size, "limit": IMPORT_MAX_BYTES},
            )

        seq = self._next_import_seq(project_id)
        dest_name = f"{project_id}_IMP_{seq:03d}{_import_suffix(asset_type, source.name)}"
        rel_dir = Path(IMPORTED_SUBDIR)
        dest_dir = project_dir(project_id) / rel_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / dest_name
        if dest.exists():
            # Never overwrite an existing file silently (seq race or leftover) —
            # the DB row would disagree with the bytes on disk.
            raise ConflictError(
                "An imported asset file with this name already exists.",
                {"name": dest_name},
            )

        # Atomic streamed copy (tmp + os.replace) with checksum computed in-flight —
        # large files never load into memory and the final path never holds a
        # partial write.
        checksum = hashlib.sha256()
        tmp_dest = dest_dir / f".{dest.name}.{uuid.uuid4().hex}.tmp"
        try:
            with source.open("rb") as src, tmp_dest.open("wb") as out:
                for chunk in iter(lambda: src.read(_STREAM_CHUNK), b""):
                    checksum.update(chunk)
                    out.write(chunk)
            os.replace(tmp_dest, dest)
        finally:
            tmp_dest.unlink(missing_ok=True)
        digest = checksum.hexdigest()

        media = probe(dest) or {}
        mime_type = None
        if asset_type == "image":
            fmt = media.get("format") or "png"
            mime_type = _IMAGE_MIME_BY_FORMAT.get(fmt, f"image/{fmt}")

        thumbnail_rel = self.create_thumbnail(project_id, dest) if asset_type == "image" else None

        meta = {"asset_type": asset_type}
        if purpose:
            meta["purpose"] = purpose
        if source_name:
            meta["source_name"] = source_name
        if "codec_type" in media:
            meta["codec"] = media.get("codec_name")

        asset = Asset(
            project_id=project_id,
            type=asset_type,
            name=dest.name,
            file_path=str(rel_dir / dest.name).replace("\\", "/"),
            thumbnail_path=thumbnail_rel,
            mime_type=mime_type,
            width=media.get("width"),
            height=media.get("height"),
            duration=media.get("duration"),
            file_size=size,
            meta_json=json.dumps(meta, ensure_ascii=False),
            status="ready",
            source_type="imported",
            checksum=digest,
            version_group_id=None,
            version_number=None,
            generation_id=None,
            parent_asset_id=None,
        )
        self.session.add(asset)
        self.session.commit()
        self._publish_asset_created(asset)
        logger.info("asset imported: %s -> %s (%d bytes)", dest_name, project_id, size)
        return asset

    def mark_assets_stale(self, asset_ids: list[str]) -> int:
        """P8-T017: mark the given assets as STALE (status change only — never
        auto-regenerate; a user/Agent decides whether to regenerate). Returns the
        number of assets actually flipped to stale. Idempotent."""
        if not asset_ids:
            return 0
        from sqlalchemy import update

        result = self.session.execute(
            update(Asset)
            .where(
                Asset.id.in_(asset_ids),
                Asset.deleted_at.is_(None),
                Asset.status != "stale",
            )
            .values(status="stale")
            .execution_options(synchronize_session=False)
        )
        self.session.commit()
        return int(result.rowcount or 0)

    def check_missing_assets(self, project_id: str) -> tuple[int, int]:
        """P3-T005: scan a project's assets; mark ready assets whose file is
        missing as "missing" (record is KEPT, file untouched). Returns
        (checked, newly_missing)."""
        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        rows = list(
            self.session.scalars(
                select(Asset).where(
                    Asset.project_id == project_id,
                    Asset.deleted_at.is_(None),
                    Asset.file_path.is_not(None),
                    Asset.status == "ready",
                )
            )
        )
        checked = 0
        newly_missing = 0
        for asset in rows:
            checked += 1
            path = project_dir(project_id) / asset.file_path
            if not path.is_file():
                asset.status = "missing"
                newly_missing += 1
        self.session.commit()
        logger.info("missing-asset scan for %s: checked=%d new_missing=%d", project_id, checked, newly_missing)
        return checked, newly_missing

    def _next_import_seq(self, project_id: str) -> int:
        """Next free IMP sequence: MAX(existing numeric suffix) + 1.

        COUNT+1 could collide after purges and let two concurrent imports race
        onto the same file name; parsing the suffix is monotonic and gap-tolerant.
        """
        prefix = f"{project_id}_IMP_"
        names = self.session.scalars(
            select(Asset.name).where(
                Asset.project_id == project_id,
                Asset.name.like(f"{prefix}%"),
            )
        )
        max_seq = 0
        for name in names:
            stem = name[len(prefix):].split(".", 1)[0]
            if stem.isdigit():
                max_seq = max(max_seq, int(stem))
        return max_seq + 1

    def _publish_asset_created(self, asset: Asset) -> None:
        bus.publish(
            StudioEvent(
                event_type=EVENT_ASSET_CREATED,
                entity_type="asset",
                entity_id=asset.id,
                project_id=asset.project_id,
                payload={"type": asset.type, "source": "import"},
            )
        )

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

    def list_assets(
        self,
        *,
        project_id: str,
        limit: int = 50,
        offset: int = 0,
        asset_type: str | None = None,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[int, list[Asset]]:
        """P6-B: paginated, filtered project-scope asset listing (live rows by default).

        Returns (total, rows) ordered by created_at DESC (newest first). Asset-level
        filter/status validation yields 422 (invalid type/status). Soft-deleted rows
        are excluded unless include_deleted=True.
        """
        if self.session.get(Project, project_id) is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        if asset_type is not None and asset_type not in set(ASSET_TYPES):
            raise ValidationError(
                "Invalid asset_type filter.",
                {"asset_type": asset_type, "allowed": sorted(ASSET_TYPES)},
            )
        if status is not None and status not in set(ASSET_STATUSES):
            raise ValidationError(
                "Invalid status filter.",
                {"status": status, "allowed": sorted(ASSET_STATUSES)},
            )

        conds = [Asset.project_id == project_id]
        if not include_deleted:
            conds.append(Asset.deleted_at.is_(None))
        if asset_type:
            conds.append(Asset.type == asset_type)
        if status:
            conds.append(Asset.status == status)

        total = self.session.scalar(select(func.count()).select_from(Asset).where(*conds))
        rows = list(
            self.session.scalars(
                select(Asset)
                .where(*conds)
                .order_by(Asset.created_at.desc(), Asset.id.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        return int(total or 0), rows

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
