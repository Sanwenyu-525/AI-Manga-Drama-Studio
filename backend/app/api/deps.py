"""Shared API dependencies."""

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.factory import create_gateway
from app.llm.gateway import LLMGateway

# Re-export for routers; override in tests via app.dependency_overrides.
__all__ = ["get_db", "get_llm", "DbSession"]

DbSession = Generator[Session, None, None]


def get_llm() -> LLMGateway:
    """Provide the LLM gateway selected by STUDIO_LLM_MODE (fake by default)."""
    return create_gateway()
