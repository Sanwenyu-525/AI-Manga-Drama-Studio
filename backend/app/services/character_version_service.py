"""CharacterVersionService (P2-T007/T008; database-v0.1 §7, domain-model-design §31/§32/§39-41).

Character visual versions (CharacterVersion) + the MASTER pointer on Character.

Design (mirrors ADR-001/ADR-002 but scoped to characters):
- character_versions is an immutable version chain: edits create vN+1 (max+1 with a
  unique-index backstop); soft-deleted rows are excluded from numbering so a deleted
  version frees its slot.
- A new version defaults to status=stale — it is NOT auto-activated. The project
  approves a look by activating it (promote to active + point Character.master_version_id).
- characters.master_version_id is the AUTHORITATIVE MASTER pointer (ADR-002 pattern).
  Activation flips: old active -> stale, new -> active, master -> new version, in a
  single transaction (commit then publish — red line).
- Activating the already-master version is idempotent (no write, no re-publish).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.db.models import Asset, Character, CharacterVersion
from app.domain.character import CharacterVersionCreate, CharacterVersionRead
from app.events.bus import (
    EVENT_CHARACTER_VERSION_ACTIVATED,
    EVENT_CHARACTER_VERSION_CREATED,
    StudioEvent,
    bus,
)
from app.repositories import CharacterRepository, CharacterVersionRepository


def _to_read(version: CharacterVersion, is_master: bool) -> CharacterVersionRead:
    return CharacterVersionRead(
        id=version.id,
        character_id=version.character_id,
        version_number=version.version_number,
        asset_id=version.asset_id,
        name=version.name,
        description=version.description,
        status=version.status,
        checksum=version.checksum,
        is_master=is_master,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


class CharacterVersionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.characters = CharacterRepository(session)
        self.versions = CharacterVersionRepository(session)

    # --- reads ---

    def list_versions(self, character_id: str) -> list[CharacterVersionRead]:
        """All live versions of one character, ordered by version_number (v1, v2, ...)."""
        character = self._require_character(character_id)
        rows = self.versions.list_for_character(character_id)
        return [_to_read(v, v.id == character.master_version_id) for v in rows]

    # --- writes ---

    def create_version(self, character_id: str, data: CharacterVersionCreate) -> CharacterVersionRead:
        """Register a new CharacterVersion (stale by default — no auto activation).

        Validates:
        - the character exists (404) and is not soft-deleted.
        - the asset exists (404) and belongs to the same project (422) — cross-project
        guard mirrors Character/Shot references (NO cross-project asset leaks).
        """
        character = self._require_character(character_id)
        asset = self._require_same_project_asset(character.project_id, data.asset_id)

        version = CharacterVersion(
            character_id=character_id,
            version_number=self.versions.next_version_number(character_id),
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
                event_type=EVENT_CHARACTER_VERSION_CREATED,
                entity_type="character",
                entity_id=character_id,
                project_id=character.project_id,
                payload={
                    "character_id": character_id,
                    "version_id": version.id,
                    "version_number": version.version_number,
                    "asset_id": data.asset_id,
                },
            )
        )
        return _to_read(version, is_master=False)

    def activate_version(self, character_id: str, version_id: str) -> CharacterVersionRead:
        """Promote a version to active and point Character.master_version_id at it.

        Single transaction: old active -> stale, target -> active, master pointer ->
        target (commit then publish). Idempotent: re-activating the current master is
        a no-op (no write, no event). Versions must belong to the given character.
        """
        character = self._require_character(character_id)
        version = self._require_character_version(character_id, version_id)

        # Idempotent: already the master / already active -> nothing to do.
        if character.master_version_id == version_id and version.status == "active":
            return _to_read(version, is_master=True)

        # Single logical transaction: demote any current active, promote target.
        self.session.execute(
            update(CharacterVersion)
            .where(
                CharacterVersion.character_id == character_id,
                CharacterVersion.status == "active",
                CharacterVersion.deleted_at.is_(None),
            )
            .values(status="stale", updated_at=datetime.now(UTC).isoformat())
            .execution_options(synchronize_session=False)
        )
        version.status = "active"
        version.updated_at = datetime.now(UTC).isoformat()
        character.master_version_id = version.id
        self.session.commit()

        bus.publish(
            StudioEvent(
                event_type=EVENT_CHARACTER_VERSION_ACTIVATED,
                entity_type="character",
                entity_id=character_id,
                project_id=character.project_id,
                payload={
                    "character_id": character_id,
                    "version_id": version.id,
                    "version_number": version.version_number,
                    "asset_id": version.asset_id,
                },
            )
        )
        return _to_read(version, is_master=True)

    # --- helpers ---

    def _require_character(self, character_id: str) -> Character:
        character = self.characters.get(character_id)
        if character is None:
            raise NotFoundError("Character does not exist.", {"character_id": character_id})
        return character

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

    def _require_character_version(self, character_id: str, version_id: str) -> CharacterVersion:
        version = self.session.scalar(
            select(CharacterVersion).where(
                CharacterVersion.id == version_id,
                CharacterVersion.deleted_at.is_(None),
            )
        )
        if version is None:
            raise NotFoundError("Character version does not exist.", {"version_id": version_id})
        if version.character_id != character_id:
            raise NotFoundError(
                "Character version does not belong to this character.",
                {"version_id": version_id, "character_id": character_id},
            )
        return version
