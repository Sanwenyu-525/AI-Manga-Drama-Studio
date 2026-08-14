"""LLM Gateway — Studio's own abstraction over model providers (backend-architecture §17).

Agents and ScriptService depend on this interface, never on a concrete model SDK.
Internal implementations: FakeLLMGateway (deterministic, no key) and LangChainOpenAIGateway.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMGateway(Protocol):
    """Unified LLM access: invoke / structured / stream (backend-architecture §17)."""

    async def invoke(self, system: str, prompt: str) -> str:
        """Plain text completion."""
        ...

    async def structured(self, schema: type[T], system: str, prompt: str) -> T:
        """Structured output constrained to a Pydantic schema (LangChain structured output)."""
        ...

    async def structured_list(self, schema: type[T], system: str, prompt: str) -> list[T]:
        """Structured output as a list of Pydantic models."""
        ...
