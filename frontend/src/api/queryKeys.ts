// TanStack Query keys (api-event-contract §97) — single place for all query keys.

export const queryKeys = {
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  bootstrap: (projectId: string) => ["bootstrap", projectId] as const,
  episodes: (projectId: string) => ["episodes", projectId] as const,
  scene: (sceneId: string) => ["scene", sceneId] as const,
  scenes: (episodeId: string) => ["scenes", episodeId] as const,
  storyboard: (sceneId: string) => ["storyboard", sceneId] as const,
  shot: (shotId: string) => ["shot", shotId] as const,
  shots: (sceneId: string) => ["shots", sceneId] as const,
  characters: (projectId: string) => ["characters", projectId] as const,
  documents: (projectId: string) => ["documents", projectId] as const,
  costumes: (projectId: string) => ["costumes", projectId] as const,
  projectPrompts: (projectId: string) => ["prompts", projectId] as const,
  promptVersions: (promptId: string) => ["promptVersions", promptId] as const,
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
  /** P2-E3-T03: applied change sets (per project + per agent run). */
  changeSets: (projectId: string) => ["changeSets", projectId] as const,
  changeSetsForRun: (runId: string) => ["changeSets", "run", runId] as const,
  projectAssets: (projectId: string, type?: string | null) => ["projectAssets", projectId, type ?? "all"] as const,
  asset: (assetId: string) => ["asset", assetId] as const,
  /** P8-T020: scene continuity read + per-shot continuity-state + agent warning list. */
  sceneContinuity: (sceneId: string) => ["sceneContinuity", sceneId] as const,
  shotContinuity: (shotId: string) => ["shotContinuity", shotId] as const,
  continuityWarnings: (sceneId: string) => ["continuityWarnings", sceneId] as const,

  /** Phase 9 (api-event-contract §93): per-episode timeline + rendered export. */
  timeline: (episodeId: string) => ["timeline", episodeId] as const,
  finalVideo: (episodeId: string) => ["finalVideo", episodeId] as const,
  /** C2: 一键成片 pipeline（per-episode latest run）。 */
  pipeline: (episodeId: string) => ["pipeline", episodeId] as const,

  /** TASK-007: domains that previously used raw array keys — now factory-first. */
  providers: ["providers"] as const,
  llmConfig: ["llmConfig"] as const,
  /** P-LLM-Profiles: 命名连接列表 + 任务绑定（GET /llm/profiles）。 */
  llmProfiles: ["llmProfiles"] as const,
  imageConfig: ["imageConfig"] as const,
  /** 视频模型目录（GET /image/video-models，含实测可用性）。 */
  videoModels: ["video-models"] as const,
  /** P-LocalModels: ComfyUI checkpoint 列表（GET /providers/comfyui/models）。 */
  comfyuiModels: ["comfyui-models"] as const,
  /** P2-E4-T02: ComfyUI workflow 模板目录（GET /providers/comfyui/workflows）。 */
  comfyuiWorkflows: ["comfyui-workflows"] as const,
  workflows: ["workflows"] as const,
  recentGenerations: ["generations", "recent"] as const,
  shotGenerations: (shotId: string) => ["generations", shotId] as const,
  shotVersions: (shotId: string) => ["versions", shotId] as const,
  /** M1 前端闭环：镜头自动参考图预览 + 单条生成明细（含参考图溯源）。 */
  shotReferences: (shotId: string) => ["shotReferences", shotId] as const,
  generation: (generationId: string) => ["generation", generationId] as const,
  /** Timeline clip detail shape: ["shot","versions",shotId] (TimelineView clip inspector). */
  shotVersionEntries: (shotId: string) => ["shot", "versions", shotId] as const,

  /** TASK-007: explicit prefix keys for whole-domain invalidation (socket.ts + components).
   *  Matching an `as const` array by prefix is a deliberate, documented pattern — prefer
   *  these over hand-typed `["domain"]` literals so every key stays in one place. */
  prefixes: {
    shots: ["shots"] as const,
    scenes: ["scenes"] as const,
    storyboard: ["storyboard"] as const,
    prompts: ["prompts"] as const,
    generations: ["generations"] as const,
    versions: ["versions"] as const,
    timeline: ["timeline"] as const,
    finalVideo: ["finalVideo"] as const,
    pipeline: ["pipeline"] as const,
    jobs: ["jobs"] as const,
    job: ["job"] as const,
    proposals: ["proposals"] as const,
    agentRun: ["agentRun"] as const,
    changeSets: ["changeSets"] as const,
    sceneContinuity: ["sceneContinuity"] as const,
    continuityWarnings: ["continuityWarnings"] as const,
    shotContinuity: ["shotContinuity"] as const,
  },
};
