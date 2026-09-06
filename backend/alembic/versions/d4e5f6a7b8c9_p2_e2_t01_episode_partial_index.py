"""P2-E2-T01: episodes partial unique index — uq_episodes_project_number

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-09-06

The old FULL UniqueConstraint(project_id, episode_number) still covered
soft-deleted rows: deleting EP1 then creating a new episode (which reuses
number 1 via next_sequence over live rows) blew up with IntegrityError, and a
restore could never report a clean 409 conflict. Same partial-index pattern as
scenes/shots (P1-E1-T02): numbers are unique among LIVE rows only.

SQLite cannot drop a constraint without a table rebuild — batch mode handles
it. Legacy duplicates are impossible under the old full constraint, but the
pre-check runs anyway (fail loudly, never silently).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dupes = list(
        bind.execute(
            sa.text(
                "SELECT project_id, episode_number, COUNT(*) FROM episodes "
                "WHERE deleted_at IS NULL GROUP BY project_id, episode_number "
                "HAVING COUNT(*) > 1"
            )
        )
    )
    if dupes:
        raise RuntimeError(
            "P2-E2-T01 migration aborted: live duplicate episode numbers — "
            "resolve explicitly before adding the partial unique index.\n"
            + "\n".join(f"{r[0]}/{r[1]} x{r[2]}" for r in dupes)
        )
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.drop_constraint("uq_episodes_project_number", type_="unique")
        batch_op.create_index(
            "uq_episodes_project_number",
            ["project_id", "episode_number"],
            unique=True,
            sqlite_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.drop_index("uq_episodes_project_number")
        batch_op.create_unique_constraint(
            "uq_episodes_project_number", ["project_id", "episode_number"]
        )
