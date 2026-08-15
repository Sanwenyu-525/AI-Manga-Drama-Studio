"""EpisodeService (backend-architecture §12, mvp-spec §24)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Episode, Scene, Shot
from app.db.models.columns import utcnow_iso
from app.domain.episode import EpisodeCreate, EpisodeRead, EpisodeUpdate
from app.events.bus import (
    EVENT_EPISODE_CREATED,
    EVENT_EPISODE_DELETED,
    EVENT_EPISODE_UPDATED,
    StudioEvent,
    bus,
)
from app.repositories import EpisodeRepository, ProjectRepository


def _to_read(e: Episode) -> EpisodeRead:
    return EpisodeRead(
        id=e.id,
        project_id=e.project_id,
        episode_number=e.episode_number,
        title=e.title,
        source_text=e.source_text,
        script_text=e.script_text,
        summary=e.summary,
        status=e.status,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


class EpisodeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = EpisodeRepository(session)
        self.projects = ProjectRepository(session)

    def create_episode(self, project_id: str, data: EpisodeCreate) -> EpisodeRead:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        episode_number = self.repo.next_episode_number(project_id)
        episode = Episode(
            project_id=project_id,
            episode_number=episode_number,
            title=data.title or f"Episode {episode_number}",
            source_text=data.source_text,
            status="draft",
        )
        self.repo.add(episode)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_EPISODE_CREATED,
                entity_type="episode",
                entity_id=episode.id,
                project_id=project_id,
            )
        )
        return _to_read(episode)

    def get_episode(self, episode_id: str) -> EpisodeRead:
        episode = self.repo.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        return _to_read(episode)

    def list_episodes(self, project_id: str) -> list[EpisodeRead]:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        return [_to_read(e) for e in self.repo.list_ordered(order_by="episode_number", project_id=project_id)]

    def update_episode(self, episode_id: str, data: EpisodeUpdate) -> EpisodeRead:
        episode = self.repo.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        for field in ("title", "source_text", "script_text", "summary", "status"):
            value = getattr(data, field)
            if value is not None:
                setattr(episode, field, value)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_EPISODE_UPDATED,
                entity_type="episode",
                entity_id=episode.id,
                project_id=episode.project_id,
            )
        )
        return _to_read(episode)

    def delete_episode(self, episode_id: str) -> None:
        """Soft-delete the episode and cascade to its scenes and shots."""
        episode = self.repo.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        deleted_at = utcnow_iso()
        episode.deleted_at = deleted_at

        scenes = self.session.execute(
            select(Scene).where(Scene.episode_id == episode_id, Scene.deleted_at.is_(None))
        ).scalars().all()
        scene_ids = [sc.id for sc in scenes]
        if scene_ids:
            shots = self.session.execute(
                select(Shot).where(Shot.scene_id.in_(scene_ids), Shot.deleted_at.is_(None))
            ).scalars().all()
            for shot in shots:
                shot.deleted_at = deleted_at
        for scene in scenes:
            scene.deleted_at = deleted_at

        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_EPISODE_DELETED,
                entity_type="episode",
                entity_id=episode.id,
                project_id=episode.project_id,
            )
        )
