"""VersionService (backend-architecture §24, mvp-spec §28; ADR-001).

Asset-backed versions (ADR-001): media_versions merged into assets.
- assign_version: sets version_group_id (vg:shot:{shot_id}:{PURPOSE}) +
  version_number (max+1, unique index backstop) on the asset; when make_active,
  writes shots.active_{media_type}_asset_id.
- set_active_asset: explicit activation — flips the shot pointer only
  (versions stay immutable; nothing is deleted or overwritten).
- commit=False supports caller-owned transactions (worker single-commit completion).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Asset, Episode, Scene, Shot
from app.events.bus import EVENT_SHOT_ACTIVE_VERSION_CHANGED, StudioEvent, bus
from app.repositories import ShotRepository

MEDIA_TYPES = ("image", "video")
GROUP_PURPOSES = {"image": "SHOT_IMAGE", "video": "SHOT_VIDEO"}
PURPOSE_MEDIA = {"SHOT_IMAGE": "image", "SHOT_VIDEO": "video"}


def version_group_id(shot_id: str, media_type: str) -> str:
    """Deterministic group id (ADR-001 2.2): vg:shot:{shot_id}:{PURPOSE}."""
    return f"vg:shot:{shot_id}:{GROUP_PURPOSES[media_type]}"


def parse_version_group(group_id: str) -> tuple[str, str, str] | None:
    """Parse vg:shot:{shot_id}:{PURPOSE} -> (owner_type, owner_id, purpose)."""
    parts = (group_id or "").split(":")
    if len(parts) == 4 and parts[0] == "vg" and parts[2]:
        return parts[1], parts[2], parts[3]
    return None


class VersionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotRepository(session)

    def assign_version(
        self,
        *,
        shot_id: str,
        asset: Asset,
        media_type: str = "image",
        make_active: bool = True,
        commit: bool = True,
    ) -> Asset:
        """Assign version_group_id + version_number to a freshly registered asset.

        The caller passes the ORM object (it may still be pending in the session
        when the caller owns the transaction — asset.id is only valid after flush).
        """
        shot = self.shots.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        if media_type not in GROUP_PURPOSES:
            raise NotFoundError("Unsupported media type.", {"media_type": media_type})
        self.session.flush()  # assign asset.id before wiring group/version
        group = version_group_id(shot_id, media_type)
        asset.version_group_id = group
        asset.version_number = self._next_version_number(group)
        asset.status = "ready"
        if make_active:
            setattr(shot, f"active_{media_type}_asset_id", asset.id)
        if commit:
            self.session.commit()
            self._publish_active_changed(shot, media_type, asset)
        return asset

    def set_active_asset(self, asset_id: str, commit: bool = True) -> Asset:
        """Explicit activation: point the owning shot's active pointer at this asset."""
        asset = self.session.get(Asset, asset_id)
        if asset is None:
            raise NotFoundError("Asset does not exist.", {"asset_id": asset_id})
        parsed = parse_version_group(asset.version_group_id)
        if parsed is None or parsed[0] != "shot":
            raise NotFoundError("Asset is not a versioned shot asset.", {"asset_id": asset_id})
        _, shot_id, purpose = parsed
        media_type = PURPOSE_MEDIA.get(purpose)
        if media_type is None:
            raise NotFoundError("Asset has an unknown version purpose.", {"asset_id": asset_id, "purpose": purpose})
        shot = self.shots.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        setattr(shot, f"active_{media_type}_asset_id", asset.id)
        if commit:
            self.session.commit()
            self._publish_active_changed(shot, media_type, asset)
        return asset

    def list_shot_versions(self, shot_id: str, media_type: str = "image") -> list[Asset]:
        """All live assets of one shot/type, newest version first."""
        stmt = (
            select(Asset)
            .where(
                Asset.version_group_id == version_group_id(shot_id, media_type),
                Asset.deleted_at.is_(None),
            )
            .order_by(Asset.version_number.desc())
        )
        return list(self.session.scalars(stmt))

    def _next_version_number(self, group: str) -> int:
        current = self.session.scalar(
            select(func.max(Asset.version_number)).where(
                Asset.version_group_id == group, Asset.deleted_at.is_(None)
            )
        )
        return (current or 0) + 1

    def _publish_active_changed(self, shot: Shot, media_type: str, asset: Asset) -> None:
        bus.publish(
            StudioEvent(
                event_type=EVENT_SHOT_ACTIVE_VERSION_CHANGED,
                entity_type="shot",
                entity_id=shot.id,
                project_id=self._project_id(shot),
                payload={
                    "media_type": media_type,
                    "asset_id": asset.id,
                    "version_number": asset.version_number,
                },
            )
        )

    def _project_id(self, shot: Shot) -> str | None:
        scene = self.session.get(Scene, shot.scene_id) if shot else None
        if scene is None:
            return None
        episode = self.session.get(Episode, scene.episode_id)
        return episode.project_id if episode else None
