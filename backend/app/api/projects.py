"""Project API (api-event-contract §9-12, mvp-spec §32)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.project import (
    ProjectBootstrapRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from app.services import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService(db).create_project(data)


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    return ProjectService(db).list_projects()


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService(db).get_project(project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService(db).update_project(project_id, data)


@router.get("/{project_id}/bootstrap", response_model=ProjectBootstrapRead)
def get_bootstrap(project_id: str, db: Session = Depends(get_db)) -> ProjectBootstrapRead:
    """Workspace bootstrap (api-event-contract §103-104): summaries only."""
    return ProjectService(db).bootstrap(project_id)
