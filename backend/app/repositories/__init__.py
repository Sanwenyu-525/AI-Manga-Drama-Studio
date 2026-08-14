"""Concrete repositories (Stage A: Project / Episode / Scene / Shot)."""

from app.db.models import Episode, Project, Scene, Shot
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
