// P6-T004 Editor Tabs — pure tab-list reducers (unit-testable).
// IDE-style main tabs (frontend-ux-design 94-96): a non-closeable base `script`
// tab plus `scene` (Storyboard) and `shot` (Inspector detail) tabs, persisted and
// restored. All navigation flows through these pure functions so behavior is
// easy to reason about and test.

export type EditorTabKind = "script" | "scene" | "shot";

export interface EditorTab {
  id: string;
  kind: EditorTabKind;
  title: string;
  sceneId?: string;
  shotId?: string;
  projectId?: string;
}

export interface EditorTabsState {
  open: EditorTab[];
  activeTabId: string | null;
}

export const SCRIPT_TAB_ID = "script";
export const MAX_TABS = 16;

export const initialTabs = (): EditorTabsState => ({
  open: [{ id: SCRIPT_TAB_ID, kind: "script", title: "剧本" }],
  activeTabId: SCRIPT_TAB_ID,
});

function tabId(kind: EditorTabKind, ref?: string): string {
  return `${kind}:${ref ?? ""}`;
}

function upsert(open: EditorTab[], tab: EditorTab): EditorTab[] {
  const existing = tab.kind === "script" ? -1 : open.findIndex((t) => t.id === tab.id);
  if (existing >= 0) {
    return open.map((t, i) => (i === existing ? { ...t, ...tab } : t));
  }
  // Drop the oldest non-script tab when at capacity.
  if (open.length >= MAX_TABS) {
    const droppable = open.findIndex((t) => t.kind !== "script");
    const next = droppable >= 0 ? open.filter((_, i) => i !== droppable) : open;
    return [...next, tab];
  }
  return [...open, tab];
}

/* Open (create-or-activate) a scene tab. Returns a brand-new state object. */
export function openSceneTab(state: EditorTabsState, input: { projectId: string; sceneId: string; title: string }): EditorTabsState {
  const tab: EditorTab = {
    id: tabId("scene", input.sceneId),
    kind: "scene",
    title: input.title,
    sceneId: input.sceneId,
    projectId: input.projectId,
  };
  return { open: upsert(state.open, tab), activeTabId: tab.id };
}

/* Open (create-or-activate) a shot detail tab. */
export function openShotTab(state: EditorTabsState, input: { projectId: string; shotId: string; title: string; sceneId?: string }): EditorTabsState {
  const tab: EditorTab = {
    id: tabId("shot", input.shotId),
    kind: "shot",
    title: input.title,
    shotId: input.shotId,
    sceneId: input.sceneId,
    projectId: input.projectId,
  };
  return { open: upsert(state.open, tab), activeTabId: tab.id };
}

/* Ensure the non-closeable script base tab exists (no-op otherwise). */
export function ensureScriptTab(state: EditorTabsState): EditorTabsState {
  if (state.open.some((t) => t.id === SCRIPT_TAB_ID)) return state;
  return { open: [{ id: SCRIPT_TAB_ID, kind: "script", title: "剧本" }, ...state.open], activeTabId: state.activeTabId ?? SCRIPT_TAB_ID };
}

/* Activate an existing tab by id. Ignores unknown ids. */
export function activateTab(state: EditorTabsState, id: string): EditorTabsState {
  if (!state.open.some((t) => t.id === id)) return state;
  return { ...state, activeTabId: id };
}

/* Close a tab. The script base tab cannot be closed. When the active tab is
   closed, the tab to its left becomes active (falling back to the script tab). */
export function closeTab(state: EditorTabsState, id: string): EditorTabsState {
  if (id === SCRIPT_TAB_ID) return state;
  const idx = state.open.findIndex((t) => t.id === id);
  if (idx < 0) return state;
  const open = state.open.filter((t) => t.id !== id);
  let activeTabId = state.activeTabId;
  if (activeTabId === id) {
    activeTabId = open[Math.min(idx, open.length - 1)]?.id ?? SCRIPT_TAB_ID;
  }
  return { open, activeTabId };
}

/* Restore a persisted tab list: reapply the base tab, keep scene/shot tabs with
   a valid ref, resolve a valid active id. */
export function restoreTabs(persisted: EditorTab[] | undefined, persistedActive: string | null | undefined): EditorTabsState {
  const base: EditorTab = { id: SCRIPT_TAB_ID, kind: "script", title: "剧本" };
  const open: EditorTab[] = [base];
  for (const t of persisted ?? []) {
    if (!t || t.id === SCRIPT_TAB_ID) continue;
    if ((t.kind === "scene" && t.sceneId) || (t.kind === "shot" && t.shotId)) open.push(t);
  }
  const active = open.some((t) => t.id === persistedActive) ? persistedActive! : base.id;
  return { open, activeTabId: active };
}

export { tabId };