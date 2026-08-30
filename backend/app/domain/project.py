"""Project DTOs (api-event-contract §9-12, §103-104)."""

from typing import Any

from pydantic import BaseModel, Field

from app.domain.character import CharacterSummary
from app.domain.common import ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    aspect_ratio: str | None = None
    fps: int | None = Field(default=None, ge=1, le=120)
    default_language: str | None = None


class ProjectUpdate(BaseModel):
    """Patch payload — every field optional; None means 'leave unchanged'."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus | None = None
    aspect_ratio: str | None = None
    fps: int | None = Field(default=None, ge=1, le=120)
    default_language: str | None = None


class ProjectUpdateRequest(BaseModel):
    """Optimistic concurrency (api-event-contract §21/§88): {revision, patch}; 409 on mismatch."""

    revision: int = Field(ge=1)
    patch: ProjectUpdate


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    aspect_ratio: str | None
    fps: int | None
    cover_url: str | None = None
    revision: int
    created_at: str
    updated_at: str


class EpisodeSummary(BaseModel):
    """Lightweight episode for bootstrap (contract §103)."""

    id: str
    episode_number: int
    title: str | None = None
    scene_count: int = 0
    # P2 pipeline probes (contract §103): real Project State, replaces the
    # frontend's per-episode GET probes (404-probing) on the workspace overview.
    has_timeline: bool = False
    has_final_video: bool = False


class ProjectBootstrapRead(BaseModel):
    """Workspace bootstrap (api-event-contract §103-104): summaries only, never full payloads."""

    project: ProjectRead
    episodes: list[EpisodeSummary]
    characters: list[CharacterSummary]
    providers: list[dict[str, Any]]
    active_generations: int
    active_agent_runs: int


# --- ProjectSetting (database-schema-design §15, domain-model-design §9) ---


class ProjectSettingRead(BaseModel):
    """Full project settings. settings_json holds unknown/extended keys verbatim."""

    project_id: str
    language: str = "zh-CN"
    default_llm_provider: str | None = None
    default_llm_model: str | None = None
    default_image_provider: str | None = None
    default_image_model: str | None = None
    default_video_provider: str | None = None
    default_video_model: str | None = None
    default_voice_provider: str | None = None
    default_voice_model: str | None = None
    default_image_workflow_id: str | None = None
    default_video_workflow_id: str | None = None
    auto_retry: int = 1
    max_retry_count: int = 3
    auto_save: int = 1
    continuity_enabled: int = 1
    auto_activate_new_generation: int = 0
    settings_json: dict[str, Any] | None = None
    updated_at: str


class ProjectSettingUpdate(BaseModel):
    """Partial settings update — unprovided fields keep their current value.
    Unknown keys are passed through into settings_json."""

    language: str | None = None
    default_llm_provider: str | None = None
    default_llm_model: str | None = None
    default_image_provider: str | None = None
    default_image_model: str | None = None
    default_video_provider: str | None = None
    default_video_model: str | None = None
    default_voice_provider: str | None = None
    default_voice_model: str | None = None
    default_image_workflow_id: str | None = None
    default_video_workflow_id: str | None = None
    auto_retry: int | None = Field(default=None, ge=0)
    max_retry_count: int | None = Field(default=None, ge=0)
    auto_save: int | None = Field(default=None, ge=0, le=1)
    continuity_enabled: int | None = Field(default=None, ge=0, le=1)
    auto_activate_new_generation: int | None = Field(default=None, ge=0, le=1)
    settings_json: dict[str, Any] | None = None
