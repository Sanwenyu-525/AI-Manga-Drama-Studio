// Workspace / UI layout state (frontend-ux §82: Zustand holds local UI state only).
// P6-T002: panel widths/heights are hoisted here (shell-level) so left/right/bottom
// panels can be dragged and the sizes survive collapse. P6-T003 persists them.

import { create } from "zustand";
import { PANEL_BOUNDS, clampPanelSize, type PanelId } from "../lib/panels";
import { DEFAULT_LAYOUT } from "../lib/persistence";

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
  // --- P6-T002 panel sizes (hoisted to shell level) ---
  explorerWidth: number;
  rightWidth: number;
  bottomDockHeight: number;
  setPanelSize: (panel: PanelId, size: number, expanded?: boolean) => void;
}

const d = DEFAULT_LAYOUT;

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
  setExplorerCollapsed: (collapsed) =>
    set({ explorerCollapsed: collapsed, ...(collapsed ? {} : { explorerWidth: clampPanelSize(useWorkspaceStore.getState().explorerWidth, PANEL_BOUNDS.explorer, d.explorerWidth) }) }),
  rightPanelCollapsed: false,
  setRightPanelCollapsed: (collapsed) =>
    set({ rightPanelCollapsed: collapsed, ...(collapsed ? {} : { rightWidth: clampPanelSize(useWorkspaceStore.getState().rightWidth, PANEL_BOUNDS.right, d.rightWidth) }) }),
  explorerWidth: d.explorerWidth,
  rightWidth: d.rightWidth,
  bottomDockHeight: d.bottomDockHeight,
  setPanelSize: (panel, size, expanded) =>
    set((s) => {
      switch (panel) {
        case "explorer":
          return { explorerWidth: clampPanelSize(size, PANEL_BOUNDS.explorer, d.explorerWidth), explorerCollapsed: expanded ?? false };
        case "right":
          return { rightWidth: clampPanelSize(size, PANEL_BOUNDS.right, d.rightWidth), rightPanelCollapsed: expanded ?? false };
        case "bottom":
          return { bottomDockHeight: clampPanelSize(size, PANEL_BOUNDS.bottom, d.bottomDockHeight), bottomDockExpanded: expanded ?? s.bottomDockExpanded };
      }
    }),
}));