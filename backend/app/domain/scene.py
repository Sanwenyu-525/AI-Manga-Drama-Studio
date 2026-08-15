"""Scene DTOs (api-event-contract §16-17)."""

from pydantic import BaseModel, Field

from app.domain.common import SceneStatus


class SceneCreate(BaseModel):
    name: str | None = None
    scene_number: int | None = Field(default=None, ge=1)
    location_id: str | None = None  # free-text location (locations table is Phase 2)
    time_of_day: str | None = None
    lighting: str | None = None
    weather: str | None = None
    mood: str | None = None
    description: str | None = None


class SceneUpdate(BaseModel):
    """Patch payload — every field optional; None means 'leave unchanged'."""

    name: str | None = None
    location_id: str | None = None
    time_of_day: str | None = None
    lighting: str | None = None
    weather: str | None = None
    mood: str | None = None
    description: str | None = None
    status: SceneStatus | None = None


class SceneUpdateRequest(BaseModel):
    """Optimistic concurrency (api-event-contract §21/§88): {revision, patch}; 409 on mismatch."""

    revision: int = Field(ge=1)
    patch: SceneUpdate


class SceneSummary(BaseModel):
    id: str
    scene_number: int
    name: str | None


class SceneRead(SceneSummary):
    episode_id: str
    location_id: str | None
    time_of_day: str | None
    lighting: str | None
    weather: str | None
    mood: str | None
    description: str | None
    scene_order: int | None
    status: str
    shot_count: int = 0
    revision: int
    created_at: str
    updated_at: str
