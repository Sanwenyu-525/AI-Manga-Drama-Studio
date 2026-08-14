// Selection store (frontend-ux §44-46, §81): the single source of "what the user has selected".
// Passed to the AI Director on every agent request (contract §78) — Stage D wiring.

import { create } from "zustand";

export type WorkspaceType = "storyboard" | "script" | "assets" | "preview" | "timeline";

export interface StudioSelection {
  projectId?: string;
  episodeId?: string;
  sceneId?: string;
  shotIds: string[];
  assetIds: string[];
  workspace: WorkspaceType;
}

interface SelectionState {
  selection: StudioSelection;
  setProject: (projectId: string) => void;
  setEpisode: (episodeId: string) => void;
  setScene: (sceneId: string) => void;
  selectShot: (shotId: string) => void;
  clearShots: () => void;
  setWorkspace: (workspace: WorkspaceType) => void;
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selection: { shotIds: [], assetIds: [], workspace: "storyboard" },
  setProject: (projectId) =>
    set((s) => ({ selection: { ...s.selection, projectId, episodeId: undefined, sceneId: undefined, shotIds: [] } })),
  setEpisode: (episodeId) =>
    set((s) => ({ selection: { ...s.selection, episodeId, sceneId: undefined, shotIds: [] } })),
  setScene: (sceneId) => set((s) => ({ selection: { ...s.selection, sceneId, shotIds: [] } })),
  selectShot: (shotId) => set((s) => ({ selection: { ...s.selection, shotIds: [shotId] } })),
  clearShots: () => set((s) => ({ selection: { ...s.selection, shotIds: [] } })),
  setWorkspace: (workspace) => set((s) => ({ selection: { ...s.selection, workspace } })),
}));
