"""p2 (P2-T009): location visual versions + locations.master_version_id; (P2-T010): costumes

Revision ID: d1e3f5a7c9b1
Revises: d6260cbe10eb
Create Date: 2026-08-16 10:00:00

P2-T009 Location versioning (database-v0.1 §6, domain-model-design §35/§36):
- locations: reusable backgrounds, revision (optimistic concurrency) + soft delete.
- location_versions: immutable version chain per location (v1/v2/...); status =
  active|stale|archived, new version defaults to stale.
- locations.master_version_id: ADR-002-style authoritative pointer (nullable until a
  version is activated).
- scenes.location_id already exists (Text, Phase 2 table comment) — NOT altered.

P2-T010 Costume (database-v0.1 §8, domain-model-design §33): basic CRUD, optional
character owner (characters.character_id), optional reference_asset_id.

shot_characters.costume_id already exists from P1 (Text, weak ref) — left as-is so
shot assignment stays optional (validated service-side, no SQLite table rebuild).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e3f5a7c9b1"
down_revision: Union[str, Sequence[str], None] = "d6260cbe10eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visual_prompt", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_locations_project_id", "locations", ["project_id"])

    op.create_table(
        "location_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("location_id", sa.String(length=36), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(length=36), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="stale"),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
    )
    op.create_index("ix_location_versions_location_id", "location_versions", ["location_id"])
    op.create_index(
        "uq_location_versions_number", "location_versions",
        ["location_id", "version_number"], unique=True,
    )
    op.create_index("ix_location_versions_asset_id", "location_versions", ["asset_id"])

    # P2-T009: ADR-002 MASTER pointer on locations. FK expressed in the ORM model
    # only (SQLite batch mode cannot attach a FK to a newly added column without a
    # named constraint; mirrors the character_versions migration d6260cbe10eb).
    with op.batch_alter_table("locations") as batch:
        batch.add_column(sa.Column("master_version_id", sa.String(length=36), nullable=True))

    op.create_table(
        "costumes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("character_id", sa.String(length=36), sa.ForeignKey("characters.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visual_prompt", sa.Text(), nullable=True),
        sa.Column("reference_asset_id", sa.String(length=36), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_costumes_project_id", "costumes", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_costumes_project_id", table_name="costumes")
    op.drop_table("costumes")

    with op.batch_alter_table("locations") as batch:
        batch.drop_column("master_version_id")

    op.drop_index("ix_location_versions_asset_id", table_name="location_versions")
    op.drop_index("uq_location_versions_number", table_name="location_versions")
    op.drop_index("ix_location_versions_location_id", table_name="location_versions")
    op.drop_table("location_versions")

    op.drop_index("ix_locations_project_id", table_name="locations")
    op.drop_table("locations")
