"""Shared column helpers for ORM models.

Convention (database-v0.1 §0): TEXT PK UUID v4; timestamps are TEXT ISO8601 UTC.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def uuid_pk() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def ts_created() -> Mapped[str]:
    return mapped_column(Text, nullable=False, default=utcnow_iso)


def ts_updated() -> Mapped[str]:
    return mapped_column(Text, nullable=False, default=utcnow_iso, onupdate=utcnow_iso)
