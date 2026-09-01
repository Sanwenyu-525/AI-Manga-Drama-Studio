// BatchActionBar (autonomous-iteration-02): bulk update / delete / reorder flows.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../api/client";
import { BatchActionBar, moveBlock } from "../features/storyboard/BatchActionBar";
import type { ShotBatchResult, ShotSummary } from "../api/types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function makeShots(n: number): ShotSummary[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `shot_${i}`,
    shot_number: i + 1,
    shot_type: "medium",
    duration: 3,
    status: "draft",
    dirty_state: "clean",
    thumbnail_url: null,
    character_names: [],
    active_generation: null,
  }));
}

function batchResult(overrides: Partial<ShotBatchResult> = {}): ShotBatchResult {
  return {
    scene_id: "sc1",
    requested: 2,
    succeeded: 2,
    failed: 0,
    results: [],
    ...overrides,
  };
}

function renderBar(shots = makeShots(4), selectedIds = ["shot_0", "shot_1"]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onNotice = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <BatchActionBar sceneId="sc1" shots={shots} selectedIds={selectedIds} onNotice={onNotice} />
    </QueryClientProvider>,
  );
  return { onNotice };
}

describe("moveBlock", () => {
  it("moves the selected block up as a unit", () => {
    expect(moveBlock(["a", "b", "c", "d"], ["b", "c"], -1)).toEqual(["b", "c", "a", "d"]);
  });
  it("moves the selected block down as a unit", () => {
    expect(moveBlock(["a", "b", "c", "d"], ["b", "c"], 1)).toEqual(["a", "d", "b", "c"]);
  });
  it("returns null at the top edge", () => {
    expect(moveBlock(["a", "b", "c"], ["a"], -1)).toBeNull();
  });
  it("returns null at the bottom edge", () => {
    expect(moveBlock(["a", "b", "c"], ["c"], 1)).toBeNull();
  });
});

describe("BatchActionBar", () => {
  it("shows the selection count", () => {
    renderBar();
    expect(screen.getByText("已选 2 镜")).toBeTruthy();
  });

  it("batch shot_type change posts the scene-scoped batch-update endpoint", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue(batchResult());
    renderBar();
    fireEvent.change(screen.getByLabelText("批量改景别"), { target: { value: "close_up" } });
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith("/scenes/sc1/shots/batch-update", {
      shot_ids: ["shot_0", "shot_1"],
      patch: { shot_type: "close_up" },
    });
  });

  it("front-move issues reorder with the full ordered id list", async () => {
    const patch = vi.spyOn(api, "patch").mockResolvedValue([]);
    renderBar(makeShots(4), ["shot_2", "shot_3"]);
    fireEvent.click(screen.getByRole("button", { name: /前移/ }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    // Block [shot_2, shot_3] moves one slot up: [s0, s2, s3, s1]
    expect(patch).toHaveBeenCalledWith("/scenes/sc1/shots/reorder", ["shot_0", "shot_2", "shot_3", "shot_1"]);
  });

  it("edge move shows a notice without calling reorder", () => {
    const patch = vi.spyOn(api, "patch").mockResolvedValue([]);
    const { onNotice } = renderBar(makeShots(3), ["shot_0"]);
    fireEvent.click(screen.getByRole("button", { name: /前移/ }));
    expect(patch).not.toHaveBeenCalled();
    expect(onNotice).toHaveBeenCalledWith("选中镜头已在一侧边界，无需移动");
  });

  it("delete requires confirmation and posts batch-delete", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const post = vi.spyOn(api, "post").mockResolvedValue(batchResult());
    renderBar();
    fireEvent.click(screen.getByRole("button", { name: /删除/ }));
    expect(confirm).toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: /删除/ }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith("/scenes/sc1/shots/batch-delete", { shot_ids: ["shot_0", "shot_1"] });
  });

  it("partial batch results surface a per-item notice", async () => {
    vi.spyOn(api, "post").mockResolvedValue(batchResult({ succeeded: 1, failed: 1 }));
    const { onNotice } = renderBar();
    fireEvent.change(screen.getByLabelText("批量改景别"), { target: { value: "wide" } });
    await waitFor(() => expect(onNotice).toHaveBeenCalledWith("已更新 1/2 个镜头，1 个失败"));
  });
});
