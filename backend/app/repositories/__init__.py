"""Concrete repositories (Stage A: Project / Episode / Scene / Shot; P1: Character; P4: Workflow; P2: CharacterVersion)."""

from sqlalchemy import select

from app.db.models import (
    Character,
    CharacterVersion,
    Episode,
    Project,
    Scene,
    Shot,
    ShotCharacter,
    WorkflowTemplate,
    WorkflowVersion,
)
from app.repositories.base import SQLAlchemyRepository


class ProjectRepository(SQLAlchemyRepository[Project]):
    model = Project


class EpisodeRepository(SQLAlchemyRepository[Episode]):
    model = Episode

    def next_episode_number(self, project_id: str) -> int:
        return self.next_sequence("project_id", project_id, "episode_number")


class SceneRepository(SQLAlchemyRepository[Scene]):
    model = Scene

    def next_scene_number(self, episode_id: str) -> int:
        return self.next_sequence("episode_id", episode_id, "scene_number")


class ShotRepository(SQLAlchemyRepository[Shot]):
    model = Shot

    def list_for_scene(self, scene_id: str) -> list[Shot]:
        return self.list_ordered(order_by="shot_order", scene_id=scene_id)

    def next_shot_number(self, scene_id: str) -> int:
        return self.next_sequence("scene_id", scene_id, "shot_number")


class CharacterRepository(SQLAlchemyRepository[Character]):
    model = Character

    def list_for_project(self, project_id: str) -> list[Character]:
        return self.list_ordered(order_by="created_at", project_id=project_id)


class CharacterVersionRepository(SQLAlchemyRepository[CharacterVersion]):
    """Character visual versions (P2-T007) — immutable chain, soft-delete aware.

    CharacterVersion rows own their soft-delete (deleted_at) like core entities:
    list_versions excludes them; version_number computation also excludes them
    (so a v2 delete frees the "v2" slot for reuse, mirroring the shot/version rule).
    """

    model = CharacterVersion

    def list_for_character(self, character_id: str) -> list[CharacterVersion]:
        stmt = (
            select(CharacterVersion)
            .where(
                CharacterVersion.character_id == character_id,
                CharacterVersion.deleted_at.is_(None),
            )
            .order_by(CharacterVersion.version_number.asc())
        )
        return list(self.session.scalars(stmt))

    def next_version_number(self, character_id: str) -> int:
        return self.next_sequence("character_id", character_id, "version_number")


class ShotCharacterRepository(SQLAlchemyRepository[ShotCharacter]):
    """Link rows are ephemeral state (no soft delete) — queries bypass the
    soft-delete-aware base methods (ShotCharacter has no deleted_at)."""

    model = ShotCharacter

    def list_for_shots(self, shot_ids: list[str]) -> list[ShotCharacter]:
        if not shot_ids:
            return []
        stmt = (
            select(ShotCharacter)
            .where(ShotCharacter.shot_id.in_(shot_ids))
            .order_by(ShotCharacter.created_at)
        )
        return list(self.session.scalars(stmt))

    def list_for_shot(self, shot_id: str) -> list[ShotCharacter]:
        stmt = (
            select(ShotCharacter)
            .where(ShotCharacter.shot_id == shot_id)
            .order_by(ShotCharacter.created_at)
        )
        return list(self.session.scalars(stmt))

    def delete_for_shot(self, shot_id: str) -> None:
        """Hard-delete links on replace (link rows are ephemeral state, not history)."""
        links = self.list_for_shot(shot_id)
        for link in links:
            self.session.delete(link)


class WorkflowTemplateRepository(SQLAlchemyRepository[WorkflowTemplate]):
    model = WorkflowTemplate

    def by_workflow_id(self, workflow_id: str, workflow_type: str) -> WorkflowTemplate | None:
        stmt = select(WorkflowTemplate).where(
            WorkflowTemplate.workflow_id == workflow_id,
            WorkflowTemplate.workflow_type == workflow_type,
        )
        return self.session.scalars(stmt).first()

    def list_all(self) -> list[WorkflowTemplate]:
        stmt = select(WorkflowTemplate).order_by(WorkflowTemplate.created_at)
        return list(self.session.scalars(stmt))


class WorkflowVersionRepository(SQLAlchemyRepository[WorkflowVersion]):
    model = WorkflowVersion

    def list_for_template(self, template_id: str) -> list[WorkflowVersion]:
        stmt = (
            select(WorkflowVersion)
            .where(WorkflowVersion.template_id == template_id)
            .order_by(WorkflowVersion.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def latest_for_template(self, template_id: str) -> WorkflowVersion | None:
        stmt = (
            select(WorkflowVersion)
            .where(WorkflowVersion.template_id == template_id)
            .order_by(WorkflowVersion.version_number.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()
