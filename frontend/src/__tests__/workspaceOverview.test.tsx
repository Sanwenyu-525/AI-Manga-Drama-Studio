// P2 漫剧工作区 — WorkspaceOverviewPage 回归：
//   1. 每集进度行的「打开该集剧本」必须直达该集 canonical 剧本 URL
//      （回归：曾指向 legacy /script 重定向，多集项目永远落到第一集）
//   2. 「连续性检查」注意力行入口指向连续性工作区页面
//   3. 管线阶段由 bootstrap 的 has_timeline / has_final_video 推导
//      （contract §103；回归：曾逐集 404 探测，2N 请求且误报「等待」）
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
    scenes: [
      { id: "sc1", scene_number: 1, name: "场景一", shot_count: 1, shots: [readyShot] },
    ],
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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("workspace overview", () => {
  const stubApi = () => {
    // 未匹配的路径按契约拒绝（失败要响，静默降级会掩盖契约漂移）
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/projects/p1/tree") return Promise.resolve(tree);
      if (path === "/projects/p1/episodes") return Promise.resolve(episodes);
      if (path === "/projects/p1/bootstrap") return Promise.resolve(bootstrap);
      if (path === "/generations/recent") return Promise.resolve(recent);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
  };

  it("links each episode row to its own canonical script URL", async () => {
    stubApi();
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    const links = await screen.findAllByTitle("打开该集剧本");
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute("href")).toBe("/projects/p1/episodes/ep1/script");
    expect(links[1].getAttribute("href")).toBe("/projects/p1/episodes/ep2/script");
  });

  it("points the continuity attention row at the continuity workspace page", async () => {
    stubApi();
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    const continuity = await screen.findByRole("link", { name: "打开检查页" });
    expect(continuity.getAttribute("href")).toBe("/projects/p1/continuity");
  });

  it("derives pipeline stages from bootstrap flags instead of probing endpoints", async () => {
    stubApi();
    const { wrapper } = makeWrapper();
    render(<WorkspaceOverviewPage projectId="p1" />, { wrapper });

    // ep1 has_timeline=true → 时间线阶段已完成；export 未产出 → 首个未完成阶段 = 当前行动点「进行中」
    // （管线区块先于 bootstrap 返回渲染，需等 flags 到位后的重渲染）
    await screen.findByText("生产管线");
    await waitFor(() => {
      const stage = screen.getByText("时间线").closest("li");
      expect(stage?.textContent).toContain("已完成");
    });
    const exportStage = screen.getByText("导出").closest("li");
    expect(exportStage?.textContent).toContain("进行中");
    // 不应再向每集端点发探测请求
    expect(client.api.get).not.toHaveBeenCalledWith("/episodes/ep1/timeline");
    expect(client.api.get).not.toHaveBeenCalledWith("/episodes/ep1/final-video");
  });
});
