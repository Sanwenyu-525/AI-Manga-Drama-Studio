"""p3 (ADR-001): asset self-versioning — merge media_versions into assets

Revision ID: d3e4f5a6b7c8
Revises: 5f1c9a2b7d40
Create Date: 2026-08

ADR-001 (docs/adr/ADR-001-asset-self-versioning.md):
- assets gain version_group_id / version_number / status / source_type / checksum /
  parent_asset_id; source_generation_id renamed to generation_id.
- shots.active_image_asset_id / active_video_asset_id replace active_*_version_id.
- media_versions rows are backfilled into assets, then the table is dropped.
- Version group id format: vg:{owner_type}:{owner_id}:{purpose} (purpose SHOT_IMAGE/SHOT_VIDEO).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "5f1c9a2b7d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _group_id(shot_id: str, media_type: str) -> str:
    purpose = "SHOT_IMAGE" if media_type == "image" else "SHOT_VIDEO"
    return f"vg:shot:{shot_id}:{purpose}"


def upgrade() -> None:
    bind = op.get_bind()

    # 1) assets: versioning columns + rename source_generation_id -> generation_id
    with op.batch_alter_table("assets") as batch:
        batch.add_column(sa.Column("version_group_id", sa.Text(), nullable=True))
        batch.add_column(sa.Column("version_number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("status", sa.Text(), nullable=False, server_default="ready"))
        batch.add_column(sa.Column("source_type", sa.Text(), nullable=False, server_default="generated"))
        batch.add_column(sa.Column("checksum", sa.Text(), nullable=True))
        batch.add_column(sa.Column("parent_asset_id", sa.Text(), nullable=True))
        batch.alter_column("source_generation_id", new_column_name="generation_id")

    op.create_index(
        "uq_assets_version", "assets", ["version_group_id", "version_number"],
        unique=True,
        sqlite_where=sa.text("version_group_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index("idx_assets_version_group", "assets", ["version_group_id"])
    op.create_index("idx_assets_generation", "assets", ["generation_id"])
    op.create_index("idx_assets_parent", "assets", ["parent_asset_id"])

    # 2) shots: active asset pointers
    with op.batch_alter_table("shots") as batch:
        batch.add_column(sa.Column("active_image_asset_id", sa.Text(), nullable=True))
        batch.add_column(sa.Column("active_video_asset_id", sa.Text(), nullable=True))

    # 3) backfill media_versions -> assets (ordered so version_number stays stable)
    rows = bind.execute(
        sa.text(
            "SELECT id, shot_id, asset_id, media_type, version_number, generation_id, is_active, created_at "
            "FROM media_versions ORDER BY shot_id, media_type, version_number"
        )
    ).fetchall()
    for row in rows:
        mv_id, shot_id, asset_id, media_type, version_number, generation_id, is_active, created_at = row
        group = _group_id(shot_id, media_type)
        bind.execute(
            sa.text(
                "UPDATE assets SET version_group_id = :g, version_number = :n, generation_id = COALESCE(generation_id, :gen) "
                "WHERE id = :aid"
            ),
            {"g": group, "n": version_number, "gen": generation_id, "aid": asset_id},
        )
        if is_active:
            col = "active_image_asset_id" if media_type == "image" else "active_video_asset_id"
            bind.execute(
                sa.text(f"UPDATE shots SET {col} = :aid WHERE id = :sid"),
                {"aid": asset_id, "sid": shot_id},
            )

    # 4) integrity verification before dropping the legacy table
    dup = bind.execute(
        sa.text(
            "SELECT version_group_id, version_number, COUNT(*) AS c FROM assets "
            "WHERE version_group_id IS NOT NULL GROUP BY version_group_id, version_number HAVING c > 1"
        )
    ).fetchall()
    if dup:
        raise RuntimeError(f"legacy duplicates after version backfill: {dup}")

    # 5) drop legacy version rows/columns
    op.drop_table("media_versions")
    with op.batch_alter_table("shots") as batch:
        batch.drop_column("active_image_version_id")
        batch.drop_column("active_video_version_id")


def downgrade() -> None:
    bind = op.get_bind()

    # 1) recreate legacy shot pointers
    with op.batch_alter_table("shots") as batch:
        batch.add_column(sa.Column("active_image_version_id", sa.Text(), nullable=True))
        batch.add_column(sa.Column("active_video_version_id", sa.Text(), nullable=True))

    # 2) recreate media_versions (same schema as the Stage C migration)
    op.create_table(
        "media_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("shot_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "uq_media_versions_shot_number", "media_versions",
        ["shot_id", "media_type", "version_number"], unique=True,
    )
    op.create_index(
        "uq_media_versions_active", "media_versions", ["shot_id"],
        unique=True, sqlite_where=sa.text("is_active = 1"),
    )

    # 3) backfill assets -> media_versions
    assets = bind.execute(
        sa.text(
            "SELECT id, version_group_id, version_number, generation_id, created_at FROM assets "
            "WHERE version_group_id IS NOT NULL"
        )
    ).fetchall()
    for asset_id, group, version_number, generation_id, created_at in assets:
        # group format: vg:shot:{shot_id}:{purpose}
        parts = group.split(":")
        if len(parts) != 4 or parts[0] != "vg" or parts[1] != "shot":
            continue
        shot_id, purpose = parts[2], parts[3]
        media_type = "image" if purpose == "SHOT_IMAGE" else "video"
        active = bind.execute(
            sa.text(
                f"SELECT active_{media_type}_asset_id FROM shots WHERE id = :sid"
            ),
            {"sid": shot_id},
        ).scalar()
        is_active = 1 if active == asset_id else 0
        bind.execute(
            sa.text(
                "INSERT INTO media_versions (id, shot_id, asset_id, media_type, version_number, generation_id, is_active, created_at) "
                "VALUES (:id, :sid, :aid, :mt, :n, :gen, :ia, :ca)"
            ),
            {
                "id": asset_id, "sid": shot_id, "aid": asset_id, "mt": media_type,
                "n": version_number, "gen": generation_id, "ia": is_active, "ca": created_at or "1970-01-01T00:00:00+00:00",
            },
        )
        if is_active:
            bind.execute(
                sa.text(
                    f"UPDATE shots SET active_{media_type}_version_id = :vid WHERE id = :sid"
                ),
                {"vid": asset_id, "sid": shot_id},
            )

    # 4) drop new asset columns / indexes, restore legacy name
    op.drop_index("idx_assets_parent", table_name="assets")
    op.drop_index("idx_assets_generation", table_name="assets")
    op.drop_index("idx_assets_version_group", table_name="assets")
    op.drop_index("uq_assets_version", table_name="assets")
    with op.batch_alter_table("assets") as batch:
        batch.alter_column("generation_id", new_column_name="source_generation_id")
        batch.drop_column("parent_asset_id")
        batch.drop_column("checksum")
        batch.drop_column("source_type")
        batch.drop_column("status")
        batch.drop_column("version_number")
        batch.drop_column("version_group_id")

    with op.batch_alter_table("shots") as batch:
        batch.drop_column("active_video_asset_id")
        batch.drop_column("active_image_asset_id")
