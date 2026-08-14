"""Shot model — the atomic production unit (database-v0.1 §10, mvp-spec §18)."""

from sqlalchemy import ForeignKey, Text
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
    active_image_version_id: Mapped[str | None] = mapped_column(Text)
    active_video_version_id: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    dirty_state: Mapped[str] = mapped_column(Text, nullable=False, default="clean")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)

    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()
