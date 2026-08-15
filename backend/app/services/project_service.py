"""ProjectService (backend-architecture §11, mvp-spec §23, contract §103-104 bootstrap)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pathlib import Path

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.db.models import Character, Episode, Generation, Project, Scene, Shot
from app.db.models.columns import utcnow_iso
from app.events.bus import (
    EVENT_PROJECT_CREATED,
    EVENT_PROJECT_DELETED,
    EVENT_PROJECT_UPDATED,
    StudioEvent,
    bus,
)
from app.domain.project import (
    EpisodeSummary,
    ProjectBootstrapRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from app.repositories import ProjectRepository
from app.services.character_service import CharacterService


def _to_read(p: Project) -> ProjectRead:
    return ProjectRead(
        id=p.id,
        name=p.name,
        description=p.description,
        status=p.status,
        aspect_ratio=p.aspect_ratio,
        fps=p.fps,
        cover_url=f"/api/v1/projects/{p.id}/cover" if p.cover_path else None,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ProjectRepository(session)

    def create_project(self, data: ProjectCreate) -> ProjectRead:
        project = Project(
            name=data.name,
            description=data.description,
            status="draft",
            aspect_ratio=data.aspect_ratio,
            fps=data.fps,
            default_language=data.default_language,
        )
        self.repo.add(project)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_CREATED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
            )
        )
        return _to_read(project)

    def get_project(self, project_id: str) -> ProjectRead:
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        return _to_read(project)

    def list_projects(self) -> list[ProjectRead]:
        return [_to_read(p) for p in self.repo.list_ordered(order_by="created_at")]

    def update_project(self, project_id: str, data: ProjectUpdate) -> ProjectRead:
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        for field in ("name", "description", "status", "aspect_ratio", "fps", "default_language"):
            value = getattr(data, field)
            if value is not None:
                setattr(project, field, value)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_UPDATED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
            )
        )
        return _to_read(project)

    def save_cover(self, project_id: str, filename: str, content: bytes) -> ProjectRead:
        """Persist an uploaded cover image under the project directory.

        DB stores only the relative path (portable layout, database-v0.1 §38-40).
        """
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        ext = Path(filename).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            raise ValidationError("Unsupported cover format.", {"filename": filename, "supported": [".png", ".jpg", ".jpeg", ".webp", ".gif"]})
        if len(content) > 10 * 1024 * 1024:
            raise ValidationError("Cover image too large (max 10 MB).", {"bytes": len(content)})

        cover_dir = settings.data_dir / "projects" / project_id
        cover_dir.mkdir(parents=True, exist_ok=True)
        # 固定文件名：cover<ext>，覆盖旧封面（每次上传替换）
        dest = cover_dir / f"cover{ext}"
        dest.write_bytes(content)
        project.cover_path = f"cover{ext}"
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_UPDATED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
                payload={"cover": True},
            )
        )
        return _to_read(project)

    def cover_path(self, project_id: str) -> Path | None:
        """Resolve the stored cover file, if any."""
        project = self.repo.get(project_id)
        if project is None or not project.cover_path:
            return None
        path = settings.data_dir / "projects" / project_id / project.cover_path
        return path if path.exists() else None

    def delete_project(self, project_id: str) -> None:
        """Soft-delete the project and cascade to episodes / scenes / shots / characters."""
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        deleted_at = utcnow_iso()  # ISO timestamp (soft delete, database-v0.1 §41)
        project.deleted_at = deleted_at

        # cascade soft delete (project tree disappears as a unit)
        episodes = self.session.execute(
            select(Episode).where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
        ).scalars().all()
        episode_ids = [ep.id for ep in episodes]
        scenes = self.session.execute(
            select(Scene).where(
                Scene.episode_id.in_(episode_ids) if episode_ids else Scene.id == "",
                Scene.deleted_at.is_(None),
            )
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
        for episode in episodes:
            episode.deleted_at = deleted_at
        for character in self.session.execute(
            select(Character).where(Character.project_id == project_id, Character.deleted_at.is_(None))
        ).scalars().all():
            character.deleted_at = deleted_at

        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_PROJECT_DELETED,
                entity_type="project",
                entity_id=project.id,
                project_id=project.id,
            )
        )

    def bootstrap(self, project_id: str) -> ProjectBootstrapRead:
        """Workspace bootstrap (api-event-contract §103): summaries only — never full
        shots/prompts/assets (contract §104)."""
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})

        episodes = self.session.execute(
            select(Episode).where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
        ).scalars().all()
        episode_ids = [ep.id for ep in episodes]
        scene_counts: dict[str, int] = {}
        if episode_ids:
            rows = self.session.execute(
                select(Scene.episode_id, func.count(Scene.id))
                .where(Scene.episode_id.in_(episode_ids), Scene.deleted_at.is_(None))
                .group_by(Scene.episode_id)
            ).all()
            scene_counts = {episode_id: count for episode_id, count in rows}

        from app.agents.director.runner import active_run_count

        active_generations = self.session.scalar(
            select(func.count(Generation.id)).where(
                Generation.project_id == project_id,
                Generation.deleted_at.is_(None),
                Generation.status.in_(("queued", "running", "retrying")),
            )
        ) or 0

        from app.providers.registry import provider_status

        return ProjectBootstrapRead(
            project=_to_read(project),
            episodes=[
                EpisodeSummary(
                    id=ep.id,
                    episode_number=ep.episode_number,
                    title=ep.title,
                    scene_count=scene_counts.get(ep.id, 0),
                )
                for ep in episodes
            ],
            characters=CharacterService(self.session).list_summaries(project_id),
            providers=provider_status(),
            active_generations=active_generations,
            active_agent_runs=active_run_count(project_id),
        )
