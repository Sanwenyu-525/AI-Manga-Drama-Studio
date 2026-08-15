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
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus | None = None
    aspect_ratio: str | None = None
    fps: int | None = Field(default=None, ge=1, le=120)
    default_language: str | None = None


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    aspect_ratio: str | None
    fps: int | None
    cover_url: str | None = None
    created_at: str
    updated_at: str


class EpisodeSummary(BaseModel):
    """Lightweight episode for bootstrap (contract §103)."""

    id: str
    episode_number: int
    title: str | None = None
    scene_count: int = 0


class ProjectBootstrapRead(BaseModel):
    """Workspace bootstrap (api-event-contract §103-104): summaries only, never full payloads."""

    project: ProjectRead
    episodes: list[EpisodeSummary]
    characters: list[CharacterSummary]
    providers: list[dict[str, Any]]
    active_generations: int
    active_agent_runs: int
