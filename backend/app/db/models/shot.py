"""Shot model — the atomic production unit (database-v0.1 §10, mvp-spec §18)."""

from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

SHOT_STATUSES = (
    "draft",
    "planned",
    "storyboard_ready",
    "image_generating",
    "image_ready",
    "video_generating",
    "video_ready",
    "approved",
    "failed",
)

DIRTY_STATES = ("clean", "dirty_storyboard", "dirty_image", "dirty_video", "dirty_audio")

SHOT_TYPES = ("extreme_wide", "wide", "full", "medium", "close_up", "extreme_close_up")


class Shot(Base):
    __tablename__ = "shots"
    __table_args__ = (
        # P1-E1-T02: one live shot_number / shot_order per scene (soft-deleted rows excluded)
        Index("uq_shots_scene_number", "scene_id", "shot_number", unique=True, sqlite_where=text("deleted_at IS NULL")),
        Index("uq_shots_scene_order", "scene_id", "shot_order", unique=True, sqlite_where=text("deleted_at IS NULL")),
    )

    id: Mapped[str] = uuid_pk()
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)

    shot_number: Mapped[int] = mapped_column(nullable=False)
    shot_order: Mapped[int] = mapped_column(nullable=False, default=0)

    shot_type: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    camera_angle: Mapped[str | None] = mapped_column(Text)  # low_angle|high_angle|eye_level...
    camera_movement: Mapped[str | None] = mapped_column(Text)  # static|pan|tilt|dolly|handheld
    lens: Mapped[str | None] = mapped_column(Text)
    duration: Mapped[float | None] = mapped_column()
    action: Mapped[str | None] = mapped_column(Text)
    emotion: Mapped[str | None] = mapped_column(Text)
    dialogue: Mapped[str | None] = mapped_column(Text)
    environment_description: Mapped[str | None] = mapped_column(Text)
    image_prompt: Mapped[str | None] = mapped_column(Text)
    video_prompt: Mapped[str | None] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text)

    previous_shot_id: Mapped[str | None] = mapped_column(Text)
    next_shot_id: Mapped[str | None] = mapped_column(Text)
    # ADR-001: active selection points at assets (media_versions merged into assets)
    active_image_asset_id: Mapped[str | None] = mapped_column(Text)
    active_video_asset_id: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    dirty_state: Mapped[str] = mapped_column(Text, nullable=False, default="clean")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    analysis_key: Mapped[str | None] = mapped_column(Text)  # P1-E1-T01: storyboard key; NOT NULL marks AI-created shots

    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()
