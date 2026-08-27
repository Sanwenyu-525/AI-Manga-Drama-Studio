"""Prompt API (ADR-002; Alpha backend design §34)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.domain.prompt import PromptCreate, PromptRead, PromptVersionCreate, PromptVersionRead
from app.services.prompt_service import PROJECT_TARGET, PromptService

router = APIRouter(tags=["prompts"])


def _prompt_read(p, version_count: int = 0) -> PromptRead:
    return PromptRead(
        id=p.id,
        project_id=p.project_id,
        target_type=p.target_type,
        target_id=p.target_id,
        prompt_type=p.prompt_type,
        active_version_id=p.active_version_id,
        versions_count=version_count,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _version_read(v, active_version_id: str | None = None) -> PromptVersionRead:
    import json

    spec = None
    if v.structured_spec_json:
        try:
            spec = json.loads(v.structured_spec_json)
        except ValueError:
            spec = None
    return PromptVersionRead(
        id=v.id,
        prompt_id=v.prompt_id,
        version_number=v.version_number,
        positive_prompt=v.positive_prompt,
        negative_prompt=v.negative_prompt,
        structured_spec=spec,
        provider=v.provider,
        model=v.model,
        generated_by=v.generated_by,
        parent_version_id=v.parent_version_id,
        created_at=v.created_at,
        is_active=v.id == active_version_id,
    )


@router.get("/shots/{shot_id}/prompts", response_model=list[PromptRead])
def list_shot_prompts(shot_id: str, db: Session = Depends(get_db)) -> list[PromptRead]:
    service = PromptService(db)
    prompts = service.list_shot_prompts(shot_id)
    return [_prompt_read(p, len(service.list_versions(p.id))) for p in prompts]


@router.post("/shots/{shot_id}/prompts", response_model=PromptVersionRead, status_code=status.HTTP_201_CREATED)
def create_shot_prompt(shot_id: str, data: PromptCreate, db: Session = Depends(get_db)) -> PromptVersionRead:
    from app.repositories import ShotRepository

    shot = ShotRepository(db).get(shot_id)
    if shot is None:
        raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
    service = PromptService(db)
    version = service.create_version(
        project_id=_project_id_of(db, shot),
        target_type="SHOT",
        target_id=shot_id,
        prompt_type=data.prompt_type,
        positive=data.positive_prompt,
        negative=data.negative_prompt,
        generated_by=data.generated_by,
    )
    return _version_read(version, version.id)


@router.get("/prompts/{prompt_id}/versions", response_model=list[PromptVersionRead])
def list_prompt_versions(prompt_id: str, db: Session = Depends(get_db)) -> list[PromptVersionRead]:
    service = PromptService(db)
    prompt = service.get_prompt_by_id(prompt_id)
    return [_version_read(v, prompt.active_version_id) for v in service.list_versions(prompt_id)]


@router.post("/prompts/{prompt_id}/versions", response_model=PromptVersionRead, status_code=status.HTTP_201_CREATED)
def create_prompt_version(prompt_id: str, data: PromptVersionCreate, db: Session = Depends(get_db)) -> PromptVersionRead:
    service = PromptService(db)
    prompt = service.get_prompt_by_id(prompt_id)
    version = service.create_version(
        project_id=prompt.project_id,
        target_type=prompt.target_type,
        target_id=prompt.target_id,
        prompt_type=prompt.prompt_type,
        positive=data.positive_prompt,
        negative=data.negative_prompt,
        structured_spec=data.structured_spec,
        provider=data.provider,
        model=data.model,
        generated_by=data.generated_by,
    )
    return _version_read(version, version.id)


@router.post("/prompts/{prompt_id}/versions/{version_id}/activate", response_model=PromptVersionRead)
def activate_prompt_version(prompt_id: str, version_id: str, db: Session = Depends(get_db)) -> PromptVersionRead:
    service = PromptService(db)
    version = service.activate_version(version_id)
    return _version_read(version, version.id)


def _ensure_project(db: Session, project_id: str) -> None:
    from app.repositories import ProjectRepository

    if ProjectRepository(db).get(project_id) is None:
        raise NotFoundError("Project does not exist.", {"project_id": project_id})


# --- 提示词库：项目级预设（target_type=PROJECT），复用 prompts 领域模型 ---

@router.get("/projects/{project_id}/prompts", response_model=list[PromptRead])
def list_project_prompts(project_id: str, db: Session = Depends(get_db)) -> list[PromptRead]:
    _ensure_project(db, project_id)
    service = PromptService(db)
    result: list[PromptRead] = []
    for p in service.list_project_presets(project_id):
        active = service.get_active_version(p) if p.active_version_id else None
        result.append(
            _prompt_read(p, len(service.list_versions(p.id))).model_copy(
                update={
                    "active_positive_prompt": active.positive_prompt if active else None,
                    "active_negative_prompt": active.negative_prompt if active else None,
                }
            )
        )
    return result


@router.post("/projects/{project_id}/prompts", response_model=PromptVersionRead, status_code=status.HTTP_201_CREATED)
def create_project_preset(project_id: str, data: PromptCreate, db: Session = Depends(get_db)) -> PromptVersionRead:
    _ensure_project(db, project_id)
    service = PromptService(db)
    version = service.create_version(
        project_id=project_id,
        target_type=PROJECT_TARGET,
        target_id=project_id,
        prompt_type=data.prompt_type,
        positive=data.positive_prompt,
        negative=data.negative_prompt,
        generated_by=data.generated_by,
    )
    return _version_read(version, version.id)


@router.delete("/prompts/{prompt_id}", status_code=status.HTTP_200_OK)
def delete_prompt(prompt_id: str, db: Session = Depends(get_db)) -> dict:
    PromptService(db).delete_prompt(prompt_id)
    return {"deleted": True}


def _project_id_of(db: Session, shot) -> str:
    from app.db.models import Episode, Scene

    scene = db.get(Scene, shot.scene_id) if shot else None
    if scene is None:
        return ""
    episode = db.get(Episode, scene.episode_id)
    return episode.project_id if episode else ""
