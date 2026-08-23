// P7-T019 — AIDirectorPanel WAITING_HUMAN badge + panel hint + proposal card area.
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { AIDirectorPanel } from "../features/director/AIDirectorPanel";
import { useAgentStore } from "../stores/agentStore";
import { MemoryRouter } from "react-router-dom";

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return {
    qc,
    W: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useAgentStore.getState().reset();
});

describe("AIDirectorPanel (WAITING_HUMAN)", () => {
  it("shows the 等待审批 badge and the approval hint", async () => {
    useAgentStore.getState().approvalRequired("run_1", "update_shot");
    const get = vi.fn().mockImplementation((p: string) => {
      if (p.endsWith("/proposals")) return Promise.resolve([]);
      return Promise.resolve({
        id: "run_1",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        pending_proposals: [],
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { W } = wrapper();
    render(
      <MemoryRouter initialEntries={["/projects/p1/episodes/e1/script"]}>
        <AIDirectorPanel />
      </MemoryRouter>,
      { wrapper: W },
    );
    // badge: agent-status shows 等待审批 (normalized from store waiting_human)
    expect(await screen.findByText("等待审批")).toBeTruthy();
    // panel hint text is present
    expect(screen.getByText(/等待审批——请在上方 Proposal 卡片/)).toBeTruthy();
  });

  it("renders the 待审批 Proposal review section when a run is pending", async () => {
    useAgentStore.getState().approvalRequired("run_2", "update_shot");
    const get = vi.fn().mockImplementation((p: string) => {
      if (p.endsWith("/proposals"))
        return Promise.resolve([
          {
            id: "prop_1",
            tool: "update_shot",
            target_type: "shot",
            target_id: "shot_xyz",
            base_revision: 2,
            changes: { image_prompt: { from: "a", to: "b" } },
            status: "pending",
          },
        ]);
      return Promise.resolve({
        id: "run_2",
        status: "WAITING_HUMAN",
        project_id: "p1",
        plan: null,
        approval: null,
        change_set_id: null,
        result: null,
        pending_proposals: [],
        created_at: "",
        updated_at: "",
      });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { W } = wrapper();
    render(
      <MemoryRouter initialEntries={["/projects/p1/episodes/e1/script"]}>
        <AIDirectorPanel />
      </MemoryRouter>,
      { wrapper: W },
    );
    expect(await screen.findByText("待审批 Proposal")).toBeTruthy();
    expect(await screen.findByText("修改镜头")).toBeTruthy();
  });
});
