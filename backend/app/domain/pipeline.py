"""Pipeline DTOs (C2 一键成片, api-event-contract §15.1, mvp-spec DOC-C2).

stages maps stage name → "done"|"pending"; status drives the UI:
- running:      an execution is in flight (images queued etc.)
- waiting_confirm: analysis preview done, waiting for the user to confirm plans
- completed:    all five stages done (final video render queued)
- failed:       a stage raised (details in error_message)
"""

from pydantic import BaseModel, Field

from app.domain.analysis import ScenePlan

PIPELINE_STAGES = ("analyze", "shots", "images", "timeline", "render")


class PipelineRead(BaseModel):
    id: str
    episode_id: str
    project_id: str
    status: str  # running | waiting_confirm | completed | failed
    current_stage: str | None
    stages: dict[str, str] = Field(default_factory=dict)
    snapshot_id: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class PipelineRunRead(BaseModel):
    """Response of run/confirm/finalize/resume — the pipeline + what the user needs.

    plans is present while waiting_confirm (the reviewed scene plan list).
    pending_shot_ids is present right after confirm (shots queued for images).
    """

    pipeline: PipelineRead
    plans: list[ScenePlan] | None = None
    pending_shot_ids: list[str] = Field(default_factory=list)


__all__ = [
    "PIPELINE_STAGES",
    "PipelineRead",
    "PipelineRunRead",
]
