"""Project API (api-event-contract §9-12, mvp-spec §32)."""

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
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


@router.post("/{project_id}/cover", response_model=ProjectRead)
async def upload_cover(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ProjectRead:
    """Upload/replace the project cover image (multipart; stored under the project dir)."""
    service = ProjectService(db)
    content = await file.read()
    return service.save_cover(project_id, file.filename or "cover.png", content)


@router.get("/{project_id}/cover")
def get_cover(project_id: str, db: Session = Depends(get_db)) -> FileResponse:
    path = ProjectService(db).cover_path(project_id)
    if path is None:
        raise NotFoundError("Project cover does not exist.", {"project_id": project_id})
    return FileResponse(path)


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    """Soft-delete the project and its episode/scene/shot/character tree."""
    ProjectService(db).delete_project(project_id)
    return {"id": project_id, "deleted": True}
