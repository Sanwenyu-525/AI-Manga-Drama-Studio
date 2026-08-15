"""Generation DTOs (api-event-contract §35-39)."""

from pydantic import BaseModel, Field

from typing import Literal


class GenerationCreate(BaseModel):
    type: Literal["image", "video"] = "image"
    provider: str | None = None  # None → studio default (settings.image_provider)
    workflow_id: str | None = None
    prompt: str | None = None  # fallback: shot.image_prompt
    negative_prompt: str | None = None
    seed: int | None = None
    width: int | None = Field(default=None, ge=64, le=4096)
    height: int | None = Field(default=None, ge=64, le=4096)
    max_attempts: int = Field(default=1, ge=1, le=5)


class GenerationRead(BaseModel):
    id: str
    project_id: str
    shot_id: str | None
    type: str
    provider: str
    model: str | None
    workflow_id: str | None
    status: str
    progress: int
    stage: str | None
    output_asset_id: str | None
    error_message: str | None
    retry_of: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


class MediaVersionRead(BaseModel):
    id: str
    shot_id: str
    asset_id: str
    media_type: str
    version_number: int
    generation_id: str | None
    is_active: bool
    notes: str | None
    created_at: str
