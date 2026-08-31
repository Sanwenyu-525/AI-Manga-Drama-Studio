"""fix: character_versions.deleted_at (schema drift)

The P2 migration d6260cbe10eb created character_versions without deleted_at,
but the ORM model (app/db/models/character.py) later added the column for
soft-deleted draft versions. Every live query filters deleted_at.is_(None),
which raised "no such column: character_versions.deleted_at" -> 500.

Revision ID: f3a5b7c9d1e3
Revises: c9d0e1f2a3b4
Create Date: 2026-08-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a5b7c9d1e3"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("character_versions") as batch:
        batch.add_column(sa.Column("deleted_at", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("character_versions") as batch:
        batch.drop_column("deleted_at")