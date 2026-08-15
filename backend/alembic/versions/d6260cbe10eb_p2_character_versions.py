"""p2 (P2-T007/T008): character visual versions + MASTER pointer

Revision ID: d6260cbe10eb
Revises: a1b2c3d4e5f6
Create Date: 2026-08-15 20:11:08.717647

P2 CharacterVersion (database-v0.1 §7, domain-model-design §31/§32):
- character_versions: immutable version chain per character. version_number is
  group-scoped auto-increment (v1/v2/...); status = active|stale|archived, a new
  version defaults to stale and is promoted to active only on activate.
- characters.master_version_id: ADR-002-style authoritative pointer to the
  project-approved standard look (nullable until a version is activated).
  Shot creation binds Character.masterVersionId; existing shots are NOT migrated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6260cbe10eb"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("character_id", sa.String(length=36), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(length=36), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="stale"),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_character_versions_character_id", "character_versions", ["character_id"])
    op.create_index(
        "uq_character_versions_number", "character_versions",
        ["character_id", "version_number"], unique=True,
    )
    op.create_index("ix_character_versions_asset_id", "character_versions", ["asset_id"])

    with op.batch_alter_table("characters") as batch:
        batch.add_column(
            sa.Column("master_version_id", sa.String(length=36), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("characters") as batch:
        batch.drop_column("master_version_id")
    op.drop_index("ix_character_versions_asset_id", table_name="character_versions")
    op.drop_index("uq_character_versions_number", table_name="character_versions")
    op.drop_index("ix_character_versions_character_id", table_name="character_versions")
    op.drop_table("character_versions")
