"""LLM gateway factory — 按 task 解析连接链并缓存（mvp-spec §101；P-LLM-Profiles/Fallback）。

- fake   → FakeLLMGateway (dev/test only; deterministic keyword rules, no key)
- openai → LangChainOpenAIGateway (production OpenAI-compatible endpoints)

连接解析（P-LLM-Profiles）：`get_task_llm_chain(task)` 给出任务的**有序候选链**
——主连接（任务绑定；未绑定则激活连接）+ 显式配置的降级连接。链长 >1 时包一层
`FallbackLLMGateway`（显式降级：每次降级发 `llm.fallback.used` 事件 + WARNING
日志 + 响应归因；链耗尽抛错带明细 —— 不静默掩盖模型故障）。默认无降级配置，
行为与纯 fail-fast 完全一致。

缓存按连接四元组（单候选）或链四元组序列（链）keyed：同配置共享实例；任何
连接/绑定/降级变更由 llm_settings_service 调 reset_gateway() 全清。

降级策略: fake 是键控开发/测试的默认值，**不算降级**——它是确定性规则输出，不代表真实
模型质量。openai 路径任一调用失败以 ProviderUnavailableError 上报，factory 不做静默
换道（能发生的降级都是显式配置且被事件宣告的）。

APP_ENV / settings UI switch freely; business code only ever sees the LLMGateway protocol.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.llm.fake import FakeLLMGateway
from app.llm.gateway import LLMGateway
from app.llm.langchain_gateway import LangChainOpenAIGateway
from app.services.llm_settings_service import get_task_llm_chain

logger = get_logger("llm.factory")

# 连接四元组 → gateway 实例；链四元组序列 → FallbackLLMGateway（同配置共享）。
_gateways: dict[tuple, LLMGateway] = {}
_chain_gateways: dict[tuple, LLMGateway] = {}


def _gateway_key(cfg: dict) -> tuple:
    return (cfg["mode"], cfg["base_url"], cfg["api_key"], cfg["model"])


def _get_or_build(cfg: dict) -> LLMGateway:
    key = _gateway_key(cfg)
    gateway = _gateways.get(key)
    if gateway is None:
        if cfg["mode"] == "openai":
            gateway = LangChainOpenAIGateway(
                base_url=cfg["base_url"],
                api_key=cfg["api_key"],
                model=cfg["model"],
            )
            logger.info(
                "LLM gateway: openai (%s @ %s)", cfg.get("model"), cfg.get("base_url")
            )
        else:
            gateway = FakeLLMGateway()
            logger.info("LLM gateway: fake (set openai for real models)")
        _gateways[key] = gateway
    return gateway


def create_gateway(task: str = "default") -> LLMGateway:
    candidates = get_task_llm_chain(task)
    if not candidates:
        # Registry 极端情况（空）：回落任务的生效配置，保证业务不断链。
        from app.services.llm_settings_service import get_task_llm_config

        candidates = [get_task_llm_config(task)]
    if len(candidates) > 1:
        # 显式降级链：候选共享底层 gateway 实例，链本身按链 key 缓存。
        from app.llm.fallback import FallbackLLMGateway

        chain_key = tuple(_gateway_key(c) + (c["profile_id"],) for c in candidates)
        chain = _chain_gateways.get(chain_key)
        if chain is None:
            chain = FallbackLLMGateway(task=task, candidates=candidates, builder=_get_or_build)
            _chain_gateways[chain_key] = chain
            logger.info(
                "LLM gateway[%s]: fallback chain (%s)",
                task,
                " -> ".join(str(c.get("profile_name") or c["profile_id"]) for c in candidates),
            )
        return chain
    return _get_or_build(candidates[0])


def reset_gateway() -> None:
    """Reset cached gateways (config/binding/fallback changes; used by tests)."""
    _gateways.clear()
    _chain_gateways.clear()
