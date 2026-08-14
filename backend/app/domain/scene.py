"""Scene DTOs (api-event-contract §16-17)."""

from pydantic import BaseModel, Field

from app.domain.common import SceneStatus


class SceneCreate(BaseModel):
    name: str | None = None
    scene_number: int | None = Field(default=None, ge=1)
    time_of_day: str | None = None
    lighting: str | None = None
    weather: str | None = None
    mood: str | None = None
    description: str | None = None


class SceneUpdate(BaseModel):
    name: str | None = None
    time_of_day: str | None = None
    lighting: str | None = None
    weather: str | None = None
    mood: str | None = None
    description: str | None = None
    status: SceneStatus | None = None


class SceneSummary(BaseModel):
    id: str
    scene_number: int
    name: str | None


class SceneRead(SceneSummary):
    episode_id: str
    time_of_day: str | None
    lighting: str | None
    weather: str | None
    mood: str | None
    description: str | None
    scene_order: int | None
    status: str
    shot_count: int = 0
    created_at: str
    updated_at: str
