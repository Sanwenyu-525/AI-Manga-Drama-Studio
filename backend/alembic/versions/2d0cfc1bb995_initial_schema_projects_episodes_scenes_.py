"""initial schema: projects, episodes, scenes, shots

Revision ID: 2d0cfc1bb995
Revises:
Create Date: 2026-08-14 18:41:57.716816

Stage A tables only (mvp-spec §15): projects, episodes, scenes, shots.
Soft-delete via `deleted_at` (database-v0.1 §41).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2d0cfc1bb995"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("style_config", sa.Text(), nullable=True),
        sa.Column("default_language", sa.Text(), nullable=True),
        sa.Column("aspect_ratio", sa.Text(), nullable=True),
        sa.Column("fps", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "episodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("script_text", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("project_id", "episode_number", name="uq_episodes_project_number"),
    )
    op.create_index("ix_episodes_project_id", "episodes", ["project_id"])

    op.create_table(
        "scenes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("episode_id", sa.String(36), sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("location_id", sa.Text(), nullable=True),
        sa.Column("time_of_day", sa.Text(), nullable=True),
        sa.Column("lighting", sa.Text(), nullable=True),
        sa.Column("weather", sa.Text(), nullable=True),
        sa.Column("mood", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scene_order", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_scenes_episode_id", "scenes", ["episode_id"])

    op.create_table(
        "shots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scene_id", sa.String(36), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("shot_number", sa.Integer(), nullable=False),
        sa.Column("shot_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shot_type", sa.Text(), nullable=False, server_default="medium"),
        sa.Column("camera_angle", sa.Text(), nullable=True),
        sa.Column("camera_movement", sa.Text(), nullable=True),
        sa.Column("lens", sa.Text(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("emotion", sa.Text(), nullable=True),
        sa.Column("dialogue", sa.Text(), nullable=True),
        sa.Column("environment_description", sa.Text(), nullable=True),
        sa.Column("image_prompt", sa.Text(), nullable=True),
        sa.Column("video_prompt", sa.Text(), nullable=True),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("previous_shot_id", sa.Text(), nullable=True),
        sa.Column("next_shot_id", sa.Text(), nullable=True),
        sa.Column("active_image_version_id", sa.Text(), nullable=True),
        sa.Column("active_video_version_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("dirty_state", sa.Text(), nullable=False, server_default="clean"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_shots_scene_id", "shots", ["scene_id"])


def downgrade() -> None:
    op.drop_index("ix_shots_scene_id", table_name="shots")
    op.drop_table("shots")
    op.drop_index("ix_scenes_episode_id", table_name="scenes")
    op.drop_table("scenes")
    op.drop_index("ix_episodes_project_id", table_name="episodes")
    op.drop_table("episodes")
    op.drop_table("projects")
