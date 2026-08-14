"""LangChain-backed LLM gateway — OpenAI-compatible endpoints (backend-architecture §17, §53-54).

Supports DeepSeek / OpenAI / Ollama / vLLM / MiniMax via base_url override.
Structured output via `with_structured_output` (LangChain structured output).
"""

from __future__ import annotations

from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger

logger = get_logger("llm.openai")

T = TypeVar("T", bound=BaseModel)


class LangChainOpenAIGateway:
    """LLMGateway protocol implementation on ChatOpenAI."""

    def __init__(self) -> None:
        if not settings.llm_base_url:
            raise ProviderUnavailableError(
                "STUDIO_LLM_BASE_URL is required when STUDIO_LLM_MODE=openai.",
                {"mode": settings.llm_mode, "base_url": settings.llm_base_url},
            )
        self._chat = ChatOpenAI(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            temperature=0.7,
            timeout=120,
            max_retries=2,
        )
        logger.info("LLM gateway ready: base_url=%s model=%s", settings.llm_base_url, settings.llm_model)

    async def invoke(self, system: str, prompt: str) -> str:
        try:
            response = await self._chat.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
            return str(response.content)
        except Exception as exc:  # noqa: BLE001 — normalize provider errors (contract §57)
            raise ProviderUnavailableError(str(exc), {"base_url": settings.llm_base_url}) from exc

    async def structured(self, schema: type[T], system: str, prompt: str) -> T:
        try:
            model = self._chat.with_structured_output(schema, method=settings.llm_structured_method)
            response = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
            if response is None:
                raise ProviderUnavailableError("LLM returned no structured result.", {})
            return response
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ProviderUnavailableError):
                raise
            raise ProviderUnavailableError(
                f"Structured output failed: {exc}", {"method": settings.llm_structured_method}
            ) from exc

    async def structured_list(self, schema: type[T], system: str, prompt: str) -> list[T]:
        """Request a list by wrapping the schema in a single-item container model."""
        from pydantic import create_model

        ListContainer = create_model(  # noqa: N806
            "ListContainer",
            items=(list[schema], ...),  # type: ignore[valid-type]
        )
        result = await self.structured(ListContainer, system, prompt)
        return list(result.items)
