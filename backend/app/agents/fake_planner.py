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
# 连续性修复意图识别：planner 只发 shot_id（warning_id 由执行器按镜头自动解析，
# 真实 LLM 也可经 context.open_warnings 直引 warning_id）。
_CONTINUITY_KEYWORDS = ("连续性", "接不上", "穿帮", "不连贯")
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


def _continuity_target_and_patch(
    text: str, selection_shot_id: str | None
) -> tuple[str | None, bool, dict]:
    """连续性分支的目标与 patch 解析（复用镜头关键词规则；patch 可为空）。"""
    m = re.search(r"(?:第|镜头|shot\s*)?(\d{1,3})\s*镜", text)
    target_ref: str | None = f"shot_number:{m.group(1)}" if m else selection_shot_id
    wants_generate = any(k in text for k in ("生成", "重生成", "出图", "重新生成"))
    patch: dict = {}
    shot_type = next((v for k, v in _SHOT_TYPE_KEYWORDS.items() if k in text), None)
    if shot_type:
        patch["shot_type"] = shot_type
    emotion = next((v for k, v in _EMOTION_KEYWORDS.items() if k in text), None)
    if emotion:
        patch["emotion"] = emotion
    duration_m = re.search(r"(\d+(?:\.\d+)?)\s*秒", text)
    if duration_m:
        patch["duration"] = float(duration_m.group(1))
    return target_ref, wants_generate, patch


# 批量结构分支：删除/新建关键词，或一句含多个镜头编号 → 逐分句解析多操作。
_DELETE_KEYWORDS = ("删除", "删掉", "去掉", "移除")
_CREATE_KEYWORDS = ("新建", "新增")
# 压缩/合并需要看到全场镜头（planner 无 DB）：fake 路径诚实澄清，真机经 context.scene_shots 规划。
_COMPRESS_KEYWORDS = ("压缩", "精简", "合并", "节奏")
_MAX_BATCH_OPS = 5


def _clause_op(
    clause: str, selection_shot_id: str | None, selection_scene_id: str | None
) -> ToolOperation | str | None:
    """Parse one clause. Returns an op, None (no-op clause), or "NEED_TARGET"."""
    m = re.search(r"(?:第|镜头|shot\s*)?(\d{1,3})\s*镜", clause)
    target_ref: str | None = f"shot_number:{m.group(1)}" if m else selection_shot_id
    wants_generate = any(k in clause for k in ("生成", "重生成", "出图", "重新生成"))
    wants_update = any(k in clause for k in ("改成", "改", "换成", "调整", "设置"))
    shot_type = next((v for k, v in _SHOT_TYPE_KEYWORDS.items() if k in clause), None)
    emotion = next((v for k, v in _EMOTION_KEYWORDS.items() if k in clause), None)
    duration_m = re.search(r"(\d+(?:\.\d+)?)\s*秒", clause)

    if any(k in clause for k in _DELETE_KEYWORDS):
        if not target_ref:
            return "NEED_TARGET"
        return ToolOperation(tool="delete_shot", arguments={"shot_id": target_ref})
    if any(k in clause for k in _CREATE_KEYWORDS):
        if not selection_scene_id:
            return "NEED_TARGET"
        patch: dict = {}
        if shot_type:
            patch["shot_type"] = shot_type
        if emotion:
            patch["emotion"] = emotion
        if duration_m:
            patch["duration"] = float(duration_m.group(1))
        return ToolOperation(
            tool="create_shot", arguments={"scene_id": selection_scene_id, "shot": patch}
        )
    if wants_update or shot_type or emotion or duration_m:
        if not target_ref:
            return "NEED_TARGET"
        args: dict = {}
        if shot_type:
            args["shot_type"] = shot_type
        if emotion:
            args["emotion"] = emotion
        if duration_m:
            args["duration"] = float(duration_m.group(1))
        return ToolOperation(tool="update_shot", arguments={"shot_id": target_ref, "patch": args})
    if wants_generate:
        if not target_ref:
            return "NEED_TARGET"
        return ToolOperation(tool="generate_image", arguments={"shot_id": target_ref})
    return None


def _parse_batch_plan(
    text: str, selection_shot_id: str | None, selection_scene_id: str | None
) -> DirectorPlan | None:
    """Multi-op plan, or None when the message is not a batch/structure intent."""
    numbers = re.findall(r"(?:第|镜头|shot\s*)?(\d{1,3})\s*镜", text)
    structural = any(k in text for k in _DELETE_KEYWORDS + _CREATE_KEYWORDS)
    if len(numbers) < 2 and not structural:
        return None
    if any(k in text for k in _COMPRESS_KEYWORDS) and len(numbers) < 2 and not structural:
        return DirectorPlan(
            objective="压缩场景",
            steps=[],
            requires_clarification=True,
            clarification_message="压缩需要明确保留/删除哪些镜头（我看不到全场分镜表）。例如：删除第9镜；或把第8镜改成近景。",
        )
    clauses = [c for c in re.split(r"[，。；、？！\n]|然后|再|并", text) if c.strip()]
    operations: list[ToolOperation] = []
    for clause in clauses[:_MAX_BATCH_OPS]:
        op = _clause_op(clause, selection_shot_id, selection_scene_id)
        if op == "NEED_TARGET":
            return DirectorPlan(
                objective="批量修改",
                steps=[],
                requires_clarification=True,
                clarification_message="请先选中目标镜头/场景，或在每句中说明第几镜（例如：删除第9镜）。",
            )
        if op is not None:
            operations.append(op)
    if not operations:
        return None
    if len(clauses) > _MAX_BATCH_OPS:
        operations = operations[:_MAX_BATCH_OPS]
    return DirectorPlan(objective=text[:80] or "执行用户指令", steps=operations)


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

    # --- 批量结构分支（删除/新建/多编号一句）：逐分句多操作 ---
    batch = _parse_batch_plan(text, selection_shot_id, selection_scene_id)
    if batch is not None:
        return batch

    # --- 连续性修复：关键词 → continuity_fix（只带 shot_id，warning 由执行器解析） ---
    if any(k in text for k in _CONTINUITY_KEYWORDS):
        target_ref, wants_generate, shot_patch = _continuity_target_and_patch(text, selection_shot_id)
        if not target_ref:
            return DirectorPlan(
                objective="修复连续性",
                steps=[],
                requires_clarification=True,
                clarification_message="哪两镜接不上？请先选中一个镜头，或说明要修复第几镜的连续性（我会查找该镜头的开放连续性警告）。",
            )
        operations.append(
            ToolOperation(tool="continuity_fix", arguments={"shot_id": target_ref, "patch": shot_patch})
        )
        if wants_generate:
            operations.append(ToolOperation(tool="generate_image", arguments={"shot_id": target_ref}))
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
    tools = {op.tool for op in plan.steps}
    intent_type = "modify" if tools & {"update_shot", "update_scene"} else "generate"
    if "continuity_fix" in tools:
        intent_type = "review"
    if "create_shot" in tools or "reorder_shots" in tools:
        intent_type = "create"
    if "delete_shot" in tools:
        intent_type = "delete"
    if "get_shot" in tools and len(plan.steps) == 1:
        intent_type = "query"
    return ProductionIntent(
        intent_type=intent_type,
        target_type="scene" if any(op.tool in ("update_scene", "reorder_shots") for op in plan.steps) else "shot",
        target_reference=plan.steps[0].arguments.get("shot_id") or plan.steps[0].arguments.get("scene_id") if plan.steps else None,
        instruction=message,
        batch=len(plan.steps) > 1,
        destructive="delete_shot" in tools,
        operations=plan.steps,
    )
