// P6-T003 Workspace Persistence — bridge between the Zustand stores and
// `../lib/persistence` (localStorage). One module owns hydration + save-subscription
// so store logic stays framework-free and unit-testable in isolation.

import {
  WORKSPACE_STORAGE_KEY,
  createDebounced,
  loadWorkspace,
  saveWorkspace,
  sanitizeLayout,
  type ParsedWorkspaceSnapshot,
  type WorkspaceSnapshot,
} from "../lib/persistence";
import { useWorkspaceStore } from "./workspaceStore";
import { useEditorTabsStore } from "./editorTabsStore";

const SAVE_DEBOUNCE_MS = 250;

function defaultStorage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** Read a snapshot off the provided storage (defaults to window.localStorage). */
export function hydrateWorkspace(storage?: Storage | null): ParsedWorkspaceSnapshot | null {
  const target = storage ?? defaultStorage();
  if (!target) return null;
  return loadWorkspace(target);
}

/** Apply a persisted snapshot to the stores (layout + safe v2 tabs only). */
export function applyWorkspace(snapshot: ParsedWorkspaceSnapshot | null) {
  if (!snapshot) return;
  const layout = sanitizeLayout(snapshot.layout);
  useWorkspaceStore.setState({
    explorerWidth: layout.explorerWidth,
    rightWidth: layout.rightWidth,
    bottomDockHeight: layout.bottomDockHeight,
    explorerCollapsed: layout.explorerCollapsed,
    rightPanelCollapsed: layout.rightPanelCollapsed,
    bottomDockExpanded: layout.bottomDockExpanded,
    rightPanelTab: layout.rightPanelTab,
    bottomDockTab: layout.bottomDockTab,
  });
  if (snapshot.schemaVersion === 2) {
    useEditorTabsStore.getState().restore(snapshot.tabs.open, snapshot.tabs.activeTabId);
  } else {
    useEditorTabsStore.getState().restore(undefined, undefined);
  }
}

/** Build the current snapshot from the stores. */
export function collectSnapshot(): WorkspaceSnapshot {
  const ws = useWorkspaceStore.getState();
  const tabs = useEditorTabsStore.getState();
  return {
    schemaVersion: 2,
    layout: {
      explorerWidth: ws.explorerWidth,
      rightWidth: ws.rightWidth,
      bottomDockHeight: ws.bottomDockHeight,
      explorerCollapsed: ws.explorerCollapsed,
      rightPanelCollapsed: ws.rightPanelCollapsed,
      bottomDockExpanded: ws.bottomDockExpanded,
      rightPanelTab: ws.rightPanelTab,
      bottomDockTab: ws.bottomDockTab,
    },
    tabs: { activeTabId: tabs.activeTabId ?? "script", open: tabs.open },
  };
}

let attached = false;

function makeSaver(storage: Storage) {
  const write = () => saveWorkspace(collectSnapshot(), storage);
  const debounced = createDebounced(write, SAVE_DEBOUNCE_MS);
  return {
    saveNow: () => write(),
    cancel: () => debounced.cancel(),
  };
}

/** Subscribe the stores to persistence. Safe to call more than once (idempotent).
 *  Returns an unsubscribe that stops saving (does not cancel prior writes). */
export function attachWorkspacePersistence(storage?: Storage): () => void {
  const target = storage ?? defaultStorage();
  if (!target) return () => {};
  if (attached && !storage) return () => {};
  const saver = makeSaver(target);
  const unsubWorkspace = useWorkspaceStore.subscribe(() => saver.saveNow());
  const unsubTabs = useEditorTabsStore.subscribe(() => saver.saveNow());
  attached = true;
  return () => {
    unsubWorkspace();
    unsubTabs();
    saver.cancel();
    attached = false;
  };
}

/** Remove the persisted key (used by tests and a settings reset action). */
export function clearWorkspacePersistence(storage?: Storage) {
  const target = storage ?? defaultStorage();
  target?.removeItem?.(WORKSPACE_STORAGE_KEY);
}

export { WORKSPACE_STORAGE_KEY };
