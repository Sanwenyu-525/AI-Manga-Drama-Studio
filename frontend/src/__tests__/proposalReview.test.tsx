// P7-T019/020/021 — Proposal Review:
//   1. normalizeProposalChanges accepts BOTH backend changes shapes
//   2. ProposalReview renders tool/target/from→to diffs and calls approve/reject
//   3. conflict proposals show the conflict warning
//   4. resume (继续执行) calls /resume once no proposal is pending
//   5. EventRouter refreshes run/proposal queries on proposal.* and approval events
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EventRouter } from "../events/socket";
import type { AgentProposal } from "../api/types";
import * as client from "../api/client";
import * as agentLib from "../lib/agentProposals";
import { ProposalReview } from "../features/director/ProposalReview";
import { useAgentStore } from "../stores/agentStore";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useAgentStore.getState().reset();
});

// ---- 1. changes shape tolerance ----
describe("normalizeProposalChanges", () => {
  it("parses the object-map shape { field: { from, to } }", () => {
    const diffs = agentLib.normalizeProposalChanges({ image_prompt: { from: "旧", to: "新" } } as never);
    expect(diffs).toEqual([{ field: "image_prompt", from: "旧", to: "新" }]);
  });

  it("parses multiple fields in the object-map shape", () => {
    const diffs = agentLib.normalizeProposalChanges({
      duration: { from: 6, to: 4 },
      shot_type: { from: "medium", to: "close_up" },
    } as never);
    expect(diffs).toEqual([
      { field: "duration", from: 6, to: 4 },
      { field: "shot_type", from: "medium", to: "close_up" },
    ]);
  });

  it("parses the single-item shape { field, from, to }", () => {
    const diffs = agentLib.normalizeProposalChanges({ field: "image_prompt", from: "旧", to: "新" } as never);
    expect(diffs).toEqual([{ field: "image_prompt", from: "旧", to: "新" }]);
  });

  it("returns [] for null/empty payloads", () => {
    expect(agentLib.normalizeProposalChanges(undefined)).toEqual([]);
    expect(agentLib.normalizeProposalChanges(null)).toEqual([]);
    expect(agentLib.normalizeProposalChanges({})).toEqual([]);
  });

  it("fieldLabel maps shot fields to Chinese", () => {
    expect(agentLib.fieldLabel("image_prompt")).toBe("画面提示词");
    expect(agentLib.fieldLabel("unknown_x")).toBe("unknown_x");
  });
});

// ---- 2. ProposalReview rendering + actions ----
const pendingShot: AgentProposal = {
  id: "prop_1",
  tool: "update_shot",
  target_type: "shot",
  target_id: "shot_abc123",
  base_revision: 3,
  status: "pending",
  changes: { image_prompt: { from: "旧提示词", to: "新提示词" } } as never,
};
const approvedShot: AgentProposal = { ...pendingShot, id: "prop_2", status: "approved" };
const conflictedShot: AgentProposal = { ...pendingShot, id: "prop_3", status: "conflict" };

describe("ProposalReview (pending)", () => {
  it("fetches proposals and renders tool/target/base_revision + from→to diff", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([pendingShot]);
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    expect(await screen.findByText("修改镜头")).toBeTruthy();
    expect(screen.getByText(/目标：镜头/)).toBeTruthy();
    expect(screen.getByText(/基准版本：v3/)).toBeTruthy();
    expect(screen.getByText("画面提示词")).toBeTruthy();
    expect(screen.getByText("旧提示词")).toBeTruthy();
    expect(screen.getByText("新提示词")).toBeTruthy();
    expect(screen.getAllByText("待审批").length).toBeGreaterThan(0);
  });

  it("approve posts to /agent/proposals/{id}/approve", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([pendingShot]);
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    fireEvent.click(await screen.findByText("批准"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/agent/proposals/prop_1/approve"));
  });

  it("reject posts to /agent/proposals/{id}/reject", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([pendingShot]);
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    fireEvent.click(await screen.findByText("拒绝"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/agent/proposals/prop_1/reject"));
  });

  it("shows the approved badge for resolved proposals and hides actions", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([approvedShot]);
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    expect(await screen.findByText("已批准")).toBeTruthy();
    expect(screen.queryByText("批准")).toBeNull();
  });
});

describe("ProposalReview (conflict)", () => {
  it("renders the conflict banner and a refresh button", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([conflictedShot]);
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    expect(await screen.findByText(/proposal 冲突/)).toBeTruthy();
    expect(screen.getByText("刷新")).toBeTruthy();
  });
  it("hides approve/reject for a conflicted proposal but shows conflict status", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([conflictedShot]);
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    expect(await screen.findByText("冲突")).toBeTruthy();
    expect(screen.queryByText("批准")).toBeNull();
  });
  it("renders ApiErrorPanel in case of a run-detail fetch error (panel does not crash)", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([pendingShot]);
      return Promise.reject(new Error("boom")); // runs detail fails
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    expect(await screen.findByText("boom")).toBeTruthy();
  });
});

describe("ProposalReview (resume)", () => {
  it("shows 继续执行 when WAITING_HUMAN and no proposal is pending, and calls /resume", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([approvedShot]); // all resolved
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    fireEvent.click(await screen.findByText("继续执行"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/agent/runs/run_1/resume", { decision: "approve" }));
  });
  it("hides 继续执行 while a proposal is still pending", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/proposals")) return Promise.resolve([pendingShot]);
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ProposalReview runId="run_1" fallbackStatus="WAITING_HUMAN" />, { wrapper });
    expect(await screen.findByText("待审批")).toBeTruthy();
    expect(screen.queryByText("继续执行")).toBeNull();
  });
});

describe("agentStore approval/resume", () => {
  it("approvalRequired sets WAITING_HUMAN status and pushes a hint message", () => {
    useAgentStore.getState().approvalRequired("run_1", "update_shot", { image_prompt: {} });
    expect(useAgentStore.getState().status).toBe("waiting_human");
    expect(useAgentStore.getState().runId).toBe("run_1");
    const lastMsg = useAgentStore.getState().messages[useAgentStore.getState().messages.length - 1];
    expect(lastMsg?.content).toContain("需要审批");
  });
  it("resumeRun returns status to executing", () => {
    useAgentStore.getState().approvalRequired("run_1");
    useAgentStore.getState().resumeRun();
    expect(useAgentStore.getState().status).toBe("executing");
  });
});

describe("EventRouter proposal/approval events", () => {
  it("approval.required sets waiting_human and invalidates run+proposals", async () => {
    const qc = new QueryClient();
    const invalidationSpy = vi.spyOn(qc, "invalidateQueries");
    const router = new EventRouter(qc);
    router.handle({
      event_id: "e1",
      event_type: "agent.approval.required",
      event_version: 1,
      project_id: "p1",
      entity_type: "proposal",
      entity_id: "prop_1",
      timestamp: "2026-01-01",
      sequence: 3,
      payload: { run_id: "run_1", proposal_id: "prop_1", tool: "update_shot", changes: {} },
    });
    expect(useAgentStore.getState().status).toBe("waiting_human");
    expect(invalidationSpy).toHaveBeenCalledWith({ queryKey: ["agentRun", "run_1"] });
    expect(invalidationSpy).toHaveBeenCalledWith({ queryKey: ["proposals", "run_1"] });
  });
  it("proposal.created invalidates run+proposals", () => {
    const qc = new QueryClient();
    // prevent flush warning
    const spy = vi.spyOn(qc, "invalidateQueries");
    const router = new EventRouter(qc);
    router.handle({
      event_id: "e2",
      event_type: "agent.proposal.created",
      event_version: 1,
      project_id: "p1",
      entity_type: "proposal",
      entity_id: "prop_1",
      timestamp: "2026-01-01",
      sequence: 4,
      payload: { run_id: "run_2" },
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["agentRun", "run_2"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["proposals", "run_2"] });
  });
  it("run.updated with WAITING_HUMAN sets store status", () => {
    const qc = new QueryClient();
    const router = new EventRouter(qc);
    router.handle({
      event_id: "e3",
      event_type: "agent.run.updated",
      event_version: 1,
      project_id: "p1",
      entity_type: "run",
      entity_id: "run_1",
      timestamp: "2026-01-01",
      sequence: 5,
      payload: { run_id: "run_1", status: "WAITING_HUMAN" },
    });
    expect(useAgentStore.getState().status).toBe("waiting_human");
  });
});
