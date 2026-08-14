"""stage c: assets, generations, media_versions

Revision ID: 395a4fdc3dfc
Revises: 2d0cfc1bb995
Create Date: 2026-08-14 20:34:52.037516

Stage C tables (mvp-spec §63-75): assets, generations, media_versions.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "395a4fdc3dfc"
down_revision: Union[str, Sequence[str], None] = "2d0cfc1bb995"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("source_generation_id", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_assets_project_id", "assets", ["project_id"])

    op.create_table(
        "generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("shot_id", sa.String(36), sa.ForeignKey("shots.id"), nullable=True),
        sa.Column("type", sa.Text(), nullable=False, server_default="image"),
        sa.Column("provider", sa.Text(), nullable=False, server_default="mock"),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("workflow_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="created"),
        sa.Column("parameters", sa.Text(), nullable=True),
        sa.Column("output_asset_id", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column("retry_of", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("provider_ref", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
    )
    op.create_index("ix_generations_project_id", "generations", ["project_id"])
    op.create_index("ix_generations_shot_id", "generations", ["shot_id"])

    op.create_table(
        "media_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shot_id", sa.String(36), sa.ForeignKey("shots.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False, server_default="image"),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_media_versions_shot_id", "media_versions", ["shot_id"])


def downgrade() -> None:
    op.drop_index("ix_media_versions_shot_id", table_name="media_versions")
    op.drop_table("media_versions")
    op.drop_index("ix_generations_shot_id", table_name="generations")
    op.drop_index("ix_generations_project_id", table_name="generations")
    op.drop_table("generations")
    op.drop_index("ix_assets_project_id", table_name="assets")
    op.drop_table("assets")
