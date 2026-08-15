"""p1 (ProjectSetting + revision optimistic locking)

Revision ID: f0a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-08

Phase-1 (ProjectSetting + revision 乐观锁, database-schema-design §15):
- project_settings table (per-project generation/config defaults).
- projects / episodes / scenes each gain a revision column (optimistic concurrency,
  red line AGENTS.md §3.10 — 409 Conflict on stale writes).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- project_settings (database-schema-design §13/§15) ---
    op.create_table(
        "project_settings",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("language", sa.Text(), nullable=False, server_default="zh-CN"),
        sa.Column("default_llm_provider", sa.Text(), nullable=True),
        sa.Column("default_llm_model", sa.Text(), nullable=True),
        sa.Column("default_image_provider", sa.Text(), nullable=True),
        sa.Column("default_image_model", sa.Text(), nullable=True),
        sa.Column("default_video_provider", sa.Text(), nullable=True),
        sa.Column("default_video_model", sa.Text(), nullable=True),
        sa.Column("default_voice_provider", sa.Text(), nullable=True),
        sa.Column("default_voice_model", sa.Text(), nullable=True),
        sa.Column("default_image_workflow_id", sa.Text(), nullable=True),
        sa.Column("default_video_workflow_id", sa.Text(), nullable=True),
        sa.Column("auto_retry", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_retry_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("auto_save", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("continuity_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("auto_activate_new_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("settings_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_project_settings_project", "project_settings", ["project_id"])

    # --- revision optimistic-concurrency columns ---
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
        )
    with op.batch_alter_table("episodes") as batch:
        batch.add_column(
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
        )
    with op.batch_alter_table("scenes") as batch:
        batch.add_column(
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("scenes") as batch:
        batch.drop_column("revision")
    with op.batch_alter_table("episodes") as batch:
        batch.drop_column("revision")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("revision")
    op.drop_index("idx_project_settings_project", table_name="project_settings")
    op.drop_table("project_settings")
