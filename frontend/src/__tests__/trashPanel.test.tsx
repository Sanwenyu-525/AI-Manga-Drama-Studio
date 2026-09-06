// P2-E2-T01 TrashPanel tests：删除行列表 + 逐行恢复 + 409 冲突可操作提示。
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ApiError } from "../api/client";
import type { TrashItem } from "../api/types";
import { TrashPanel } from "../features/project/TrashPanel";

function makeItems(): TrashItem[] {
  return [
    { entity_type: "shot", id: "sh1", name: "SH002", number: 2, parent_id: "sc1", deleted_at: "2026-09-06T02:00:00Z" },
    { entity_type: "scene", id: "sc1", name: "SC1", number: 1, parent_id: "ep1", deleted_at: "2026-09-06T01:00:00Z" },
  ];
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  const wrapper = ({ children }: { children?: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(<TrashPanel projectId="p1" />, { wrapper });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TrashPanel (P2-E2-T01)", () => {
  it("列出删除行并按实体恢复", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(makeItems() as never);
    const post = vi.fn().mockResolvedValue({ id: "sh1" });
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    renderPanel();
    expect(await screen.findByText("SH002")).toBeTruthy();
    expect(screen.getByText("SC1")).toBeTruthy();

    const buttons = await screen.findAllByRole("button", { name: /恢复/ });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/shots/sh1/restore"));
  });

  it("空回收站不渲染面板", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue([] as never);
    const { container } = renderPanel();
    await waitFor(() => expect(container.textContent ?? "").not.toContain("回收站"));
    expect(container.querySelector(".trash-panel")).toBeNull();
  });

  it("409 冲突显示可操作错误且不崩溃", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(makeItems() as never);
    const conflict = new ApiError(409, {
      error: { code: "CONFLICT", message: "编号被占用", details: { conflict: "number" } },
    });
    const post = vi.fn().mockRejectedValueOnce(conflict);
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    renderPanel();
    const buttons = await screen.findAllByRole("button", { name: /恢复/ });
    fireEvent.click(buttons[0]);
    expect(await screen.findByText(/编号被占用/)).toBeTruthy();
  });
});
