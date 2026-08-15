"""Location + LocationVersion DTOs (database-v0.1 §6, api-event-contract P2-T009)."""

from pydantic import BaseModel, Field


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    visual_prompt: str | None = None
    status: str = "active"


class LocationUpdate(BaseModel):
    """Patch payload — every field optional; None means 'leave unchanged'."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    visual_prompt: str | None = None
    status: str | None = None


class LocationUpdateRequest(BaseModel):
    """Optimistic concurrency: {revision, patch}; 409 on mismatch."""

    revision: int = Field(ge=1)
    patch: LocationUpdate


class LocationRead(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    visual_prompt: str | None
    status: str
    revision: int
    master_version_id: str | None = None  # P2-T009: authoritative MASTER pointer
    created_at: str
    updated_at: str


class LocationVersionCreate(BaseModel):
    """Create a new location visual version (P2-T009).

    asset_id must reference a live Asset that belongs to the same project as the
    location (the representative / 参考 image for this visual version).
    """

    asset_id: str
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class LocationVersionRead(BaseModel):
    """Location visual version DTO (P2-T009)."""

    id: str
    location_id: str
    version_number: int
    asset_id: str
    name: str | None
    description: str | None
    status: str  # active | stale | archived
    checksum: str | None
    is_master: bool = False  # True when this is the location's MASTER pointer target
    created_at: str
    updated_at: str
