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
    # None → settings.generation_max_attempts (default 3); explicit 1-5 overrides.
    max_attempts: int | None = Field(default=None, ge=1, le=5)
    # M1 参考图显式覆盖：传入时替代 ShotCharacter→MASTER 自动解析，作为本条
    # generation 的参考图来源（P3 一致性预研 §5.1；缺省 = 自动解析，行为不变）。
    reference_asset_ids: list[str] | None = None


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


class ShotReferenceRead(BaseModel):
    """M1 前端闭环：镜头生成将自动注入的角色 + 场景地点参考图预览。

    GET /shots/{id}/reference-images — 与 create_generation 的自动解析
    （ShotCharacter → MASTER CharacterVersion；Scene.location_id →
    Location MASTER）完全同一逻辑，供生成面板在提交前展示；asset_id 可直接
    用于 /assets/{id}/thumbnail。角色行带 character_id/name，地点行带
    location_id/name。
    """

    character_id: str | None = None
    character_name: str | None = None
    location_id: str | None = None
    location_name: str | None = None
    version_id: str | None = None
    asset_id: str


class GenerationReferenceRead(BaseModel):
    """单条生成实际记录的参考图溯源（GET /generations/{id} 明细独有）。

    source: auto（ShotCharacter→MASTER / Scene→Location MASTER 解析）|
    explicit（调用方显式指定）。
    """

    character_id: str | None = None
    character_name: str | None = None
    location_id: str | None = None
    location_name: str | None = None
    version_id: str | None = None
    asset_id: str
    source: str = "auto"


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
    # M1 前端闭环：仅单条明细端点填充（列表端点保持 None，避免 N+1）。
    references: list[GenerationReferenceRead] | None = None


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
