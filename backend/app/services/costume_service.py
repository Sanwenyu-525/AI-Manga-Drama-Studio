"""CostumeService (P2-T010; database-v0.1 §8, domain-model-design §33).

Basic CRUD only — no version system (a future CostumeVersion task mirrors
Character/CharacterVersion). Rules (same as CharacterService):
- update_costume() bumps revision (optimistic concurrency, api-event-contract §21/§88).
- All mutations publish domain events AFTER commit (red line: commit then publish).
- Soft delete only (contract §89).
- optional character owner and reference_asset_id are validated (existence + same project).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models import Asset, Character, Costume, Project, ShotCharacter
from app.domain.costume import CostumeCreate, CostumeRead, CostumeUpdate
from app.events.bus import (
    EVENT_COSTUME_CREATED,
    EVENT_COSTUME_DELETED,
    EVENT_COSTUME_UPDATED,
    StudioEvent,
    bus,
)
from app.repositories import CostumeRepository, ProjectRepository, ShotCharacterRepository

UPDATE_FIELDS = ("name", "description", "visual_prompt", "reference_asset_id", "character_id")


def _to_read(c: Costume, shot_count: int = 0) -> CostumeRead:
    return CostumeRead(
        id=c.id,
        project_id=c.project_id,
        character_id=c.character_id,
        name=c.name,
        description=c.description,
        visual_prompt=c.visual_prompt,
        reference_asset_id=c.reference_asset_id,
        revision=c.revision,
        shot_count=shot_count,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


class CostumeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CostumeRepository(session)
        self.projects = ProjectRepository(session)
        self.links = ShotCharacterRepository(session)

    # --- reads ---

    def get_costume(self, costume_id: str) -> CostumeRead:
        costume = self.repo.get(costume_id)
        if costume is None:
            raise NotFoundError("Costume does not exist.", {"costume_id": costume_id})
        counts = self._shot_counts([costume_id])
        return _to_read(costume, counts.get(costume_id, 0))

    def list_costumes(self, project_id: str) -> list[CostumeRead]:
        self._require_project(project_id)
        costumes = self.repo.list_for_project(project_id)
        counts = self._shot_counts([c.id for c in costumes])
        return [_to_read(c, counts.get(c.id, 0)) for c in costumes]

    # --- writes ---

    def create_costume(self, project_id: str, data: CostumeCreate) -> CostumeRead:
        self._require_project(project_id)
        if data.character_id is not None:
            self._validate_character(data.character_id, project_id)
        if data.reference_asset_id is not None:
            self._validate_asset(data.reference_asset_id, project_id)
        costume = Costume(
            project_id=project_id,
            character_id=data.character_id,
            name=data.name,
            description=data.description,
            visual_prompt=data.visual_prompt,
            reference_asset_id=data.reference_asset_id,
            revision=1,
        )
        self.repo.add(costume)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_COSTUME_CREATED,
                entity_type="costume",
                entity_id=costume.id,
                project_id=project_id,
            )
        )
        return _to_read(costume)

    def update_costume(
        self, costume_id: str, revision: int, patch: CostumeUpdate
    ) -> CostumeRead:
        """Optimistic concurrency (ATOMIC conditional update — two stale writers can't both win)."""
        costume = self.repo.get(costume_id)
        if costume is None:
            raise NotFoundError("Costume does not exist.", {"costume_id": costume_id})

        if patch.character_id is not None:
            self._validate_character(patch.character_id, costume.project_id)
        if patch.reference_asset_id is not None:
            self._validate_asset(patch.reference_asset_id, costume.project_id)

        values: dict = {}
        changed: list[str] = []
        for field in UPDATE_FIELDS:
            # allow reference_asset_id / character_id to be set to None explicitly
            if field in ("reference_asset_id", "character_id"):
                if field not in patch.model_fields_set:
                    continue
                values[field] = getattr(patch, field)
                changed.append(field)
                continue
            value = getattr(patch, field)
            if value is not None:
                values[field] = value
                changed.append(field)
        if not changed:
            counts = self._shot_counts([costume_id])
            return _to_read(costume, counts.get(costume_id, 0))

        values["updated_at"] = datetime.now(UTC).isoformat()
        stmt = (
            update(Costume)
            .where(
                Costume.id == costume_id,
                Costume.revision == revision,
                Costume.deleted_at.is_(None),
            )
            .values(revision=Costume.revision + 1, **values)
            .execution_options(synchronize_session=False)
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            current = self.session.scalar(select(Costume.revision).where(Costume.id == costume_id))
            raise ConflictError(
                "Costume was modified by another writer.",
                {
                    "costume_id": costume_id,
                    "expected_revision": revision,
                    "current_revision": current,
                },
            )
        self.session.commit()
        self.session.refresh(costume)
        bus.publish(
            StudioEvent(
                event_type=EVENT_COSTUME_UPDATED,
                entity_type="costume",
                entity_id=costume.id,
                project_id=costume.project_id,
                payload={"revision": costume.revision, "changed_fields": changed},
            )
        )
        counts = self._shot_counts([costume_id])
        return _to_read(costume, counts.get(costume_id, 0))

    def delete_costume(self, costume_id: str) -> None:
        """Soft delete (contract §89). Shot links are kept as history."""
        costume = self.repo.get(costume_id)
        if costume is None:
            raise NotFoundError("Costume does not exist.", {"costume_id": costume_id})
        self.repo.delete(costume)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_COSTUME_DELETED,
                entity_type="costume",
                entity_id=costume.id,
                project_id=costume.project_id,
            )
        )

    def validate_costume(self, costume_id: str, project_id: str) -> None:
        """Service layer check for shot_characters.costume_id (weak ref — no DB FK)."""
        costume = self.repo.get(costume_id)
        if costume is None:
            raise NotFoundError("Costume does not exist.", {"costume_id": costume_id})
        if costume.project_id != project_id:
            raise ValidationError(
                "Costume belongs to another project.",
                {"costume_id": costume_id, "project_id": project_id, "costume_project_id": costume.project_id},
            )

    # --- helpers ---

    def _require_project(self, project_id: str) -> Project:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        return project

    def _validate_character(self, character_id: str, project_id: str) -> None:
        character = self.session.scalar(
            select(Character).where(Character.id == character_id, Character.deleted_at.is_(None))
        )
        if character is None:
            raise NotFoundError("Character does not exist.", {"character_id": character_id})
        if character.project_id != project_id:
            raise ValidationError(
                "Character belongs to another project.",
                {"character_id": character_id, "project_id": project_id, "character_project_id": character.project_id},
            )

    def _validate_asset(self, asset_id: str, project_id: str) -> None:
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

    def _shot_counts(self, costume_ids: list[str]) -> dict[str, int]:
        if not costume_ids:
            return {}
        rows = self.session.execute(
            select(ShotCharacter.costume_id, func.count(ShotCharacter.id))
            .where(ShotCharacter.costume_id.in_(costume_ids))
            .group_by(ShotCharacter.costume_id)
        ).all()
        return {costume_id: count for costume_id, count in rows}
