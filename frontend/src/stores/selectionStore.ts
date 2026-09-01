// Temporary selection store (frontend-ux §44-46, §81). Route entities come from
// the URL; this store only owns transient Shot/Asset selection made in a view.

import { create } from "zustand";

export interface StudioSelection {
  shotIds: string[];
  assetIds: string[];
}

interface SelectionState {
  selection: StudioSelection;
  /** Single-select semantics: replaces the array (existing behavior). */
  selectShot: (shotId: string) => void;
  /** Multi-select (autonomous-iteration-02): additive toggle for batch operations. */
  toggleShot: (shotId: string) => void;
  /** Multi-select: bulk set (Shift+click range selection). */
  setShotIds: (shotIds: string[]) => void;
  clearShots: () => void;
  selectAsset: (assetId: string) => void;
  clearAssets: () => void;
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selection: { shotIds: [], assetIds: [] },
  selectShot: (shotId) => set((s) => ({ selection: { ...s.selection, shotIds: [shotId] } })),
  toggleShot: (shotId) =>
    set((s) => {
      const has = s.selection.shotIds.includes(shotId);
      const shotIds = has
        ? s.selection.shotIds.filter((id) => id !== shotId)
        : [...s.selection.shotIds, shotId];
      return { selection: { ...s.selection, shotIds } };
    }),
  setShotIds: (shotIds) => set((s) => ({ selection: { ...s.selection, shotIds } })),
  clearShots: () => set((s) => ({ selection: { ...s.selection, shotIds: [] } })),
  selectAsset: (assetId) => set((s) => ({ selection: { ...s.selection, assetIds: [assetId] } })),
  clearAssets: () => set((s) => ({ selection: { ...s.selection, assetIds: [] } })),
}));
