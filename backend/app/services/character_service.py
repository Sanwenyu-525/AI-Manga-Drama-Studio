"""CharacterService (backend-architecture §12, database-v0.1 §7, mvp-spec §105-BE).

Rules (same as ShotService):
- update_character() bumps revision (optimistic concurrency, api-event-contract §21/§88).
- All mutations publish domain events AFTER commit (red line: commit then publish).
- Soft delete only — never hard-delete characters (contract §89).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Character, Project, ShotCharacter
from app.domain.character import (
    CharacterCreate,
    CharacterRead,
    CharacterSummary,
    CharacterUpdate,
)
from app.events.bus import (
    EVENT_CHARACTER_CREATED,
    EVENT_CHARACTER_DELETED,
    EVENT_CHARACTER_UPDATED,
    StudioEvent,
    bus,
)
from app.repositories import CharacterRepository, ProjectRepository, ShotCharacterRepository

UPDATE_FIELDS = (
    "name",
    "alias",
    "gender",
    "age_description",
    "appearance",
    "personality",
    "visual_prompt",
    "negative_prompt",
    "status",
)


def _to_read(c: Character, shot_count: int = 0) -> CharacterRead:
    return CharacterRead(
        id=c.id,
        project_id=c.project_id,
        name=c.name,
        alias=c.alias,
        gender=c.gender,
        age_description=c.age_description,
        appearance=c.appearance,
        personality=c.personality,
        visual_prompt=c.visual_prompt,
        negative_prompt=c.negative_prompt,
        default_costume_id=c.default_costume_id,
        status=c.status,
        revision=c.revision,
        shot_count=shot_count,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _to_summary(c: Character) -> CharacterSummary:
    return CharacterSummary(id=c.id, name=c.name, alias=c.alias, status=c.status)


class CharacterService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CharacterRepository(session)
        self.projects = ProjectRepository(session)
        self.links = ShotCharacterRepository(session)

    # --- reads ---

    def get_character(self, character_id: str) -> CharacterRead:
        character = self.repo.get(character_id)
        if character is None:
            raise NotFoundError("Character does not exist.", {"character_id": character_id})
        counts = self._shot_counts([character_id])
        return _to_read(character, counts.get(character_id, 0))

    def list_characters(self, project_id: str) -> list[CharacterRead]:
        self._require_project(project_id)
        characters = self.repo.list_for_project(project_id)
        counts = self._shot_counts([c.id for c in characters])
        return [_to_read(c, counts.get(c.id, 0)) for c in characters]

    def list_summaries(self, project_id: str) -> list[CharacterSummary]:
        """Bootstrap payload (api-event-contract §103) — no shot_count, cheap."""
        self._require_project(project_id)
        return [_to_summary(c) for c in self.repo.list_for_project(project_id)]

    # --- writes ---

    def create_character(self, project_id: str, data: CharacterCreate) -> CharacterRead:
        self._require_project(project_id)
        character = Character(
            project_id=project_id,
            name=data.name,
            alias=data.alias,
            gender=data.gender,
            age_description=data.age_description,
            appearance=data.appearance,
            personality=data.personality,
            visual_prompt=data.visual_prompt,
            negative_prompt=data.negative_prompt,
            status=data.status,
            revision=1,
        )
        self.repo.add(character)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_CHARACTER_CREATED,
                entity_type="character",
                entity_id=character.id,
                project_id=project_id,
            )
        )
        return _to_read(character)

    def update_character(self, character_id: str, revision: int, patch: CharacterUpdate) -> CharacterRead:
        """Optimistic concurrency: revision must match; every mutation bumps revision."""
        character = self.repo.get(character_id)
        if character is None:
            raise NotFoundError("Character does not exist.", {"character_id": character_id})
        if character.revision != revision:
            raise ConflictError(
                "Character was modified by another writer.",
                {
                    "character_id": character_id,
                    "expected_revision": revision,
                    "current_revision": character.revision,
                },
            )
        changed: list[str] = []
        for field in UPDATE_FIELDS:
            value = getattr(patch, field)
            if value is not None:
                setattr(character, field, value)
                changed.append(field)
        if changed:
            character.revision += 1
        self.session.commit()
        if changed:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_CHARACTER_UPDATED,
                    entity_type="character",
                    entity_id=character.id,
                    project_id=character.project_id,
                    payload={"revision": character.revision, "changed_fields": changed},
                )
            )
        counts = self._shot_counts([character_id])
        return _to_read(character, counts.get(character_id, 0))

    def delete_character(self, character_id: str) -> None:
        """Soft delete (contract §89). Shot links are kept as history — summaries stop
        showing the name only after the character row is truly gone (it never is in MVP)."""
        character = self.repo.get(character_id)
        if character is None:
            raise NotFoundError("Character does not exist.", {"character_id": character_id})
        self.repo.delete(character)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_CHARACTER_DELETED,
                entity_type="character",
                entity_id=character.id,
                project_id=character.project_id,
            )
        )

    # --- helpers ---

    def _require_project(self, project_id: str) -> Project:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        return project

    def _shot_counts(self, character_ids: list[str]) -> dict[str, int]:
        """character_id → number of shots referencing it (for shot_count in reads)."""
        if not character_ids:
            return {}
        rows = self.session.execute(
            select(ShotCharacter.character_id, func.count(ShotCharacter.id))
            .where(ShotCharacter.character_id.in_(character_ids))
            .group_by(ShotCharacter.character_id)
        ).all()
        return {character_id: count for character_id, count in rows}

    def validate_character_ids(self, character_ids: list[str], project_id: str) -> None:
        """All referenced characters must exist (not deleted) and belong to the same project."""
        if not character_ids:
            return
        characters = self.repo.list_all()  # soft-delete aware
        by_id = {c.id: c for c in characters}
        unknown = [cid for cid in character_ids if cid not in by_id]
        if unknown:
            raise NotFoundError("Character does not exist.", {"character_ids": unknown})
        foreign = [cid for cid in character_ids if by_id[cid].project_id != project_id]
        if foreign:
            from app.core.errors import ValidationError

            raise ValidationError(
                "Character belongs to another project.",
                {"character_ids": foreign, "project_id": project_id},
            )
