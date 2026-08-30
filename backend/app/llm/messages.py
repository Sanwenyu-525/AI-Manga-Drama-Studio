"""Studio Domain Contract for chat messages (red line §3.7).

External SDK shapes (LangChain Message, OpenAI dict, …) must never leak past the
gateway — agents/services speak ONLY these Pydantic types. The message-shaped
`chat()` interface is the foundation for conversation surfaces (production chat,
memory) that the prompt-shaped `invoke(system, prompt)` cannot express.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    """One turn in a conversation. Tool/tool-result roles land here when the
    agent runtime grows a native tool-calling loop (MVP uses the structured
    planner, so only the three conversational roles are modeled)."""

    role: ChatRole
    content: str


class ChatOptions(BaseModel):
    """Per-call generation overrides (None → gateway/provider defaults)."""

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout: float | None = Field(default=None, gt=0)


class TokenUsage(BaseModel):
    """Token accounting for one completion (cost tracking builds on this)."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ChatResponse(BaseModel):
    """Message-shaped completion result."""

    content: str
    model: str | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    # 降级链归因（不静默掩盖原则）：实际服务的连接 profile。FallbackLLMGateway
    # 总是标注（含主连接直接服务的情况，便于观测归因）；None = 非链路网关。
    served_by_profile: str | None = None
    served_by_profile_name: str | None = None
