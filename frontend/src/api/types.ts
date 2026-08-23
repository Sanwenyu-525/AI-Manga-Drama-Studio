// DTO types mirroring backend Pydantic schemas (api-event-contract §9-21, §100-102).

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  aspect_ratio: string | null;
  fps: number | null;
  cover_url: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface Episode {
  id: string;
  project_id: string;
  episode_number: number;
  title: string | null;
  source_text: string | null;
  script_text: string | null;
  summary: string | null;
  status: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface Scene {
  id: string;
  episode_id: string;
  scene_number: number;
  name: string | null;
  location_id: string | null;
  time_of_day: string | null;
  lighting: string | null;
  weather: string | null;
  mood: string | null;
  description: string | null;
  scene_order: number | null;
  status: string;
  shot_count: number;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface SceneSummary {
  id: string;
  scene_number: number;
  name: string | null;
}

export interface Shot {
  id: string;
  scene_id: string;
  shot_number: number;
  shot_order: number;
  shot_type: string;
  camera_angle: string | null;
  camera_movement: string | null;
  lens: string | null;
  duration: number | null;
  action: string | null;
  emotion: string | null;
  dialogue: string | null;
  image_prompt: string | null;
  character_ids: string[];
  status: string;
  dirty_state: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface ShotSummary {
  id: string;
  shot_number: number;
  shot_type: string;
  duration: number | null;
  status: string;
  dirty_state: string;
  thumbnail_url: string | null;
  character_names: string[];
  active_generation: Record<string, unknown> | null;
}

export interface Storyboard {
  scene: SceneSummary;
  shots: ShotSummary[];
}

export interface ShotUpdateRequest {
  revision: number;
  patch: Partial<ShotUpdatePatch>;
}

export interface ShotUpdatePatch {
  shot_type: string;
  camera_angle: string | null;
  camera_movement: string | null;
  duration: number | null;
  action: string | null;
  emotion: string | null;
  dialogue: string | null;
  image_prompt: string | null;
  character_ids?: string[];
  status: string;
  dirty_state: string;
}

// --- Optimistic-concurrency update requests (api-event-contract §21/§88):
//     {revision, patch}; 409 CONFLICT when the caller's revision is stale. ---

export interface EpisodeUpdatePatch {
  title?: string | null;
  source_text?: string | null;
  script_text?: string | null;
  summary?: string | null;
  status?: string;
}

export interface EpisodeUpdateRequest {
  revision: number;
  patch: EpisodeUpdatePatch;
}

export interface SceneUpdatePatch {
  name?: string | null;
  location_id?: string | null;
  time_of_day?: string | null;
  lighting?: string | null;
  weather?: string | null;
  mood?: string | null;
  description?: string | null;
  status?: string;
}

export interface SceneUpdateRequest {
  revision: number;
  patch: SceneUpdatePatch;
}

export interface ProjectUpdatePatch {
  name?: string | null;
  description?: string | null;
  status?: string;
  aspect_ratio?: string | null;
  fps?: number | null;
  default_language?: string | null;
}

export interface ProjectUpdateRequest {
  revision: number;
  patch: ProjectUpdatePatch;
}

// --- ProjectSettings (database-schema-design §15) ---

export interface ProjectSettings {
  project_id: string;
  language: string;
  default_llm_provider: string | null;
  default_llm_model: string | null;
  default_image_provider: string | null;
  default_image_model: string | null;
  default_video_provider: string | null;
  default_video_model: string | null;
  default_voice_provider: string | null;
  default_voice_model: string | null;
  default_image_workflow_id: string | null;
  default_video_workflow_id: string | null;
  auto_retry: number;
  max_retry_count: number;
  auto_save: number;
  continuity_enabled: number;
  auto_activate_new_generation: number;
  settings_json: Record<string, unknown> | null;
  updated_at: string;
}
// --- ProjectSettingUpdate (api-event-contract §142: PUT /projects/{id}/settings) ---
// Partial settings update — unprovided fields keep their current value on the server.
// 0/1 integer flags: auto_retry/max_retry_count range over 0.., boolean-ish flags are 0|1.

export interface ProjectSettingUpdate {
  language?: string;
  default_llm_provider?: string | null;
  default_llm_model?: string | null;
  default_image_provider?: string | null;
  default_image_model?: string | null;
  default_video_provider?: string | null;
  default_video_model?: string | null;
  default_voice_provider?: string | null;
  default_voice_model?: string | null;
  default_image_workflow_id?: string | null;
  default_video_workflow_id?: string | null;
  auto_retry?: number;
  max_retry_count?: number;
  auto_save?: number;
  continuity_enabled?: number;
  auto_activate_new_generation?: number;
}

export interface Health {
  status: string;
  database: string;
  backend_version: string;
  api_version: string;
  event_protocol_version: string;
  env: string;
}

export interface ProviderStatus {
  id: string;
  name: string;
  type: string;
  status: string;
  capabilities: Record<string, boolean>;
  base_url?: string;
}

// --- P1: character DTOs (database-v0.1 §7, api-event-contract §20/§88) ---

export interface Character {
  id: string;
  project_id: string;
  name: string;
  alias: string | null;
  gender: string | null;
  age_description: string | null;
  appearance: string | null;
  personality: string | null;
  visual_prompt: string | null;
  negative_prompt: string | null;
  default_costume_id: string | null;
  status: string;
  revision: number;
  shot_count: number;
  master_version_id: string | null; // P2-T008: authoritative MASTER pointer
  created_at: string;
  updated_at: string;
}

export interface CharacterCreate {
  name: string;
  alias?: string | null;
  gender?: string | null;
  age_description?: string | null;
  appearance?: string | null;
  personality?: string | null;
  visual_prompt?: string | null;
  negative_prompt?: string | null;
  status?: string;
}

export interface CharacterUpdatePatch {
  name?: string;
  alias?: string | null;
  gender?: string | null;
  age_description?: string | null;
  appearance?: string | null;
  personality?: string | null;
  visual_prompt?: string | null;
  negative_prompt?: string | null;
  status?: string;
}

export interface CharacterUpdateRequest {
  revision: number;
  patch: CharacterUpdatePatch;
}

export interface CharacterSummary {
  id: string;
  name: string;
  alias: string | null;
  status: string;
}

// --- bootstrap (api-event-contract §103-104) ---

export interface BootstrapEpisode {
  id: string;
  episode_number: number;
  title: string | null;
  scene_count: number;
}

export interface ProjectBootstrap {
  project: Project;
  episodes: BootstrapEpisode[];
  characters: CharacterSummary[];
  providers: ProviderStatus[];
  active_generations: number;
  active_agent_runs: number;
}

// --- Stage B: AI planning DTOs (mvp-spec §55-57) ---

export interface ScenePlan {
  scene_number: number;
  title: string;
  location: string;
  time: string | null;
  description: string;
  mood: string | null;
}

export interface ShotPlan {
  shot_number: number;
  shot_type: string;
  camera_angle: string | null;
  camera_movement: string | null;
  duration: number;
  action: string;
  emotion: string | null;
  dialogue: string | null;
  image_prompt: string | null;
}

export type OperationStatus = "queued" | "running" | "completed" | "failed";

export interface Operation {
  id: string;
  type: string;
  project_id: string | null;
  status: OperationStatus;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// --- Stage C: generation DTOs (api-event-contract §35-39) ---

export interface GenerationRead {
  id: string;
  project_id: string;
  shot_id: string | null;
  type: string;
  provider: string;
  model: string | null;
  workflow_id: string | null;
  prompt_version_id: string | null; // ADR-002
  status: string;
  progress: number;
  stage: string | null;
  output_asset_id: string | null;
  error_message: string | null;
  retry_of: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AssetVersionRead {
  id: string; // asset id (ADR-001: id == asset_id)
  shot_id: string;
  asset_id: string;
  media_type: string;
  version_number: number;
  generation_id: string | null;
  is_active: boolean;
  status: string;
  notes: string | null;
  created_at: string;
}

// --- Stage D: agent DTOs (api-event-contract §23-33) ---

export interface AgentPlanStep {
  tool: string;
  arguments: Record<string, unknown>;
}

export type AgentRunStatus =
  | "idle"
  | "thinking"
  | "planning"
  | "executing"
  | "reviewing"
  | "cancelling"
  | "cancelled"
  | "WAITING_HUMAN"
  | "waiting_human"
  | "completed"
  | "failed";

export interface AgentRunRead {
  id: string;
  project_id: string;
  status: AgentRunStatus;
  current_stage: string | null;
  plan: {
    objective: string;
    steps: AgentPlanStep[];
    requires_clarification: boolean;
    clarification_message: string | null;
  } | null;
  approval: Record<string, unknown> | null;
  change_set_id: string | null;
  result: Record<string, unknown> | null;
  /** P7-T020: proposals awaiting (or in) human review, inlined on the run detail. */
  pending_proposals?: AgentProposal[];
  created_at: string;
  updated_at: string;
}

// --- P7-T020/021: Director proposal DTOs (api-event-contract §100-102).
// Backend Proposal system ships in the same merge batch; the changes field is
// implemented here against BOTH agreed shapes (normalized by the panel parser):
//     1. object map  { image_prompt: { from: "旧", to: "新" } }
//     2. single item { field: "image_prompt", from: "旧", to: "新" }

export type AgentProposalStatus = "pending" | "approved" | "rejected" | "conflict";

/** Normalized per-field change (output of normalizeProposalChanges). */
export interface AgentProposalFieldChange {
  field: string;
  from: unknown;
  to: unknown;
}

/** Raw changes payload — supports either backend shape, normalized before render. */
export type AgentProposalChanges =
  Record<string, { from: unknown; to: unknown }> | { field: string; from: unknown; to: unknown };

export interface AgentProposal {
  id: string;
  tool: string;
  target_type: string;
  target_id: string;
  base_revision: number | null;
  changes: AgentProposalChanges;
  status: AgentProposalStatus;
  created_at?: string | null;
}

export const SHOT_TYPES = ["extreme_wide", "wide", "full", "medium", "close_up", "extreme_close_up"] as const;

export const SHOT_TYPE_LABELS: Record<string, string> = {
  extreme_wide: "大远景",
  wide: "远景",
  full: "全景",
  medium: "中景",
  close_up: "近景",
  extreme_close_up: "特写",
};
// --- Provenance (P3-T012/T013: GET /assets/{asset_id}/provenance) ---

export interface GenerationInputRead {
  id: string;
  generation_id: string;
  input_type: string;
  reference_type: string | null;
  reference_id: string | null;
  role: string | null;
  order_index: number;
  metadata_json: string | null;
}

export interface GenerationOutputRead {
  generation_id: string;
  asset_id: string;
  role: string | null;
  order_index: number;
  type: string | null;
  status: string | null;
  version_number: number | null;
  file_path: string | null;
}

// The "producing generation" block of an asset (provenance.py GenerationProvenanceBlock).
// parameters is the raw generation JSON-string (parsed at the call site).
export interface GenerationProvenanceBlock {
  id: string;
  type: string;
  provider: string;
  model: string | null;
  workflow_id: string | null;
  prompt_version_id: string | null;
  status: string | null;
  created_at: string | null;
  completed_at: string | null;
  parameters: string | null;
}

// Asset summary (asset dict emitted by ProvenanceService._asset_summary).
export interface ProvenanceAsset {
  id: string;
  project_id: string;
  type: string;
  name: string | null;
  file_path: string | null;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  status: string;
  source_type: string;
  version_group_id: string | null;
  version_number: number | null;
  generation_id: string | null;
  parent_asset_id: string | null;
  meta: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ProvenanceRead {
  asset: ProvenanceAsset;
  generation: GenerationProvenanceBlock | null;
  inputs: GenerationInputRead[];
  retry_of: string | null;
  parent_asset_id: string | null;
  ancestors: string[]; // retry chain, oldest first, excluding this generation
}

// --- P6: character / location visual-version DTOs (P2-T007/T008/T009) & asset/tree ---
// Backend: backend/app/domain/character.py, location.py, asset.py, readmodels.py.

export interface CharacterVersionCreate {
  asset_id: string;
  name?: string | null;
  description?: string | null;
}

export interface CharacterVersion {
  id: string;
  character_id: string;
  version_number: number;
  asset_id: string;
  name: string | null;
  description: string | null;
  status: string; // active | stale | archived
  checksum: string | null;
  is_master: boolean;
  created_at: string;
  updated_at: string;
}

export interface Location {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  visual_prompt: string | null;
  status: string;
  revision: number;
  master_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface LocationCreate {
  name: string;
  description?: string | null;
  visual_prompt?: string | null;
  status?: string;
}

export interface LocationVersionCreate {
  asset_id: string;
  name?: string | null;
  description?: string | null;
}

export interface LocationVersion {
  id: string;
  location_id: string;
  version_number: number;
  asset_id: string;
  name: string | null;
  description: string | null;
  status: string; // active | stale | archived
  checksum: string | null;
  is_master: boolean;
  created_at: string;
  updated_at: string;
}

export interface AssetRead {
  id: string;
  project_id: string;
  type: string;
  name: string | null;
  file_path: string | null;
  thumbnail_path: string | null;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  duration: number | null;
  file_size: number | null;
  meta: Record<string, unknown> | null;
  version_group_id: string | null;
  version_number: number | null;
  status: string;
  source_type: string;
  checksum: string | null;
  generation_id: string | null;
  parent_asset_id: string | null;
  created_at: string;
}

// --- P2-T011 / P6-T016: project tree (asset browser aggregation source) ---

export interface ShotTreeItem {
  id: string;
  shot_number: number;
  shot_type: string;
  status: string;
  dirty_state: string;
  revision: number;
  active_image_version: number | null;
  active_video_version: number | null;
  active_prompt_version_id: string | null;
}

export interface SceneTreeItem {
  id: string;
  scene_number: number;
  name: string | null;
  shot_count: number;
  shots: ShotTreeItem[];
}

export interface EpisodeTreeItem {
  id: string;
  episode_number: number;
  title: string | null;
  scene_count: number;
  scenes: SceneTreeItem[];
}

export interface ProjectTreeRead {
  project: Project;
  episodes: EpisodeTreeItem[];
}

// --- P6-T022/023/024: scene-generation Job + JobTask DTOs (api-event-contract §142) ---
// Backend: backend/app/domain/job.py (P5-E1/E2).

export type JobTaskType = "image" | "video";

export interface JobTaskRead {
  id: string;
  job_id: string;
  task_type: JobTaskType;
  target_type: "shot";
  target_id: string;
  shot_id: string;
  status: string;
  priority: number;
  progress: number;
  generation_id: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobSummaryRead {
  id: string;
  project_id: string;
  name: string;
  job_type: string;
  scene_id: string | null;
  status: string;
  progress: number;
  error_summary: string | null;
  task_count: number;
  created_at: string;
  updated_at: string;
}

export interface JobRead extends JobSummaryRead {
  task_status_counts: Record<string, number>;
  tasks: JobTaskRead[];
}

export interface JobCreate {
  scene_id: string;
  name?: string | null;
}

// --- P6 (parallel backend task) asset listing/detail DTOs.
// Backend asset.py DTO shape (GET /projects/{id}/assets → {total, items};
// GET /assets/{id} → AssetRead). Implemented against the agreed convention while the
// backend listing endpoint ships in the same merge batch.

export interface AssetListRead {
  total: number;
  items: AssetRead[];
}

// --- P8-T020: Continuity state + warnings DTOs.
// Implemented against the agreed Phase-8 continuity contract (parallel backend task
// feature/P8-continuity-state + feature/P8-continuity-agent). All shapes stay loose
// (optional fields) so a forward-loaded backend variant still renders.

/** Per-character continuity snapshot (JSON state shape). */
export interface CharacterState {
  character_id?: string | null;
  character_version_id?: string | null;
  costume_id?: string | null;
  position?: string | null;
  orientation?: string | null;
  action?: string | null;
  emotion?: string | null;
}

/** Per-location environment continuity snapshot (JSON state shape). */
export interface EnvironmentState {
  location_id?: string | null;
  time_of_day?: string | null;
  lighting?: string | null;
  weather?: string | null;
  mood?: string | null;
}

/** Per-prop continuity snapshot (JSON state shape). */
export interface PropState {
  prop_id?: string | null;
  holder_character_id?: string | null;
  visible?: boolean | null;
}

/** Union of the JSON state shapes carried by a continuity snapshot. */
export interface ContinuityState {
  characters?: CharacterState[] | Record<string, CharacterState> | null;
  environment?: EnvironmentState | null;
  props?: PropState[] | Record<string, PropState> | null;
  [key: string]: unknown;
}

export type ContinuitySeverity = "info" | "warning" | "error";

/** One continuity warning (deterministic rule or agent semantic detection). */
export interface ContinuityWarning {
  id?: string;
  category?: string | null;
  severity: ContinuitySeverity | string;
  message: string;
  evidence?: unknown;
  status?: string | null; // open | acknowledged | fixed
  created_at?: string | null;
}

/** Per-shot continuity delta summary inside a scene read. */
export interface ContinuityShotRead {
  shot_id: string;
  start_state?: ContinuityState | null;
  end_state?: ContinuityState | null;
  delta?: Record<string, unknown> | null;
  state_hash?: string | null;
  warnings?: ContinuityWarning[];
}

/** GET /scenes/{id}/continuity — scene-wide continuity read. */
export interface ContinuitySceneRead {
  scene_id: string;
  base_state?: ContinuityState | null;
  shots?: ContinuityShotRead[];
  scene_warnings?: ContinuityWarning[];
}

/** GET /shots/{id}/continuity-state — single-shot continuity card. */
export interface ContinuityShotReadCard extends Omit<ContinuityShotRead, "shot_id"> {
  shot_id: string;
}

/** Agent continuity run trigger result (202 Accepted + run_id). */
export interface AgentContinuityRun {
  run_id?: string;
  status?: string;
  message?: string;
}

// --- Phase 9 (P9-E1/E2/E3): Timeline + Episode Render DTOs (api-event-contract §93).
// Backend: backend/app/domain/timeline.py (TimelineRead/TrackRead/ClipRead/RenderRead/FinalVideoRead).

export type TimelineTrackType = "VIDEO" | "VOICE" | "MUSIC" | "SFX" | "SUBTITLE";

/** Lightweight asset summary bound to a clip (never raw paths). */
export interface TimelineClipAsset {
  id: string;
  type: string;
  name: string | null;
  status: string;
  version_group_id: string | null;
  version_number: number | null;
  thumbnail_url: string | null;
  mime_type: string | null;
}

export interface TimelineClip {
  id: string;
  timeline_id: string;
  track_id: string;
  asset_id: string;
  shot_id: string | null;
  start_time: number;
  end_time: number;
  source_in: number;
  source_out: number | null;
  order_index: number;
  enabled: number;
  text: string | null; // subtitle/voice content
  asset: TimelineClipAsset | null;
  created_at: string;
  updated_at: string;
}

export interface TimelineTrack {
  id: string;
  timeline_id: string;
  track_type: string;
  name: string | null;
  order_index: number;
  locked: number;
  muted: number;
  created_at: string;
}

export interface Timeline {
  id: string;
  project_id: string;
  episode_id: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  status: string;
  tracks: TimelineTrack[];
  clips: TimelineClip[];
  created_at: string;
  updated_at: string;
}

export interface TimelineClipCreate {
  track_id: string;
  asset_id: string;
  shot_id?: string | null;
  start_time?: number;
  end_time?: number;
  source_in?: number;
  source_out?: number | null;
  order_index?: number | null;
  enabled?: number;
}

export interface TimelineClipUpdatePatch {
  track_id?: string;
  start_time?: number;
  end_time?: number;
  source_in?: number;
  source_out?: number | null;
  order_index?: number;
  enabled?: number;
}

export interface TimelineTrackCreate {
  track_type?: TimelineTrackType;
  name?: string | null;
  order_index?: number | null;
}

export interface TimelineRenderRead {
  generation_id: string;
  timeline_id: string;
  episode_id: string | null;
  status: string;
  message: string | null;
}

/** Latest rendered episode export (FINAL_VIDEO asset) — the deliverable. */
export interface FinalVideoRead {
  asset_id: string;
  project_id: string;
  episode_id: string;
  name: string | null;
  type: string;
  version_number: number | null;
  mime_type: string | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  file_size: number | null;
  status: string;
  content_url: string;
  thumbnail_url: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
}

export const TIMELINE_TRACK_LABELS: Record<string, string> = {
  VIDEO: "视频",
  VOICE: "对白",
  MUSIC: "音乐",
  SFX: "音效",
  SUBTITLE: "字幕",
};
