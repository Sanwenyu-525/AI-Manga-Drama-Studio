"""LLM Gateway — Studio's own abstraction over model providers (backend-architecture §17).

Agents and ScriptService depend on this interface, never on a concrete model SDK.
Internal implementations: FakeLLMGateway (deterministic, no key) and LangChainOpenAIGateway.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.llm.messages import ChatMessage, ChatOptions, ChatResponse

T = TypeVar("T", bound=BaseModel)


class LLMGateway(Protocol):
    """Unified LLM access: chat / invoke / structured / stream (backend-architecture §17).

    `chat()` is the message-shaped core (conversation history in, usage out);
    `invoke()`/`stream()` remain as prompt-shaped conveniences for the current
    one-shot call sites. Implementations express everything through the Studio
    message contract in app.llm.messages — never through SDK shapes.
    """

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        options: ChatOptions | None = None,
    ) -> ChatResponse:
        """Message-shaped completion: full conversation in, content + usage out."""
        ...

    async def invoke(self, system: str, prompt: str) -> str:
        """Plain text completion (prompt-shaped convenience over chat())."""
        ...

    async def structured(self, schema: type[T], system: str, prompt: str) -> T:
        """Structured output constrained to a Pydantic schema (LangChain structured output)."""
        ...

    async def structured_list(self, schema: type[T], system: str, prompt: str) -> list[T]:
        """Structured output as a list of Pydantic models."""
        ...

    def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        """Yield text deltas for free-form generations.

        Structured planner calls (ScenePlan/DirectorPlan…) do not stream; this
        serves future free-form surfaces (production chat, long-form drafting).
        """
        ...
