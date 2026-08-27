"""LangChain-backed LLM gateway — OpenAI-compatible endpoints (backend-architecture §17, §53-54).

Supports DeepSeek / OpenAI / Ollama / vLLM / MiniMax via base_url override.
Structured output via `with_structured_output` (LangChain structured output).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
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

    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        model: str,
    ) -> None:
        if not base_url:
            raise ProviderUnavailableError(
                "Base URL is required when the LLM mode is openai.",
                {"base_url": base_url},
            )
        self._chat = ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key or "not-needed",
            temperature=0.7,
            timeout=120,
            max_retries=2,
        )
        self._base_url = base_url
        logger.info("LLM gateway ready: base_url=%s model=%s", base_url, model)

    async def invoke(self, system: str, prompt: str) -> str:
        try:
            response = await self._chat.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
            return str(response.content)
        except Exception as exc:
            raise ProviderUnavailableError(str(exc), {"base_url": self._base_url}) from exc

    async def structured(self, schema: type[T], system: str, prompt: str) -> T:
        try:
            model = self._chat.with_structured_output(schema, method=settings.llm_structured_method)
            response = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
            if response is None:
                raise ProviderUnavailableError("LLM returned no structured result.", {})
            return response
        except Exception as exc:
            if isinstance(exc, ProviderUnavailableError):
                raise
            raise ProviderUnavailableError(
                f"Structured output failed: {exc}", {"method": settings.llm_structured_method}
            ) from exc

    async def structured_list(self, schema: type[T], system: str, prompt: str) -> list[T]:
        """Request a list by wrapping the schema in a single-item container model."""
        from pydantic import create_model

        ListContainer = create_model(
            "ListContainer",
            items=(list[schema], ...),  # type: ignore[valid-type]
        )
        result = await self.structured(ListContainer, system, prompt)
        return list(result.items)

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        """Yield text deltas via ChatOpenAI.astream (free-form generations)."""
        try:
            async for chunk in self._chat.astream([SystemMessage(content=system), HumanMessage(content=prompt)]):
                text = chunk.text()
                if text:
                    yield text
        except Exception as exc:
            raise ProviderUnavailableError(str(exc), {"base_url": self._base_url}) from exc
