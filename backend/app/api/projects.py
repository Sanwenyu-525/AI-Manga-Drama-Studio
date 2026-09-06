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
    ProjectSettingRead,
    ProjectSettingUpdate,
    ProjectUpdateRequest,
    TrashItem,
)
from app.domain.readiness import ReadinessRead
from app.services import ProjectReadinessService, ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService(db).create_project(data)


@router.get("", response_model=list[ProjectRead])
def list_projects(
    include_deleted: bool = False, db: Session = Depends(get_db)
) -> list[ProjectRead]:
    """Live projects by default; ?include_deleted=true appends trash rows (P2-E2-T01)."""
    return ProjectService(db).list_projects(include_deleted=include_deleted)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService(db).get_project(project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    data: ProjectUpdateRequest,
    db: Session = Depends(get_db),
) -> ProjectRead:
    return ProjectService(db).update_project(project_id, data.revision, data.patch)


@router.get("/{project_id}/settings", response_model=ProjectSettingRead)
def get_settings(project_id: str, db: Session = Depends(get_db)) -> ProjectSettingRead:
    """Project generation/config defaults (database-schema-design §15)."""
    return ProjectService(db).get_settings(project_id)


@router.put("/{project_id}/settings", response_model=ProjectSettingRead)
def update_settings(
    project_id: str,
    data: ProjectSettingUpdate,
    db: Session = Depends(get_db),
) -> ProjectSettingRead:
    """Partial settings update — unprovided fields keep their current value;
    unknown keys are forwarded into settings_json."""
    return ProjectService(db).update_settings(project_id, data)


@router.get("/{project_id}/bootstrap", response_model=ProjectBootstrapRead)
def get_bootstrap(project_id: str, db: Session = Depends(get_db)) -> ProjectBootstrapRead:
    """Workspace bootstrap (api-event-contract §103-104): summaries only."""
    return ProjectService(db).bootstrap(project_id)


@router.get("/{project_id}/readiness", response_model=ReadinessRead)
def get_readiness(project_id: str, db: Session = Depends(get_db)) -> ReadinessRead:
    """生产就绪度（自主迭代 04，契约 §103.1）：角色 MASTER 覆盖 / 场景地点绑定覆盖 /
    开放连续性警告——一致性缺口在生成前可见。确定性聚合、只读、无 LLM。"""
    return ProjectReadinessService(db).readiness(project_id)


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


@router.post("/{project_id}/restore", response_model=ProjectRead)
def restore_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    """P2-E2-T01: restore a soft-deleted project + its cascade set (same-timestamp rows only)."""
    return ProjectService(db).restore_project(project_id)


@router.get("/{project_id}/trash", response_model=list[TrashItem])
def get_trash(project_id: str, db: Session = Depends(get_db)) -> list[TrashItem]:
    """P2-E2-T01: soft-deleted episode/scene/shot/character rows for review + restore."""
    return ProjectService(db).get_trash(project_id)
