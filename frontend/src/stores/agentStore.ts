// Agent UI state (frontend-ux §84): mirrors AgentRun lifecycle; driven by WS events.

import { create } from "zustand";

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
      tools: s.tools.map((t) =>
        t.tool === tool ? { ...t, status: "running", detail: targetId } : t,
      ),
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
      const messages =
        clarification
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

  reset: () => set({ runId: null, status: "idle", objective: null, steps: [], tools: [], result: null }),
}));
