// 自主迭代 05 — agentStore.hydrate：刷新后从服务器 run 水合上一次会话。
import { beforeEach, describe, expect, it } from "vitest";
import type { AgentRunRead } from "../api/types";
import { useAgentStore } from "../stores/agentStore";

function makeRun(overrides: Partial<AgentRunRead> = {}): AgentRunRead {
  return {
    id: "run_9",
    project_id: "p1",
    status: "completed",
    current_stage: null,
    plan: {
      objective: "把镜头改成近景",
      steps: [{ tool: "update_shot", arguments: { shot_type: "close_up" } }],
      requires_clarification: false,
      clarification_message: null,
    },
    approval: null,
    change_set_id: null,
    result: { summary: "已改近景。" },
    pending_proposals: [],
    messages: [
      { role: "user", content: "把这个镜头改成近景" },
      { role: "assistant", content: "已改近景。" },
    ],
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

beforeEach(() => {
  useAgentStore.getState().reset();
});

describe("agentStore.hydrate（刷新恢复）", () => {
  it("completed run → 水合 runId/status/messages/plan/result", () => {
    useAgentStore.getState().hydrate(makeRun());
    const state = useAgentStore.getState();
    expect(state.runId).toBe("run_9");
    expect(state.status).toBe("completed");
    expect(state.objective).toBe("把镜头改成近景");
    expect(state.steps).toEqual([{ tool: "update_shot", args: { shot_type: "close_up" } }]);
    expect(state.tools).toEqual([{ tool: "update_shot", status: "pending" }]);
    expect(state.messages).toEqual([
      { role: "user", content: "把这个镜头改成近景" },
      { role: "assistant", content: "已改近景。" },
    ]);
    expect(state.result).toEqual({ summary: "已改近景。" });
  });

  it("后端 running → 归一为 executing；waiting_human → waiting_human", () => {
    useAgentStore.getState().hydrate(makeRun({ status: "running" as AgentRunRead["status"] }));
    expect(useAgentStore.getState().status).toBe("executing");
    useAgentStore.getState().reset();
    useAgentStore.getState().hydrate(makeRun({ status: "waiting_human" }));
    expect(useAgentStore.getState().status).toBe("waiting_human");
  });

  it("无 plan/result/messages 的裸 run → 安全水合（空列表、空目标）", () => {
    useAgentStore.getState().hydrate(makeRun({ plan: null, result: null, messages: [] }));
    const state = useAgentStore.getState();
    expect(state.runId).toBe("run_9");
    expect(state.steps).toEqual([]);
    expect(state.tools).toEqual([]);
    expect(state.messages).toEqual([]);
    expect(state.objective).toBeNull();
  });
});
