"""Shared API dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.factory import create_gateway
from app.llm.gateway import LLMGateway

# Re-export for routers; override in tests via app.dependency_overrides.
__all__ = ["DbSession", "get_db", "get_llm", "get_script_llm"]

DbSession = Generator[Session]


def get_llm() -> LLMGateway:
    """Provide the default-task LLM gateway（激活连接）."""
    return create_gateway()


def get_script_llm() -> LLMGateway:
    """Script-analysis task gateway（analyze / generate-shots 走 script 绑定）。"""
    return create_gateway("script")
