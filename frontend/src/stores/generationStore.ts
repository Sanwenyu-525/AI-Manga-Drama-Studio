// Generation state (frontend-ux §85): ONLY live transient state — progress, speed, queue position.
// Final generation data always comes from the server (TanStack Query).

import { create } from "zustand";

export interface LiveGeneration {
  id: string;
  shotId: string | null;
  progress: number;
  stage: string | null;
  status: string;
}

interface GenerationState {
  live: Record<string, LiveGeneration>;
  upsert: (gen: LiveGeneration) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export const useGenerationStore = create<GenerationState>((set) => ({
  live: {},
  upsert: (gen) => set((s) => ({ live: { ...s.live, [gen.id]: gen } })),
  remove: (id) =>
    set((s) => {
      const { [id]: _removed, ...rest } = s.live;
      return { live: rest };
    }),
  clear: () => set({ live: {} }),
}));
