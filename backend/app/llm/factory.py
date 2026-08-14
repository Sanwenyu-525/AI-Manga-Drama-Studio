"""LLM gateway factory — returns the gateway selected by STUDIO_LLM_MODE (mvp-spec §101).

- fake   → FakeLLMGateway (default; deterministic, keyless; used by tests & dev)
- openai → LangChainOpenAIGateway (OpenAI-compatible endpoints)

APP_ENV / STUDIO_LLM_MODE switch freely; business code only ever sees the LLMGateway protocol.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.fake import FakeLLMGateway
from app.llm.gateway import LLMGateway
from app.llm.langchain_gateway import LangChainOpenAIGateway

logger = get_logger("llm.factory")

_gateway: LLMGateway | None = None


def create_gateway() -> LLMGateway:
    global _gateway
    if _gateway is not None:
        return _gateway
    if settings.llm_mode == "openai":
        _gateway = LangChainOpenAIGateway()
        logger.info("LLM gateway: openai (%s @ %s)", settings.llm_model, settings.llm_base_url)
    else:
        _gateway = FakeLLMGateway()
        logger.info("LLM gateway: fake (STUDIO_LLM_MODE=fake; set openai for real models)")
    return _gateway


def reset_gateway() -> None:
    """Reset cached gateway (used by tests)."""
    global _gateway
    _gateway = None
