// 自主迭代 03 — LocationsSection（地点库）：列表 + MASTER 徽标 + 内联创建 + 删除。
// 视觉版本链由 EntityVersionBlock(kind="location") 承载（已在 entityVersionBlock.test 覆盖）。
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Location } from "../api/types";
import * as client from "../api/client";
import { LocationsSection } from "../features/libraries/LocationsSection";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { qc, wrapper };
}

const LOCATIONS: Location[] = [
  {
    id: "loc_1",
    project_id: "proj_1",
    name: "天台",
    description: "篮球场天台",
    visual_prompt: "rooftop basketball court, dusk",
    status: "active",
    revision: 1,
    master_version_id: "lv1",
    created_at: "",
    updated_at: "",
  },
  {
    id: "loc_2",
    project_id: "proj_1",
    name: "更衣室",
    description: null,
    visual_prompt: null,
    status: "active",
    revision: 1,
    master_version_id: null,
    created_at: "",
    updated_at: "",
  },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("LocationsSection", () => {
  it("列出地点并在有 MASTER 的地点显示徽标", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/projects/proj_1/locations") return Promise.resolve(LOCATIONS);
      if (path === "/projects/proj_1/documents") return Promise.resolve([]);
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<LocationsSection projectId="proj_1" />, { wrapper });
    expect(await screen.findByText("天台")).toBeTruthy();
    expect(screen.getByText("更衣室")).toBeTruthy();
    // 天台有 MASTER 版本 → 徽标；更衣室没有
    expect(screen.getAllByText("MASTER").length).toBeGreaterThanOrEqual(1);
  });

  it("内联创建地点：输入名称 → POST /projects/{id}/locations", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/projects/proj_1/locations") return Promise.resolve(LOCATIONS);
      if (path === "/projects/proj_1/documents") return Promise.resolve([]);
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({ id: "loc_3", name: "球场", project_id: "proj_1", revision: 1, master_version_id: null, description: null, visual_prompt: null, status: "active", created_at: "", updated_at: "" });
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<LocationsSection projectId="proj_1" />, { wrapper });
    await screen.findByText("天台");
    fireEvent.click(screen.getByRole("button", { name: "地点" })); // 内联创建行（标题按钮名含计数，不冲突）
    fireEvent.change(screen.getByPlaceholderText("地点名（必填）"), { target: { value: "球场" } });
    fireEvent.click(screen.getByLabelText("保存地点"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/projects/proj_1/locations", { name: "球场" }));
  });

  it("删除地点前二次确认，确认后 DELETE /locations/{id}", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/projects/proj_1/locations") return Promise.resolve([LOCATIONS[0]]);
      if (path === "/projects/proj_1/documents") return Promise.resolve([]);
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const del = vi.fn().mockResolvedValue({ id: "loc_1", deleted: true });
    vi.spyOn(client.api, "delete").mockImplementation(del);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { wrapper } = makeWrapper();
    render(<LocationsSection projectId="proj_1" />, { wrapper });
    // 展开编辑区（行内删除按钮）
    fireEvent.click(await screen.findByText("天台"));
    fireEvent.click(screen.getByText("删除"));
    await waitFor(() => expect(del).toHaveBeenCalledWith("/locations/loc_1"));
  });
});
