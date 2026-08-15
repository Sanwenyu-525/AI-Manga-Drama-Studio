"""p1-e2-t02: generation claim/lease/backoff columns

Revision ID: c1d2e3f4a5b6
Revises: b1e2f3a4c5d6
Create Date: 2026-08-20

P1-E2-T02 (Generation 状态机、原子认领与崩溃恢复):

- claim_token      — unique-ish token of the worker that claimed the row
- claimed_at       — when the claim happened
- lease_expires_at — claim lease; workers refresh it (heartbeat); a stale lease
                     means the previous process died → recovery re-queues
- next_attempt_at  — retry backoff gate: the claim query skips rows not yet due
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b1e2f3a4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("generations", sa.Column("claim_token", sa.Text(), nullable=True))
    op.add_column("generations", sa.Column("claimed_at", sa.Text(), nullable=True))
    op.add_column("generations", sa.Column("lease_expires_at", sa.Text(), nullable=True))
    op.add_column("generations", sa.Column("next_attempt_at", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("generations", "next_attempt_at")
    op.drop_column("generations", "lease_expires_at")
    op.drop_column("generations", "claimed_at")
    op.drop_column("generations", "claim_token")
