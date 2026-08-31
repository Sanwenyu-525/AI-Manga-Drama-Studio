// P2-E3-T03 — ChangeSetPanel:
//   1. renders the run's change records (tool label / revision / before→after
//      diff, active-version pseudo field rendered as the 激活版本切换 note)
//   2. 撤销 posts to /agent/change-sets/{id}/undo with {force:false}
//   3. an empty change-set list renders nothing
//   4. 撤销全部 posts to /agent/runs/{runId}/change-sets/undo and lists the
//      per-item results (undone/conflict/skipped → Chinese labels)
//   5. a 409 undo conflict shows the conflicting fields + 强制恢复 (force:true)
//   6. 跳转镜头 drives the selection store and emits studio:select-shot
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import * as client from "../api/client";
import type { AgentChangeSet } from "../api/types";
import { ChangeSetPanel } from "../features/director/ChangeSetPanel";
import { useSelectionStore } from "../stores/selectionStore";

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
  useSelectionStore.getState().clearShots();
});

const updateChangeSet: AgentChangeSet = {
  id: "cs_1",
  project_id: "p1",
  run_id: "run_1",
  source: "agent",
  tool: "update_shot",
  entity_type: "shot",
  entity_id: "shot_abc12345",
  revision_before: 3,
  revision_after: 4,
  before: { image_prompt: "旧提示词", shot_type: "medium" },
  after: { image_prompt: "新提示词", shot_type: "close_up" },
  undone: false,
  undone_at: null,
  undone_by_change_set_id: null,
  created_at: "2026-08-31T10:00:00Z",
};

const generateChangeSet: AgentChangeSet = {
  ...updateChangeSet,
  id: "cs_2",
  tool: "generate_image",
  before: { active_image_asset_id: "asset_old" },
  after: { active_image_asset_id: "asset_new" },
};

const undoneChangeSet: AgentChangeSet = {
  ...updateChangeSet,
  id: "cs_3",
  undone: true,
  undone_at: "2026-08-31T11:00:00Z",
  undone_by_change_set_id: "cs_9",
};

describe("ChangeSetPanel (rendering)", () => {
  it("renders the run's change records with tool labels, revisions and diffs", async () => {
    const get = vi.fn().mockResolvedValue([updateChangeSet, generateChangeSet]);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ChangeSetPanel runId="run_1" />, { wrapper });
    expect(await screen.findByText("修改镜头")).toBeTruthy();
    expect(screen.getByText("生成图片（版本切换）")).toBeTruthy();
    expect(screen.getAllByText(/版本：v3 → v4/).length).toBe(2);
    expect(screen.getByText("画面提示词")).toBeTruthy();
    expect(screen.getByText("旧提示词")).toBeTruthy();
    expect(screen.getByText("新提示词")).toBeTruthy();
    // the active-version pseudo field is not rendered as a diff row…
    expect(screen.queryByText("active_image_asset_id")).toBeNull();
    // …but as the 激活版本切换 note
    expect(screen.getByText("激活版本切换")).toBeTruthy();
    expect(get).toHaveBeenCalledWith("/agent/change-sets?run_id=run_1");
  });

  it("shows the 已撤销 badge + compensating reference for undone rows", async () => {
    const get = vi.fn().mockResolvedValue([undoneChangeSet]);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ChangeSetPanel runId="run_1" />, { wrapper });
    expect(await screen.findByText("已撤销")).toBeTruthy();
    expect(screen.getByText(/补偿变更 cs_9/)).toBeTruthy();
    // undone rows offer no 撤销 button
    expect(screen.queryByText("撤销")).toBeNull();
  });

  it("renders nothing when the change-set list is empty", async () => {
    const get = vi.fn().mockResolvedValue([]);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper, qc } = makeWrapper();
    const { container } = render(<ChangeSetPanel runId="run_1" />, { wrapper });
    await waitFor(() => expect(qc.getQueryData(["changeSets", "run", "run_1"])).toEqual([]));
    expect(container.querySelector(".change-set-panel")).toBeNull();
  });
});

describe("ChangeSetPanel (undo actions)", () => {
  it("撤销 posts to /agent/change-sets/{id}/undo with {force:false}", async () => {
    const get = vi.fn().mockResolvedValue([updateChangeSet]);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<ChangeSetPanel runId="run_1" />, { wrapper });
    fireEvent.click(await screen.findByText("撤销"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/agent/change-sets/cs_1/undo", { force: false }));
  });

  it("撤销全部 posts to /agent/runs/{runId}/change-sets/undo and lists per-item results", async () => {
    const get = vi.fn().mockResolvedValue([updateChangeSet]);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({
      results: [
        { change_set_id: "cs_1", status: "undone" },
        { change_set_id: "cs_2", status: "conflict" },
        { change_set_id: "cs_3", status: "skipped" },
      ],
    });
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<ChangeSetPanel runId="run_1" />, { wrapper });
    fireEvent.click(await screen.findByText("撤销全部"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/agent/runs/run_1/change-sets/undo"));
    expect(await screen.findByText("已撤销")).toBeTruthy();
    expect(screen.getByText("冲突")).toBeTruthy();
    expect(screen.getByText("跳过")).toBeTruthy();
  });

  it("shows the conflict fields + 强制恢复 on a 409 and retries with force:true", async () => {
    const get = vi.fn().mockResolvedValue([updateChangeSet]);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const conflictError = new ApiError(409, {
      error: { code: "CHANGE_SET_CONFLICT", message: "撤销冲突", details: { conflicting_fields: ["image_prompt"] } },
    });
    const post = vi.fn().mockRejectedValueOnce(conflictError).mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<ChangeSetPanel runId="run_1" />, { wrapper });
    fireEvent.click(await screen.findByText("撤销"));
    expect(await screen.findByText(/撤销冲突：image_prompt/)).toBeTruthy();
    fireEvent.click(screen.getByText("强制恢复"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/agent/change-sets/cs_1/undo", { force: true }));
  });

  it("跳转镜头 selects the shot and emits studio:select-shot", async () => {
    const get = vi.fn().mockResolvedValue([updateChangeSet]);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");
    const { wrapper } = makeWrapper();
    render(<ChangeSetPanel runId="run_1" />, { wrapper });
    fireEvent.click(await screen.findByText("跳转镜头"));
    expect(useSelectionStore.getState().selection.shotIds).toEqual(["shot_abc12345"]);
    const emitted = dispatchSpy.mock.calls.map((call) => call[0]).find((event) => event.type === "studio:select-shot");
    expect(emitted).toBeTruthy();
  });
});
