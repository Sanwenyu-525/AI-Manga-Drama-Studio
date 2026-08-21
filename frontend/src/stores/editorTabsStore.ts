// P6-T004 Editor Tabs store: wraps the pure reducers in `../lib/editorTabs` so the
// center WorkspaceHost can subscribe and every mutation flows through testable pure
// functions. Persistence is delegated to the workspace-persistence subscriber
// module (P6-T003) so one place owns saving/restoring the whole snapshot.

import { create } from "zustand";
import {
  initialTabs,
  openSceneTab,
  openShotTab,
  activateTab as activateTabReducer,
  closeTab as closeTabReducer,
  restoreTabs,
  type EditorTab,
  type EditorTabsState,
} from "../lib/editorTabs";

interface EditorTabsStore extends EditorTabsState {
  openScene: (input: { projectId: string; episodeId?: string; sceneId: string; title: string }) => void;
  openShot: (input: { projectId: string; episodeId?: string; shotId: string; title: string; sceneId?: string }) => void;
  activateTab: (id: string) => void;
  closeTab: (id: string) => void;
  restore: (open: EditorTab[] | undefined, activeTabId: string | null | undefined) => void;
}

export const useEditorTabsStore = create<EditorTabsStore>((set) => ({
  ...initialTabs(),
  openScene: (input) => set((s) => openSceneTab(s, input)),
  openShot: (input) => set((s) => openShotTab(s, input)),
  activateTab: (id) => set((s) => activateTabReducer(s, id)),
  closeTab: (id) => set((s) => closeTabReducer(s, id)),
  restore: (open, activeTabId) => set(() => restoreTabs(open, activeTabId)),
}));
