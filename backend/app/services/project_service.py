"""ProjectService (backend-architecture §11, mvp-spec §23)."""

from sqlalchemy.orm import Session

from app.db.models import Project
from app.domain.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.core.errors import NotFoundError
from app.events.bus import EVENT_PROJECT_CREATED, EVENT_PROJECT_UPDATED, StudioEvent, bus
from app.repositories import ProjectRepository


def _to_read(p: Project) -> ProjectRead:
    return ProjectRead(
        id=p.id,
        name=p.name,
        description=p.description,
        status=p.status,
        aspect_ratio=p.aspect_ratio,
        fps=p.fps,
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
