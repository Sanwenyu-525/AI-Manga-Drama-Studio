"""LocationService + LocationVersionService (P2-T009; database-v0.1 §6, domain-model-design §35/§36).

Location versioning mirrors the CharacterVersion pattern (P2-T007/T008, character_version_service.py):
- location_versions is an immutable version chain: edits create vN+1 (max+1 unique-index backstop,
  soft-deleted rows excluded so a deleted version frees its slot).
- a new version defaults to status=stale — NOT auto-activated. The project approves a look by
  activating it (promote to active + point locations.master_version_id).
- activation flips old active -> stale, new -> active, master -> new, in a single transaction
  (commit then publish — red line). Activating the already-master version is idempotent.

CRUD:
- soft delete (deleted_at) for both locations and location_versions.
- revision optimistic concurrency (409) on update_location.
- scenes.location_id is a weak Text ref (no hard FK); this service and SceneService validate
  location existence + project membership at the service layer only.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models import Asset, Location, LocationVersion, Project
from app.domain.location import (
    LocationCreate,
    LocationRead,
    LocationUpdate,
    LocationVersionCreate,
    LocationVersionRead,
)
from app.events.bus import (
    EVENT_LOCATION_CREATED,
    EVENT_LOCATION_DELETED,
    EVENT_LOCATION_UPDATED,
    EVENT_LOCATION_VERSION_ACTIVATED,
    EVENT_LOCATION_VERSION_CREATED,
    StudioEvent,
    bus,
)
from app.repositories import (
    LocationRepository,
    LocationVersionRepository,
    ProjectRepository,
)

UPDATE_FIELDS = ("name", "description", "visual_prompt", "status")


def _to_read(loc: Location) -> LocationRead:
    return LocationRead(
        id=loc.id,
        project_id=loc.project_id,
        name=loc.name,
        description=loc.description,
        visual_prompt=loc.visual_prompt,
        status=loc.status,
        revision=loc.revision,
        master_version_id=loc.master_version_id,
        created_at=loc.created_at,
        updated_at=loc.updated_at,
    )


def _version_to_read(v: LocationVersion, is_master: bool) -> LocationVersionRead:
    return LocationVersionRead(
        id=v.id,
        location_id=v.location_id,
        version_number=v.version_number,
        asset_id=v.asset_id,
        name=v.name,
        description=v.description,
        status=v.status,
        checksum=v.checksum,
        is_master=is_master,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


class LocationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = LocationRepository(session)
        self.projects = ProjectRepository(session)

    # --- reads ---

    def list_locations(self, project_id: str) -> list[LocationRead]:
        self._require_project(project_id)
        return [_to_read(loc) for loc in self.repo.list_for_project(project_id)]

    def get_location(self, location_id: str) -> LocationRead:
        location = self.repo.get(location_id)
        if location is None:
            raise NotFoundError("Location does not exist.", {"location_id": location_id})
        return _to_read(location)

    # --- writes ---

    def create_location(self, project_id: str, data: LocationCreate) -> LocationRead:
        self._require_project(project_id)
        location = Location(
            project_id=project_id,
            name=data.name,
            description=data.description,
            visual_prompt=data.visual_prompt,
            status=data.status,
            revision=1,
        )
        self.repo.add(location)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_LOCATION_CREATED,
                entity_type="location",
                entity_id=location.id,
                project_id=project_id,
            )
        )
        return _to_read(location)

    def update_location(
        self, location_id: str, revision: int, patch: LocationUpdate
    ) -> LocationRead:
        """Optimistic concurrency (ATOMIC conditional update — two stale writers can't both win)."""
        location = self.repo.get(location_id)
        if location is None:
            raise NotFoundError("Location does not exist.", {"location_id": location_id})

        values: dict = {}
        changed: list[str] = []
        for field in UPDATE_FIELDS:
            value = getattr(patch, field)
            if value is not None:
                values[field] = value
                changed.append(field)
        if not changed:
            return _to_read(location)

        values["updated_at"] = datetime.now(UTC).isoformat()
        stmt = (
            update(Location)
            .where(
                Location.id == location_id,
                Location.revision == revision,
                Location.deleted_at.is_(None),
            )
            .values(revision=Location.revision + 1, **values)
            .execution_options(synchronize_session=False)
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            current = self.session.scalar(select(Location.revision).where(Location.id == location_id))
            raise ConflictError(
                "Location was modified by another writer.",
                {
                    "location_id": location_id,
                    "expected_revision": revision,
                    "current_revision": current,
                },
            )
        self.session.commit()
        self.session.refresh(location)
        bus.publish(
            StudioEvent(
                event_type=EVENT_LOCATION_UPDATED,
                entity_type="location",
                entity_id=location.id,
                project_id=location.project_id,
                payload={"revision": location.revision, "changed_fields": changed},
            )
        )
        return _to_read(location)

    def delete_location(self, location_id: str) -> None:
        """Soft delete (contract §89). location_versions are kept as history."""
        location = self.repo.get(location_id)
        if location is None:
            raise NotFoundError("Location does not exist.", {"location_id": location_id})
        self.repo.delete(location)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_LOCATION_DELETED,
                entity_type="location",
                entity_id=location.id,
                project_id=location.project_id,
            )
        )

    def validate_location(self, location_id: str, project_id: str) -> None:
        """Service layer check for scenes.location_id (weak ref — no DB FK on scenes)."""
        location = self.repo.get(location_id)
        if location is None:
            raise NotFoundError("Location does not exist.", {"location_id": location_id})
        if location.project_id != project_id:
            raise ValidationError(
                "Location belongs to another project.",
                {"location_id": location_id, "project_id": project_id, "location_project_id": location.project_id},
            )

    # --- helpers ---

    def _require_project(self, project_id: str) -> Project:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        return project


class LocationVersionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.locations = LocationRepository(session)
        self.versions = LocationVersionRepository(session)

    # --- reads ---

    def list_versions(self, location_id: str) -> list[LocationVersionRead]:
        location = self._require_location(location_id)
        rows = self.versions.list_for_location(location_id)
        return [_version_to_read(v, v.id == location.master_version_id) for v in rows]

    # --- writes ---

    def create_version(self, location_id: str, data: LocationVersionCreate) -> LocationVersionRead:
        """Register a new LocationVersion (stale by default — no auto activation)."""
        location = self._require_location(location_id)
        asset = self._require_same_project_asset(location.project_id, data.asset_id)

        version = LocationVersion(
            location_id=location_id,
            version_number=self.versions.next_version_number(location_id),
            asset_id=data.asset_id,
            name=data.name,
            description=data.description,
            status="stale",
            checksum=asset.checksum,
        )
        self.versions.add(version)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_LOCATION_VERSION_CREATED,
                entity_type="location",
                entity_id=location_id,
                project_id=location.project_id,
                payload={
                    "location_id": location_id,
                    "version_id": version.id,
                    "version_number": version.version_number,
                    "asset_id": data.asset_id,
                },
            )
        )
        return _version_to_read(version, is_master=False)

    def activate_version(self, location_id: str, version_id: str) -> LocationVersionRead:
        """Promote a version to active and point locations.master_version_id at it.

        Single transaction: old active -> stale, target -> active, master pointer ->
        target (commit then publish). Idempotent: re-activating the current master is
        a no-op (no write, no event).
        """
        location = self._require_location(location_id)
        version = self._require_location_version(location_id, version_id)

        if location.master_version_id == version_id and version.status == "active":
            return _version_to_read(version, is_master=True)

        self.session.execute(
            update(LocationVersion)
            .where(
                LocationVersion.location_id == location_id,
                LocationVersion.status == "active",
                LocationVersion.deleted_at.is_(None),
            )
            .values(status="stale", updated_at=datetime.now(UTC).isoformat())
            .execution_options(synchronize_session=False)
        )
        version.status = "active"
        version.updated_at = datetime.now(UTC).isoformat()
        location.master_version_id = version.id
        self.session.commit()

        bus.publish(
            StudioEvent(
                event_type=EVENT_LOCATION_VERSION_ACTIVATED,
                entity_type="location",
                entity_id=location_id,
                project_id=location.project_id,
                payload={
                    "location_id": location_id,
                    "version_id": version.id,
                    "version_number": version.version_number,
                    "asset_id": version.asset_id,
                },
            )
        )
        return _version_to_read(version, is_master=True)

    # --- helpers ---

    def _require_location(self, location_id: str) -> Location:
        location = self.locations.get(location_id)
        if location is None:
            raise NotFoundError("Location does not exist.", {"location_id": location_id})
        return location

    def _require_same_project_asset(self, project_id: str, asset_id: str) -> Asset:
        asset = self.session.scalar(
            select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
        )
        if asset is None:
            raise NotFoundError("Asset does not exist.", {"asset_id": asset_id})
        if asset.project_id != project_id:
            raise ValidationError(
                "Asset belongs to another project.",
                {"asset_id": asset_id, "project_id": project_id, "asset_project_id": asset.project_id},
            )
        return asset

    def _require_location_version(self, location_id: str, version_id: str) -> LocationVersion:
        version = self.session.scalar(
            select(LocationVersion).where(
                LocationVersion.id == version_id,
                LocationVersion.deleted_at.is_(None),
            )
        )
        if version is None:
            raise NotFoundError("Location version does not exist.", {"version_id": version_id})
        if version.location_id != location_id:
            raise NotFoundError(
                "Location version does not belong to this location.",
                {"version_id": version_id, "location_id": location_id},
            )
        return version
