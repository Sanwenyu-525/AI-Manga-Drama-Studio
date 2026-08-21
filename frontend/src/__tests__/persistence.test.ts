// P6-T003: workspace persistence — parse/sanitize/save/load + debounce.
import { describe, expect, it, vi } from "vitest";
import {
  WORKSPACE_STORAGE_KEY,
  DEFAULT_LAYOUT,
  parseWorkspace,
  saveWorkspace,
  loadWorkspace,
  createDebounced,
  type StorageLike,
  type TabState,
} from "../lib/persistence";
import { PANEL_BOUNDS as PB } from "../lib/panels";

function memoryStorage(initial: Record<string, string> = {}): StorageLike & { data: Record<string, string> } {
  const data = { ...initial };
  return {
    data,
    getItem: (key) => data[key] ?? null,
    setItem: (key, value) => { data[key] = value; },
  };
}

function snapshotOverrides(partial: Record<string, unknown>): string {
  const base = {
    schemaVersion: 2,
    layout: DEFAULT_LAYOUT,
    tabs: { activeTabId: "script", open: [{ id: "script", kind: "script", title: "剧本" }] },
  };
  return JSON.stringify({ ...base, ...partial });
}

describe("persistence — save/load round trip", () => {
  it("saves and reloads the snapshot", () => {
    const storage = memoryStorage();
    const snap = {
      schemaVersion: 2 as const,
      layout: { ...DEFAULT_LAYOUT, explorerWidth: 250, rightWidth: 420, bottomDockHeight: 300, explorerCollapsed: true, bottomDockExpanded: true },
      tabs: { activeTabId: "scene:s1", open: [{ id: "script", kind: "script", title: "剧本" }, { id: "scene:s1", kind: "scene", title: "Scene 1", sceneId: "s1", episodeId: "e1" }] as TabState[] },
    };
    expect(saveWorkspace(snap, storage)).toBe(true);
    const loaded = loadWorkspace(storage);
    expect(loaded).not.toBeNull();
    if (!loaded || loaded.schemaVersion !== 2) throw new Error("expected v2 workspace snapshot");
    expect(loaded!.layout.explorerWidth).toBe(250);
    expect(loaded!.layout.rightWidth).toBe(420);
    expect(loaded!.layout.explorerCollapsed).toBe(true);
    expect(loaded!.tabs.open).toHaveLength(2);
  });
  it("loadWorkspace returns null when empty", () => {
    expect(loadWorkspace(memoryStorage())).toBeNull();
  });
  it("loadWorkspace returns null for corrupt JSON", () => {
    const storage = memoryStorage({ [WORKSPACE_STORAGE_KEY]: "{{{not json" });
    expect(loadWorkspace(storage)).toBeNull();
  });
  it("saveWorkspace tolerates throwing storage", () => {
    const bad = { getItem: () => null, setItem: () => { throw new Error("quota"); } };
    expect(saveWorkspace({} as never, bad)).toBe(false);
  });
});

describe("persistence — parse / sanitize", () => {
  it("sanitizes out-of-range sizes into panel bounds", () => {
    const raw = snapshotOverrides({ layout: { explorerWidth: 5, rightWidth: 999, bottomDockHeight: -10 } });
    const parsed = parseWorkspace(raw);
    expect(parsed!.layout.explorerWidth).toBe(PB.explorer.min);
    expect(parsed!.layout.rightWidth).toBe(PB.right.max);
    expect(parsed!.layout.bottomDockHeight).toBe(PB.bottom.min);
  });
  it("rejects unknown schema versions", () => {
    const raw = snapshotOverrides({ schemaVersion: 3 });
    expect(parseWorkspace(raw)).toBeNull();
  });
  it("keeps only layout when reading the v1 workspace snapshot", () => {
    const raw = JSON.stringify({ version: 1, layout: { ...DEFAULT_LAYOUT, explorerWidth: 260 }, selection: { shotIds: ["stale"] }, tabs: { activeTabId: "scene:stale", open: [] } });
    const parsed = parseWorkspace(raw);
    expect(parsed?.schemaVersion).toBe(1);
    expect(parsed?.layout.explorerWidth).toBe(260);
    expect(parsed && "tabs" in parsed).toBe(false);
  });
  it("rejects non-object payloads", () => {
    expect(parseWorkspace("42")).toBeNull();
    expect(parseWorkspace(JSON.stringify([1, 2]))).toBeNull();
  });
  it("drops invalid tab entries when restoring", () => {
    const raw = snapshotOverrides({
      tabs: { activeTabId: "scene:bad", open: [{ id: "script", kind: "script", title: "剧本" }, 7, null, { id: "shot:1", kind: "shot", title: "Shot" }] },
    });
    const parsed = parseWorkspace(raw)!;
    expect(parsed.schemaVersion).toBe(2);
    if (parsed.schemaVersion !== 2) throw new Error("expected v2 workspace snapshot");
    expect(parsed.tabs.open.every((t) => typeof t.id === "string")).toBe(true);
    expect(parsed.tabs.open.some((t) => t.kind === "shot")).toBe(true);
  });
});

describe("persistence — debounce", () => {
  it("coalesces rapid calls and flushes after the wait", async () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const debounced = createDebounced(fn, 250);
    debounced("a");
    debounced("b");
    vi.advanceTimersByTime(300);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("b");
    vi.useRealTimers();
  });
  it("cancel prevents a pending call", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const debounced = createDebounced(fn, 100);
    debounced("x");
    debounced.cancel();
    vi.advanceTimersByTime(200);
    expect(fn).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
