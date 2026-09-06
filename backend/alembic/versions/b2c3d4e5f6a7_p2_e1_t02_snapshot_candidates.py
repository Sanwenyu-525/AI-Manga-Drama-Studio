"""P2-E1-T02: snapshot character candidates — analysis_snapshots.character_candidates_json

Revision ID: b2c3d4e5f6a7
Revises: f0b2c4d6e8f0
Create Date: 2026-09-06

P2-E1-T02 stores the LLM-extracted character candidates on the immutable
snapshot (like plans) so refresh rehydration and the decisions endpoint share
one server truth. Nullable TEXT — old snapshots read back as "no candidates".
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "f0b2c4d6e8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_snapshots",
        sa.Column("character_candidates_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_snapshots", "character_candidates_json")
