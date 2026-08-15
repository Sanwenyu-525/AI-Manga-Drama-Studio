"""Scene model (database-v0.1 §5)."""

from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        # P1-E1-T02: one live scene_number per episode (soft-deleted rows excluded)
        Index(
            "uq_scenes_episode_number",
            "episode_id",
            "scene_number",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = uuid_pk()
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), nullable=False, index=True)
    scene_number: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    location_id: Mapped[str | None] = mapped_column(Text)  # FK to locations (Phase 2 table)
    time_of_day: Mapped[str | None] = mapped_column(Text)  # day|night|dusk|dawn
    lighting: Mapped[str | None] = mapped_column(Text)
    weather: Mapped[str | None] = mapped_column(Text)
    mood: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    scene_order: Mapped[int | None] = mapped_column()
    analysis_key: Mapped[str | None] = mapped_column(Text)  # P1-E1-T01: episode analysis key; NOT NULL marks AI-created scenes
    storyboard_key: Mapped[str | None] = mapped_column(Text)  # P1-E1-T01: last shot-planning key of this scene
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()
