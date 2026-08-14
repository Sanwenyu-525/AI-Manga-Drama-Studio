import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Project } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { ProjectExplorer } from "./ProjectExplorer";
import { StoryboardView } from "../storyboard/StoryboardView";
import { ShotInspector } from "../storyboard/ShotInspector";
import { EpisodePanel } from "../script/EpisodePanel";
import { useWorkspaceStore } from "../../stores/workspaceStore";

export function StudioPage() {
  const { projectId = "" } = useParams();
  const selection = useSelectionStore((s) => s.selection);
  const setProject = useSelectionStore((s) => s.setProject);
  const setEpisode = useSelectionStore((s) => s.setEpisode);
  const rightPanelTab = useWorkspaceStore((s) => s.rightPanelTab);

  useEffect(() => {
    setProject(projectId);
  }, [projectId, setProject]);

  const { data: project } = useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => api.get<Project>(`/projects/${projectId}`),
  });

  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => api.get<Episode[]>(`/projects/${projectId}/episodes`),
    enabled: !!projectId,
  });

  // auto-select first episode so the explorer has a scene to expand
  useEffect(() => {
    if (!selection.episodeId && episodes && episodes.length > 0) {
      setEpisode(episodes[0].id);
    }
  }, [episodes, selection.episodeId, setEpisode]);

  const activeEpisode = episodes?.find((e) => e.id === selection.episodeId);

  return (
    <div className="app-shell">
      <header className="top-bar">
        <Link to="/" className="brand">
          🎬 AI Manga Drama Studio
        </Link>
        <span className="top-project">{project?.name ?? "…"}</span>
        <span className="top-spacer" />
        <span className={`dot ${selection.sceneId ? "on" : ""}`}>
          {selection.sceneId ? "Storyboard" : "Script"}
        </span>
      </header>

      <aside className="explorer">
        <ProjectExplorer projectId={projectId} />
      </aside>

      <main className="workspace">
        {selection.sceneId ? (
          <StoryboardView sceneId={selection.sceneId} />
        ) : activeEpisode ? (
          <EpisodePanel episode={activeEpisode} />
        ) : (
          <div className="empty-state">
            <p>从左侧选择一个剧集开始</p>
            <p className="muted">创建项目 → 添加剧集 → 导入小说 → AI 分析 → 生成分镜</p>
          </div>
        )}
      </main>

      <aside className="right-panel">
        {rightPanelTab === "inspector" ? <ShotInspector /> : <DirectorPlaceholder />}
      </aside>

      <footer className="bottom-dock">
        <span className="muted">Generation Queue（Stage C 接入 ComfyUI 后启用）</span>
      </footer>
    </div>
  );
}

function DirectorPlaceholder() {
  const setRightPanelTab = useWorkspaceStore((s) => s.setRightPanelTab);
  return (
    <div className="panel-tab-content">
      <div className="panel-tabs">
        <button className="tab active" onClick={() => setRightPanelTab("inspector")}>
          Inspector
        </button>
        <button className="tab">AI Director</button>
      </div>
      <div className="placeholder-note">
        <h3>AI Director</h3>
        <p className="muted">Stage D 接入。届时可直接说：“把这个镜头改成近景”。</p>
      </div>
    </div>
  );
}
