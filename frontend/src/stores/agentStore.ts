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

  startRun: (runId: string, userMessage: string) => void;
  setPlan: (objective: string, steps: AgentPlanStep[]) => void;
  toolStarted: (tool: string, targetId?: string) => void;
  toolCompleted: (tool: string, success: boolean, changedFields?: string[], error?: string) => void;
  runCompleted: (result: Record<string, unknown> | null) => void;
  runFailed: (error?: string) => void;
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

export const useAgentStore = create<AgentState>((set) => ({
  runId: null,
  status: "idle",
  objective: null,
  steps: [],
  tools: [],
  messages: [],
  result: null,

  startRun: (runId, userMessage) =>
    set((s) => ({
      runId,
      status: "thinking",
      objective: null,
      steps: [],
      tools: [],
      result: null,
      messages: [...s.messages, { role: "user", content: userMessage }],
    })),

  setPlan: (objective, steps) =>
    set({
      status: "planning",
      objective,
      steps,
      tools: steps.map((step) => ({ tool: step.tool, status: "pending" })),
    }),

  toolStarted: (tool, targetId) =>
    set((s) => ({
      status: "executing",
      tools: s.tools.map((t) => (t.tool === tool ? { ...t, status: "running", detail: targetId } : t)),
    })),

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
      return { status: "completed", result, messages };
    }),

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
    }),

  reset: () => set({ runId: null, status: "idle", objective: null, steps: [], tools: [], result: null }),
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
