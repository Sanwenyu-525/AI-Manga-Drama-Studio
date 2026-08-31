"""Generation DTOs (api-event-contract §35-39)."""

from pydantic import BaseModel, Field

from typing import Literal


class GenerationCreate(BaseModel):
    type: Literal["image", "video"] = "image"
    provider: str | None = None  # None → studio default (settings.image_provider)
    workflow_id: str | None = None
    prompt: str | None = None  # fallback: shot.image_prompt
    negative_prompt: str | None = None
    seed: int | None = None
    width: int | None = Field(default=None, ge=64, le=4096)
    height: int | None = Field(default=None, ge=64, le=4096)
    seconds: int | None = Field(default=None, ge=4, le=12)  # 视频时长（agnes 4-12s）
    max_attempts: int = Field(default=1, ge=1, le=5)


class VoiceoverGenerateRequest(BaseModel):
    """TASK-012: queue a type="audio" voiceover generation for a timeline clip.

    text=None/blank → the clip's own text is used (PATCH /timeline-clips/{id}).
    provider=None → studio default (settings.audio_provider).
    """

    text: str | None = Field(default=None, max_length=4000)
    provider: str | None = None
    voice: str | None = None
    rate: str | None = None  # e.g. "+10%" / "-5%"


class VoiceoverBatchItem(BaseModel):
    """One successfully queued voiceover inside a batch (C1 整轨批量配音)."""

    clip_id: str
    generation_id: str
    text_head: str | None = None


class VoiceoverBatchResult(BaseModel):
    """Batch result of POST /timelines/{id}/generate-voiceovers (C1).

    submitted: clips that got a new type="audio" generation queued.
    skipped_no_text: VOICE clips without text (clip.text blank).
    already_bound: VOICE clips already bound to an AUDIO asset (won't re-generate).
    """

    timeline_id: str
    submitted: list[VoiceoverBatchItem] = Field(default_factory=list)
    skipped_no_text: list[str] = Field(default_factory=list)
    already_bound: list[str] = Field(default_factory=list)


class GenerationRead(BaseModel):
    id: str
    project_id: str
    shot_id: str | None
    type: str
    provider: str
    model: str | None
    workflow_id: str | None
    prompt_version_id: str | None = None  # ADR-002
    status: str
    progress: int
    stage: str | None
    output_asset_id: str | None
    error_message: str | None
    retry_of: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


class AssetVersionRead(BaseModel):
    """Asset-backed version row (ADR-001): id == asset_id for back-compat."""

    id: str  # asset id (activate endpoints accept it)
    shot_id: str
    asset_id: str
    media_type: str  # image | video (derived from version group purpose)
    version_number: int
    generation_id: str | None
    is_active: bool
    status: str
    notes: str | None = None  # legacy field kept for frontend compat
    created_at: str
