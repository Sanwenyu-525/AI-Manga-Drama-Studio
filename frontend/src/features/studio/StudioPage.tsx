import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Circle, FilmReel, FilmStrip, ImageSquare, MagicWand, Play, Scroll, SquaresFour } from "@phosphor-icons/react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, GenerationRead, Project, ProviderStatus } from "../../api/types";
import { EventRouter, setEventRouter, startEventSocket } from "../../events/socket";
import { useSelectionStore } from "../../stores/selectionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { AIDirectorPanel } from "../director/AIDirectorPanel";
import { GenerationQueue } from "../generation/GenerationQueue";
import { EpisodePanel } from "../script/EpisodePanel";
import { ShotInspector } from "../storyboard/ShotInspector";
import { StoryboardView } from "../storyboard/StoryboardView";
import { ProjectExplorer } from "./ProjectExplorer";

export function StudioPage() {
  const { projectId = "" } = useParams();
  const selection = useSelectionStore((state) => state.selection);
  const setProject = useSelectionStore((state) => state.setProject);
  const setEpisode = useSelectionStore((state) => state.setEpisode);
  const rightPanelTab = useWorkspaceStore((state) => state.rightPanelTab);
  const dockExpanded = useWorkspaceStore((state) => state.bottomDockExpanded);
  const queryClient = useQueryClient();

  useEffect(() => {
    startEventSocket();
    setEventRouter(new EventRouter(queryClient));
    return () => setEventRouter(null);
  }, [queryClient]);

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
    enabled: Boolean(projectId),
  });

  const { data: providers } = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.get<ProviderStatus[]>("/providers"),
    staleTime: 30_000,
  });

  useEffect(() => {
    if (!selection.episodeId && episodes?.[0]) setEpisode(episodes[0].id);
  }, [episodes, selection.episodeId, setEpisode]);

  const activeEpisode = episodes?.find((episode) => episode.id === selection.episodeId);
  const provider = providers?.find((item) => item.status === "active") ?? providers?.find((item) => item.status === "connected");
  const selectedShotId = selection.shotIds[0];
  const generateSelectedShot = useMutation({
    mutationFn: () => {
      if (!selectedShotId) throw new Error("请先选择镜头");
      return api.post<GenerationRead>(`/shots/${selectedShotId}/generations`, { type: "image" });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["generations"] }),
  });

  return (
    <div className={`app-shell ${dockExpanded ? "dock-expanded" : ""}`}>
      <header className="top-bar">
        <Link to="/" className="studio-project-name">{project?.name ?? "AI Manga Drama Studio"}</Link>
        <nav className="studio-nav" aria-label="工作台导航">
          <button className={!selection.sceneId ? "active" : ""} onClick={() => activeEpisode && setEpisode(activeEpisode.id)}>
            <Scroll size={17} /> 剧本
          </button>
          <button className={selection.sceneId ? "active" : ""} disabled={!selection.sceneId}>
            <SquaresFour size={17} /> 分镜
          </button>
          <button disabled title="Stage D 后开放"><MagicWand size={17} /> 导演画布</button>
          <button disabled title="素材库后续接入"><ImageSquare size={17} /> 素材</button>
          <button disabled title="时间线后续接入"><FilmReel size={17} /> 时间线</button>
        </nav>
        <div className="studio-statuses">
          <span className="connection-status"><Circle size={9} weight="fill" /> {provider?.name ?? "Provider"}</span>
          <span className="director-status"><Circle size={9} weight="fill" /> AI 导演 {rightPanelTab === "director" ? "已打开" : "空闲"}</span>
          <button
            className="btn primary compact"
            disabled={!selectedShotId || generateSelectedShot.isPending}
            onClick={() => generateSelectedShot.mutate()}
            title={selectedShotId ? "为当前镜头提交图片生成任务" : "先选择一个镜头"}
          >
            <Play size={14} weight="fill" /> {generateSelectedShot.isPending ? "提交中…" : "生成图片"}
          </button>
        </div>
      </header>

      <aside className="explorer"><ProjectExplorer projectId={projectId} /></aside>

      <main className="workspace">
        {selection.sceneId ? (
          <StoryboardView sceneId={selection.sceneId} />
        ) : activeEpisode ? (
          <EpisodePanel episode={activeEpisode} />
        ) : (
          <div className="empty-state studio-empty">
            <FilmStrip size={34} />
            <h2>添加第一个剧集</h2>
            <p>从左侧项目树建立剧集，然后导入小说开始 AI 分析。</p>
          </div>
        )}
      </main>

      <aside className="right-panel">{rightPanelTab === "inspector" ? <ShotInspector /> : <AIDirectorPanel />}</aside>
      <footer className="bottom-dock"><GenerationQueue /></footer>
    </div>
  );
}
