// Workspace Persistence — save/restore local UI layout and tab metadata.
// Route entities and temporary Shot/Asset selection are intentionally not persisted.

import { PANEL_BOUNDS, clampPanelSize, type PanelId } from "./panels";

export const WORKSPACE_STORAGE_KEY = "studio-workspace-v1";
export const WORKSPACE_SCHEMA_VERSION = 2 as const;

export interface LayoutState {
  explorerWidth: number;
  rightWidth: number;
  bottomDockHeight: number;
  explorerCollapsed: boolean;
  rightPanelCollapsed: boolean;
  bottomDockExpanded: boolean;
  rightPanelTab: "inspector" | "director";
  bottomDockTab: "queue" | "history" | "jobs";
}

export interface TabState {
  id: string;
  kind: "script" | "scene" | "shot";
  title: string;
  sceneId?: string;
  shotId?: string;
  episodeId?: string;
  projectId?: string;
}

export interface WorkspaceSnapshot {
  schemaVersion: typeof WORKSPACE_SCHEMA_VERSION;
  layout: LayoutState;
  tabs: { activeTabId: string; open: TabState[] };
}

export interface LegacyWorkspaceSnapshot {
  schemaVersion: 1;
  layout: LayoutState;
}

export type ParsedWorkspaceSnapshot = WorkspaceSnapshot | LegacyWorkspaceSnapshot;

export const DEFAULT_LAYOUT: LayoutState = {
  explorerWidth: 260, // 略收窄，把更多横向空间留给中央工作台
  rightWidth: 328, // DESIGN.md §4：Agent Dock 固定宽
  bottomDockHeight: 100,
  explorerCollapsed: false,
  rightPanelCollapsed: false,
  bottomDockExpanded: false,
  rightPanelTab: "inspector",
  bottomDockTab: "queue",
};

/** Clamp any loaded layout into valid panel bounds (guards against stale/bad data). */
export function sanitizeLayout(raw: Partial<LayoutState> | undefined): LayoutState {
  const d = DEFAULT_LAYOUT;
  if (!raw) return { ...d };
  return {
    explorerWidth: clampPanelSize(raw.explorerWidth ?? d.explorerWidth, PANEL_BOUNDS.explorer, d.explorerWidth),
    rightWidth: clampPanelSize(raw.rightWidth ?? d.rightWidth, PANEL_BOUNDS.right, d.rightWidth),
    bottomDockHeight: clampPanelSize(
      raw.bottomDockHeight ?? d.bottomDockHeight,
      PANEL_BOUNDS.bottom,
      d.bottomDockHeight,
    ),
    explorerCollapsed: Boolean(raw.explorerCollapsed ?? d.explorerCollapsed),
    rightPanelCollapsed: Boolean(raw.rightPanelCollapsed ?? d.rightPanelCollapsed),
    bottomDockExpanded: Boolean(raw.bottomDockExpanded ?? d.bottomDockExpanded),
    rightPanelTab: raw.rightPanelTab === "director" ? "director" : "inspector",
    bottomDockTab: raw.bottomDockTab === "history" ? "history" : raw.bottomDockTab === "jobs" ? "jobs" : "queue",
  };
}

/** Parse a persisted snapshot, tolerating corrupt/missing data. Returns null when unusable. */
export function parseWorkspace(raw: string | null): ParsedWorkspaceSnapshot | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const obj = parsed as { schemaVersion?: unknown; version?: unknown; layout?: unknown; tabs?: unknown };
    const layout = sanitizeLayout(obj.layout as Partial<LayoutState> | undefined);
    if (obj.schemaVersion !== WORKSPACE_SCHEMA_VERSION) {
      // v1 snapshots may still contain safe panel dimensions, but their active
      // tab/selection must not override the URL after the R1 migration.
      return obj.version === 1 ? { schemaVersion: 1, layout } : null;
    }
    const tabBlock = obj.tabs as { activeTabId?: unknown; open?: unknown } | undefined;
    const open = Array.isArray(tabBlock?.open) ? (tabBlock.open as TabState[]).filter(isTabState) : [];
    const activeTabId = typeof tabBlock?.activeTabId === "string" ? tabBlock.activeTabId : (open[0]?.id ?? "script");
    return {
      schemaVersion: WORKSPACE_SCHEMA_VERSION,
      layout,
      tabs: { activeTabId, open },
    };
  } catch {
    return null;
  }
}

function isTabState(t: unknown): t is TabState {
  if (!t || typeof t !== "object") return false;
  const o = t as TabState;
  return typeof o.id === "string" && (o.kind === "script" || o.kind === "scene" || o.kind === "shot");
}

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** Load + parse the persisted snapshot (returns null when empty/corrupt). */
export function loadWorkspace(storage: StorageLike): ParsedWorkspaceSnapshot | null {
  try {
    return parseWorkspace(storage.getItem(WORKSPACE_STORAGE_KEY));
  } catch {
    return null;
  }
}

/** Serialize + write a snapshot. Never throws — persistence is best-effort. */
export function saveWorkspace(snapshot: WorkspaceSnapshot, storage: StorageLike): boolean {
  try {
    storage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(snapshot));
    return true;
  } catch {
    return false;
  }
}

/** Small debounce helper so high-frequency resize events don't write every frame. */
export function createDebounced<A extends unknown[]>(fn: (...args: A) => void, waitMs: number) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const debounced = (...args: A) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, waitMs);
  };
  debounced.cancel = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };
  debounced.flush = (...args: A) => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    fn(...args);
  };
  return debounced;
}

export type { PanelId };
