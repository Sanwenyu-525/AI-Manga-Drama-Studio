"""Continuity DTOs (api-event-contract §142 P8; continuity-engine-design §176-177).

These shape the JSON returned by the three Phase-8 endpoints:
  GET  /api/v1/scenes/{id}/continuity        → SceneContinuityRead
  GET  /api/v1/shots/{id}/continuity-state   → ShotContinuityRead
  POST /api/v1/scenes/{id}/continuity/recompute → ContinuityRecomputeRead

The nested state dicts mirror the canonical JSON stored in the *_json columns:
  EnvironmentState {location_id, time_of_day, lighting, weather, mood}
  CharacterState   {character_id, character_version_id, costume_id, position,
                    orientation, action, emotion, physical}
  PropState        {prop_id, holder_character_id, visible, position}

Warnings are returned in the canonical warning shape:
  {code, category, severity, message, shot_id, source}
"""

from typing import Any

from pydantic import BaseModel, Field


class ContinuityWarning(BaseModel):
    """A single rule-engine warning (continuity-engine-design §81-84)."""

    code: str
    category: str
    severity: str = "WARNING"
    message: str
    shot_id: str | None = None
    source: str = "RULE"


class ShotContinuityRead(BaseModel):
    """Per-shot continuity state + warnings (api-event-contract §177)."""

    shot_id: str
    shot_number: int
    start_state: dict[str, Any] = Field(default_factory=dict)
    end_state: dict[str, Any] = Field(default_factory=dict)
    delta: dict[str, Any] = Field(default_factory=dict)
    state_hash: str = ""
    warnings: list[ContinuityWarning] = Field(default_factory=list)


class SceneContinuityRead(BaseModel):
    """Scene Continuity view (design §173): base state + one entry per shot."""

    scene_id: str
    base_state: dict[str, Any] = Field(default_factory=dict)
    base_state_hash: str = ""
    shots: list[ShotContinuityRead] = Field(default_factory=list)


class ContinuityRecomputeRead(BaseModel):
    """Result of a recompute (POST /scenes/{id}/continuity/recompute)."""

    scene_id: str
    recomputed_from: str | None = None
    recomputed_shots: int = 0
    total_shots: int = 0
    state_hash: str = ""
