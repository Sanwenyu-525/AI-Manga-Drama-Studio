"""SceneService (backend-architecture §13, mvp-spec §25)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Episode, Scene, Shot
from app.domain.scene import SceneCreate, SceneRead, SceneUpdate
from app.events.bus import EVENT_SCENE_CREATED, EVENT_SCENE_DELETED, EVENT_SCENE_UPDATED, StudioEvent, bus
from app.repositories import EpisodeRepository, SceneRepository


def _to_read(scene: Scene, shot_count: int = 0) -> SceneRead:
    return SceneRead(
        id=scene.id,
        scene_number=scene.scene_number,
        name=scene.name,
        episode_id=scene.episode_id,
        location_id=scene.location_id,
        time_of_day=scene.time_of_day,
        lighting=scene.lighting,
        weather=scene.weather,
        mood=scene.mood,
        description=scene.description,
        scene_order=scene.scene_order,
        status=scene.status,
        shot_count=shot_count,
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )


class SceneService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SceneRepository(session)
        self.episodes = EpisodeRepository(session)

    def create_scene(self, episode_id: str, data: SceneCreate) -> SceneRead:
        """Create ONE scene; commits and publishes scene.created (manual/API path)."""
        scene = self.create_scenes(episode_id, [data])[0]
        self.session.commit()
        episode = self.episodes.get(episode_id)
        bus.publish(
            StudioEvent(
                event_type=EVENT_SCENE_CREATED,
                entity_type="scene",
                entity_id=scene.id,
                project_id=episode.project_id if episode else None,
            )
        )
        return _to_read(scene)

    def create_scenes(
        self,
        episode_id: str,
        datas: list[SceneCreate],
        analysis_key: str | None = None,
    ) -> list[Scene]:
        """Batch create WITHOUT committing (P1-E1-T01: caller owns the transaction).

        All-or-nothing: any error raises before commit; the caller rolls back and
        nothing is persisted. analysis_key marks AI-created scenes (replace policy).
        """
        episode = self.episodes.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        created: list[Scene] = []
        for data in datas:
            scene_number = data.scene_number or self.repo.next_scene_number(episode_id)
            scene = Scene(
                episode_id=episode_id,
                scene_number=scene_number,
                scene_order=scene_number,
                name=data.name,
                location_id=data.location_id,
                time_of_day=data.time_of_day,
                lighting=data.lighting,
                weather=data.weather,
                mood=data.mood,
                description=data.description,
                analysis_key=analysis_key,
                status="draft",
            )
            self.repo.add(scene)
            created.append(scene)
        return created

    def soft_delete_scenes(self, scene_ids: list[str]) -> None:
        """Soft-delete scenes WITHOUT committing (P1-E1-T01: caller owns the transaction)."""
        if not scene_ids:
            return
        scenes = self.session.scalars(
            select(Scene).where(Scene.id.in_(scene_ids), Scene.deleted_at.is_(None))
        )
        for scene in scenes:
            self.repo.delete(scene)

    def get_scene(self, scene_id: str) -> SceneRead:
        scene = self.repo.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        return _to_read(scene, shot_count=self._count_shots(scene_id))

    def list_scenes(self, episode_id: str) -> list[SceneRead]:
        episode = self.episodes.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        scenes = self.repo.list_ordered(order_by="scene_number", episode_id=episode_id)
        counts = self._shot_counts([s.id for s in scenes])
        return [_to_read(s, counts.get(s.id, 0)) for s in scenes]

    def update_scene(self, scene_id: str, data: SceneUpdate) -> SceneRead:
        scene = self.repo.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        episode = self.episodes.get(scene.episode_id)
        for field in ("name", "location_id", "time_of_day", "lighting", "weather", "mood", "description", "status"):
            value = getattr(data, field)
            if value is not None:
                setattr(scene, field, value)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_SCENE_UPDATED,
                entity_type="scene",
                entity_id=scene.id,
                project_id=episode.project_id if episode else None,
            )
        )
        return _to_read(scene, shot_count=self._count_shots(scene_id))

    def delete_scene(self, scene_id: str) -> None:
        scene = self.repo.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        self.repo.delete(scene)  # soft delete
        self.session.commit()
        episode = self.session.get(Episode, scene.episode_id)
        bus.publish(
            StudioEvent(
                event_type=EVENT_SCENE_DELETED,
                entity_type="scene",
                entity_id=scene.id,
                project_id=episode.project_id if episode else None,
            )
        )

    def _count_shots(self, scene_id: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Shot).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None))
        ) or 0

    def _shot_counts(self, scene_ids: list[str]) -> dict[str, int]:
        if not scene_ids:
            return {}
        rows = self.session.execute(
            select(Shot.scene_id, func.count())
            .where(Shot.scene_id.in_(scene_ids), Shot.deleted_at.is_(None))
            .group_by(Shot.scene_id)
        ).all()
        return {scene_id: count for scene_id, count in rows}
