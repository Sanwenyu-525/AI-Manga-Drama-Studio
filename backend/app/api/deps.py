"""Shared API dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.factory import create_gateway
from app.llm.gateway import LLMGateway

# Re-export for routers; override in tests via app.dependency_overrides.
__all__ = ["DbSession", "get_db", "get_llm"]

DbSession = Generator[Session]


def get_llm() -> LLMGateway:
    """Provide the LLM gateway selected by STUDIO_LLM_MODE (fake by default)."""
    return create_gateway()
