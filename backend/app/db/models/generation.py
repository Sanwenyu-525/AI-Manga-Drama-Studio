"""Generation model (database-v0.1 §16, mvp-spec §20): one row per model call.

The table is the persisted queue: worker claims status IN ('queued','retrying').
Generations never overwrite history; retry creates a new row (retry_of).
"""

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, uuid_pk

GENERATION_TYPES = ("image", "video", "audio", "text", "vision_review")

GENERATION_STATUSES = (
    "created",
    "queued",
    "running",
    "waiting_provider",
    "processing_output",
    "completed",
    "failed",
    "cancelled",
    "retrying",
)


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    shot_id: Mapped[str | None] = mapped_column(ForeignKey("shots.id"), index=True)
    type: Mapped[str] = mapped_column(Text, nullable=False, default="image")
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="mock")  # mock|comfyui|...
    model: Mapped[str | None] = mapped_column(Text)
    workflow_id: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")
    parameters: Mapped[str | None] = mapped_column(Text)  # JSON input (prompt, seed, size...)
    output_asset_id: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    stage: Mapped[str | None] = mapped_column(Text)  # queued|sampling|saving...

    retry_of: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # P1-E2-T02: atomic claim + lease (crash recovery) + retry backoff gate
    claim_token: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[str | None] = mapped_column(Text)

    cost: Mapped[float | None] = mapped_column()
    provider_ref: Mapped[str | None] = mapped_column(Text)  # provider-side ref (comfyui prompt_id)

    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    started_at: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[str | None] = mapped_column(Text)
