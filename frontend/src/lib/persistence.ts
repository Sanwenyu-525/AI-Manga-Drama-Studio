// P6-T003 Workspace Persistence — save/restore UI workspace state to localStorage.
// frontend-ux-design §92-93: layout + selection + open tabs are *User Workspace
// State*, kept in local app settings (not Project DB). Key: studio-workspace-v1.
// We only persist small, non-sensitive IDs and sizes — never server payloads.

import { PANEL_BOUNDS, clampPanelSize, type PanelId } from "./panels";

export const WORKSPACE_STORAGE_KEY = "studio-workspace-v1";

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

export interface SelectionState {
  projectId?: string;
  episodeId?: string;
  sceneId?: string;
  shotIds: string[];
}

export interface TabState {
  id: string;
  kind: "script" | "scene" | "shot";
  title: string;
  sceneId?: string;
  shotId?: string;
  projectId?: string;
}

export interface WorkspaceSnapshot {
  version: 1;
  layout: LayoutState;
  selection: SelectionState;
  tabs: { activeTabId: string; open: TabState[] };
}

export const DEFAULT_LAYOUT: LayoutState = {
  explorerWidth: PANEL_BOUNDS.explorer.max - 100, // 300 matches the current shell default
  rightWidth: 380,
  bottomDockHeight: 104,
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
    bottomDockHeight: clampPanelSize(raw.bottomDockHeight ?? d.bottomDockHeight, PANEL_BOUNDS.bottom, d.bottomDockHeight),
    explorerCollapsed: Boolean(raw.explorerCollapsed ?? d.explorerCollapsed),
    rightPanelCollapsed: Boolean(raw.rightPanelCollapsed ?? d.rightPanelCollapsed),
    bottomDockExpanded: Boolean(raw.bottomDockExpanded ?? d.bottomDockExpanded),
    rightPanelTab: raw.rightPanelTab === "director" ? "director" : "inspector",
    bottomDockTab: raw.bottomDockTab === "history" ? "history" : raw.bottomDockTab === "jobs" ? "jobs" : "queue",
  };
}

/** Parse a persisted snapshot, tolerating corrupt/missing data. Returns null when unusable. */
export function parseWorkspace(raw: string | null): WorkspaceSnapshot | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const obj = parsed as { version?: unknown; layout?: unknown; selection?: unknown; tabs?: unknown };
    if (obj.version !== 1) return null;
    const layout = sanitizeLayout(obj.layout as Partial<LayoutState> | undefined);
    const sel = (obj.selection ?? { shotIds: [] }) as Partial<SelectionState>;
    const tabBlock = obj.tabs as { activeTabId?: unknown; open?: unknown } | undefined;
    const open = Array.isArray(tabBlock?.open) ? (tabBlock.open as TabState[]).filter(isTabState) : [];
    const activeTabId = typeof tabBlock?.activeTabId === "string" ? tabBlock.activeTabId : (open[0]?.id ?? "script");
    return {
      version: 1,
      layout,
      selection: {
        projectId: typeof sel.projectId === "string" ? sel.projectId : undefined,
        episodeId: typeof sel.episodeId === "string" ? sel.episodeId : undefined,
        sceneId: typeof sel.sceneId === "string" ? sel.sceneId : undefined,
        shotIds: Array.isArray(sel.shotIds) ? sel.shotIds.filter((s): s is string => typeof s === "string") : [],
      },
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
export function loadWorkspace(storage: StorageLike): WorkspaceSnapshot | null {
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