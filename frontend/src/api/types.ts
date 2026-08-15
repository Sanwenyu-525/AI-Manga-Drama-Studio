// DTO types mirroring backend Pydantic schemas (api-event-contract §9-21, §100-102).

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  aspect_ratio: string | null;
  fps: number | null;
  cover_url: string | null;
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

export interface AgentRunRead {
  id: string;
  project_id: string;
  status: string;
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
  created_at: string;
  updated_at: string;
}

export const SHOT_TYPES = [
  "extreme_wide",
  "wide",
  "full",
  "medium",
  "close_up",
  "extreme_close_up",
] as const;

export const SHOT_TYPE_LABELS: Record<string, string> = {
  extreme_wide: "大远景",
  wide: "远景",
  full: "全景",
  medium: "中景",
  close_up: "近景",
  extreme_close_up: "特写",
};
