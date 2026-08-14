"""Project DTOs (api-event-contract §9-12)."""

from pydantic import BaseModel, Field

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
    created_at: str
    updated_at: str
