"""LangChain-backed LLM gateway — OpenAI-compatible endpoints (backend-architecture §17, §53-54).

Supports DeepSeek / OpenAI / Ollama / vLLM / MiniMax via base_url override.
Structured output via `with_structured_output` (LangChain structured output).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TypeVar

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger
from app.llm.messages import ChatMessage, ChatOptions, ChatResponse, TokenUsage

logger = get_logger("llm.openai")

T = TypeVar("T", bound=BaseModel)

_ROLE_TO_MESSAGE = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


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
            # base_url 是用户显式配置的端点（常为本地 Ollama/vLLM）：不跟随系统代理。
            # 否则终端残留的 HTTP(S)_PROXY 会把连接劫持到不可用代理上
            # （与 llm_settings_service._CLIENT_KWARGS 的 trust_env=False 决策一致）。
            http_client=httpx.Client(trust_env=False),
            http_async_client=httpx.AsyncClient(trust_env=False),
        )
        self._base_url = base_url
        logger.info("LLM gateway ready: base_url=%s model=%s", base_url, model)

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        options: ChatOptions | None = None,
    ) -> ChatResponse:
        """Message-shaped core: contract messages in, content + token usage out."""
        try:
            lc_messages = [_ROLE_TO_MESSAGE[m.role](content=m.content) for m in messages]
            chat_model = self._chat
            if options is not None:
                overrides = {
                    key: value
                    for key, value in {
                        "temperature": options.temperature,
                        "max_tokens": options.max_tokens,
                        "timeout": options.timeout,
                    }.items()
                    if value is not None
                }
                if overrides:
                    chat_model = self._chat.bind(**overrides)
            response = await chat_model.ainvoke(lc_messages)
        except Exception as exc:
            raise ProviderUnavailableError(str(exc), {"base_url": self._base_url}) from exc
        usage_raw = getattr(response, "usage_metadata", None) or {}
        usage = None
        if usage_raw:
            usage = TokenUsage(
                input_tokens=int(usage_raw.get("input_tokens") or 0),
                output_tokens=int(usage_raw.get("output_tokens") or 0),
            )
        metadata = getattr(response, "response_metadata", None) or {}
        return ChatResponse(
            content=str(response.content),
            model=metadata.get("model_name") or metadata.get("model"),
            finish_reason=metadata.get("finish_reason"),
            usage=usage,
        )

    async def invoke(self, system: str, prompt: str) -> str:
        response = await self.chat(
            [ChatMessage(role="system", content=system), ChatMessage(role="user", content=prompt)]
        )
        return response.content

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
