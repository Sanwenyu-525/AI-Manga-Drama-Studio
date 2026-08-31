"""Stage B AI schemas — the data contract between LLM and Studio Domain (backend-architecture §19).

Pydantic models are used as structured output schemas for the LLM gateway, then
persisted via Application Services (ScriptService / ShotService).
"""

from pydantic import BaseModel, Field

from app.domain.common import ShotType


class ScenePlan(BaseModel):
    """LLM output for episode analysis (mvp-spec §56)."""

    scene_number: int = Field(ge=1)
    title: str
    location: str
    time: str | None = None  # time of day / temporal marker
    description: str
    mood: str | None = None


class ShotPlan(BaseModel):
    """LLM output for storyboard planning (mvp-spec §57, agent-director §18)."""

    shot_number: int = Field(ge=1)
    shot_type: ShotType
    camera_angle: str | None = None
    camera_movement: str | None = None
    duration: float = Field(default=3.0, gt=0, le=30)
    action: str
    emotion: str | None = None
    dialogue: str | None = None
    image_prompt: str | None = None


class AnalysisResult(BaseModel):
    """Result payload of an episode analysis operation."""

    episode_id: str
    scene_plans: list[ScenePlan]
    created_scene_ids: list[str]


class AnalysisPreview(BaseModel):
    """P2-E1-T01: preview response — the persisted snapshot the user reviewed.

    Confirm submits `snapshot_id`; the backend writes EXACTLY `plans` (no second
    LLM call), so what the user saw is what gets written.
    """

    snapshot_id: str
    episode_id: str
    source_hash: str
    plans: list[ScenePlan]
    model: str | None = None
    status: str = "pending"


class SnapshotRead(BaseModel):
    """Snapshot retrieval (refresh rehydration / audit)."""

    id: str
    episode_id: str
    source_hash: str
    episode_revision: int
    status: str
    plans: list[ScenePlan]
    model: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    created_scene_ids: list[str] = []
    created_at: str


class ShotPlanResult(BaseModel):
    """Result payload of a generate-shots operation."""

    scene_id: str
    shot_plans: list[ShotPlan]
    created_shot_ids: list[str]
