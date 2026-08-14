"""Director Graph (agent-director §9, §75; mvp-spec §79): LangGraph orchestration.

MVP graph: START → Understand → LoadContext → Plan → Execute → Review → END.

Execution pattern: Structured Planner + Deterministic Executor (agent-director §70) —
the LLM outputs typed ProductionIntent / DirectorPlan; ToolExecutor runs them through
Studio Services. No LLM tool-calling loop in MVP.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.logging import get_logger
from app.db import session as db_session_module
from app.domain.agent import DirectorPlan, ProductionIntent, ToolOperation
from app.events.bus import (
    EVENT_AGENT_PLAN_CREATED,
    EVENT_AGENT_TOOL_COMPLETED,
    EVENT_AGENT_TOOL_STARTED,
    StudioEvent,
    bus,
)
from app.llm.gateway import LLMGateway
from app.llm.factory import create_gateway
from app.agents.tools import TOOL_SCHEMAS, ToolExecutor, ToolResult

logger = get_logger("agent.director")

UNDERSTAND_SYSTEM_PROMPT = (
    "你是 AI 漫剧 Studio 的导演。把用户的自然语言指令解析为结构化意图。"
    "支持：query / modify / generate。目标可以是 shot（镜头）。"
    "如果用户说『这个』『它』且未指明编号，用 selection 提供的信息。"
    "当用户要求修改但未说明具体改法时，输出空的 operations 并要求澄清。"
    "严格遵守输出 JSON 结构。"
)


class DirectorState(TypedDict, total=False):
    # identity (from API)
    run_id: str
    project_id: str
    session_id: str
    user_message: str
    selection: dict[str, Any]

    # understanding / context
    intent: dict[str, Any] | None
    context: dict[str, Any] | None

    # planning / execution
    plan: dict[str, Any] | None
    tool_results: list[dict[str, Any]]

    # outcome
    status: str
    final_result: dict[str, Any] | None


def _publish(event_type: str, state: DirectorState, payload: dict[str, Any] | None = None) -> None:
    bus.publish(
        StudioEvent(
            event_type=event_type,
            entity_type="agent_run",
            entity_id=state.get("run_id", ""),
            project_id=state.get("project_id"),
            payload=payload or {},
        )
    )


# ---------- nodes ----------

async def understand_node(state: DirectorState) -> DirectorState:
    llm: LLMGateway = create_gateway()
    message = state.get("user_message", "")
    selection = state.get("selection") or {}
    shot_ids = selection.get("shot_ids") or []
    prompt = (
        f"用户指令：{message}\n"
        f"当前 UI 选择：scene={selection.get('scene_id')}, shots={shot_ids}\n"
        "请解析意图。"
    )
    intent = await llm.structured(ProductionIntent, UNDERSTAND_SYSTEM_PROMPT, prompt)  # type: ignore[return-value]
    logger.info("run %s intent=%s ops=%d", state.get("run_id"), intent.intent_type, len(intent.operations))
    return {**state, "intent": intent.model_dump()}


async def load_context_node(state: DirectorState) -> DirectorState:
    """Resolve the target shot and load Minimum Sufficient Context (agent-director §18, §27)."""
    intent = ProductionIntent.model_validate(state["intent"])
    selection = state.get("selection") or {}
    project_id = state.get("project_id", "")
    shot_ids = selection.get("shot_ids") or []

    factory = db_session_module.session_factory_provider()
    with factory() as session:
        from app.services.context_service import ContextService

        context_service = ContextService(session)
        shot_id = context_service.resolve_shot_reference(project_id, intent.target_reference, shot_ids)
        context: dict[str, Any] = {"resolved_shot_id": shot_id, "selection": selection}
        if shot_id:
            context["shot"] = context_service.get_shot_context(shot_id)

    return {**state, "context": context}


async def plan_node(state: DirectorState) -> DirectorState:
    """Build the DirectorPlan. Fake mode: intent.operations carry the plan already;
    real mode: LLM refines the plan with context (same schema, Structured Planner)."""
    intent = ProductionIntent.model_validate(state["intent"])
    context = state.get("context") or {}

    if intent.operations:
        # planner (LLM or rules) already produced the operation list
        plan = DirectorPlan(objective=intent.instruction or intent.intent_type, steps=intent.operations)
    else:
        llm: LLMGateway = create_gateway()
        plan = await llm.structured(  # type: ignore[return-value]
            DirectorPlan,
            UNDERSTAND_SYSTEM_PROMPT,
            f"用户指令：{state.get('user_message')}\n上下文：{context}\n请给出操作计划。",
        )

    _publish(EVENT_AGENT_PLAN_CREATED, state, {"plan": plan.model_dump()})
    return {**state, "plan": plan.model_dump()}


async def execute_node(state: DirectorState) -> DirectorState:
    plan = DirectorPlan.model_validate(state["plan"])
    if plan.requires_clarification:
        return {**state, "status": "completed", "tool_results": [], "final_result": {"clarification": plan.clarification_message}}

    context = state.get("context") or {}
    resolved_shot_id = context.get("resolved_shot_id")
    results: list[dict[str, Any]] = []

    factory = db_session_module.session_factory_provider()
    with factory() as session:
        executor = ToolExecutor(session)
        for step in plan.steps:
            # resolve symbolic references ('shot_number:N') to real ids (context node resolved them)
            args = dict(step.arguments)
            ref = args.get("shot_id")
            if isinstance(ref, str) and ref.startswith("shot_number:"):
                if resolved_shot_id is None:
                    results.append(
                        {
                            "tool": step.tool,
                            "arguments": args,
                            "result": ToolResult(
                                success=False, error="Could not resolve the referenced shot."
                            ).model_dump(),
                        }
                    )
                    continue
                args["shot_id"] = resolved_shot_id
            op = ToolOperation(tool=step.tool, arguments=args)
            _publish(EVENT_AGENT_TOOL_STARTED, state, {"tool": op.tool, "target": {"type": "shot", "id": op.arguments.get("shot_id")}})
            result: ToolResult = executor.execute(op)
            _publish(
                EVENT_AGENT_TOOL_COMPLETED,
                state,
                {"tool": op.tool, "success": result.success, "changed_fields": result.changed_fields, "error": result.error},
            )
            results.append({"tool": op.tool, "arguments": op.arguments, "result": result.model_dump()})

    return {**state, "tool_results": results}


async def review_node(state: DirectorState) -> DirectorState:
    """Task-level review (agent-director §36-37): summarize what happened for the user."""
    results = state.get("tool_results") or []
    plan = state.get("plan") or {}
    failures = [r for r in results if not r["result"].get("success")]
    generated = [r for r in results if r["tool"] == "generate_image" and r["result"].get("success")]

    final: dict[str, Any] = {
        "summary": _summarize(results),
        "tool_count": len(results),
        "failed": len(failures),
        "generation_submitted": len(generated),
        "details": results,
        "clarification": plan.get("clarification_message") if plan.get("requires_clarification") else None,
    }
    return {**state, "status": "completed" if not failures else "failed", "final_result": final}


def _summarize(results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for r in results:
        tool = r["tool"]
        if tool == "update_shot":
            fields = r["result"].get("changed_fields") or []
            parts.append(f"已修改镜头 {r['arguments'].get('shot_id', '')[-4:]}（{', '.join(fields)}）" if fields else "镜头无实际变化")
        elif tool == "generate_image":
            parts.append("已提交图片生成任务（不等待完成）")
        elif tool == "get_shot":
            parts.append("已读取镜头信息")
    return "；".join(parts) or "没有执行任何操作。"


# ---------- graph ----------

def build_director_graph():
    builder = StateGraph(DirectorState)
    builder.add_node("understand", understand_node)
    builder.add_node("load_context", load_context_node)
    builder.add_node("plan", plan_node)
    builder.add_node("execute", execute_node)
    builder.add_node("review", review_node)
    builder.add_edge(START, "understand")
    builder.add_edge("understand", "load_context")
    builder.add_edge("load_context", "plan")
    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "review")
    builder.add_edge("review", END)
    return builder.compile()


director_graph = build_director_graph()
