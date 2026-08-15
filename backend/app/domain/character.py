"""Character DTOs (database-v0.1 §7, api-event-contract §20/§88: revision + soft delete)."""

from pydantic import BaseModel, Field


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    alias: str | None = None
    gender: str | None = None
    age_description: str | None = None
    appearance: str | None = None
    personality: str | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    status: str = "active"


class CharacterUpdate(BaseModel):
    """Patch payload — every field optional; None means 'leave unchanged'."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    alias: str | None = None
    gender: str | None = None
    age_description: str | None = None
    appearance: str | None = None
    personality: str | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    status: str | None = None


class CharacterUpdateRequest(BaseModel):
    """Optimistic concurrency (api-event-contract §21/§88): {revision, patch}; 409 on mismatch."""

    revision: int = Field(ge=1)
    patch: CharacterUpdate


class CharacterSummary(BaseModel):
    """Lightweight character for trees / bootstrap (api-event-contract §103)."""

    id: str
    name: str
    alias: str | None = None
    status: str = "active"


class CharacterRead(BaseModel):
    id: str
    project_id: str
    name: str
    alias: str | None
    gender: str | None
    age_description: str | None
    appearance: str | None
    personality: str | None
    visual_prompt: str | None
    negative_prompt: str | None
    default_costume_id: str | None
    status: str
    revision: int
    shot_count: int = 0  # shots currently referencing this character
    master_version_id: str | None = None  # P2-T008: authoritative MASTER pointer
    created_at: str
    updated_at: str


class CharacterVersionCreate(BaseModel):
    """Create a new character visual version (P2-T007).

    asset_id must reference a live Asset that belongs to the same project as the
    character (the representative/参考 image for this visual version).
    """

    asset_id: str
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class CharacterVersionRead(BaseModel):
    """Character visual version DTO (api-event-contract §20 / P2-T007)."""

    id: str
    character_id: str
    version_number: int
    asset_id: str
    name: str | None
    description: str | None
    status: str  # active | stale | archived
    checksum: str | None
    is_master: bool = False  # True when this is the character's MASTER pointer target
    created_at: str
    updated_at: str
