"""Timeline models (database-v0.1 §32, Phase 9 — Timeline & Episode Render).

One timeline per episode organizing generated shots/assets into a renderable
episode: timelines + timeline_tracks + timeline_clips.

- timeline_tracks: VIDEO / VOICE / MUSIC / SFX / SUBTITLE lanes.
- timeline_clips (Timeline Item): one clip = an asset bound to a track over a
  time range. asset_id binds a SPECIFIC version (design §70 "Timeline Active
  Asset"): independent of shots.active_*_asset_id on purpose.

Renders are type='render' Generations whose output registers as a FINAL_VIDEO
asset under the version group vg:episode:{episode_id}:FINAL_VIDEO.
"""

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

TRACK_TYPES = ("VIDEO", "VOICE", "MUSIC", "SFX", "SUBTITLE")
DEFAULT_TRACK_TYPES = ("VIDEO", "VOICE", "MUSIC", "SUBTITLE")  # created with a new timeline

TIMELINE_STATUSES = ("DRAFT", "READY", "RENDERED", "RENDER_FAILED")


class Timeline(Base):
    __tablename__ = "timelines"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), nullable=False, unique=True)

    duration: Mapped[float | None] = mapped_column()
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column()

    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class TimelineTrack(Base):
    __tablename__ = "timeline_tracks"
    __table_args__ = (Index("idx_timeline_tracks", "timeline_id", "order_index"),)

    id: Mapped[str] = uuid_pk()
    timeline_id: Mapped[str] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False, index=True
    )

    track_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[float] = mapped_column(nullable=False, default=0)

    locked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    muted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[str] = ts_created()


class TimelineClip(Base):
    __tablename__ = "timeline_clips"
    __table_args__ = (
        Index("idx_timeline_clips_track_time", "track_id", "start_time"),
        Index("idx_timeline_clips_shot", "shot_id"),
    )

    id: Mapped[str] = uuid_pk()
    timeline_id: Mapped[str] = mapped_column(ForeignKey("timelines.id"), nullable=False, index=True)
    track_id: Mapped[str] = mapped_column(
        ForeignKey("timeline_tracks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    shot_id: Mapped[str | None] = mapped_column(Text, index=True)  # soft ref (no FK: clip↔shot 无一对一)

    start_time: Mapped[float] = mapped_column(nullable=False, default=0)
    end_time: Mapped[float] = mapped_column(nullable=False, default=0)
    source_in: Mapped[float] = mapped_column(nullable=False, default=0)
    source_out: Mapped[float | None] = mapped_column()
    text: Mapped[str | None] = mapped_column(Text)  # subtitle content (VOICE/SUBTITLE clips)
    order_index: Mapped[float] = mapped_column(nullable=False, default=0)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()