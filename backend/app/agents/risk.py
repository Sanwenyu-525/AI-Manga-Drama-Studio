"""Risk evaluation (agent-director §24, P2-E3-T02): every planned tool operation
is classified R0–R3 BEFORE it runs.

Levels (design ai-director §24):
- R0 Read: get_shot / get_scene_shots — auto.
- R1 Reversible Edit: update_shot — auto-apply per policy, recorded as a
  ChangeSet so it is undoable (P2-E3-T03). We deliberately do NOT require
  approval for every close-up edit (task risk note: 审批粒度过细会打断创作).
- R2 Expensive: generate_image — queues a generation task; approval required
  by default (configurable), with affected entity / task count / cost surfaced.
- R3 Destructive: no MVP tool maps here yet; the classifier is ready for
  delete/overwrite tools, which must always be approved.

The policy never trusts the planner's self-assessment: classification is
deterministic from (tool, arguments).
"""

from __future__ import annotations

from app.core.config import settings
from app.domain.agent import RiskAssessment, RISK_R0, RISK_R1, RISK_R2, RISK_R3

_READ_TOOLS = ("get_shot", "get_scene_shots", "check_workflow", "inspect_comfy")


def classify_tool_operation(tool: str, arguments: dict) -> RiskAssessment:
    """Deterministic R0–R3 classification of one planned tool operation."""
    if tool in _READ_TOOLS:
        return RiskAssessment(
            risk_level=RISK_R0,
            reason="只读操作，无写入。",
            affected_entities=[str(arguments.get("shot_id") or arguments.get("scene_id") or "")],
        )
    if tool == "update_shot":
        return RiskAssessment(
            risk_level=RISK_R1,
            reason="可逆编辑：通过 ChangeSet 记录，可撤销。",
            affected_entities=[str(arguments.get("shot_id") or "")],
            estimated_tasks=1,
        )
    if tool == "update_scene":
        return RiskAssessment(
            risk_level=RISK_R1,
            reason="可逆场景编辑：通过 ChangeSet 记录，可撤销；触发连续性重算。",
            affected_entities=[str(arguments.get("scene_id") or "")],
            estimated_tasks=1,
        )
    if tool == "generate_image":
        return RiskAssessment(
            risk_level=RISK_R2,
            reason="昂贵操作：将创建图片生成任务，占用生成资源。",
            affected_entities=[str(arguments.get("shot_id") or "")],
            estimated_tasks=1,
            # Local providers have no price list — show unknown, never fabricate.
            estimated_cost=None,
        )
    if tool == "continuity_fix":
        return RiskAssessment(
            risk_level=RISK_R1,
            reason="可逆修复：走 Proposal 审批，可撤销。",
            affected_entities=[str(arguments.get("shot_id") or "")],
            estimated_tasks=1,
        )
    # Unknown future tool — treat as destructive (fail safe: approval required).
    return RiskAssessment(
        risk_level=RISK_R3,
        reason="未识别的破坏性操作，必须人工审批。",
        affected_entities=[str(arguments.get("shot_id") or arguments.get("scene_id") or "")],
        irreversible=True,
    )


def requires_approval(assessment: RiskAssessment) -> bool:
    """Risk policy: R0/R1 auto-execute; R2 per settings; R3 always approval.

    R1 update_shot auto-applies WITH a ChangeSet (undo safety net), so the
    default flow is not interrupted by confirmation fatigue.
    """
    if assessment.risk_level in (RISK_R0, RISK_R1):
        return False
    if assessment.risk_level == RISK_R2:
        return not settings.agent_auto_approve_r2
    return True  # R3 (and anything unknown)


def approval_needed(tool: str, arguments: dict) -> bool:
    """Convenience: classify then apply the policy."""
    return requires_approval(classify_tool_operation(tool, arguments))


__all__ = [
    "classify_tool_operation",
    "requires_approval",
    "approval_needed",
    "RISK_R0",
    "RISK_R1",
    "RISK_R2",
    "RISK_R3",
]
