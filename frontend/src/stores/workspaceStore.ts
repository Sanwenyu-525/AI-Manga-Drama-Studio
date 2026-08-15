// Workspace / UI layout state (frontend-ux §82: Zustand holds local UI state only).

import { create } from "zustand";

interface WorkspaceState {
  activeShotId: string | null;
  setActiveShot: (shotId: string | null) => void;
  rightPanelTab: "inspector" | "director";
  setRightPanelTab: (tab: "inspector" | "director") => void;
  bottomDockTab: "queue" | "history";
  setBottomDockTab: (tab: "queue" | "history") => void;
  bottomDockExpanded: boolean;
  setBottomDockExpanded: (expanded: boolean) => void;
  explorerCollapsed: boolean;
  setExplorerCollapsed: (collapsed: boolean) => void;
  rightPanelCollapsed: boolean;
  setRightPanelCollapsed: (collapsed: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeShotId: null,
  setActiveShot: (shotId) => set({ activeShotId: shotId }),
  rightPanelTab: "inspector",
  setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
  bottomDockTab: "queue",
  setBottomDockTab: (tab) => set({ bottomDockTab: tab }),
  bottomDockExpanded: false,
  setBottomDockExpanded: (expanded) => set({ bottomDockExpanded: expanded }),
  explorerCollapsed: false,
  setExplorerCollapsed: (collapsed) => set({ explorerCollapsed: collapsed }),
  rightPanelCollapsed: false,
  setRightPanelCollapsed: (collapsed) => set({ rightPanelCollapsed: collapsed }),
}));
