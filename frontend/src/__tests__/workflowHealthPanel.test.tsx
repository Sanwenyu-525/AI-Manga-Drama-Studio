// P2-E4-T02 工作流 live 健康检查面板测试：workflow 目录下拉（默认选中 is_default）、
// 「检查」后逐节点结果（ok 列表 / 缺节点 / 缺模型）、unreachable 顶层文案。
// Mock api client（spyOn client.api，不发网络请求）——与 settingsPage.test.tsx 同一 spy 模式。
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "../features/settings/SettingsPage";
import * as client from "../api/client";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { wrapper };
}

const providers = [
  {
    id: "comfyui_local",
    name: "ComfyUI (Local)",
    type: "image",
    status: "connected",
    capabilities: { image_generation: true, reference_image: true },
    base_url: "http://127.0.0.1:8188",
  },
];

const workflowsResp = {
  workflows: [
    { id: "default_image_api", filename: "default_image_api.json", is_default: false },
    { id: "zimage_turbo", filename: "zimage_turbo.json", is_default: true },
  ],
};

// SettingsPage 默认 AI Tab；「生成服务」Tab 渲染 comfyui_local 卡 + 工作流检查区。
// get 按 path 分发，未匹配路径回退「ComfyUI 未连接」形态，保证其余卡片渲染健壮。
function mockGet(handlers: Record<string, unknown> = {}) {
  return vi.fn().mockImplementation((path: string) => {
    if (path === "/providers") return Promise.resolve(providers);
    if (path === "/providers/comfyui/workflows") return Promise.resolve(workflowsResp);
    if (path in handlers) return Promise.resolve(handlers[path]);
    return Promise.resolve({ connected: false, base_url: "", models: [] });
  });
}

// 挂载页面 → 切到「生成服务」→ 等工作流下拉出现（工作流目录已加载）。
async function openProvidersTab(get: ReturnType<typeof mockGet>) {
  vi.spyOn(client.api, "get").mockImplementation(get);
  const { wrapper } = makeWrapper();
  render(<SettingsPage />, { wrapper });
  fireEvent.click(screen.getByRole("tab", { name: "生成服务" }));
  return (await screen.findByLabelText("工作流模板")) as HTMLSelectElement;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("工作流 live 健康检查面板（SettingsPage · ComfyUI 卡）", () => {
  it("① 加载 workflow 目录渲染下拉并默认选中 is_default 项", async () => {
    const get = mockGet();
    const select = await openProvidersTab(get);
    await waitFor(() => expect(select.options.length).toBe(2));
    expect(get).toHaveBeenCalledWith("/providers/comfyui/workflows");
    expect(select.value).toBe("zimage_turbo"); // 未手动选择 → 默认 is_default 项
    expect(screen.getByText("default_image_api")).toBeTruthy();
    expect(screen.getByText("zimage_turbo（默认）")).toBeTruthy();
  });

  it("② 点击「检查」渲染逐节点 ok 列表（node_id + class_type）", async () => {
    const post = vi.fn().mockImplementation((path: string) => {
      if (path === "/providers/comfyui/workflows/zimage_turbo/validate") {
        return Promise.resolve({
          workflow_id: "zimage_turbo",
          status: "ok",
          source: "workflows/zimage_turbo.json",
          ok: true,
          nodes: [
            { node_id: "10", class_type: "UNETLoader", status: "ok", detail: null, missing_choices: [] },
            { node_id: "20", class_type: "TextEncodeZImageOmni", status: "ok", detail: null, missing_choices: [] },
          ],
          missing_nodes: [],
          missing_models: [],
          broken_links: [],
          static_error: null,
          error: null,
        });
      }
      return Promise.resolve({});
    });
    vi.spyOn(client.api, "post").mockImplementation(post);
    await openProvidersTab(mockGet());

    fireEvent.click(screen.getByRole("button", { name: "检查" }));
    await screen.findByText(/检查通过 · 全部节点可用/);
    expect(post).toHaveBeenCalledWith("/providers/comfyui/workflows/zimage_turbo/validate", {});
    expect(screen.getByText("10")).toBeTruthy();
    expect(screen.getByText("UNETLoader")).toBeTruthy();
    expect(screen.getByText("20")).toBeTruthy();
    expect(screen.getByText("TextEncodeZImageOmni")).toBeTruthy();
    expect(screen.getAllByText("正常").length).toBe(2);
  });

  it("③ invalid 时显示缺节点 / 缺模型与候选数量提示", async () => {
    const post = vi.fn().mockImplementation((path: string) => {
      if (path === "/providers/comfyui/workflows/zimage_turbo/validate") {
        return Promise.resolve({
          workflow_id: "zimage_turbo",
          status: "invalid",
          source: "workflows/zimage_turbo.json",
          ok: false,
          nodes: [
            {
              node_id: "10",
              class_type: "UNETLoader",
              status: "missing_model",
              detail: "value not in choices",
              missing_choices: ["z_image_turbo_fp16.safetensors", "z_image_turbo_int8.safetensors"],
            },
            { node_id: "30", class_type: "VintageClipGlue", status: "missing_node", detail: null, missing_choices: [] },
          ],
          missing_nodes: ["VintageClipGlue"],
          missing_models: ["z_image_turbo_fp16.safetensors (UNETLoader.unet_name)"],
          broken_links: [],
          static_error: null,
          error: null,
        });
      }
      return Promise.resolve({});
    });
    vi.spyOn(client.api, "post").mockImplementation(post);
    await openProvidersTab(mockGet());

    fireEvent.click(screen.getByRole("button", { name: "检查" }));
    await screen.findByText(/检查未通过（2 项问题）/);
    expect(screen.getByText("缺模型")).toBeTruthy();
    expect(screen.getByText("缺节点")).toBeTruthy();
    expect(screen.getByText("VintageClipGlue")).toBeTruthy();
    expect(screen.getByText(/缺 2 个模型候选/)).toBeTruthy();
    expect(screen.getByText("value not in choices")).toBeTruthy();
  });

  it("④ unreachable 时显示连接错误文案且不渲染节点列表", async () => {
    const post = vi.fn().mockImplementation((path: string) => {
      if (path === "/providers/comfyui/workflows/zimage_turbo/validate") {
        return Promise.resolve({
          workflow_id: "zimage_turbo",
          status: "unreachable",
          source: null,
          ok: false,
          nodes: [],
          missing_nodes: [],
          missing_models: [],
          broken_links: [],
          static_error: null,
          error: "ComfyUI API 连接失败: connection refused",
        });
      }
      return Promise.resolve({});
    });
    vi.spyOn(client.api, "post").mockImplementation(post);
    await openProvidersTab(mockGet());

    fireEvent.click(screen.getByRole("button", { name: "检查" }));
    await screen.findByText(/无法连接 ComfyUI/);
    expect(screen.getByText(/connection refused/)).toBeTruthy();
    expect(screen.queryByText("UNETLoader")).toBeNull(); // 无逐节点数据
  });
});
