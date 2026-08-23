"""Fake intent/plan parsing — deterministic rules so the Director chain runs keyless.

DEV-ONLY (不要用于生产): 本模块仅作为 `FakeLLMGateway` 的确定性实现，供测试与无 key
的开发环境使用。关键词规则（6 景别 + 6 情绪 + 时长秒数）**不是**真实语言理解，无法覆盖
自然语言的组合意图。生产/真实数据验证必须 `STUDIO_LLM_MODE=openai` 走真实模型。

降级策略: 与 `continuity_service.semantic_check` 对齐 —— fake 路径 = 规则输出（确定、
可测试）；openai 路径 = 真实结构化生成。两者共用同一 schema（ProductionIntent /
DirectorPlan），因此业务层（graph 的 understand/plan 节点）感知不到底层是哪条路径。

Extends FakeLLMGateway to answer DirectorPlan structured calls by parsing the user
message with simple keyword rules (agent-director §70: Structured Planner works even
with weak tool-calling models — here it is fully deterministic).
"""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel

from app.domain.agent import DirectorPlan, ProductionIntent, ToolOperation

T = TypeVar("T", bound=BaseModel)

_SHOT_TYPE_KEYWORDS = {
    "近景": "close_up",
    "特写": "extreme_close_up",
    "中景": "medium",
    "全景": "full",
    "远景": "wide",
    "大远景": "extreme_wide",
}

_EMOTION_KEYWORDS = {
    "紧张": "tense",
    "平静": "calm",
    "兴奋": "excited",
    "悲伤": "sad",
    "愤怒": "angry",
    "温柔": "gentle",
}


def parse_director_plan(message: str, selection_shot_id: str | None) -> DirectorPlan:
    """Rule-based planner mirroring the LLM prompt behavior (used by FakeLLMGateway)."""
    text = message.strip().lower()
    operations: list[ToolOperation] = []

    # --- resolve target ---
    target_ref: str | None = None
    m = re.search(r"(?:第|镜头|shot\s*)?(\d{1,3})\s*镜", text)
    if m:
        target_ref = f"shot_number:{m.group(1)}"
    elif selection_shot_id:
        target_ref = selection_shot_id

    wants_generate = any(k in text for k in ("生成", "重生成", "出图", "重新生成"))
    wants_update = any(k in text for k in ("改成", "改", "换成", "调整", "设置"))

    shot_type = next((v for k, v in _SHOT_TYPE_KEYWORDS.items() if k in text), None)
    emotion = next((v for k, v in _EMOTION_KEYWORDS.items() if k in text), None)
    duration_m = re.search(r"(\d+(?:\.\d+)?)\s*秒", text)

    if wants_update and not shot_type and not emotion and not duration_m:
        # generic "改一下" without a concrete instruction
        return DirectorPlan(
            objective="修改镜头",
            steps=[],
            requires_clarification=True,
            clarification_message="你希望怎么改？例如：改成近景、情绪改紧张、时长改 3 秒。",
        )

    if wants_update or shot_type or emotion or duration_m:
        if not target_ref:
            return DirectorPlan(
                objective="修改镜头",
                steps=[],
                requires_clarification=True,
                clarification_message="请先选中一个镜头，或说明要修改第几镜。",
            )
        args: dict = {}
        if shot_type:
            args["shot_type"] = shot_type
        if emotion:
            args["emotion"] = emotion
        if duration_m:
            args["duration"] = float(duration_m.group(1))
        operations.append(ToolOperation(tool="update_shot", arguments={"shot_id": target_ref, "patch": args}))

    if wants_generate:
        if not target_ref:
            return DirectorPlan(
                objective="生成图片",
                steps=[],
                requires_clarification=True,
                clarification_message="请先选中一个镜头，或说明要生成第几镜。",
            )
        operations.append(ToolOperation(tool="generate_image", arguments={"shot_id": target_ref}))

    if not operations:
        # fall back to a read query of the selected shot
        if selection_shot_id:
            operations.append(ToolOperation(tool="get_shot", arguments={"shot_id": selection_shot_id}))
        else:
            return DirectorPlan(
                objective="查询",
                steps=[],
                requires_clarification=True,
                clarification_message="请说明你想做什么，例如：改成近景、重新生成、检查镜头。",
            )

    return DirectorPlan(objective=text[:80] or "执行用户指令", steps=operations)


def parse_production_intent(message: str, selection_shot_id: str | None) -> ProductionIntent:
    plan = parse_director_plan(message, selection_shot_id)
    intent_type = "modify" if any(op.tool == "update_shot" for op in plan.steps) else "generate"
    if any(op.tool == "get_shot" for op in plan.steps):
        intent_type = "query"
    return ProductionIntent(
        intent_type=intent_type,
        target_type="shot",
        target_reference=plan.steps[0].arguments.get("shot_id") if plan.steps else None,
        instruction=message,
        batch=False,
        destructive=False,
        operations=plan.steps,
    )
