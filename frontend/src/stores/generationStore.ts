// Generation state (frontend-ux §85): ONLY live transient state — progress, speed, queue position.
// Final generation data always comes from the server (TanStack Query).

import { create } from "zustand";

export interface LiveGeneration {
  id: string;
  shotId: string | null;
  progress: number;
  stage: string | null;
  status: string;
  type?: string | null; // image | render | audio (TASK-012) — payload may omit it
}

interface GenerationState {
  live: Record<string, LiveGeneration>;
  upsert: (gen: LiveGeneration) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export const useGenerationStore = create<GenerationState>((set) => ({
  live: {},
  // Merge sparse events: null/undefined fields (e.g. generation.started carries no
  // `type`) are dropped so they never clobber values set by earlier events.
  upsert: (gen) =>
    set((s) => {
      const patch = Object.fromEntries(
        Object.entries(gen).filter(([, v]) => v !== null && v !== undefined),
      ) as LiveGeneration;
      return { live: { ...s.live, [gen.id]: { ...s.live[gen.id], ...patch } } };
    }),
  remove: (id) =>
    set((s) => {
      const { [id]: _removed, ...rest } = s.live;
      return { live: rest };
    }),
  clear: () => set({ live: {} }),
}));
