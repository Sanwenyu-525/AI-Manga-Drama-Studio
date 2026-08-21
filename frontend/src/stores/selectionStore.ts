// Temporary selection store (frontend-ux §44-46, §81). Route entities come from
// the URL; this store only owns transient Shot/Asset selection made in a view.

import { create } from "zustand";

export interface StudioSelection {
  shotIds: string[];
  assetIds: string[];
}

interface SelectionState {
  selection: StudioSelection;
  selectShot: (shotId: string) => void;
  clearShots: () => void;
  selectAsset: (assetId: string) => void;
  clearAssets: () => void;
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selection: { shotIds: [], assetIds: [] },
  selectShot: (shotId) => set((s) => ({ selection: { ...s.selection, shotIds: [shotId] } })),
  clearShots: () => set((s) => ({ selection: { ...s.selection, shotIds: [] } })),
  selectAsset: (assetId) => set((s) => ({ selection: { ...s.selection, assetIds: [assetId] } })),
  clearAssets: () => set((s) => ({ selection: { ...s.selection, assetIds: [] } })),
}));
