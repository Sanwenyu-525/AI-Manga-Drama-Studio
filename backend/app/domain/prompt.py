"""Prompt DTOs (ADR-002; Alpha backend design §34-35)."""

from pydantic import BaseModel

from typing import Literal

PromptType = Literal["SHOT_IMAGE", "SHOT_VIDEO", "CHARACTER", "LOCATION", "STORYBOARD", "VOICE", "MUSIC", "DIRECTOR_INSTRUCTION", "CUSTOM"]


class PromptCreate(BaseModel):
    prompt_type: PromptType = "SHOT_IMAGE"
    positive_prompt: str | None = None
    negative_prompt: str | None = None
    generated_by: str = "user"


class PromptVersionCreate(BaseModel):
    positive_prompt: str | None = None
    negative_prompt: str | None = None
    structured_spec: dict | None = None
    provider: str | None = None
    model: str | None = None
    generated_by: str = "user"


class PromptRead(BaseModel):
    id: str
    project_id: str
    target_type: str
    target_id: str
    prompt_type: str
    active_version_id: str | None
    versions_count: int
    created_at: str
    updated_at: str


class PromptVersionRead(BaseModel):
    id: str
    prompt_id: str
    version_number: int
    positive_prompt: str | None
    negative_prompt: str | None
    structured_spec: dict | None = None
    provider: str | None
    model: str | None
    generated_by: str | None
    parent_version_id: str | None
    created_at: str
    is_active: bool = False
