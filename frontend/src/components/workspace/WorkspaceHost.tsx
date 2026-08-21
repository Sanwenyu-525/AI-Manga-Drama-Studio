// P6-T004 Editor Tabs — WorkspaceHost renders the URL-selected content in the center.
// Tabs mirror navigable script/scene/shot URLs; they do not choose a second center view.

import { FilmStrip, SquaresFour } from "@phosphor-icons/react";
import type { Episode } from "../../api/types";
import { EpisodePanel } from "../../features/script/EpisodePanel";
import { StoryboardView } from "../../features/storyboard/StoryboardView";
import { ShotInspector } from "../../features/storyboard/ShotInspector";
import { EditorTabsBar } from "./EditorTabsBar";
import { useStudioRoute } from "../../features/studio/studioRoute";

interface WorkspaceHostProps {
  projectId: string;
  activeEpisode: Episode | undefined;
  /** Called after AI creates scenes so the caller can navigate (kept for parity). */
  onScenesCreated?: (sceneIds: string[]) => void;
}

export function WorkspaceHost({ activeEpisode, onScenesCreated }: WorkspaceHostProps) {
  const route = useStudioRoute();

  let body: React.ReactNode;
  if (route.workspace === "storyboard" && route.sceneId) body = <StoryboardView sceneId={route.sceneId} />;
  else if (route.workspace === "shot") body = <ShotInspector variant="center" />;
  else body = scriptBody(activeEpisode, onScenesCreated);

  return (
    <div className="workspace-host">
      <EditorTabsBar />
      <div className="workspace-host-body">{body}</div>
    </div>
  );
}

function scriptBody(activeEpisode: Episode | undefined, onScenesCreated?: (sceneIds: string[]) => void) {
  if (!activeEpisode) {
    return (
      <div className="empty-state studio-empty">
        <FilmStrip size={34} />
        <h2>添加第一个剧集</h2>
        <p>从左侧项目树建立剧集，然后导入小说开始 AI 分析。</p>
      </div>
    );
  }
  return <EpisodePanel episode={activeEpisode} onScenesCreated={onScenesCreated} />;
}

export function SceneEmptyState() {
  return (
    <div className="empty-state studio-empty">
      <SquaresFour size={34} />
      <h2>选择一个场景</h2>
      <p>从左侧项目树选择场景查看分镜。</p>
    </div>
  );
}
