// Workspace / UI layout state (frontend-ux §82: Zustand holds local UI state only).

import { create } from "zustand";

interface WorkspaceState {
  activeShotId: string | null;
  setActiveShot: (shotId: string | null) => void;
  rightPanelTab: "inspector" | "director";
  setRightPanelTab: (tab: "inspector" | "director") => void;
  bottomDockTab: "queue" | "logs";
  setBottomDockTab: (tab: "queue" | "logs") => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeShotId: null,
  setActiveShot: (shotId) => set({ activeShotId: shotId }),
  rightPanelTab: "inspector",
  setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
  bottomDockTab: "queue",
  setBottomDockTab: (tab) => set({ bottomDockTab: tab }),
}));
