"""FallbackLLMGateway — 任务级显式降级链（P-LLM-Fallback）。

设计原则（用户定调）：**不静默掩盖模型故障**。落到实现的四条硬约束：

1. **链是显式配置的**：候选顺序来自 `llm_profiles.json` 的 `task_fallbacks`
   （设置页编辑），默认空 —— 空链 = 单候选 = 完全保持原有 fail-fast 行为。
   未配置的连接（如激活连接）绝不会"悄悄"进入已绑定任务的链。
2. **降级必宣告**：每次真实降级（主连接失败 → 后备连接服务）都 publish
   `llm.fallback.used` 事件（WS 可见）并打 WARNING 日志；主连接直接成功不发事件。
3. **结果可归因**：chat() 的 ChatResponse 标注 `served_by_profile(_name)`，
   API / 日志 / 下游消费方永远知道实际是谁在服务。
4. **失败不吞**：整条链耗尽时抛 ProviderUnavailableError，details 里带
   `attempted`（每条候选的错误明细）—— 绝不把模型故障包装成"看起来正常"。

流式语义：仅在**首个分片产出前**失败才降级；一旦开始出流，中途失败原样上抛
（无法回滚已发出的分片，静默重放反而是掩盖）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import TypeVar

from pydantic import BaseModel

from app.core.logging import get_logger
from app.events.bus import EVENT_LLM_FALLBACK_USED, StudioEvent, bus
from app.llm.gateway import LLMGateway
from app.llm.messages import ChatMessage, ChatOptions, ChatResponse

logger = get_logger("llm.fallback")

T = TypeVar("T", bound=BaseModel)

# 链候选：来自 registry 的一条连接解析结果（profile_id 必有，其余为连接四元组）。
Candidate = dict


class FallbackLLMGateway:
    """实现 LLMGateway 协议的降级链包装。候选按顺序尝试，首个成功者服务。"""

    def __init__(
        self,
        *,
        task: str,
        candidates: Sequence[Candidate],
        builder: Callable[[Candidate], LLMGateway],
    ) -> None:
        self._task = task
        self._candidates = list(candidates)
        self._builder = builder

    # ---------------- 内部：failover 驱动 ----------------

    async def _failover(self, call: Callable[[LLMGateway], Awaitable]) -> tuple[object, Candidate]:
        """Try candidates in order; return (result, served_candidate). Announces real failovers."""
        attempts: list[dict] = []
        last_error: Exception | None = None
        for candidate in self._candidates:
            try:
                gateway = self._builder(candidate)
            except Exception as exc:  # noqa: BLE001 — 构造失败（如缺 base_url）= 该候选不可用
                attempts.append(
                    {"profile_id": candidate.get("profile_id"), "error": f"配置无效：{exc}"}
                )
                last_error = exc
                continue
            try:
                result = await call(gateway)
            except Exception as exc:  # noqa: BLE001 — 任何失败都记入链路明细后试下一候选
                attempts.append(
                    {
                        "profile_id": candidate.get("profile_id"),
                        "profile_name": candidate.get("profile_name"),
                        "error": str(exc)[:300],
                    }
                )
                last_error = exc
                continue
            if attempts:
                self._announce(candidate, attempts)
            return result, candidate
        raise self._exhausted(attempts, last_error)

    def _announce(self, served: Candidate, attempts: list[dict]) -> None:
        """降级宣告：WARNING 日志 + WS 事件。这是本模块存在的意义，不是可选装饰。"""
        logger.warning(
            "LLM fallback used: task=%s served_by=%s (%s); failed_candidates=%s",
            self._task,
            served.get("profile_name") or served.get("profile_id"),
            served.get("model"),
            [(a.get("profile_id"), a.get("error")) for a in attempts],
        )
        bus.publish(
            StudioEvent(
                event_type=EVENT_LLM_FALLBACK_USED,
                entity_type="llm_profile",
                entity_id=str(served.get("profile_id") or ""),
                payload={
                    "task": self._task,
                    "served_by_profile_id": served.get("profile_id"),
                    "served_by_profile_name": served.get("profile_name"),
                    "failed": attempts,
                },
            )
        )

    def _exhausted(self, attempts: list[dict], last_error: Exception | None) -> Exception:
        from app.core.errors import ProviderUnavailableError

        detail = "; ".join(f"{a.get('profile_id')}: {a.get('error')}" for a in attempts)
        return ProviderUnavailableError(
            f"LLM 降级链全部失败（task={self._task}，尝试 {len(attempts)} 条连接）：{detail or last_error}",
            {"task": self._task, "attempted": attempts},
        )

    # ---------------- LLMGateway 协议 ----------------

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        options: ChatOptions | None = None,
    ) -> ChatResponse:
        result, served = await self._failover(lambda gw: gw.chat(messages, options=options))
        response: ChatResponse = result  # type: ignore[assignment]
        response.served_by_profile = served.get("profile_id")
        response.served_by_profile_name = served.get("profile_name")
        return response

    async def invoke(self, system: str, prompt: str) -> str:
        result, _ = await self._failover(lambda gw: gw.invoke(system, prompt))
        return str(result)

    async def structured(self, schema: type[T], system: str, prompt: str) -> T:
        result, _ = await self._failover(lambda gw: gw.structured(schema, system, prompt))
        return result  # type: ignore[return-value]

    async def structured_list(self, schema: type[T], system: str, prompt: str) -> list[T]:
        result, _ = await self._failover(lambda gw: gw.structured_list(schema, system, prompt))
        return result  # type: ignore[return-value]

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        attempts: list[dict] = []
        for candidate in self._candidates:
            try:
                gateway = self._builder(candidate)
            except Exception as exc:  # noqa: BLE001
                attempts.append({"profile_id": candidate.get("profile_id"), "error": f"配置无效：{exc}"})
                continue
            try:
                aiter = gateway.stream(system, prompt)
                first = await aiter.__anext__()
            except StopAsyncIteration:
                if attempts:
                    self._announce(candidate, attempts)
                return
            except Exception as exc:  # noqa: BLE001 — 首片前的失败才可降级
                attempts.append(
                    {
                        "profile_id": candidate.get("profile_id"),
                        "profile_name": candidate.get("profile_name"),
                        "error": str(exc)[:300],
                    }
                )
                continue
            if attempts:
                self._announce(candidate, attempts)
            yield first
            # 已出流：中途失败原样上抛（见模块 docstring 流式语义）。
            async for chunk in aiter:
                yield chunk
            return
        raise self._exhausted(attempts, None)
