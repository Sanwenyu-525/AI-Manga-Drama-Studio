// 顶部内容面包屑（2026-08 改版）回归：
//   1. 祖先段可点击 → SPA 跳转（项目→项目首页 / EP→该集剧本 / SC→该场景分镜板）
//   2. 末段（当前节点）只读高亮，不渲染链接
//   3. 悬停有同级内容的段 → 同级菜单；横向切换后 URL 正确
//   4. 模块菜单在剧集上下文内直达该集的剧本/时间线（episode-aware build）
//   5. 跨场景切换时清空上一场景的镜头选择（右侧检查器不残留脏上下文）
//   6. Escape 关闭菜单；无项目页面显示 muted 文案
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ContentBreadcrumb } from "../components/shell/ContentBreadcrumb";
import { useSelectionStore } from "../stores/selectionStore";
import type { Episode, Project, Scene, Storyboard } from "../api/types";

const project: Project = {
  id: "p1",
  name: "最后一村村法",
  description: null,
  status: "active",
  aspect_ratio: null,
  fps: null,
  cover_url: null,
  revision: 1,
  created_at: "",
  updated_at: "",
};

const projects: Project[] = [project, { ...project, id: "p2", name: "另一部剧" }];

const episodes: Episode[] = [
  {
    id: "ep1",
    project_id: "p1",
    episode_number: 1,
    title: "初入村",
    source_text: null,
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
    title: "风波",
    source_text: null,
    script_text: null,
    summary: null,
    status: "active",
    revision: 1,
    created_at: "",
    updated_at: "",
  },
];

const storyboard: Storyboard = {
  scene: { id: "sc1", scene_number: 3, name: "村口对峙" },
  shots: [
    {
      id: "sh1",
      shot_number: 3,
      shot_type: "close_up",
      duration: null,
      status: "draft",
      dirty_state: "clean",
      thumbnail_url: null,
      character_names: [],
      active_generation: null,
    },
  ],
};

const scenes: Scene[] = [
  {
    id: "sc0",
    episode_id: "ep1",
    scene_number: 1,
    name: "开场",
    location_id: null,
    time_of_day: null,
    lighting: null,
    weather: null,
    mood: null,
    description: null,
    scene_order: null,
    status: "active",
    shot_count: 0,
    revision: 1,
    created_at: "",
    updated_at: "",
  },
  {
    id: "sc2",
    episode_id: "ep1",
    scene_number: 2,
    name: "午后",
    location_id: null,
    time_of_day: null,
    lighting: null,
    weather: null,
    mood: null,
    description: null,
    scene_order: null,
    status: "active",
    shot_count: 0,
    revision: 1,
    created_at: "",
    updated_at: "",
  },
  {
    id: "sc1",
    episode_id: "ep1",
    scene_number: 3,
    name: "村口对峙",
    location_id: null,
    time_of_day: null,
    lighting: null,
    weather: null,
    mood: null,
    description: null,
    scene_order: null,
    status: "active",
    shot_count: 1,
    revision: 1,
    created_at: "",
    updated_at: "",
  },
];

const STORYBOARD_ROUTE = "/projects/p1/episodes/ep1/scenes/sc1/storyboard";

function LocationProbe() {
  const { pathname } = useLocation();
  return <div data-testid="loc">{pathname}</div>;
}

function makeWrapper(initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <LocationProbe />
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function stubApi() {
  const get = vi.fn().mockImplementation((path: string) => {
    if (path === "/projects/p1") return Promise.resolve(project);
    if (path === "/projects") return Promise.resolve(projects);
    if (path === "/projects/p1/episodes") return Promise.resolve(episodes);
    if (path === "/scenes/sc1/storyboard") return Promise.resolve(storyboard);
    if (path === "/episodes/ep1/scenes") return Promise.resolve(scenes);
    // 未匹配的路径按契约拒绝（失败要响，静默降级会掩盖契约漂移）
    return Promise.reject(new Error("unexpected " + path));
  });
  vi.spyOn(client.api, "get").mockImplementation(get);
}

function selectShot(shotId: string) {
  useSelectionStore.setState({ selection: { shotIds: [shotId], assetIds: [] } });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useSelectionStore.setState({ selection: { shotIds: [], assetIds: [] } });
});

describe("content breadcrumb", () => {
  it("renders the content hierarchy with clickable ancestors and a read-only current node", async () => {
    stubApi();
    selectShot("sh1");
    render(<ContentBreadcrumb />, { wrapper: makeWrapper(STORYBOARD_ROUTE) });

    const projectLink = await screen.findByRole("link", { name: "最后一村村法" });
    expect(projectLink.getAttribute("href")).toBe("/projects/p1/workspace");

    const episodeLink = screen.getByRole("link", { name: /^EP01/ });
    expect(episodeLink.getAttribute("href")).toBe("/projects/p1/episodes/ep1/script");

    const sceneLink = screen.getByRole("link", { name: /^SC03/ });
    expect(sceneLink.getAttribute("href")).toBe("/projects/p1/episodes/ep1/scenes/sc1/storyboard");

    const shotCrumb = screen.getByText("SH03").closest("span.crumb-current");
    expect(shotCrumb).not.toBeNull();
    expect(shotCrumb?.getAttribute("aria-current")).toBe("location");
    expect(screen.queryByRole("link", { name: "SH03" })).toBeNull();
  });

  it("switches episodes laterally from the EP sibling menu", async () => {
    stubApi();
    render(<ContentBreadcrumb />, { wrapper: makeWrapper(STORYBOARD_ROUTE) });

    fireEvent.mouseOver(await screen.findByRole("link", { name: /^EP01/ }));
    const ep2 = await screen.findByRole("menuitem", { name: /EP02/ });
    fireEvent.click(ep2);

    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/projects/p1/episodes/ep2/script"));
  });

  it("switches scenes laterally and clears the stale shot selection", async () => {
    stubApi();
    selectShot("sh1");
    render(<ContentBreadcrumb />, { wrapper: makeWrapper(STORYBOARD_ROUTE) });

    fireEvent.mouseOver(await screen.findByRole("link", { name: /^SC03/ }));
    const sc1 = await screen.findByRole("menuitem", { name: /SC01/ });
    fireEvent.click(sc1);

    await waitFor(() =>
      expect(screen.getByTestId("loc").textContent).toBe("/projects/p1/episodes/ep1/scenes/sc0/storyboard"),
    );
    expect(useSelectionStore.getState().selection.shotIds).toEqual([]);
  });

  it("marks the current scene inside its sibling menu and closes on Escape", async () => {
    stubApi();
    // 预置镜头选中 → SH03 成为末段（只读），SC03 保持可交互祖先段。
    selectShot("sh1");
    render(<ContentBreadcrumb />, { wrapper: makeWrapper(STORYBOARD_ROUTE) });

    fireEvent.mouseOver(await screen.findByRole("link", { name: /^SC03/ }));
    const active = await screen.findByRole("menuitem", { name: /SC03/ });
    expect(active.className).toContain("active");

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("offers the module menu and reaches the episode-aware timeline", async () => {
    stubApi();
    render(<ContentBreadcrumb />, { wrapper: makeWrapper(STORYBOARD_ROUTE) });

    fireEvent.mouseOver(await screen.findByRole("link", { name: "分镜" }));
    expect(await screen.findByRole("menuitem", { name: "AI导演" })).not.toBeNull();
    fireEvent.click(screen.getByRole("menuitem", { name: "时间线" }));

    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/projects/p1/episodes/ep1/timeline"));
  });

  it("lists sibling projects from the project segment menu", async () => {
    stubApi();
    render(<ContentBreadcrumb />, { wrapper: makeWrapper(STORYBOARD_ROUTE) });

    fireEvent.mouseOver(await screen.findByRole("link", { name: "最后一村村法" }));
    const other = await screen.findByRole("menuitem", { name: "另一部剧" });
    fireEvent.click(other);

    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/projects/p2/workspace"));
  });

  it("falls back to muted hints when no project is open", async () => {
    stubApi();
    render(<ContentBreadcrumb />, { wrapper: makeWrapper("/") });
    expect(await screen.findByText("项目库")).not.toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
