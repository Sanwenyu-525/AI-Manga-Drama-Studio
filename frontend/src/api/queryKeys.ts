// TanStack Query keys (api-event-contract §97) — single place for all query keys.

export const queryKeys = {
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  episodes: (projectId: string) => ["episodes", projectId] as const,
  scenes: (episodeId: string) => ["scenes", episodeId] as const,
  storyboard: (sceneId: string) => ["storyboard", sceneId] as const,
  shot: (shotId: string) => ["shot", shotId] as const,
  shots: (sceneId: string) => ["shots", sceneId] as const,
};
