"""p9: timelines + timeline_tracks + timeline_clips (Timeline & Episode Render)

Revision ID: c9d0e1f2a3b4
Revises: a8b9c0d1e2f3
Create Date: 2026-08

Phase 9 (Timeline & Episode Render) domain persistence:

- timelines: one per episode (episode_id UNIQUE), overall duration/resolution/fps/status.
- timeline_tracks: lanes VIDEO / VOICE / MUSIC / SFX / SUBTITLE (order_index vertical).
- timeline_clips: Timeline Items — asset_id binds a SPECIFIC asset version; start/end
  times place it on the timeline; source_in/out address into the source media; shot_id
  is a soft reference (no FK — no one-shot/one-clip assumption, redesign §73).

Indexes per database-schema-design §69:
  idx_timeline_tracks(timeline_id, order_index)
  idx_timeline_clips_track_time(track_id, start_time)
  idx_timeline_clips_shot(shot_id)
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "timelines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"]),
    )
    op.create_index("ix_timelines_project_id", "timelines", ["project_id"])
    op.create_index("ix_timelines_episode_id", "timelines", ["episode_id"], unique=True)

    op.create_table(
        "timeline_tracks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("timeline_id", sa.String(length=36), nullable=False),
        sa.Column("track_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Float(), nullable=False, server_default="0"),
        sa.Column("locked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("muted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_timeline_tracks", "timeline_tracks", ["timeline_id", "order_index"])
    op.create_index("ix_timeline_tracks_timeline_id", "timeline_tracks", ["timeline_id"])

    op.create_table(
        "timeline_clips",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("timeline_id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("shot_id", sa.Text(), nullable=True),
        sa.Column("start_time", sa.Float(), nullable=False, server_default="0"),
        sa.Column("end_time", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_in", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_out", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),  # subtitle content
        sa.Column("order_index", sa.Float(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"]),
        sa.ForeignKeyConstraint(["track_id"], ["timeline_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
    )
    op.create_index("idx_timeline_clips_track_time", "timeline_clips", ["track_id", "start_time"])
    op.create_index("idx_timeline_clips_shot", "timeline_clips", ["shot_id"])
    op.create_index("ix_timeline_clips_timeline_id", "timeline_clips", ["timeline_id"])
    op.create_index("ix_timeline_clips_track_id", "timeline_clips", ["track_id"])
    op.create_index("ix_timeline_clips_asset_id", "timeline_clips", ["asset_id"])


def downgrade() -> None:
    op.drop_table("timeline_clips")
    op.drop_table("timeline_tracks")
    op.drop_table("timelines")