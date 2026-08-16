"""Continuity domain schemas (P8-T018/T019; api-event-contract §142 Continuity).

The Continuity Agent emits STRUCTURED semantic warnings (never free text). A fix is
triggered per warning and travels through the P7 Proposal system (WAITING_HUMAN),
so a human approves/rejects before any domain change is applied.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Warning lifecycle (design continuity-engine §83, §191).
WARNING_STATUS_OPEN = "open"
WARNING_STATUS_ACKNOWLEDGED = "acknowledged"
WARNING_STATUS_FIXED = "fixed"

WARNING_STATUSES = (WARNING_STATUS_OPEN, WARNING_STATUS_ACKNOWLEDGED, WARNING_STATUS_FIXED)
WARNING_SEVERITIES = ("info", "warning", "error")


class SemanticWarning(BaseModel):
    """One structured continuity warning produced by the Continuity Agent (P8-T018).

    scope=scene means it references the whole scene (no specific shot); scope=shot
    carries an optional shot_id. evidence carries a short reasoning snippet so the
    human (and the fix proposal) can reference the source facts.
    """

    scope: Literal["scene", "shot"]
    shot_id: str | None = None
    category: str = Field(default="semantic")  # costume|prop|location|time|emotion|visual_flow|action_logic|...
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    evidence: dict = Field(default_factory=dict)


class ContinuityWarningRead(BaseModel):
    """A continuity_warnings row surfaced to the frontend (api-event-contract §142)."""

    id: str
    project_id: str
    scene_id: str
    shot_id: str | None = None
    run_id: str | None = None
    category: str
    severity: str
    message: str
    evidence: dict = Field(default_factory=dict)
    status: str
    created_at: str
    resolved_at: str | None = None


class ContinuityCheckRequest(BaseModel):
    """Body for POST /agent/continuity/check (P8-T018)."""

    scene_id: str
    skip_rules: bool = False  # reserved: if true, only the LLM semantic pass runs


class ContinuityCheckResult(BaseModel):
    """Aggregate returned by a continuity_check run (202 + run_id → polled via GET)."""

    run_id: str
    scene_id: str
    warnings_created: int
    warnings: list[ContinuityWarningRead] = Field(default_factory=list)


class ContinuityFixRequest(BaseModel):
    """Body for POST /agent/continuity/fix (P8-T019, separate design).

    warning_id selects the warning to fix; patch optionally overrides the shot
    fields to change (valid update_shot keys). The shot is resolved from the
    warning; scene-scoped warnings produce a continuity (no-mutation) fix.
    """

    warning_id: str
    patch: dict = Field(default_factory=dict)


class TransitionRead(BaseModel):
    """One shot_transition row (P8-T024..T026 structure)."""

    id: str
    scene_id: str
    from_shot_id: str
    to_shot_id: str | None = None
    mode: str
    frame_from_asset_id: str | None = None
    frame_to_asset_id: str | None = None
    created_at: str
