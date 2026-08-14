// DTO types mirroring backend Pydantic schemas (api-event-contract §9-21, §100-102).

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  aspect_ratio: string | null;
  fps: number | null;
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
