"""Costume DTOs (database-v0.1 §8, api-event-contract P2-T010)."""

from pydantic import BaseModel, Field


class CostumeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    character_id: str | None = None  # optional owning character
    description: str | None = None
    visual_prompt: str | None = None
    reference_asset_id: str | None = None  # optional 参考图 asset


class CostumeUpdate(BaseModel):
    """Patch payload — every field optional; None means 'leave unchanged'."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    character_id: str | None = None
    description: str | None = None
    visual_prompt: str | None = None
    reference_asset_id: str | None = None


class CostumeUpdateRequest(BaseModel):
    """Optimistic concurrency: {revision, patch}; 409 on mismatch."""

    revision: int = Field(ge=1)
    patch: CostumeUpdate


class CostumeRead(BaseModel):
    id: str
    project_id: str
    character_id: str | None
    name: str
    description: str | None
    visual_prompt: str | None
    reference_asset_id: str | None
    revision: int
    shot_count: int = 0  # shots referencing this costume
    created_at: str
    updated_at: str
