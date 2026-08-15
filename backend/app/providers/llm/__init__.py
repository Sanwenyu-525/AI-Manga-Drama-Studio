"""LlmProvider adapter family (P4-T001).

Minimal-invasive registration: the LLMGateway Protocol already IS a provider-agnostic
Studio abstraction (backend-architecture §17) living in app/llm/gateway.py. Phase 4
only needs it registered in the adapters layer and the ProviderRegistry. Rather than
duplicating the Protocol, this package re-exports it and names the canonical adapter
type (LlmProviderAdapter = LLMGateway). Business code keeps depending on LLMGateway;
the registry can resolve llm providers by canonical id (fake | openai).
"""

from __future__ import annotations

from app.llm.gateway import LLMGateway
from app.llm.factory import create_gateway, reset_gateway

# Canonical adapter alias — the registry resolves LLM providers to this Protocol.
type LlmProviderAdapter = LLMGateway

__all__ = ["LlmProviderAdapter", "LLMGateway", "create_gateway", "reset_gateway"]
