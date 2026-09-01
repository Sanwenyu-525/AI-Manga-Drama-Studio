// 自主迭代 06 — ScenePropertiesEditor：场景环境编辑（时段/光照/天气/氛围/描述）。
// PATCH /scenes/{id} {revision, patch}；脏检查；409 冲突提示；复用 ApiErrorPanel。
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Scene } from "../api/types";
import * as client from "../api/client";
import { ScenePropertiesEditor } from "../features/storyboard/ScenePropertiesEditor";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const scene: Scene = {
  id: "sc1",
  episode_id: "ep1",
  scene_number: 1,
  name: "天台",
  location_id: null,
  time_of_day: "白天",
  lighting: null,
  weather: null,
  mood: "轻松",
  description: null,
  scene_order: null,
  status: "active",
  shot_count: 3,
  revision: 2,
  created_at: "",
  updated_at: "",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ScenePropertiesEditor", () => {
  it("从场景预填字段并展示", () => {
    const { wrapper } = makeWrapper();
    render(<ScenePropertiesEditor sceneId="sc1" scene={scene} onClose={() => {}} />, { wrapper });
    expect(screen.getByLabelText("时段")).toBeTruthy();
    expect((screen.getByLabelText("时段") as HTMLInputElement).value).toBe("白天");
    expect((screen.getByLabelText("氛围") as HTMLInputElement).value).toBe("轻松");
  });

  it("未改动时保存按钮禁用；改动后提交 PATCH /scenes/{id}", async () => {
    const patch = vi.fn().mockResolvedValue(scene);
    vi.spyOn(client.api, "patch").mockImplementation(patch);
    const { wrapper } = makeWrapper();
    render(<ScenePropertiesEditor sceneId="sc1" scene={scene} onClose={() => {}} />, { wrapper });
    // 未改动 → 保存禁用
    expect((screen.getByRole("button", { name: /保存/ }) as HTMLButtonElement).disabled).toBe(true);
    // 改动时段
    fireEvent.change(screen.getByLabelText("时段"), { target: { value: "夜晚" } });
    fireEvent.click(screen.getByRole("button", { name: /保存/ }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith("/scenes/sc1", {
        revision: 2,
        patch: {
          time_of_day: "夜晚",
          lighting: "",
          weather: "",
          mood: "轻松",
          description: "",
        },
      }),
    );
  });

  it("409 冲突 → 显示冲突提示并保留编辑区（不静默）", async () => {
    const err = new Error("409 Conflict: scene was modified");
    vi.spyOn(client.api, "patch").mockRejectedValue(err);
    const { wrapper } = makeWrapper();
    render(<ScenePropertiesEditor sceneId="sc1" scene={scene} onClose={() => {}} />, { wrapper });
    fireEvent.change(screen.getByLabelText("时段"), { target: { value: "夜晚" } });
    fireEvent.click(screen.getByRole("button", { name: /保存/ }));
    expect(await screen.findByText(/409 冲突/)).toBeTruthy();
    expect(screen.getByText(/请关闭后重新打开编辑/)).toBeTruthy();
  });

  it("保存成功后调用 onClose", async () => {
    const patch = vi.fn().mockResolvedValue(scene);
    vi.spyOn(client.api, "patch").mockImplementation(patch);
    const onClose = vi.fn();
    const { wrapper } = makeWrapper();
    render(<ScenePropertiesEditor sceneId="sc1" scene={scene} onClose={onClose} />, { wrapper });
    fireEvent.change(screen.getByLabelText("时段"), { target: { value: "夜晚" } });
    fireEvent.click(screen.getByRole("button", { name: /保存/ }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
