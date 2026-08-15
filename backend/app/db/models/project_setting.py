"""ProjectSetting model (database-schema-design §13/§15, domain-model-design §9)."""

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_updated


class ProjectSetting(Base):
    __tablename__ = "project_settings"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="zh-CN")
    default_llm_provider: Mapped[str | None] = mapped_column(Text)
    default_llm_model: Mapped[str | None] = mapped_column(Text)
    default_image_provider: Mapped[str | None] = mapped_column(Text)
    default_image_model: Mapped[str | None] = mapped_column(Text)
    default_video_provider: Mapped[str | None] = mapped_column(Text)
    default_video_model: Mapped[str | None] = mapped_column(Text)
    default_voice_provider: Mapped[str | None] = mapped_column(Text)
    default_voice_model: Mapped[str | None] = mapped_column(Text)
    default_image_workflow_id: Mapped[str | None] = mapped_column(Text)
    default_video_workflow_id: Mapped[str | None] = mapped_column(Text)
    auto_retry: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    auto_save: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    continuity_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    auto_activate_new_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settings_json: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = ts_updated()
