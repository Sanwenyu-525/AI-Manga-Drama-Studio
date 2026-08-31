"""P4-E3-T02 (AC-2): timeline_clips.transition + revision.

Fills the "Timeline 编辑（时长/转场）有 revision 与 undo" acceptance gap:
- transition (cut/fade/dissolve) — basic transition at the clip head.
- revision — optimistic-concurrency guard so concurrent editors get a 409
  instead of silently overwriting each other.

Revision ID: a4b5c6d7e8f9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("timeline_clips") as batch:
        batch.add_column(sa.Column("transition", sa.Text(), nullable=False, server_default="cut"))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("timeline_clips") as batch:
        batch.drop_column("revision")
        batch.drop_column("transition")
