import { useSelectionStore, type StudioSelection } from "../../stores/selectionStore";
import { useStudioRoute, type StudioRoute } from "../studio/studioRoute";

export type DirectorWorkspace = "storyboard" | "script" | "assets" | "timeline";

export interface DirectorContext {
  workspace: DirectorWorkspace;
  project_id?: string;
  episode_id?: string;
  scene_id?: string;
  shot_ids: string[];
  asset_ids: string[];
}

export function buildDirectorContext(route: StudioRoute, selection: StudioSelection): DirectorContext {
  const workspace: DirectorWorkspace = route.workspace === "shot" ? "storyboard" : route.workspace;
  const isStoryboard = route.workspace === "storyboard" || route.workspace === "shot";
  return {
    workspace,
    project_id: route.projectId || undefined,
    episode_id:
      workspace === "script" || workspace === "storyboard" || workspace === "timeline" ? route.episodeId : undefined,
    scene_id: isStoryboard ? route.sceneId : undefined,
    shot_ids: route.shotId ? [route.shotId] : isStoryboard ? selection.shotIds : [],
    asset_ids: workspace === "assets" ? selection.assetIds : [],
  };
}

export function useDirectorContext(): DirectorContext {
  const route = useStudioRoute();
  const selection = useSelectionStore((state) => state.selection);
  return buildDirectorContext(route, selection);
}
