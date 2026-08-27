"""LLM gateway factory — returns the gateway selected by STUDIO_LLM_MODE (mvp-spec §101).

- fake   → FakeLLMGateway (dev/test only; deterministic keyword rules, no key)
- openai → LangChainOpenAIGateway (production OpenAI-compatible endpoints)

降级策略: fake 是键控开发/测试的默认值，**不算降级**——它是确定性规则输出，不代表真实
模型质量。真实产品链路应设 `STUDIO_LLM_MODE=openai`。openai 路径任一调用失败会以
ProviderUnavailableError 上报（业务层如 continuity_service.semantic_check 若有需要会自己
降级到规则路径），gateway 本身不做静默切换，避免把模型故障掩盖成"看起来正常"。

APP_ENV / STUDIO_LLM_MODE switch freely; business code only ever sees the LLMGateway protocol.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.llm.fake import FakeLLMGateway
from app.llm.gateway import LLMGateway
from app.llm.langchain_gateway import LangChainOpenAIGateway
from app.services.llm_settings_service import get_llm_config

logger = get_logger("llm.factory")

_gateway: LLMGateway | None = None


def create_gateway() -> LLMGateway:
    global _gateway
    if _gateway is not None:
        return _gateway
    cfg = get_llm_config()
    if cfg["mode"] == "openai":
        _gateway = LangChainOpenAIGateway(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            model=cfg["model"],
        )
        logger.info("LLM gateway: openai (%s @ %s)", cfg["model"], cfg["base_url"])
    else:
        _gateway = FakeLLMGateway()
        logger.info("LLM gateway: fake (mode=fake; set openai for real models)")
    return _gateway


def reset_gateway() -> None:
    """Reset cached gateway (used by tests)."""
    global _gateway
    _gateway = None
