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


class CharacterCandidate(BaseModel):
    """P2-E1-T02: LLM-extracted character candidate (reviewed before creation).

    Never auto-created: the user picks create / merge / skip per candidate in
    POST /episodes/{id}/analyze/characters. Existing project characters with
    the same name are matched server-side for the merge suggestion.
    """

    name: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=500)


class CharacterCandidateRead(BaseModel):
    """Candidate + same-project name match (merge suggestion, if any)."""

    name: str
    description: str
    existing_character_id: str | None = None
    existing_character_name: str | None = None


class AnalysisPreview(BaseModel):
    """P2-E1-T01: preview response — the persisted snapshot the user reviewed.

    Confirm submits `snapshot_id`; the backend writes EXACTLY `plans` (no second
    LLM call), so what the user saw is what gets written.

    P2-E1-T02: long texts are chunked (no silent truncation) — source_chars /
    analyzed_chars / chunk_count / llm_calls make the scope and cost visible.
    """

    snapshot_id: str
    episode_id: str
    source_hash: str
    plans: list[ScenePlan]
    model: str | None = None
    status: str = "pending"
    source_chars: int = 0
    analyzed_chars: int = 0
    chunk_count: int = 1
    llm_calls: int = 1
    max_chars: int = 0
    character_candidates: list[CharacterCandidateRead] = []


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
    source_chars: int = 0
    analyzed_chars: int = 0
    chunk_count: int = 1
    llm_calls: int = 1
    max_chars: int = 0
    character_candidates: list[CharacterCandidateRead] = []


class CharacterDecision(BaseModel):
    """One per-candidate user decision (action explicit — no silent auto-create)."""

    name: str = Field(min_length=1, max_length=50)
    action: str = Field(pattern="^(create|merge|skip)$")
    character_id: str | None = None  # required for merge


class CharacterDecisionsRequest(BaseModel):
    """Apply reviewed candidate decisions against an immutable snapshot.

    Candidate names/descriptions come from the snapshot (server truth), never
    from the client — the client only picks the action per name.
    """

    snapshot_id: str
    decisions: list[CharacterDecision] = Field(max_length=50)


class CharacterDecisionResult(BaseModel):
    """Per-item outcome (batch逐项结果模式 — partial failure stays 200)."""

    name: str
    action: str
    status: str  # created | merged | skipped | conflict | failed
    character_id: str | None = None
    message: str | None = None


class CharacterDecisionsResult(BaseModel):
    episode_id: str
    results: list[CharacterDecisionResult]


class ShotPlanResult(BaseModel):
    """Result payload of a generate-shots operation."""

    scene_id: str
    shot_plans: list[ShotPlan]
    created_shot_ids: list[str]
