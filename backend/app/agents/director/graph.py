"""Director Graph (agent-director §9, §75; mvp-spec §79): LangGraph orchestration.

MVP graph: START → Understand → LoadContext → Plan → Execute → Review → END.

Execution pattern: Structured Planner + Deterministic Executor (agent-director §70) —
the LLM outputs typed ProductionIntent / DirectorPlan; ToolExecutor runs them through
Studio Services. No LLM tool-calling loop in MVP.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.tools import ToolExecutor
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
from app.llm.factory import create_gateway
from app.llm.gateway import LLMGateway

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


def _stage(state: DirectorState, stage: str) -> None:
    """Record current_stage in the run store (P1-E3-T02: GET run shows live stage)."""
    from app.agents.director.runner import set_run_stage

    set_run_stage(state.get("run_id", ""), stage)


def _cancelled(state: DirectorState) -> bool:
    """Cooperative cancel token (P1-E3-T02): consulted at every node + tool boundary."""
    from app.agents.director.runner import is_cancel_requested

    return is_cancel_requested(state.get("run_id", ""))


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
    _stage(state, "understand")
    if _cancelled(state):
        return {**state, "status": "cancelled"}
    llm: LLMGateway = create_gateway("director")
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
    """Resolve the target shot and load Minimum Sufficient Context (agent-director §18, §27).

    P1-E3-T01: resolution is ownership-checked and ambiguity-aware; ambiguous /
    not-found / rejected targets are reported to the executor instead of guessing.
    """
    _stage(state, "load_context")
    if _cancelled(state):
        return {**state, "status": "cancelled"}
    intent = ProductionIntent.model_validate(state["intent"])
    selection = state.get("selection") or {}
    project_id = state.get("project_id", "")
    shot_ids = selection.get("shot_ids") or []
    scene_id = selection.get("scene_id")

    factory = db_session_module.session_factory_provider()
    with factory() as session:
        from app.services.context_service import ContextService

        context_service = ContextService(session)
        resolution = context_service.resolve_shot_reference(
            project_id, intent.target_reference, shot_ids, scene_id
        )
        context: dict[str, Any] = {
            "resolved_shot_id": resolution.shot_id,
            "selection": selection,
            "resolution_status": resolution.status,
        }
        if resolution.message:
            context["resolution_message"] = resolution.message
        if resolution.shot_id:
            context["shot"] = context_service.get_shot_context(resolution.shot_id)
        # P7-T005/6/7: attach a budgeted, typed context via ContextResolver (shot_planning)
        # so the resolver integration is exercised and the LLM gets a token-capped block.
        from app.agents.context_resolver import ContextResolver

        resolver = ContextResolver(session)
        context["resolved_context"] = resolver.resolve(
            "shot_planning",
            project_id,
            shot_id=resolution.shot_id,
            scene_id=scene_id,
        )

    return {**state, "context": context}


async def plan_node(state: DirectorState) -> DirectorState:
    """Build the DirectorPlan. Fake mode: intent.operations carry the plan already;
    real mode: LLM refines the plan with context (same schema, Structured Planner)."""
    _stage(state, "plan")
    if _cancelled(state):
        return {**state, "status": "cancelled"}
    intent = ProductionIntent.model_validate(state["intent"])
    context = state.get("context") or {}

    if intent.operations:
        # planner (LLM or rules) already produced the operation list
        plan = DirectorPlan(objective=intent.instruction or intent.intent_type, steps=intent.operations)
    else:
        llm: LLMGateway = create_gateway("director")
        plan = await llm.structured(  # type: ignore[return-value]
            DirectorPlan,
            UNDERSTAND_SYSTEM_PROMPT,
            f"用户指令：{state.get('user_message')}\n上下文：{context}\n请给出操作计划。",
        )

    _publish(EVENT_AGENT_PLAN_CREATED, state, {"plan": plan.model_dump()})
    return {**state, "plan": plan.model_dump()}


async def execute_node(state: DirectorState) -> DirectorState:
    _stage(state, "execute")
    if _cancelled(state):
        return {**state, "status": "cancelled", "tool_results": [], "final_result": {"summary": "已取消。", "clarification": None}}
    plan = DirectorPlan.model_validate(state["plan"])
    if plan.requires_clarification:
        return {**state, "status": "completed", "tool_results": [], "final_result": {"clarification": plan.clarification_message}}

    context = state.get("context") or {}
    resolved_shot_id = context.get("resolved_shot_id")
    if resolved_shot_id is None and plan.steps:
        # P1-E3-T01: ambiguous / not found / forged target — never guess, ask.
        # 自主迭代 07：场景级工具（update_scene / get_scene_shots / 检查通道）不需要
        # 镜头解析——只有镜头定位工具才强制 resolved_shot_id。
        shot_tools = {"get_shot", "update_shot", "generate_image", "continuity_fix"}
        if any(op.tool in shot_tools for op in plan.steps):
            message = (
                context.get("resolution_message")
                or plan.clarification_message
                or "请先选中一个镜头，或说明要修改第几镜。"
            )
            return {
                **state,
                "status": "completed",
                "tool_results": [],
                "final_result": {"clarification": message},
            }

    results: list[dict[str, Any]] = []
    status = state.get("status", "running")

    factory = db_session_module.session_factory_provider()
    with factory() as session:
        executor = ToolExecutor(
            session,
            project_id=state.get("project_id"),
            resolved_shot_id=resolved_shot_id,
            run_id=state.get("run_id"),
        )
        for step in plan.steps:
            # P1-E3-T02: tool boundary cancel check — stop before the NEXT tool,
            # no new side effects after cancellation.
            if _cancelled(state):
                status = "cancelled"
                break
            # resolve symbolic references ('shot_number:N') to real ids (context node resolved them)
            args = dict(step.arguments)
            ref = args.get("shot_id")
            if isinstance(ref, str) and ref.startswith("shot_number:"):
                args["shot_id"] = resolved_shot_id
            op = ToolOperation(tool=step.tool, arguments=args)
            _publish(EVENT_AGENT_TOOL_STARTED, state, {"tool": op.tool, "target": {"type": "shot", "id": op.arguments.get("shot_id")}})
            result = executor.execute(op)
            _publish(
                EVENT_AGENT_TOOL_COMPLETED,
                state,
                {"tool": op.tool, "success": result.success, "changed_fields": result.changed_fields, "error": result.error},
            )
            results.append({"tool": op.tool, "arguments": op.arguments, "result": result.model_dump()})

            # P7-T013: update_shot emitted a Proposal and parked the run in
            # WAITING_HUMAN. Suspend the graph for a human decision; the resume
            # value ({\"decision\": \"approve\"|\"reject\"}) is returned here.
            if result.proposal_created:
                status = "waiting_human"
                decision = interrupt(
                    {
                        "reason": "awaiting human approval",
                        "proposal_ids": [result.proposal_id],
                        "target_id": result.entity_id,
                    }
                )
                # Record the human decision on the tool result for the audit trail.
                results[-1]["decision"] = (decision or {}).get("decision") if isinstance(decision, dict) else decision
                # After approval we continue to the NEXT planned step (if any,
                # e.g. generate_image); rejection simply skips the mutation.

    return {**state, "status": status, "tool_results": results}


async def review_node(state: DirectorState) -> DirectorState:
    """Task-level review (agent-director §36-37): summarize what happened for the user."""
    _stage(state, "review")
    results = state.get("tool_results") or []
    plan = state.get("plan") or {}

    # P7-T017: a run suspended awaiting a human decision must keep waiting_human —
    # review must never silently complete it.
    if state.get("status") == "waiting_human":
        return {
            **state,
            "status": "waiting_human",
            "final_result": {
                "summary": "等待人工审批。",
                "tool_count": len(results),
                "failed": 0,
                "generation_submitted": 0,
                "details": results,
                "clarification": None,
            },
        }

    # P1-E3-T02: a cancelled run keeps its cancelled status — review must never
    # overwrite it with completed/failed (contradictory terminal states).
    if state.get("status") == "cancelled":
        return {
            **state,
            "status": "cancelled",
            "final_result": {
                "summary": "已取消。",
                "tool_count": len(results),
                "failed": 0,
                "generation_submitted": 0,
                "details": results,
                "clarification": None,
            },
        }

    # P1-E3-T01: a clarification produced by execute_node (ambiguous / not found /
    # rejected target) is the final word — never replace it with an empty summary.
    # Keep the standard result shape (tool_count etc.) for contract stability.
    if (state.get("final_result") or {}).get("clarification"):
        return {
            **state,
            "status": "completed",
            "final_result": {
                "summary": "需要澄清。",
                "tool_count": 0,
                "failed": 0,
                "generation_submitted": 0,
                "details": [],
                "clarification": state["final_result"]["clarification"],
            },
        }
    failures = [r for r in results if not r["result"].get("success")]
    # P2-E3-T02: count only actually-submitted generations — a step that only
    # CREATED a proposal (or was already decided on a resume re-run) queued nothing.
    generated = [
        r
        for r in results
        if r["tool"] == "generate_image" and (r["result"].get("data") or {}).get("generation_id")
    ]

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
            if r["result"].get("proposal_created"):
                parts.append("已提交镜头修改方案待审批")
            else:
                fields = r["result"].get("changed_fields") or []
                parts.append(f"已修改镜头 {r['arguments'].get('shot_id', '')[-4:]}（{', '.join(fields)}）" if fields else "镜头无实际变化")
        elif tool == "generate_image":
            if r["result"].get("proposal_created"):
                parts.append("已提交图片生成方案待审批（R2）")
            else:
                parts.append("已提交图片生成任务（不等待完成）")
        elif tool == "get_shot":
            parts.append("已读取镜头信息")
    return "；".join(parts) or "没有执行任何操作。"


# ---------- graph ----------

def build_director_graph(checkpointer=None):
    """Compile the Director graph. P7-T004: a persisted checkpointer keeps the
    execution state (thread_id = run_id) across the proposal interrupt so a run
    can be resumed after a WAITING_HUMAN pause (and after restart)."""
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
    return builder.compile(checkpointer=checkpointer)


def _default_checkpointer():
    """A module-scoped SqliteCheckpointSaver on the app data dir.

    In tests the client fixture overrides session_factory_provider, but the
    checkpointer path is fixed to the app data dir. To keep tests isolated we
    build the graph with a checkpointer lazily; tests that need resume use
    build_director_graph(checkpointer=...) with an in-memory/file-backed saver.
    """
    from app.agents.checkpointers.sqlite_saver import SqliteCheckpointSaver
    from app.core.config import settings

    return SqliteCheckpointSaver(settings.data_dir / "agent_checkpoints.db")


director_graph = build_director_graph(checkpointer=_default_checkpointer())
