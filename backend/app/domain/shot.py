"""Shot DTOs (api-event-contract §19-21, §100-102)."""

from pydantic import BaseModel, Field

from app.domain.common import DirtyState, ShotStatus, ShotType
from app.domain.scene import SceneSummary


class ShotCreate(BaseModel):
    shot_number: int | None = Field(default=None, ge=1)  # auto-assigned if omitted
    shot_type: ShotType = "medium"
    camera_angle: str | None = None
    camera_movement: str | None = None
    lens: str | None = None
    duration: float | None = Field(default=None, gt=0)
    action: str | None = None
    emotion: str | None = None
    dialogue: str | None = None
    image_prompt: str | None = None


class ShotUpdate(BaseModel):
    """Patch payload for a single mutation (api-event-contract §21: {revision, patch})."""

    shot_type: ShotType | None = None
    camera_angle: str | None = None
    camera_movement: str | None = None
    lens: str | None = None
    duration: float | None = Field(default=None, gt=0)
    action: str | None = None
    emotion: str | None = None
    dialogue: str | None = None
    image_prompt: str | None = None
    status: ShotStatus | None = None
    dirty_state: DirtyState | None = None


class ShotUpdateRequest(BaseModel):
    """Optimistic concurrency: client sends the revision it based its edit on (409 on mismatch)."""

    revision: int = Field(ge=1)
    patch: ShotUpdate


class ShotSummary(BaseModel):
    """Lightweight shot for storyboard grids (api-event-contract §100)."""

    id: str
    shot_number: int
    shot_type: str
    duration: float | None
    status: str
    dirty_state: str
    thumbnail_url: str | None = None
    character_names: list[str] = Field(default_factory=list)
    active_generation: dict | None = None


class ShotRead(BaseModel):
    id: str
    scene_id: str
    shot_number: int
    shot_order: int
    shot_type: str
    camera_angle: str | None
    camera_movement: str | None
    lens: str | None
    duration: float | None
    action: str | None
    emotion: str | None
    dialogue: str | None
    image_prompt: str | None
    status: str
    dirty_state: str
    revision: int
    created_at: str
    updated_at: str


class StoryboardRead(BaseModel):
    """Aggregate endpoint payload (api-event-contract §101-102): scene + shot summaries."""

    scene: SceneSummary
    shots: list[ShotSummary]
