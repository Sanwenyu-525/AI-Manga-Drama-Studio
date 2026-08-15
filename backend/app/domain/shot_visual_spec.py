"""ShotVisualSpec DTOs (domain-model-design #21-22, database-v0.1 §10, mvp-spec P2-T005).

A read model for the formalized visual spec. Reads prefer these fields and fall
back to the legacy inline shot columns (api-event-contract §100-102) when a shot
has no spec row yet (rows created before the shot_visual_specs migration).
"""
from pydantic import BaseModel, Field


class ShotVisualSpecRead(BaseModel):
    """Full visual spec of a shot (P2-T005). metadata carries arbitrary extras."""

    shot_id: str
    shot_type: str | None = None
    camera_angle: str | None = None
    camera_movement: str | None = None
    composition: str | None = None
    location_id: str | None = None
    lighting: str | None = None
    mood: str | None = None
    action: str | None = None
    facial_expression: str | None = None
    environment: str | None = None
    style_instructions: str | None = None
    negative_instructions: str | None = None
    metadata: dict = Field(default_factory=dict)
    present: bool = True  # False ⇒ spec row missing; read fell back to legacy columns
    created_at: str | None = None
    updated_at: str | None = None


class ShotVisualSpecUpdate(BaseModel):
    """Optional patch dedicated to spec-only fields (composition, lighting,
    facial_expression, style/negative instructions). The common framing fields
    (shot_type/camera_angle/camera_movement/action/mood) are updated through the
    shot's own ShotUpdate for API compatibility — this preserves the existing
    contract and only adds the formalized fields ShotService may forward."""

    composition: str | None = None
    lighting: str | None = None
    facial_expression: str | None = None
    environment: str | None = None
    style_instructions: str | None = None
    negative_instructions: str | None = None
    metadata: dict | None = None
