// P6-T004 Editor Tabs — WorkspaceHost renders the active tab's content in the center.
// Tabs: `script` (EpisodePanel), `scene` (StoryboardView), `shot` (ShotInspector,
// center variant). The base script tab preserves the existing single-view behavior;
// extra scene/shot tabs are the enhancement layer on top of the URL-driven shell.

import { FilmStrip, SquaresFour } from "@phosphor-icons/react";
import type { Episode } from "../../api/types";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { EpisodePanel } from "../../features/script/EpisodePanel";
import { StoryboardView } from "../../features/storyboard/StoryboardView";
import { ShotInspector } from "../../features/storyboard/ShotInspector";
import { EditorTabsBar } from "./EditorTabsBar";

interface WorkspaceHostProps {
  projectId: string;
  activeEpisode: Episode | undefined;
  /** Called after AI creates scenes so the caller can navigate (kept for parity). */
  onScenesCreated?: (sceneIds: string[]) => void;
}

export function WorkspaceHost({ activeEpisode, onScenesCreated }: WorkspaceHostProps) {
  const open = useEditorTabsStore((s) => s.open);
  const activeTabId = useEditorTabsStore((s) => s.activeTabId);
  const active = open.find((t) => t.id === activeTabId) ?? open[0];

  let body: React.ReactNode;
  if (!active || active.kind === "script") {
    body = scriptBody(activeEpisode, onScenesCreated);
  } else if (active.kind === "scene") {
    body = active.sceneId ? <StoryboardView sceneId={active.sceneId} /> : scriptBody(activeEpisode, onScenesCreated);
  } else {
    // shot tab → full-bleed ShotInspector detail in the center
    body = <ShotInspector variant="center" />;
  }

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