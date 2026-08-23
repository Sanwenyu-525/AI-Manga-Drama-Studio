import { useLocation } from "react-router-dom";
import type { EditorTab } from "../../lib/editorTabs";

export type StudioWorkspace = "script" | "storyboard" | "shot" | "assets" | "timeline";

export interface StudioRoute {
  projectId: string;
  episodeId?: string;
  sceneId?: string;
  shotId?: string;
  workspace: StudioWorkspace;
  legacy: boolean;
}

export function parseStudioRoute(pathname: string): StudioRoute | null {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] !== "projects" || !parts[1]) return null;
  const projectId = parts[1];

  if (parts[2] === "episodes" && parts[3]) {
    const episodeId = parts[3];
    if (parts[4] === "script") return { projectId, episodeId, workspace: "script", legacy: false };
    if (parts[4] === "timeline") return { projectId, episodeId, workspace: "timeline", legacy: false };
    if (parts[4] === "scenes" && parts[5]) {
      const sceneId = parts[5];
      if (parts[6] === "storyboard") return { projectId, episodeId, sceneId, workspace: "storyboard", legacy: false };
      if (parts[6] === "shots" && parts[7]) {
        return { projectId, episodeId, sceneId, shotId: parts[7], workspace: "shot", legacy: false };
      }
    }
  }

  if (parts[2] === "assets") return { projectId, workspace: "assets", legacy: false };
  if (parts[2] === "script") return { projectId, workspace: "script", legacy: true };
  if (parts[2] === "timeline") return { projectId, workspace: "timeline", legacy: true };
  if (parts[2] === "storyboard" && parts[3])
    return { projectId, sceneId: parts[3], workspace: "storyboard", legacy: true };
  return null;
}

export function useStudioRoute(): StudioRoute {
  const { pathname } = useLocation();
  return parseStudioRoute(pathname) ?? { projectId: "", workspace: "script", legacy: true };
}

export function canonicalScriptPath(projectId: string, episodeId: string): string {
  return `/projects/${projectId}/episodes/${episodeId}/script`;
}

export function canonicalStoryboardPath(projectId: string, episodeId: string, sceneId: string): string {
  return `/projects/${projectId}/episodes/${episodeId}/scenes/${sceneId}/storyboard`;
}

export function canonicalShotPath(projectId: string, episodeId: string, sceneId: string, shotId: string): string {
  return `/projects/${projectId}/episodes/${episodeId}/scenes/${sceneId}/shots/${shotId}`;
}

export function canonicalTimelinePath(projectId: string, episodeId: string): string {
  return `/projects/${projectId}/episodes/${episodeId}/timeline`;
}

export function editorTabPath(tab: EditorTab, current: StudioRoute): string | null {
  if (tab.kind === "script") {
    return current.episodeId
      ? canonicalScriptPath(current.projectId, current.episodeId)
      : `/projects/${current.projectId}/script`;
  }
  if (tab.kind === "scene" && tab.sceneId) {
    return tab.episodeId
      ? canonicalStoryboardPath(tab.projectId ?? current.projectId, tab.episodeId, tab.sceneId)
      : `/projects/${tab.projectId ?? current.projectId}/storyboard/${tab.sceneId}`;
  }
  if (tab.kind === "shot" && tab.shotId) {
    if (tab.episodeId && tab.sceneId)
      return canonicalShotPath(tab.projectId ?? current.projectId, tab.episodeId, tab.sceneId, tab.shotId);
    return `/projects/${tab.projectId ?? current.projectId}/shots/${tab.shotId}/versions`;
  }
  return null;
}
