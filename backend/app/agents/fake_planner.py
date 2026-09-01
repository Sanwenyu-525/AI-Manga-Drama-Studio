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

# 自主迭代 07：场景级指令识别（目标词 + 环境值词 → update_scene）。
_SCENE_TARGET_KEYWORDS = ("场景", "这场戏", "这一场", "这场")
_TIME_OF_DAY_VALUES = ("夜晚", "深夜", "傍晚", "黄昏", "清晨", "白天")
_LIGHTING_VALUES = ("明亮", "昏暗", "柔和", "月光", "霓虹")
_WEATHER_VALUES = ("下雨", "雨天", "下雪", "雪天", "晴天", "阴天")
_SCENE_MOOD_WORDS = ("紧张", "温馨", "压抑", "轻松", "欢快", "肃杀")


def _scene_env_patch(text: str) -> dict:
    """从场景指令提取环境字段 patch（确定性；每字段取首个命中值）。"""
    patch: dict = {}
    for value in _TIME_OF_DAY_VALUES:
        if value in text:
            patch["time_of_day"] = value
            break
    for value in _LIGHTING_VALUES:
        if value in text:
            patch["lighting"] = value
            break
    if any(k in text for k in ("下雨", "雨天")):
        patch["weather"] = "雨"
    elif any(k in text for k in ("下雪", "雪天")):
        patch["weather"] = "雪"
    elif "晴天" in text:
        patch["weather"] = "晴"
    elif "阴天" in text:
        patch["weather"] = "阴"
    if "氛围" in text or "基调" in text:
        for value in _SCENE_MOOD_WORDS:
            if value in text:
                patch["mood"] = value
                break
    return patch


def parse_director_plan(message: str, selection_shot_id: str | None, selection_scene_id: str | None = None) -> DirectorPlan:
    """Rule-based planner mirroring the LLM prompt behavior (used by FakeLLMGateway)."""
    text = message.strip().lower()
    operations: list[ToolOperation] = []

    # --- 场景级指令优先（自主迭代 07）：目标指向场景 + 有环境值 → update_scene ---
    is_scene_target = any(k in text for k in _SCENE_TARGET_KEYWORDS)
    scene_patch = _scene_env_patch(text) if is_scene_target else {}
    if is_scene_target:
        if not scene_patch:
            return DirectorPlan(
                objective="修改场景",
                steps=[],
                requires_clarification=True,
                clarification_message="你希望怎么改场景？例如：把这场戏改成夜晚、氛围改紧张、光照改昏暗。",
            )
        if not selection_scene_id:
            return DirectorPlan(
                objective="修改场景",
                steps=[],
                requires_clarification=True,
                clarification_message="请先选中一个场景（在分镜板选择该场景）。",
            )
        operations.append(
            ToolOperation(tool="update_scene", arguments={"scene_id": selection_scene_id, "patch": scene_patch})
        )
        return DirectorPlan(objective=text[:80] or "执行用户指令", steps=operations)

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


def parse_production_intent(message: str, selection_shot_id: str | None, selection_scene_id: str | None = None) -> ProductionIntent:
    plan = parse_director_plan(message, selection_shot_id, selection_scene_id)
    intent_type = "modify" if any(op.tool in ("update_shot", "update_scene") for op in plan.steps) else "generate"
    if any(op.tool == "get_shot" for op in plan.steps):
        intent_type = "query"
    return ProductionIntent(
        intent_type=intent_type,
        target_type="scene" if any(op.tool == "update_scene" for op in plan.steps) else "shot",
        target_reference=plan.steps[0].arguments.get("shot_id") or plan.steps[0].arguments.get("scene_id") if plan.steps else None,
        instruction=message,
        batch=False,
        destructive=False,
        operations=plan.steps,
    )
