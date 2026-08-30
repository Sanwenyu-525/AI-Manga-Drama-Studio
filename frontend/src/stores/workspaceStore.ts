// Workspace / UI layout state (frontend-ux §82: Zustand holds local UI state only).
// P6-T002: panel widths/heights are hoisted here (shell-level) so right/bottom
// panels can be dragged and the sizes survive collapse. P6-T003 persists them.

import { create } from "zustand";
import { PANEL_BOUNDS, clampPanelSize, type PanelId } from "../lib/panels";
import { DEFAULT_LAYOUT } from "../lib/persistence";

interface WorkspaceState {
  rightPanelTab: "inspector" | "director";
  setRightPanelTab: (tab: "inspector" | "director") => void;
  bottomDockTab: "queue" | "history" | "jobs";
  setBottomDockTab: (tab: "queue" | "history" | "jobs") => void;
  bottomDockExpanded: boolean;
  setBottomDockExpanded: (expanded: boolean) => void;
  rightPanelCollapsed: boolean;
  setRightPanelCollapsed: (collapsed: boolean) => void;
  // True while a panel resize gesture is live — the shell disables its layout
  // transition for the gesture so the handle tracks the pointer 1:1.
  panelResizing: boolean;
  setPanelResizing: (resizing: boolean) => void;
  // --- P6-T002 panel sizes (hoisted to shell level) ---
  rightWidth: number;
  bottomDockHeight: number;
  setPanelSize: (panel: PanelId, size: number, expanded?: boolean) => void;
}

const d = DEFAULT_LAYOUT;

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  rightPanelTab: "inspector",
  setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
  bottomDockTab: "queue",
  setBottomDockTab: (tab) => set({ bottomDockTab: tab }),
  bottomDockExpanded: false,
  setBottomDockExpanded: (expanded) => set({ bottomDockExpanded: expanded }),
  rightPanelCollapsed: false,
  setRightPanelCollapsed: (collapsed) =>
    set({
      rightPanelCollapsed: collapsed,
      ...(collapsed
        ? {}
        : { rightWidth: clampPanelSize(useWorkspaceStore.getState().rightWidth, PANEL_BOUNDS.right, d.rightWidth) }),
    }),
  panelResizing: false,
  setPanelResizing: (resizing) => set({ panelResizing: resizing }),
  rightWidth: d.rightWidth,
  bottomDockHeight: d.bottomDockHeight,
  setPanelSize: (panel, size, expanded) =>
    set((s) => {
      switch (panel) {
        case "right":
          return {
            rightWidth: clampPanelSize(size, PANEL_BOUNDS.right, d.rightWidth),
            rightPanelCollapsed: expanded ?? false,
          };
        case "bottom":
          return {
            bottomDockHeight: clampPanelSize(size, PANEL_BOUNDS.bottom, d.bottomDockHeight),
            bottomDockExpanded: expanded ?? s.bottomDockExpanded,
          };
      }
    }),
}));
