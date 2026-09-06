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

describe("agentStore.C 真流式（阶段 + 增量 + 取消）", () => {
  it("startRun → understand running；stageEvent 推进时间线", () => {
    const s = useAgentStore.getState();
    s.startRun("run_1", "改成近景");
    expect(useAgentStore.getState().stages.find((x) => x.stage === "understand")?.status).toBe("running");
    useAgentStore.getState().stageEvent("understand", "改成近景");
    useAgentStore.getState().stageEvent("load_context");
    const stages = useAgentStore.getState().stages;
    expect(stages.find((x) => x.stage === "understand")?.status).toBe("done");
    expect(stages.find((x) => x.stage === "load_context")?.status).toBe("done");
  });

  it("appendStream 拼接增量；done 收尾；同名 tool 只点亮第一个 pending", () => {
    const s = useAgentStore.getState();
    s.startRun("run_2", "改");
    s.setPlan("改", [
      { tool: "get_shot", args: {} },
      { tool: "get_shot", args: {} },
    ]);
    s.appendStream("understand", "已理解", false);
    s.appendStream("understand", "意图", true);
    expect(useAgentStore.getState().streamText).toBe("已理解意图");
    expect(useAgentStore.getState().streamDone).toBe(true);
    s.toolStarted("get_shot", "abc123");
    const running = useAgentStore.getState().tools.filter((t) => t.status === "running");
    expect(running).toHaveLength(1);
  });

  it("runCancelled 置 cancelled（非 failed）；reset 清空会话", () => {
    const s = useAgentStore.getState();
    s.startRun("run_3", "改");
    s.runCancelled();
    expect(useAgentStore.getState().status).toBe("cancelled");
    s.reset();
    const after = useAgentStore.getState();
    expect(after.runId).toBeNull();
    expect(after.messages).toEqual([]);
    expect(after.streamText).toBe("");
    expect(after.stages.every((x) => x.status === "pending")).toBe(true);
  });
});
