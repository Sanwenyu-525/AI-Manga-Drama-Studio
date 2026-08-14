"""Shared API dependencies."""

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db

# Re-export for routers; override in tests via app.dependency_overrides.
__all__ = ["get_db", "DbSession"]

DbSession = Generator[Session, None, None]
