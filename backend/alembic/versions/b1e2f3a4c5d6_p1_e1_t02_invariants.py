"""p1-e1-t02: db invariants — unique partial indexes + atomicity support

Revision ID: b1e2f3a4c5d6
Revises: e1f2a3b4c5d6
Create Date: 2026-08-20

P1-E1-T02 (建立数据库不变量、原子 revision 与安全重排):

- scenes:        UNIQUE (episode_id, scene_number) WHERE deleted_at IS NULL
- shots:         UNIQUE (scene_id, shot_number)  WHERE deleted_at IS NULL
                 UNIQUE (scene_id, shot_order)  WHERE deleted_at IS NULL
- shot_characters: UNIQUE (shot_id, character_id)
- media_versions: UNIQUE (shot_id, media_type, version_number)
                 UNIQUE (shot_id) WHERE is_active = 1  (single active per shot)
- generations:   INDEX (status, created_at)  (worker DB-poll query)

Soft-deleted rows are EXCLUDED from the uniqueness so numbers can be reused after
deletion (partial indexes). Before creating the indexes the migration DETECTS
legacy duplicates and fails loudly with their locations — historical duplicates
are never dropped silently (resolution is an explicit operator step).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1e2f3a4c5d6"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _duplicate_rows(bind, table: str, columns: list[str], where: str | None) -> list[tuple]:
    col_list = ", ".join(columns)
    sql = f"SELECT {col_list}, COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    sql += f" GROUP BY {col_list} HAVING COUNT(*) > 1"
    return list(bind.execute(sa.text(sql)))


def _assert_no_legacy_duplicates(bind) -> None:
    """P1-E1-T02: fail the migration with exact locations instead of silently
    dropping or crashing on CREATE UNIQUE INDEX."""
    problems: list[str] = []
    checks = [
        ("scenes", ["episode_id", "scene_number"], "deleted_at IS NULL"),
        ("shots", ["scene_id", "shot_number"], "deleted_at IS NULL"),
        ("shots", ["scene_id", "shot_order"], "deleted_at IS NULL"),
        ("shot_characters", ["shot_id", "character_id"], None),
        ("media_versions", ["shot_id", "media_type", "version_number"], None),
        ("media_versions", ["shot_id"], "is_active = 1"),
    ]
    for table, columns, where in checks:
        for row in _duplicate_rows(bind, table, columns, where):
            key = ", ".join(str(part) for part in row[:-1])
            problems.append(f"{table}({key}) x{row[-1]}")
    if problems:
        raise RuntimeError(
            "P1-E1-T02 migration aborted: legacy duplicates found — resolve them "
            "explicitly (merge/re-number/archive) before adding unique constraints; "
            "silent data loss is forbidden.\n" + "\n".join(problems)
        )


def upgrade() -> None:
    bind = op.get_bind()
    _assert_no_legacy_duplicates(bind)

    op.create_index(
        "uq_scenes_episode_number", "scenes", ["episode_id", "scene_number"],
        unique=True, sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_shots_scene_number", "shots", ["scene_id", "shot_number"],
        unique=True, sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_shots_scene_order", "shots", ["scene_id", "shot_order"],
        unique=True, sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_shot_characters_pair", "shot_characters", ["shot_id", "character_id"],
        unique=True,
    )
    op.create_index(
        "uq_media_versions_shot_number", "media_versions",
        ["shot_id", "media_type", "version_number"], unique=True,
    )
    op.create_index(
        "uq_media_versions_active", "media_versions", ["shot_id"],
        unique=True, sqlite_where=sa.text("is_active = 1"),
    )
    op.create_index(
        "ix_generations_status_created", "generations", ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_generations_status_created", table_name="generations")
    op.drop_index("uq_media_versions_active", table_name="media_versions")
    op.drop_index("uq_media_versions_shot_number", table_name="media_versions")
    op.drop_index("uq_shot_characters_pair", table_name="shot_characters")
    op.drop_index("uq_shots_scene_order", table_name="shots")
    op.drop_index("uq_shots_scene_number", table_name="shots")
    op.drop_index("uq_scenes_episode_number", table_name="scenes")
