// TanStack Query keys (api-event-contract §97) — single place for all query keys.

export const queryKeys = {
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  bootstrap: (projectId: string) => ["bootstrap", projectId] as const,
  episodes: (projectId: string) => ["episodes", projectId] as const,
  scenes: (episodeId: string) => ["scenes", episodeId] as const,
  storyboard: (sceneId: string) => ["storyboard", sceneId] as const,
  shot: (shotId: string) => ["shot", shotId] as const,
  shots: (sceneId: string) => ["shots", sceneId] as const,
  characters: (projectId: string) => ["characters", projectId] as const,
  characterVersions: (characterId: string) => ["characterVersions", characterId] as const,
  locations: (projectId: string) => ["locations", projectId] as const,
  locationVersions: (locationId: string) => ["locationVersions", locationId] as const,
  projectTree: (projectId: string) => ["projectTree", projectId] as const,
  projectSettings: (projectId: string) => ["projectSettings", projectId] as const,
  provenance: (assetId: string) => ["provenance", assetId] as const,
  jobs: (projectId: string) => ["jobs", projectId] as const,
  job: (jobId: string) => ["job", jobId] as const,
  /** P7-T019/020: agent run detail + its proposals (keyed by run). */
  agentRun: (runId: string) => ["agentRun", runId] as const,
  proposals: (runId: string) => ["proposals", runId] as const,
  projectAssets: (projectId: string, type?: string | null) => ["projectAssets", projectId, type ?? "all"] as const,
  asset: (assetId: string) => ["asset", assetId] as const,
};
