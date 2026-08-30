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
  const isStoryboard =
    route.workspace === "storyboard" ||
    route.workspace === "storyboard-index" ||
    route.workspace === "shots" ||
    route.workspace === "shot" ||
    route.workspace === "continuity";
  const usesTransientShotSelection = route.workspace === "storyboard";
  const workspace: DirectorWorkspace =
    route.workspace === "assets"
      ? "assets"
      : route.workspace === "timeline"
        ? "timeline"
        : isStoryboard
          ? "storyboard"
          : "script";
  return {
    workspace,
    project_id: route.projectId || undefined,
    episode_id:
      workspace === "script" || workspace === "storyboard" || workspace === "timeline" ? route.episodeId : undefined,
    scene_id: isStoryboard ? route.sceneId : undefined,
    shot_ids: route.shotId ? [route.shotId] : usesTransientShotSelection ? selection.shotIds : [],
    asset_ids: workspace === "assets" ? selection.assetIds : [],
  };
}

export function useDirectorContext(): DirectorContext {
  const route = useStudioRoute();
  const selection = useSelectionStore((state) => state.selection);
  return buildDirectorContext(route, selection);
}
