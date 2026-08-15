"""VersionService (backend-architecture §24, mvp-spec §28).

Media versions are IMMUTABLE snapshots (database-v0.1 §19):
- create_media_version: new row, version_number = max+1, never overwrite V1.
- set_active_version: flips is_active and updates shot.active_image_version_id.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import MediaVersion, Shot
from app.events.bus import EVENT_SHOT_ACTIVE_VERSION_CHANGED, StudioEvent, bus
from app.repositories import ShotRepository


class VersionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotRepository(session)

    def create_media_version(
        self,
        *,
        shot_id: str,
        asset_id: str,
        media_type: str = "image",
        generation_id: str | None = None,
        notes: str | None = None,
        make_active: bool = True,
    ) -> MediaVersion:
        shot = self.shots.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        version_number = self._next_version_number(shot_id, media_type)
        version = MediaVersion(
            shot_id=shot_id,
            asset_id=asset_id,
            media_type=media_type,
            version_number=version_number,
            generation_id=generation_id,
            is_active=1 if make_active else 0,
            notes=notes,
        )
        if make_active:
            # P1-E1-T02: deactivate existing rows BEFORE inserting the new active row
            # (partial unique index uq_media_versions_active allows one active per shot).
            self._clear_active(shot_id, media_type)
            self.session.flush()
        self.session.add(version)
        self.session.flush()  # generate version.id BEFORE wiring it onto the shot
        if make_active:
            setattr(shot, f"active_{media_type}_version_id", version.id)
        self.session.commit()
        if make_active:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_SHOT_ACTIVE_VERSION_CHANGED,
                    entity_type="shot",
                    entity_id=shot_id,
                    project_id=self._project_id(shot),
                    payload={"media_type": media_type, "version_id": version.id, "version_number": version_number},
                )
            )
        return version

    def set_active_version(self, version_id: str) -> MediaVersion:
        version = self.session.get(MediaVersion, version_id)
        if version is None:
            raise NotFoundError("Media version does not exist.", {"version_id": version_id})
        shot = self.shots.get(version.shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": version.shot_id})
        self._clear_active(version.shot_id, version.media_type)
        self.session.flush()  # P1-E1-T02: deactivate old rows before activating this one
        version.is_active = 1
        setattr(shot, f"active_{version.media_type}_version_id", version.id)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_SHOT_ACTIVE_VERSION_CHANGED,
                entity_type="shot",
                entity_id=version.shot_id,
                project_id=self._project_id(shot),
                payload={"media_type": version.media_type, "version_id": version.id, "version_number": version.version_number},
            )
        )
        return version

    def list_shot_versions(self, shot_id: str, media_type: str = "image") -> list[MediaVersion]:
        stmt = (
            select(MediaVersion)
            .where(MediaVersion.shot_id == shot_id, MediaVersion.media_type == media_type)
            .order_by(MediaVersion.version_number.desc())
        )
        return list(self.session.scalars(stmt))

    def _next_version_number(self, shot_id: str, media_type: str) -> int:
        current = self.session.scalar(
            select(func.max(MediaVersion.version_number)).where(
                MediaVersion.shot_id == shot_id, MediaVersion.media_type == media_type
            )
        )
        return (current or 0) + 1

    def _clear_active(self, shot_id: str, media_type: str) -> None:
        """Deactivate all versions of a shot/media_type via ORM (keeps identity map in sync).

        NOTE: a Core bulk UPDATE would NOT update ORM objects, so a later `version.is_active = 1`
        would compare equal to the stale in-memory value and never flush.
        """
        rows = self.session.scalars(
            select(MediaVersion).where(
                MediaVersion.shot_id == shot_id, MediaVersion.media_type == media_type
            )
        ).all()
        for version in rows:
            version.is_active = 0

    @staticmethod
    def _project_id(shot: Shot) -> str | None:
        return None  # resolved by caller if needed; kept minimal for MVP
