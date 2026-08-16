// P8-T020 — Continuity UI:
//   1. lib helpers: severity tiers / labels / category / state-value formatting
//   2. SceneWarningBadge: severity badge + count, expandable warning list,
//      recompute (重新计算) + AI 语义检测 trigger, no-warning state
//   3. ContinuityWarningList: acknowledge (/continuity-warnings/{id}/acknowledge),
//      AI-fix run trigger, expandable evidence
//   4. ShotContinuityCard: start/end state summaries (Chinese labels, — when empty)
//   5. EventRouter: continuity.warning.* events invalidate continuity queries
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import * as lib from "../lib/continuity";
import { EventRouter } from "../events/socket";
import type { ContinuitySceneRead, ContinuityShotReadCard, ContinuityWarning } from "../api/types";
import { SceneWarningBadge } from "../features/continuity/SceneWarningBadge";
import { ShotContinuityCard } from "../features/continuity/ShotContinuityCard";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (<QueryClientProvider client={qc}>{children}</QueryClientProvider>);
  return { qc, wrapper };
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// ---- lib helpers ----
describe("continuity lib", () => {
  it("severityTier normalizes to info/warning/error", () => {
    expect(lib.severityTier("error")).toBe("error");
    expect(lib.severityTier("warning")).toBe("warning");
    expect(lib.severityTier("info")).toBe("info");
    expect(lib.severityTier(undefined)).toBe("info");
  });
  it("sceneSeverityTier picks the highest tier present", () => {
    expect(lib.sceneSeverityTier([{ severity: "warning" }, { severity: "error" }])).toBe("error");
    expect(lib.sceneSeverityTier([{ severity: "info" }, { severity: "warning" }])).toBe("warning");
    expect(lib.sceneSeverityTier([])).toBe("");
  });
  it("countByTier totals per severity", () => {
    const c = lib.countByTier([{ severity: "error" }, { severity: "warning" }, { severity: "info" }, { severity: "warning" }]);
    expect(c).toEqual({ info: 1, warning: 2, error: 1 });
  });
  it("severityTierLabel + categoryLabel provide Chinese labels", () => {
    expect(lib.severityTierLabel("error")).toBe("错误");
    expect(lib.severityTierLabel("warning")).toBe("警告");
    expect(lib.severityTierLabel("info")).toBe("提示");
    expect(lib.categoryLabel("costume")).toBe("换装");
    expect(lib.categoryLabel("prop")).toBe("道具");
    expect(lib.categoryLabel("custom_x")).toBe("custom_x");
  });
  it("stateValue formats values / fallback to —", () => {
    expect(lib.stateValue(null)).toBe("—");
    expect(lib.stateValue("")).toBe("—");
    expect(lib.stateValue(true)).toBe("是");
    expect(lib.stateValue(false)).toBe("否");
    expect(lib.stateValue("medium")).toBe("medium");
  });
  it("isOpenWarning reflects acknowledge status", () => {
    expect(lib.isOpenWarning({ severity: "warning", message: "x" })).toBe(true);
    expect(lib.isOpenWarning({ severity: "warning", message: "x", status: "acknowledged" })).toBe(false);
    expect(lib.isOpenWarning({ severity: "warning", message: "x", status: "fixed" })).toBe(false);
  });
});
// ---- fixture ----
const warningError: ContinuityWarning = { id: "w_error", severity: "error", category: "prop", message: "篮球在 Shot 19→20 间消失", status: "open", evidence: "obj_missing basketball" };
const warningWarn: ContinuityWarning = { id: "w_warn", severity: "warning", category: "costume", message: "角色换装未过渡", status: "open" };
const sceneRead: ContinuitySceneRead = {
  scene_id: "scene_1",
  scene_warnings: [warningWarn],
  shots: [{ shot_id: "shot_a", start_state: null, end_state: null, warnings: [warningError] }],
};

// ---- SceneWarningBadge ----
describe("SceneWarningBadge", () => {
  it("renders a severity badge with count and expands into a warning list", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/scenes/scene_1/continuity") return Promise.resolve(sceneRead);
      if (path === "/scenes/scene_1/continuity-warnings") return Promise.resolve([] as ContinuityWarning[]);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<SceneWarningBadge sceneId="scene_1" />, { wrapper });
    expect(await screen.findByText("错误")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /2/ }));
    expect(await screen.findByText("篮球在 Shot 19→20 间消失")).toBeTruthy();
    expect(screen.getByText("角色换装未过渡")).toBeTruthy();
  });

  it("shows 无警告 and keeps actions reachable when no warnings", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/scenes/scene_1/continuity") return Promise.resolve({ scene_id: "scene_1", scene_warnings: [], shots: [] } as ContinuitySceneRead);
      if (path === "/scenes/scene_1/continuity-warnings") return Promise.resolve([] as ContinuityWarning[]);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<SceneWarningBadge sceneId="scene_1" />, { wrapper });
    expect(await screen.findByText("无警告")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /无警告/ }));
    expect(await screen.findByText("当前没有连续性警告。")).toBeTruthy();
    expect(screen.getByText("重新计算")).toBeTruthy();
    expect(screen.getByText("AI 语义检测")).toBeTruthy();
  });

  it("重新计算 posts to recompute and AI 语义检测 posts to /agent/continuity/check", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/scenes/scene_1/continuity") return Promise.resolve(sceneRead);
      if (path === "/scenes/scene_1/continuity-warnings") return Promise.resolve([] as ContinuityWarning[]);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<SceneWarningBadge sceneId="scene_1" />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: /2/ }));
    fireEvent.click(await screen.findByText("重新计算"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/scenes/scene_1/continuity/recompute"));
    fireEvent.click(screen.getByText("AI 语义检测"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/agent/continuity/check", { scene_id: "scene_1" }));
    expect(await screen.findByText(/已启动 AI 语义检测/)).toBeTruthy();
  });
});
// ---- ContinuityWarningList actions ----
describe("ContinuityWarningList actions", () => {
  it("acknowledge posts to /continuity-warnings/{id}/acknowledge", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/scenes/scene_1/continuity") return Promise.resolve(sceneRead);
      if (path === "/scenes/scene_1/continuity-warnings") return Promise.resolve([warningError]);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({});
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<SceneWarningBadge sceneId="scene_1" />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: /2/ }));
    const ackButtons = await screen.findAllByText("标记已读");
    fireEvent.click(ackButtons[0]);
    await waitFor(() => expect(post).toHaveBeenCalledWith(expect.stringMatching(/^\/continuity-warnings\/w_/)));
  });

  it("AI 修复 posts to /agent/continuity/runs and shows approval hint", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/scenes/scene_1/continuity") return Promise.resolve(sceneRead);
      if (path === "/scenes/scene_1/continuity-warnings") return Promise.resolve([] as ContinuityWarning[]);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const post = vi.fn().mockResolvedValue({ run_id: "run_x" });
    vi.spyOn(client.api, "post").mockImplementation(post);
    const { wrapper } = makeWrapper();
    render(<SceneWarningBadge sceneId="scene_1" />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: /2/ }));
    const fixButtons = await screen.findAllByText("AI 修复");
    fireEvent.click(fixButtons[0]);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/agent/continuity/runs", { scene_id: "scene_1" }));
    expect(await screen.findByText(/请在导演面板审批/)).toBeTruthy();
  });

  it("expands evidence on the expand chevron", async () => {
    const singleRead: ContinuitySceneRead = { scene_id: "scene_1", scene_warnings: [warningError], shots: [] };
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/scenes/scene_1/continuity") return Promise.resolve(singleRead);
      if (path === "/scenes/scene_1/continuity-warnings") return Promise.resolve([] as ContinuityWarning[]);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<SceneWarningBadge sceneId="scene_1" />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: /1/ }));
    fireEvent.click(await screen.findByLabelText("展开证据"));
    expect(await screen.findByText("obj_missing basketball")).toBeTruthy();
  });
});
// ---- ShotContinuityCard ----
const shotCard: ContinuityShotReadCard = {
  shot_id: "shot_a",
  end_state: {
    characters: [{ character_id: "char_1", character_version_id: "cv_1", costume_id: "cost_1", position: "左", action: "持球", emotion: "冷静" }],
    environment: { location_id: "loc_1", time_of_day: "夜", lighting: "暗" },
  },
};

describe("ShotContinuityCard", () => {
  it("renders start/end summaries with Chinese labels and — for empty", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/shots/shot_a") return Promise.resolve({ scene_id: "scene_1" });
      if (path === "/shots/shot_a/continuity-state") return Promise.resolve(shotCard);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ShotContinuityCard shotId="shot_a" />, { wrapper });
    expect(await screen.findByText("连续性状态")).toBeTruthy();
    expect(screen.getByText("起始")).toBeTruthy();
    expect(screen.getByText("结束")).toBeTruthy();
    // 结束 state has character rows with Chinese labels
    expect(screen.getByText("服装")).toBeTruthy();
    expect(screen.getByText("cost_1")).toBeTruthy();
    expect(screen.getByText("时段")).toBeTruthy();
    expect(screen.getByText("夜")).toBeTruthy();
    // no warnings → positive message
    expect(screen.getByText("镜间状态一致，无连续性警告。")).toBeTruthy();
  });
  it("shows warnings list when the shot has warnings", async () => {
    const withWarn = { ...shotCard, start_state: null, end_state: null, warnings: [warningError] as ContinuityWarning[] };
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/shots/shot_a") return Promise.resolve({ scene_id: "scene_1" });
      if (path === "/shots/shot_a/continuity-state") return Promise.resolve(withWarn);
      return Promise.reject(new Error("unexpected " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ShotContinuityCard shotId="shot_a" />, { wrapper });
    expect(await screen.findByText("篮球在 Shot 19→20 间消失")).toBeTruthy();
  });
});

// ---- EventRouter continuity events ----
describe("EventRouter continuity events", () => {
  it("continuity.warning.created invalidates scene + warnings + shot queries", () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const router = new EventRouter(qc);
    router.handle({ event_id: "e1", event_type: "continuity.warning.created", event_version: 1, project_id: "p1", entity_type: "warning", entity_id: "w1", timestamp: "2026-01-01", sequence: 1, payload: { scene_id: "scene_1", shot_id: "shot_a" } });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["sceneContinuity", "scene_1"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["continuityWarnings", "scene_1"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["shotContinuity", "shot_a"] });
  });
  it("continuity.warning.acknowledged invalidates by prefix when ids missing", () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const router = new EventRouter(qc);
    router.handle({ event_id: "e2", event_type: "continuity.warning.acknowledged", event_version: 1, project_id: "p1", entity_type: "warning", entity_id: "w1", timestamp: "2026-01-01", sequence: 2, payload: {} });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["sceneContinuity"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["continuityWarnings"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["shotContinuity"] });
  });
  it("unknown events are ignored (no crash)", () => {
    const qc = new QueryClient();
    const router = new EventRouter(qc);
    expect(() => router.handle({ event_id: "e3", event_type: "some.other", event_version: 1, project_id: null, entity_type: "x", entity_id: "y", timestamp: "2026-01-01", sequence: 3, payload: {} })).not.toThrow();
  });
});