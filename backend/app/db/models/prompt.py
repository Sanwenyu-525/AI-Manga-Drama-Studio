"""Prompt / PromptVersion models (ADR-002): versioned prompts per target per type.

prompts.active_version_id is the AUTHORITATIVE active version; shots keep a
convenience pointer (active_prompt_version_id, image priority). prompt_versions
are immutable — editing creates vN+1 (write-through cache syncs the deprecated
shot.image_prompt/video_prompt/negative_prompt columns).
"""

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

PROMPT_TYPES = ("SHOT_IMAGE", "SHOT_VIDEO", "CHARACTER", "LOCATION", "STORYBOARD", "VOICE", "MUSIC", "DIRECTOR_INSTRUCTION", "CUSTOM")


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (
        Index("idx_prompts_target", "target_type", "target_id"),
        Index("idx_prompts_type", "target_type", "target_id", "prompt_type"),
    )

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)  # SHOT | CHARACTER | ...
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_type: Mapped[str] = mapped_column(Text, nullable=False)  # SHOT_IMAGE | SHOT_VIDEO | ...
    active_version_id: Mapped[str | None] = mapped_column(Text)  # authoritative
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        Index("uq_prompt_versions_prompt_number", "prompt_id", "version_number", unique=True),
        Index("idx_prompt_versions_prompt", "prompt_id", "version_number"),
    )

    id: Mapped[str] = uuid_pk()
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_prompt: Mapped[str | None] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    structured_spec_json: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[str | None] = mapped_column(Text)  # user | agent | migration | system
    parent_version_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
