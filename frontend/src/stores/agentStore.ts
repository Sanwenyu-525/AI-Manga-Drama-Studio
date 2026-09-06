// Agent UI state (frontend-ux §84): mirrors AgentRun lifecycle; driven by WS events.
// 自主迭代 05：新增 hydrate —— 刷新后从 GET /agent/runs 水合上一次会话（恢复对话流）。

import { create } from "zustand";
import type { AgentRunRead } from "../api/types";

export interface AgentToolState {
  tool: string;
  status: "pending" | "running" | "done" | "failed";
  detail?: string;
}

export interface AgentPlanStep {
  tool: string;
  args: Record<string, unknown>;
}

export interface AgentMessage {
  role: "user" | "assistant";
  content: string;
}

/** C 真流式：graph 五阶段思考时间线（后端事件驱动，非本地猜测）。 */
export type AgentStage = "understand" | "load_context" | "plan" | "execute" | "review";

export interface AgentStageState {
  stage: AgentStage;
  status: "pending" | "running" | "done";
  detail?: string;
}

export const AGENT_STAGES: AgentStage[] = ["understand", "load_context", "plan", "execute", "review"];

export const AGENT_STAGE_LABELS: Record<AgentStage, string> = {
  understand: "理解意图",
  load_context: "加载上下文",
  plan: "制定计划",
  execute: "执行工具",
  review: "检查结果",
};

export type AgentStatus =
  | "idle"
  | "thinking"
  | "planning"
  | "executing"
  | "reviewing"
  | "cancelling"
  | "cancelled"
  | "waiting_human"
  | "completed"
  | "failed";

interface AgentState {
  runId: string | null;
  status: AgentStatus;
  objective: string | null;
  steps: AgentPlanStep[];
  tools: AgentToolState[];
  messages: AgentMessage[];
  result: Record<string, unknown> | null;
  /** C 真流式：思考时间线 + 打字机增量（WS 事件驱动）。 */
  stages: AgentStageState[];
  streamText: string;
  streamDone: boolean;

  startRun: (runId: string, userMessage: string) => void;
  setPlan: (objective: string, steps: AgentPlanStep[]) => void;
  toolStarted: (tool: string, targetId?: string) => void;
  toolCompleted: (tool: string, success: boolean, changedFields?: string[], error?: string) => void;
  runCompleted: (result: Record<string, unknown> | null) => void;
  runFailed: (error?: string) => void;
  /** 阶段事件（intent.resolved / context.loaded / review.started/completed…）。 */
  stageEvent: (stage: AgentStage, detail?: string) => void;
  /** run.stream 增量分片：拼接到打字机文本。 */
  appendStream: (stage: AgentStage, delta: string, done: boolean) => void;
  /** 取消终态（区别于失败：用户主动中断）。 */
  runCancelled: () => void;
  /** P7-T019/020: agent is paused awaiting human approval (WAITING_HUMAN). */
  approvalRequired: (runId: string, tool?: string, changes?: unknown) => void;
  /** P7-T020: update badge/status when a proposal change event arrives. */
  setRunStatus: (status: AgentStatus) => void;
  /** P7-T018: user resumed the run after review. */
  resumeRun: () => void;
  /** 自主迭代 05：刷新后从服务器 run 水合上一次会话。 */
  hydrate: (run: AgentRunRead) => void;
  reset: () => void;
}

const freshStages = (): AgentStageState[] => AGENT_STAGES.map((stage) => ({ stage, status: "pending" }));

function markStage(
  stages: AgentStageState[],
  stage: AgentStage,
  status: AgentStageState["status"],
  detail?: string,
): AgentStageState[] {
  const order = AGENT_STAGES.indexOf(stage);
  return stages.map((s) => {
    if (AGENT_STAGES.indexOf(s.stage) < order && s.status === "pending") return { ...s, status: "done" };
    if (s.stage !== stage) return s;
    return { ...s, status, detail: detail ?? s.detail };
  });
}

export const useAgentStore = create<AgentState>((set) => ({
  runId: null,
  status: "idle",
  objective: null,
  steps: [],
  tools: [],
  messages: [],
  result: null,
  stages: freshStages(),
  streamText: "",
  streamDone: false,

  startRun: (runId, userMessage) =>
    set((s) => ({
      runId,
      status: "thinking",
      objective: null,
      steps: [],
      tools: [],
      result: null,
      stages: markStage(freshStages(), "understand", "running"),
      streamText: "",
      streamDone: false,
      messages: [...s.messages, { role: "user", content: userMessage }],
    })),

  setPlan: (objective, steps) =>
    set((s) => ({
      status: "planning",
      objective,
      steps,
      tools: steps.map((step) => ({ tool: step.tool, status: "pending" })),
      stages: markStage(markStage(s.stages, "understand", "done"), "plan", "running"),
    })),

  toolStarted: (tool, targetId) =>
    set((s) => {
      // 同名 tool 并发时只点亮第一个 pending，避免整列一起跑。
      let lit = false;
      return {
        status: "executing",
        stages: markStage(markStage(s.stages, "plan", "done"), "execute", "running"),
        tools: s.tools.map((t) => {
          if (t.tool === tool && t.status === "pending" && !lit) {
            lit = true;
            return { ...t, status: "running" as const, detail: targetId ?? t.detail };
          }
          return t;
        }),
      };
    }),

  toolCompleted: (tool, success, changedFields, error) =>
    set((s) => ({
      tools: s.tools.map((t) =>
        t.tool === tool
          ? { ...t, status: success ? "done" : "failed", detail: error ?? changedFields?.join(", ") ?? t.detail }
          : t,
      ),
    })),

  runCompleted: (result) =>
    set((s) => {
      const summary = (result?.summary as string) ?? "完成。";
      const clarification = result?.clarification as string | undefined;
      const messages = clarification
        ? [...s.messages, { role: "assistant" as const, content: clarification }]
        : [...s.messages, { role: "assistant" as const, content: summary }];
      return {
        status: "completed",
        result,
        messages,
        stages: s.stages.map((st) => ({ ...st, status: "done" as const })),
        streamDone: true,
      };
    }),

  stageEvent: (stage, detail) =>
    set((s) => ({ stages: markStage(s.stages, stage, stage === "execute" ? "running" : "done", detail) })),

  appendStream: (stage, delta, done) =>
    set((s) => ({
      stages: markStage(s.stages, stage, done ? "done" : "running"),
      streamText: s.streamText + delta,
      streamDone: done ? true : s.streamDone,
    })),

  runCancelled: () =>
    set((s) => ({
      status: "cancelled",
      streamDone: true,
      messages: [...s.messages, { role: "assistant" as const, content: "已取消。" }],
    })),

  runFailed: (error) =>
    set((s) => ({
      status: "failed",
      result: { error },
      messages: [...s.messages, { role: "assistant", content: `执行失败：${error ?? "未知错误"}` }],
    })),

  // P7-T019: WAITING_HUMAN — the run is paused awaiting human review.
  approvalRequired: (runId, tool, changes) =>
    set((s) => ({
      runId,
      status: "waiting_human",
      result: null,
      messages: [
        ...s.messages,
        {
          role: "assistant",
          content: `AI 导演需要审批${tool ? `（工具：${tool}）` : ""}${changes ? "：镜头提案已生成" : ""}，请审批后继续。`,
        },
      ],
    })),

  // P7-T019/020: sync badge when a proposal/run event changes status.
  setRunStatus: (status) => set({ status }),

  // P7-T018: user resumed the run; execution proceeds (WS events refine it further).
  resumeRun: () =>
    set((s) => ({
      status: "executing",
      messages: [...s.messages, { role: "assistant", content: "已继续执行…" }],
    })),

  /** 自主迭代 05（刷新恢复）：从服务器 run 水合上一次会话（runId/status/messages/plan/result）。 */
  hydrate: (run) =>
    set({
      runId: run.id,
      status: normalizeRunStatus(run.status),
      objective: run.plan?.objective ?? null,
      steps: (run.plan?.steps ?? []).map((s) => ({ tool: s.tool, args: s.arguments })),
      tools: (run.plan?.steps ?? []).map((s) => ({ tool: s.tool, status: "pending" as const })),
      messages: run.messages ?? [],
      result: run.result ?? null,
      // 水合的是终态快照：时间线直接收尾，不重放流式。
      stages: freshStages().map((st) => ({ ...st, status: "done" as const })),
      streamText: "",
      streamDone: true,
    }),

  reset: () =>
    set({
      runId: null,
      status: "idle",
      objective: null,
      steps: [],
      tools: [],
      messages: [],
      result: null,
      stages: freshStages(),
      streamText: "",
      streamDone: false,
    }),
}));

/** 后端 run.status → 前端 store 状态归一（created/running → executing；等待审批统一 waiting_human）。 */
function normalizeRunStatus(status: string): AgentStatus {
  if (status === "completed" || status === "failed" || status === "cancelled" || status === "cancelling") {
    return status;
  }
  if (status === "waiting_human" || status === "waiting_approval" || status === "WAITING_HUMAN") {
    return "waiting_human";
  }
  return "executing"; // created / running / 其他瞬时态
}
