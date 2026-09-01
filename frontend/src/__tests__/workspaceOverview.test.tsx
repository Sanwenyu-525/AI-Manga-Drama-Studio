// P2 漫剧工作区（制作控制台重排版）回归：
//   1. 「当前生产状态区」= 剧集进度 + 生产管线合并；主按钮「继续制作」指向当前行动点
//   2. 管线阶段条由 bootstrap 的 has_timeline / has_final_video 推导（contract §103；
//      回归：曾逐集 404 探测，2N 请求且误报「等待」）
//   3. EP 工作卡整卡可点 = 该集下一步动作（开始/继续/排片/渲染/查看）
//   4. 「需要处理」异常驱动：只列真实失败与进行中任务，空闲=干净态
//   5. 最近生成缩略图直达镜头详情
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type {
  BootstrapEpisode,
  Episode,
  EpisodeTreeItem,
  GenerationRead,
  ProjectBootstrap,
  ProjectReadiness,
  ProjectTreeRead,
  ShotTreeItem,
} from "../api/types";
import { WorkspaceOverviewPage } from "../features/workspace/WorkspaceOverviewPage";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/projects/p1/workspace"]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { wrapper };
}

const readyShot: ShotTreeItem = {
  id: "sh1",
  shot_number: 1,
  shot_type: "wide",
  status: "image_ready",
  dirty_state: "clean",
  revision: 1,
  active_image_version: 1,
  active_video_version: null,
  active_prompt_version_id: null,
};

const episodeTree: EpisodeTreeItem[] = [
  {
    id: "ep1",
    episode_number: 1,
    title: "第一集",
    scene_count: 1,
    scenes: [{ id: "sc1", scene_number: 1, name: "场景一", shot_count: 1, shots: [readyShot] }],
  },
  { id: "ep2", episode_number: 2, title: "第二集", scene_count: 0, scenes: [] },
];

const tree: ProjectTreeRead = {
  project: {
    id: "p1",
    name: "测试项目",
    description: null,
    status: "active",
    aspect_ratio: null,
    fps: null,
    cover_url: null,
    revision: 1,
    created_at: "",
    updated_at: "",
  },
  episodes: episodeTree,
};

const episodes: Episode[] = [
  {
    id: "ep1",
    project_id: "p1",
    episode_number: 1,
    title: "第一集",
    source_text: "正文",
    script_text: null,
    summary: null,
    status: "active",
    revision: 1,
    created_at: "",
    updated_at: "",
  },
  {
    id: "ep2",
    project_id: "p1",
    episode_number: 2,
    title: "第二集",
    source_text: null,
    script_text: null,
    summary: null,
    status: "active",
    revision: 1,
    created_at: "",
    updated_at: "",
  },
];

const bootstrapEpisodes: BootstrapEpisode[] = [
  { id: "ep1", episode_number: 1, title: "第一集", scene_count: 1, has_timeline: true, has_final_video: false },
  { id: "ep2", episode_number: 2, title: "第二集", scene_count: 0, has_timeline: false, has_final_video: false },
];

const bootstrap: ProjectBootstrap = {
  project: tree.project,
  episodes: bootstrapEpisodes,
  characters: [],
  providers: [],
  active_generations: 0,
  active_agent_runs: 0,
};

const recent: GenerationRead[] = [];

// 自主迭代 04：生产就绪度（默认全就绪 → 干净态）。
const readyReadiness: ProjectReadiness = {
  characters: { total: 2, ready: 2, missing: 0 },
  scene_binding: { scenes_total: 1, bound: 1, bound_with_master: 1, unbound: 0 },
  continuity_open: 0,
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("workspace overview", () => {
  const stubApi = (overrides?: {
    bootstrap?: ProjectBootstrap;
    recent?: GenerationRead[];
    readiness?: ProjectReadiness;
  }) => {
    // 未匹配的路径按契约拒绝（失败要响，静默降级会掩盖契约漂移）
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/projects/p1/tree") return Promise.resolve(tree);
      if (path === "/projects/p1/episodes") return Promise.resolve(episodes);
      if (path === "/projects/p1/bootstrap") return Promise.resolve(overrides?.bootstrap ?? bootstrap);
      if (path === "/generations/recent") return Promise.resolve(overrides?.recent ?? recent);
      if (path === "/projects/p1/readiness") return Promise.resolve(overrides?.readiness ?? readyReadiness);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
  };

  it("状态区合并 EP+管线：主按钮「继续制作」指向当前行动点（导出 → ep1 时间线）", async () => {
    stubApi();
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    // ep1 已出图且有时间线、无成片 → 全项目当前阶段=导出 → 落点=ep1 时间线
    // （主按钮 href 在 bootstrap 到达前后会变：timeline→export，必须等 flags 落地）
    const primary = await screen.findByRole("link", { name: /继续制作/ }, { timeout: 4000 });
    await waitFor(
      () => {
        expect(primary.getAttribute("href")).toBe("/projects/p1/episodes/ep1/timeline");
      },
      { timeout: 4000 },
    );
    expect(screen.getByText("EP01 · 第一集")).toBeTruthy();
    expect(screen.getByText(/当前阶段：导出/)).toBeTruthy();
  });

  it("管线阶段条由 bootstrap flags 推导，而非逐集探测端点", async () => {
    stubApi();
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    // ep1 has_timeline=true → 时间线已完成；export 未产出 → 当前行动点
    await waitFor(
      () => {
        const stage = screen.getByText("时间线").closest("li");
        expect(stage?.className).toContain("done");
      },
      { timeout: 4000 },
    );
    const exportStage = screen.getByText("导出").closest("li");
    expect(exportStage?.className).toContain("running");
    // 不应再向每集端点发探测请求
    expect(client.api.get).not.toHaveBeenCalledWith("/episodes/ep1/timeline");
    expect(client.api.get).not.toHaveBeenCalledWith("/episodes/ep1/final-video");
  });

  it("EP 工作卡整卡可点：ep1 渲染导出→时间线；ep2 开始制作→剧本", async () => {
    stubApi();
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    const ep1Card = await screen.findByRole("link", { name: "渲染导出：EP01" }, { timeout: 4000 });
    expect(ep1Card.getAttribute("href")).toBe("/projects/p1/episodes/ep1/timeline");

    const ep2Card = screen.getByRole("link", { name: "开始制作：EP02" });
    expect(ep2Card.getAttribute("href")).toBe("/projects/p1/episodes/ep2/script");
    expect(ep2Card.textContent).toContain("尚未开始");
  });

  it("无异常时「需要处理」显示干净态，不塞普通导航入口", async () => {
    stubApi();
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    expect(await screen.findByText("当前没有需要处理的问题", {}, { timeout: 4000 })).toBeTruthy();
    // 已删除的重复入口不再出现
    expect(screen.queryByText("提示词版本库")).toBeNull();
    expect(screen.queryByText("连续性检查")).toBeNull();
    expect(screen.queryByText("快捷入口")).toBeNull();
  });

  it("有失败/运行中任务时逐条列出，附动作", async () => {
    const failedGen: GenerationRead = {
      id: "g1",
      project_id: "p1",
      shot_id: "sh1",
      type: "image",
      provider: "mock",
      model: null,
      workflow_id: null,
      prompt_version_id: null,
      status: "failed",
      progress: 0,
      stage: null,
      output_asset_id: null,
      error_message: "boom",
      retry_of: null,
      created_at: "",
      started_at: null,
      completed_at: null,
    };
    const busyBootstrap: ProjectBootstrap = { ...bootstrap, active_generations: 2, active_agent_runs: 1 };
    stubApi({ bootstrap: busyBootstrap, recent: [failedGen] });
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    const failedLink = await screen.findByRole("link", { name: /1 条生成失败/ }, { timeout: 4000 });
    expect(failedLink.getAttribute("href")).toBe("/projects/p1/production-log");
    expect(screen.getByRole("button", { name: /2 个生成任务运行中/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /1 个 AI 导演任务运行中/ })).toBeTruthy();
    expect(screen.queryByText("当前没有需要处理的问题")).toBeNull();
  });

  it("最近生成缩略图直达镜头详情", async () => {
    const doneGen: GenerationRead = {
      id: "g2",
      project_id: "p1",
      shot_id: "sh1",
      type: "image",
      provider: "agnes",
      model: "agnes-image-2.1-flash",
      workflow_id: null,
      prompt_version_id: null,
      status: "completed",
      progress: 100,
      stage: null,
      output_asset_id: "asset9",
      error_message: null,
      retry_of: null,
      created_at: "",
      started_at: null,
      completed_at: null,
    };
    stubApi({ recent: [doneGen] });
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    const img = await screen.findByRole("img", { name: /SHOT SH1/ }, { timeout: 4000 });
    expect(img.getAttribute("src")).toBe("/api/v1/assets/asset9/thumbnail");
    const card = img.closest("a");
    expect(card?.getAttribute("href")).toBe("/projects/p1/episodes/ep1/scenes/sc1/shots/sh1");
    expect(screen.getByRole("link", { name: "查看全部资产" })).toBeTruthy();
  });
});

describe("生产就绪度（自主迭代 04）", () => {
  it("全部就绪 → 干净态，不显示缺口卡片", async () => {
    const stubApi = (readiness: ProjectReadiness) => {
      const get = vi.fn().mockImplementation((path: string) => {
        if (path === "/projects/p1/tree") return Promise.resolve(tree);
        if (path === "/projects/p1/episodes") return Promise.resolve(episodes);
        if (path === "/projects/p1/bootstrap") return Promise.resolve(bootstrap);
        if (path === "/generations/recent") return Promise.resolve(recent);
        if (path === "/projects/p1/readiness") return Promise.resolve(readiness);
        return Promise.reject(new Error("unexpected " + path));
      });
      vi.spyOn(client.api, "get").mockImplementation(get);
    };
    stubApi(readyReadiness);
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });
    expect(await screen.findByText(/一致性资产就绪/, {}, { timeout: 4000 })).toBeTruthy();
    expect(screen.queryByText("去补齐")).toBeNull();
    expect(screen.queryByText("去绑定")).toBeNull();
    expect(screen.queryByText("去检查")).toBeNull();
  });

  it("角色缺 MASTER → 卡片显示缺口并跳转角色页", async () => {
    const readiness: ProjectReadiness = {
      characters: { total: 3, ready: 1, missing: 2 },
      scene_binding: { scenes_total: 1, bound: 1, bound_with_master: 1, unbound: 0 },
      continuity_open: 0,
    };
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/projects/p1/tree") return Promise.resolve(tree);
      if (path === "/projects/p1/episodes") return Promise.resolve(episodes);
      if (path === "/projects/p1/bootstrap") return Promise.resolve(bootstrap);
      if (path === "/generations/recent") return Promise.resolve(recent);
      if (path === "/projects/p1/readiness") return Promise.resolve(readiness);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });
    const link = await screen.findByRole("link", { name: /角色参考图/, timeout: 4000 });
    expect(link.textContent).toContain("1/3");
    expect(link.textContent).toContain("缺 2");
    expect(link.getAttribute("href")).toBe("/projects/p1/characters");
  });

  it("场景未绑定地点 → 卡片显示缺口并跳转分镜", async () => {
    const readiness: ProjectReadiness = {
      characters: { total: 2, ready: 2, missing: 0 },
      scene_binding: { scenes_total: 4, bound: 2, bound_with_master: 1, unbound: 2 },
      continuity_open: 0,
    };
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/projects/p1/tree") return Promise.resolve(tree);
      if (path === "/projects/p1/episodes") return Promise.resolve(episodes);
      if (path === "/projects/p1/bootstrap") return Promise.resolve(bootstrap);
      if (path === "/generations/recent") return Promise.resolve(recent);
      if (path === "/projects/p1/readiness") return Promise.resolve(readiness);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });
    const link = await screen.findByRole("link", { name: /场景地点/, timeout: 4000 });
    expect(link.textContent).toContain("1/4");
    expect(link.textContent).toContain("2 未绑定");
    expect(link.getAttribute("href")).toBe("/projects/p1/storyboard");
  });

  it("开放连续性警告 → 卡片显示计数并跳转连续性检查", async () => {
    const readiness: ProjectReadiness = {
      characters: { total: 2, ready: 2, missing: 0 },
      scene_binding: { scenes_total: 1, bound: 1, bound_with_master: 1, unbound: 0 },
      continuity_open: 3,
    };
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/projects/p1/tree") return Promise.resolve(tree);
      if (path === "/projects/p1/episodes") return Promise.resolve(episodes);
      if (path === "/projects/p1/bootstrap") return Promise.resolve(bootstrap);
      if (path === "/generations/recent") return Promise.resolve(recent);
      if (path === "/projects/p1/readiness") return Promise.resolve(readiness);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });
    const link = await screen.findByRole("link", { name: /连续性/, timeout: 4000 });
    expect(link.textContent).toContain("3");
    expect(link.getAttribute("href")).toBe("/projects/p1/continuity");
  });
});
