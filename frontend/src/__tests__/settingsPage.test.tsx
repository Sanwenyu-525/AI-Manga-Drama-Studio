// P-LocalModels settings page tests: local LLM server detection fill, ComfyUI
// checkpoint persistence, and local model scan/import flows. Mocks the api
// client (no network/backend) — same spy pattern as settingsModal.test.tsx.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "../features/settings/SettingsPage";
import * as client from "../api/client";
import { open as nativeOpen } from "@tauri-apps/plugin-dialog";

// 原生目录对话框 mock（Tauri 分支；浏览器分支不会 import 该模块）。
vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(async () => "D:\\Picked\\Models"),
}));

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { qc, wrapper };
}

const llmConfig = {
  mode: "fake" as const,
  base_url: null,
  model: "", // 空 → 验证「使用」会用 sample_models[0] 预填
  api_key_set: false,
  api_key_hint: null,
};

const imageConfig = {
  provider: "comfyui" as const,
  agnes_base_url: "https://api.agnes-ai.cn/v1",
  api_key_set: false,
  api_key_hint: null,
  video_provider: "mock" as const,
  video_model: "agnes-video-2.5-flash",
  comfyui_url: "http://127.0.0.1:8188",
  checkpoint: "sd_xl_base_1.0.safetensors",
  comfyui_models_root: null as string | null,
};

const providers = [
  {
    id: "mock",
    name: "Mock Image Provider",
    type: "image",
    status: "connected",
    capabilities: { image_generation: true, reference_image: false },
  },
];

// SettingsPage queries /llm/config + /image/config + /providers（+ comfyui models）。
// get 按 path 分发，未匹配路径回退「ComfyUI 未连接」形态，保证渲染健壮。
function mockGet(handlers: Record<string, unknown>) {
  return vi.fn().mockImplementation((path: string) => {
    if (path in handlers) return Promise.resolve(handlers[path]);
    return Promise.resolve({ connected: false, base_url: "", models: [] });
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SettingsPage — LLM 本地服务检测", () => {
  it("检测到 Ollama 后点「使用」把 mode/base_url/模型填入表单", async () => {
    const get = mockGet({ "/llm/config": llmConfig, "/image/config": imageConfig, "/providers": providers });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockImplementation((path: string) => {
      if (path === "/llm/detect-local") {
        return Promise.resolve({
          servers: [
            {
              kind: "ollama",
              label: "Ollama",
              base_url: "http://127.0.0.1:11434/v1",
              models_count: 2,
              sample_models: ["qwen2.5:7b", "llama3:8b"],
            },
          ],
        });
      }
      return Promise.resolve({});
    });
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });

    await screen.findByText("检测本地服务"); // AI Tab 默认激活，LLM 卡已挂载
    fireEvent.click(screen.getByText("检测本地服务").closest("button")!);
    await screen.findByText("http://127.0.0.1:11434/v1"); // 结果行出现
    expect(post).toHaveBeenCalledWith("/llm/detect-local", {});

    fireEvent.click(screen.getByText("使用").closest("button")!);
    // base_url 填入 + 模型名预填第一个 sample
    expect((screen.getByDisplayValue("http://127.0.0.1:11434/v1") as HTMLInputElement).value).toBeTruthy();
    expect(screen.getAllByDisplayValue("qwen2.5:7b").length).toBeGreaterThan(0);
  });

  it("未发现本地服务时给出可读提示而非报错", async () => {
    const get = mockGet({ "/llm/config": llmConfig, "/image/config": imageConfig, "/providers": providers });
    vi.spyOn(client.api, "get").mockImplementation(get);
    vi.spyOn(client.api, "post").mockResolvedValue({ servers: [] });
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    await screen.findByText("检测本地服务");
    fireEvent.click(screen.getByText("检测本地服务").closest("button")!);
    await screen.findByText(/未发现运行中的本地模型服务/);
  });
});

describe("SettingsPage — ComfyUI 本地引擎", () => {
  it("checkpoint 修改后保存会把 comfyui 字段一并 PUT（未改动字段不提交）", async () => {
    const get = mockGet({
      "/llm/config": llmConfig,
      "/image/config": imageConfig,
      "/providers": providers,
      "/providers/comfyui/models": {
        connected: true,
        base_url: "http://127.0.0.1:8188",
        models: ["a.safetensors", "b.safetensors"],
      },
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const put = vi.fn().mockResolvedValue({ ...imageConfig, checkpoint: "b.safetensors" });
    vi.spyOn(client.api, "put").mockImplementation(put);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "图像服务" }));

    // checkpoint 输入框显示已保存值；datalist 里是 ComfyUI 拉到的列表
    const input = await screen.findByDisplayValue("sd_xl_base_1.0.safetensors");
    fireEvent.change(input, { target: { value: "b.safetensors" } });
    fireEvent.click(screen.getByText("保存配置").closest("button")!);
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    const [path, body] = put.mock.calls[0];
    expect(path).toBe("/image/config");
    expect(body.checkpoint).toBe("b.safetensors");
    expect(body.comfyui_url).toBeUndefined(); // 未改动 → 不提交
    expect(body.comfyui_models_root).toBeUndefined(); // 未改动 → 不提交
  });

  it("扫描目录展示分类文件并支持导入（202 + 轮询完成）", async () => {
    const handlers: Record<string, unknown> = {
      "/llm/config": llmConfig,
      "/image/config": imageConfig,
      "/providers": providers,
      "/providers/comfyui/models": { connected: true, base_url: "http://127.0.0.1:8188", models: [] },
    };
    let pollCount = 0;
    vi.spyOn(client.api, "get").mockImplementation((path: string) => {
      if (path === "/operations/op_import1") {
        pollCount += 1;
        return Promise.resolve(
          pollCount === 1
            ? { id: "op_import1", status: "running", result: null, error: null }
            : {
                id: "op_import1",
                status: "completed",
                result: {
                  source: "D:/Models/checkpoints/flux.safetensors",
                  target: "D:/ComfyUI/models/checkpoints/flux.safetensors",
                  strategy: "copy",
                  size_bytes: 2 * 1024 ** 3,
                },
                error: null,
              },
        );
      }
      if (path in handlers) return Promise.resolve(handlers[path]);
      return Promise.resolve({});
    });
    const post = vi.fn().mockImplementation((path: string) => {
      if (path === "/providers/models/scan") {
        return Promise.resolve({
          mode: "path",
          path: "D:/Models",
          total: 1,
          truncated: false,
          files: [
            {
              name: "flux.safetensors",
              path: "D:/Models/checkpoints/flux.safetensors",
              dir: "checkpoints",
              kind: "checkpoint",
              size_bytes: 2 * 1024 ** 3,
            },
          ],
        });
      }
      if (path === "/providers/models/import") return Promise.resolve({ operation_id: "op_import1", status: "queued" });
      return Promise.resolve({});
    });
    vi.spyOn(client.api, "post").mockImplementation(post);

    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "图像服务" }));
    await screen.findByDisplayValue("http://127.0.0.1:8188");

    fireEvent.change(screen.getByPlaceholderText(/如 D:\\Models，或 ComfyUI 的 models 目录/), {
      target: { value: "D:/Models" },
    });
    fireEvent.click(screen.getByText("扫描该目录").closest("button")!);
    await screen.findByText(/flux\.safetensors/); // 行内文本带目录前缀 checkpoints/…
    expect(screen.getByText("底模")).toBeTruthy(); // 分类徽标
    expect(screen.getByText("2.0 GB")).toBeTruthy();

    fireEvent.click(screen.getByText("导入到 ComfyUI").closest("button")!);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/providers/models/import", {
        source: "D:/Models/checkpoints/flux.safetensors",
        kind: "checkpoint",
      }),
    );
    await waitFor(() => expect(screen.getByText(/已导入 flux.safetensors/)).toBeTruthy(), { timeout: 5000 });
    expect(screen.getByText(/复制/)).toBeTruthy();
    expect(pollCount).toBeGreaterThanOrEqual(2); // 经历了 running → completed
  });

  it("ComfyUI 未连接时模型下拉回退手输并提示", async () => {
    const get = mockGet({
      "/llm/config": llmConfig,
      "/image/config": imageConfig,
      "/providers": providers,
      "/providers/comfyui/models": { connected: false, base_url: "http://127.0.0.1:8188", models: [] },
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "图像服务" }));
    await screen.findByPlaceholderText("ComfyUI 未连接，可手动输入文件名");
  });
});

describe("SettingsPage — 视频模型目录（后端清单）", () => {
  const videoModelsResp = {
    models: [
      { id: "agnes-video-2.5-flash", label: "快 · 当前免费", verified: true, available: true },
      { id: "agnes-video-v2.0", label: null, verified: false, available: false },
      { id: "agnes-video-2.5", label: null, verified: false, available: null },
    ],
    probed: true,
    probe_error: null,
  };
  const imageConfigAgnes = { ...imageConfig, video_provider: "agnes" as const, video_model: "agnes-video-2.5-flash" };

  function agnesGet() {
    return vi.fn().mockImplementation((path: string) => {
      if (path === "/image/video-models") return Promise.resolve(videoModelsResp);
      if (path === "/image/config") return Promise.resolve(imageConfigAgnes);
      if (path === "/providers") return Promise.resolve(providers);
      return Promise.resolve({ connected: false, base_url: "", models: [] });
    });
  }

  it("模型下拉从 /image/video-models 渲染（含未验证 / 账号不可用标记）", async () => {
    const get = agnesGet();
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "视频服务" }));

    const select = (await screen.findByLabelText("视频模型")) as HTMLSelectElement;
    await waitFor(() => expect(select.options.length).toBe(3));
    expect(get).toHaveBeenCalledWith("/image/video-models");
    expect(screen.getByText(/agnes-video-2\.5-flash（快 · 当前免费 · 实测可用）$/)).toBeTruthy();
    expect(screen.getByText(/agnes-video-v2\.0（不在账号可用列表 · 未验证）/)).toBeTruthy();
    expect(screen.getByText(/agnes-video-2\.5（未验证）$/)).toBeTruthy();
  });

  it("账号不可用模型选中时给出可读警告，保存仍走 PUT", async () => {
    vi.spyOn(client.api, "get").mockImplementation(agnesGet());
    const put = vi.fn().mockResolvedValue({ ...imageConfigAgnes, video_model: "agnes-video-v2.0" });
    vi.spyOn(client.api, "put").mockImplementation(put);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "视频服务" }));

    const select = (await screen.findByLabelText("视频模型")) as HTMLSelectElement;
    await waitFor(() => expect(select.options.length).toBe(3));
    fireEvent.change(select, { target: { value: "agnes-video-v2.0" } });
    await screen.findByText(/不在该账号可用模型列表/);

    fireEvent.click(screen.getByText("保存配置").closest("button")!);
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/image/config", {
        video_provider: "agnes",
        video_model: "agnes-video-v2.0",
      }),
    );
  });

  it("目录读取失败时仅保留当前已保存模型并提示，不渲染硬编码清单", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/image/video-models") return Promise.reject(new Error("boom"));
      if (path === "/image/config") return Promise.resolve(imageConfigAgnes);
      if (path === "/providers") return Promise.resolve(providers);
      return Promise.resolve({ connected: false, base_url: "", models: [] });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "视频服务" }));

    const select = (await screen.findByLabelText("视频模型")) as HTMLSelectElement;
    await screen.findByText(/模型目录读取失败/);
    expect(select.options.length).toBe(1);
    expect(select.options[0].textContent).toContain("当前保存 · 不在目录");
  });
});

describe("SettingsPage — 目录浏览选择（P-LocalModels 文件浏览器）", () => {
  // GET /providers/fs/list 按 ?path=<encodeURIComponent(cwd)> 分发（"" = 根视图/盘符）。
  const fsListings: Record<string, unknown> = {
    "/providers/fs/list?path=": {
      path: "",
      parent: null,
      entries: [
        { name: "C:\\", path: "C:\\", type: "dir" },
        { name: "D:\\", path: "D:\\", type: "dir" },
      ],
      truncated: false,
    },
    "/providers/fs/list?path=D%3A%5C": {
      path: "D:\\",
      parent: null,
      entries: [
        { name: "Models", path: "D:\\Models", type: "dir" },
        { name: "readme.txt", path: "D:\\readme.txt", type: "file", size_bytes: 2048 },
      ],
      truncated: false,
    },
    "/providers/fs/list?path=D%3A%5CModels": {
      path: "D:\\Models",
      parent: "D:\\",
      entries: [{ name: "checkpoints", path: "D:\\Models\\checkpoints", type: "dir" }],
      truncated: false,
    },
  };

  function fsGet() {
    return vi.fn().mockImplementation((path: string) => {
      if (path in fsListings) return Promise.resolve(fsListings[path]);
      if (path === "/llm/config") return Promise.resolve(llmConfig);
      if (path === "/image/config") return Promise.resolve(imageConfig);
      if (path === "/providers") return Promise.resolve(providers);
      return Promise.resolve({ connected: false, base_url: "", models: [] });
    });
  }

  it("浏览 → 进盘符/子目录 → 选择此目录回填扫描路径输入框", async () => {
    const get = fsGet();
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "图像服务" }));
    await screen.findByDisplayValue("http://127.0.0.1:8188");
    fireEvent.click(screen.getByTitle(/浏览并选择要扫描的目录/));

    const dialog = await screen.findByRole("dialog", { name: "选择要扫描的模型目录" });
    expect(get).toHaveBeenCalledWith("/providers/fs/list?path=");
    await screen.findByText("D:\\"); // 根视图列出盘符
    expect(screen.getByTitle("返回上一级目录").hasAttribute("disabled")).toBe(true); // 根视图无上一级

    fireEvent.click(screen.getByText("D:\\"));
    await screen.findByText("Models"); // 进入 D:\ 后列出子目录
    expect(screen.getByText("readme.txt")).toBeTruthy(); // 文件只读展示
    expect(screen.getByText("2 KB")).toBeTruthy();

    fireEvent.click(screen.getByText("Models"));
    await screen.findByText("checkpoints");
    expect(screen.getByText("D:\\Models")).toBeTruthy(); // 底部当前目录

    fireEvent.click(screen.getByText("选择此目录"));
    expect((screen.getByDisplayValue("D:\\Models") as HTMLInputElement).value).toBe("D:\\Models");
    expect(screen.queryByRole("dialog")).toBeNull(); // 选择后弹窗关闭
    expect(dialog).toBeTruthy();
  });

  it("初始路径无效时自动回落根视图并提示", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/providers/fs/list?path=X%3A%5C%E4%B8%8D%E5%AD%98%E5%9C%A8") {
        return Promise.reject(new Error("目录不存在"));
      }
      if (path in fsListings) return Promise.resolve(fsListings[path]);
      if (path === "/llm/config") return Promise.resolve(llmConfig);
      if (path === "/image/config") return Promise.resolve(imageConfig);
      if (path === "/providers") return Promise.resolve(providers);
      return Promise.resolve({ connected: false, base_url: "", models: [] });
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "图像服务" }));
    await screen.findByDisplayValue("http://127.0.0.1:8188");
    fireEvent.change(screen.getByPlaceholderText(/如 D:\\Models，或 ComfyUI 的 models 目录/), {
      target: { value: "X:\\不存在" },
    });
    fireEvent.click(screen.getByTitle(/浏览并选择要扫描的目录/));

    await screen.findByText(/已回到根目录/);
    await screen.findByText("D:\\"); // 回落后展示盘符列表
    // 取消不改动输入框
    fireEvent.click(screen.getByText("取消"));
    expect(screen.getByDisplayValue("X:\\不存在")).toBeTruthy();
  });
});

describe("SettingsPage — 原生目录对话框（Tauri 桌面壳）", () => {
  afterEach(() => {
    delete (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  });

  function tauriGet() {
    return vi.fn().mockImplementation((path: string) => {
      if (path === "/providers/fs/list?path=") {
        // 内置浏览回落时的根视图（盘符列表）
        return Promise.resolve({
          path: "",
          parent: null,
          entries: [{ name: "D:\\", path: "D:\\", type: "dir" }],
          truncated: false,
        });
      }
      if (path === "/llm/config") return Promise.resolve(llmConfig);
      if (path === "/image/config") return Promise.resolve(imageConfig);
      if (path === "/providers") return Promise.resolve(providers);
      return Promise.resolve({ connected: false, base_url: "", models: [] });
    });
  }

  it("Tauri 环境点「浏览」调原生对话框并把绝对路径回填扫描输入框（不开内置弹窗）", async () => {
    (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    vi.mocked(nativeOpen).mockResolvedValue("D:\\Picked\\Models");
    vi.spyOn(client.api, "get").mockImplementation(tauriGet());
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "图像服务" }));
    await screen.findByDisplayValue("http://127.0.0.1:8188");
    fireEvent.click(screen.getByTitle(/浏览并选择要扫描的目录/));
    await waitFor(() =>
      expect(nativeOpen).toHaveBeenCalledWith(expect.objectContaining({ directory: true, multiple: false })),
    );
    await waitFor(() =>
      expect((screen.getByDisplayValue("D:\\Picked\\Models") as HTMLInputElement).value).toBe("D:\\Picked\\Models"),
    );
    expect(screen.queryByRole("dialog")).toBeNull(); // 内置弹窗没有打开
  });

  it("原生对话框取消（null）→ 表单不动；调用抛错（旧壳无插件）→ 回落内置浏览", async () => {
    (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    vi.mocked(nativeOpen).mockResolvedValueOnce(null).mockRejectedValueOnce(new Error("plugin not registered"));
    vi.spyOn(client.api, "get").mockImplementation(tauriGet());
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "图像服务" }));
    await screen.findByDisplayValue("http://127.0.0.1:8188");
    // 第一次：取消 → 输入框保持为空，无内置弹窗
    fireEvent.click(screen.getByTitle(/浏览并选择要扫描的目录/));
    await waitFor(() => expect(nativeOpen).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.queryByDisplayValue("D:\\Picked\\Models")).toBeNull();

    // 第二次：旧壳缺插件抛错 → 回落内置目录浏览弹窗（根视图）
    fireEvent.click(screen.getByTitle(/浏览并选择要扫描的目录/));
    await screen.findByRole("dialog", { name: "选择要扫描的模型目录" });
    await screen.findByText("D:\\"); // 内置弹窗的根视图盘符列表
  });
});

describe("SettingsPage — LLM 连接 Profiles（P-LLM-Profiles）", () => {
  const profilesResp = {
    profiles: [
      {
        id: "default",
        name: "默认连接",
        mode: "fake",
        base_url: null,
        model: null,
        api_key_set: false,
        api_key_hint: null,
        is_active: true,
        bound_tasks: [] as string[],
        capabilities: { tools: false, vision: false, reasoning: false, source: "heuristic" },
      },
      {
        id: "prof_local",
        name: "本地 Qwen",
        mode: "openai",
        base_url: "http://127.0.0.1:11434/v1",
        model: "qwen3",
        api_key_set: false,
        api_key_hint: null,
        is_active: false,
        bound_tasks: ["director"],
        capabilities: { tools: true, vision: false, reasoning: false, source: "heuristic" },
      },
    ],
    active_profile_id: "default",
    task_bindings: {
      director: { profile_id: "prof_local", profile_name: "本地 Qwen" },
      script: null,
      continuity: null,
    },
    task_fallbacks: {
      director: [] as { profile_id: string; profile_name: string }[],
      script: [],
      continuity: [],
    },
    tasks: [
      { id: "director", label: "AI 导演" },
      { id: "script", label: "剧本分析 / 分镜" },
      { id: "continuity", label: "连续性检查" },
    ],
  };

  function llmGet() {
    return mockGet({
      "/llm/config": llmConfig,
      "/image/config": imageConfig,
      "/providers": providers,
      "/llm/profiles": profilesResp,
    });
  }

  it("渲染已存连接 chips（含绑定数）并支持点击激活", async () => {
    vi.spyOn(client.api, "get").mockImplementation(llmGet());
    const post = vi.fn().mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });

    await screen.findByRole("button", { name: /本地 Qwen/ });
    expect(screen.getByText(/1 任务绑定/)).toBeTruthy(); // director 绑定数可见
    fireEvent.click(screen.getByRole("button", { name: /本地 Qwen/ }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/llm/profiles/prof_local/activate", {}));
  });

  it("任务分配下拉切换发起 PUT /llm/task-bindings（跟随激活 → null）", async () => {
    vi.spyOn(client.api, "get").mockImplementation(llmGet());
    const put = vi.fn().mockResolvedValue(profilesResp);
    vi.spyOn(client.api, "put").mockImplementation(put);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });

    const directorSelect = (await screen.findByLabelText("AI 导演")) as HTMLSelectElement;
    expect(directorSelect.value).toBe("prof_local");
    fireEvent.change(directorSelect, { target: { value: "" } });
    await waitFor(() => expect(put).toHaveBeenCalledWith("/llm/task-bindings", { bindings: { director: null } }));
  });

  it("「+ 存为新连接」展开内联命名行，输入名称后 POST 为命名 profile（空名禁用保存）", async () => {
    vi.spyOn(client.api, "get").mockImplementation(llmGet());
    const post = vi.fn().mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });

    fireEvent.click(await screen.findByText("+ 存为新连接"));
    const nameInput = screen.getByPlaceholderText("连接名称（如：本地 Qwen）");
    // 空名称时「保存」禁用（即时校验，不弹原生 prompt）
    expect((screen.getByText("保存").closest("button") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(nameInput, { target: { value: "我的连接" } });
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/llm/profiles", {
        name: "我的连接",
        mode: "fake",
        base_url: null,
        model: null,
      }),
    );
  });

  it("非激活连接提供删除按钮并发起 DELETE", async () => {
    vi.spyOn(client.api, "get").mockImplementation(llmGet());
    const del = vi.fn().mockResolvedValue({ deleted: "prof_local" });
    vi.spyOn(client.api, "delete").mockImplementation(del);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });

    fireEvent.click(await screen.findByTitle("删除此连接"));
    await waitFor(() => expect(del).toHaveBeenCalledWith("/llm/profiles/prof_local"));
  });

  it("添加降级连接发起 PUT /llm/task-fallbacks（追加到链尾）", async () => {
    vi.spyOn(client.api, "get").mockImplementation(llmGet());
    const put = vi.fn().mockResolvedValue(profilesResp);
    vi.spyOn(client.api, "put").mockImplementation(put);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });

    const addSelect = (await screen.findByLabelText("添加降级-AI 导演")) as HTMLSelectElement;
    fireEvent.change(addSelect, { target: { value: "default" } });
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/llm/task-fallbacks", {
        fallbacks: { director: ["default"] },
      }),
    );
  });

  it("降级链 chip 支持移除与排序（PUT 全量有序列表）", async () => {
    const withFallback = {
      ...profilesResp,
      task_fallbacks: {
        director: [
          { profile_id: "prof_local", profile_name: "本地 Qwen" },
          { profile_id: "default", profile_name: "默认连接" },
        ],
        script: [],
        continuity: [],
      },
    };
    vi.spyOn(client.api, "get").mockImplementation(
      mockGet({
        "/llm/config": llmConfig,
        "/image/config": imageConfig,
        "/providers": providers,
        "/llm/profiles": withFallback,
      }),
    );
    const put = vi.fn().mockResolvedValue(withFallback);
    vi.spyOn(client.api, "put").mockImplementation(put);
    const { wrapper } = makeWrapper();
    render(<SettingsPage />, { wrapper });

    // 两条降级 chip 渲染（director 链），其余任务无 chip
    expect((await screen.findAllByTitle("移除降级")).length).toBe(2);
    // 移除第一位的「本地 Qwen」
    const chips = screen.getAllByTitle("移除降级");
    fireEvent.click(chips[0]);
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/llm/task-fallbacks", {
        fallbacks: { director: ["default"] },
      }),
    );
    // 前移「默认连接」→ 链变为 [default, prof_local]
    fireEvent.click(screen.getByTitle("前移（更早尝试）"));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/llm/task-fallbacks", {
        fallbacks: { director: ["default", "prof_local"] },
      }),
    );
  });
});
