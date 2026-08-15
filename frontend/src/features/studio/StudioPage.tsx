import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Circle, FilmStrip, ImageSquare, MagicWand, Play, Scroll, SquaresFour } from "@phosphor-icons/react";
import { Link, Outlet, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";
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

// Studio context handed to the workspace child routes (URL-driven views).
interface StudioContext {
  projectId: string;
  activeEpisode: Episode | undefined;
}

// ---------- Layout route: /projects/:projectId ----------
// The top bar + explorer + right panel + bottom dock stay mounted; the center
// workspace is swapped by the nested <Outlet/> (script / storyboard views).
export function StudioPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const setProject = useSelectionStore((state) => state.setProject);
  const rightPanelTab = useWorkspaceStore((state) => state.rightPanelTab);
  const setRightPanelTab = useWorkspaceStore((state) => state.setRightPanelTab);
  const dockExpanded = useWorkspaceStore((state) => state.bottomDockExpanded);
  const selection = useSelectionStore((state) => state.selection);
  const setEpisode = useSelectionStore((state) => state.setEpisode);
  const setScene = useSelectionStore((state) => state.setScene);
  const clearScene = useSelectionStore((state) => state.clearScene);

  useEffect(() => {
    startEventSocket();
    setEventRouter(new EventRouter(queryClient));
    return () => setEventRouter(null);
  }, [queryClient]);

  // Project id is URL-sourced; keep the selection store in sync so the AI
  // Director and shot generation see the right context.
  useEffect(() => {
    setProject(projectId);
  }, [projectId, setProject]);

  // Scene id is URL-sourced too (deep-linkable/refreshable). The parent must sync
  // it after setProject because setProject clears the previous selection context.
  const storyboardSceneId = getStoryboardSceneId(location.pathname);
  useEffect(() => {
    if (storyboardSceneId) {
      setScene(storyboardSceneId);
    } else {
      clearScene(); // leaving storyboard → don't leave stale scene context around
    }
  }, [storyboardSceneId, setScene, clearScene]);

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

  // The selected episode is UI context (kept in the selection store); scenes are
  // URL-driven so the storyboard is deep-linkable and refreshable.
  useEffect(() => {
    if (!selection.episodeId && episodes?.[0]) setEpisode(episodes[0].id);
  }, [episodes, selection.episodeId, setEpisode]);

  const activeEpisode = episodes?.find((episode) => episode.id === selection.episodeId) ?? episodes?.[0];
  const provider = providers?.find((item) => item.status === "active") ?? providers?.find((item) => item.status === "connected");
  const selectedShotId = selection.shotIds[0];

  const generateSelectedShot = useMutation({
    mutationFn: () => {
      if (!selectedShotId) throw new Error("请先选择镜头");
      return api.post<GenerationRead>(`/shots/${selectedShotId}/generations`, { type: "image" });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["generations"] }),
  });

  const scriptPath = `/projects/${projectId}/script`;
  // URL is the source of truth for the current storyboard scene.
  const activeSceneId = storyboardSceneId ?? selection.sceneId;
  const storyboardPath = activeSceneId ? `/projects/${projectId}/storyboard/${activeSceneId}` : null;
  const onStoryboard = Boolean(storyboardSceneId);

  return (
    <div className={`app-shell ${dockExpanded ? "dock-expanded" : ""}`}>
      <header className="top-bar">
        <Link to="/" className="studio-project-name"><img src="/assets/logo.png" alt="" className="app-logo" /> {project?.name ?? "AI Manga Drama Studio"}</Link>
        <nav className="studio-nav" aria-label="工作台导航">
          {/* URL-driven views: the active tab matches the current route, not a hidden state. */}
          <Link to={scriptPath} className={!onStoryboard ? "active" : ""}>
            <Scroll size={17} /> 剧本
          </Link>
          <Link
            to={storyboardPath ?? scriptPath}
            className={onStoryboard ? "active" : ""}
            aria-disabled={!storyboardPath}
            onClick={(event) => {
              if (!storyboardPath) event.preventDefault();
            }}
            title={storyboardPath ? "返回分镜视图" : "先选择一个场景"}
          >
            <SquaresFour size={17} /> 分镜
          </Link>
          <button className={rightPanelTab === "director" ? "active" : ""} onClick={() => setRightPanelTab("director")} title="打开 AI Director">
            <MagicWand size={17} /> 导演画布
          </button>
          <button onClick={() => navigate("/assets")} title="全局素材库">
            <ImageSquare size={17} /> 素材
          </button>
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
          {generateSelectedShot.isError && (
            <span
              className="error-text studio-generate-error"
              title={generateSelectedShot.error instanceof Error ? generateSelectedShot.error.message : String(generateSelectedShot.error)}
            >
              {generateSelectedShot.error instanceof Error ? generateSelectedShot.error.message : String(generateSelectedShot.error)}
            </span>
          )}
        </div>
      </header>

      <aside className="explorer"><ProjectExplorer projectId={projectId} /></aside>

      <main className="workspace">
        <Outlet context={{ projectId, activeEpisode } satisfies StudioContext} />
      </main>

      <aside className="right-panel">{rightPanelTab === "inspector" ? <ShotInspector /> : <AIDirectorPanel />}</aside>
      <footer className="bottom-dock"><GenerationQueue /></footer>
    </div>
  );
}

// ---------- Workspace: 剧本 (script analysis) ----------
// Reads the episode from the URL; falls back to the first episode.
export function ScriptWorkspace() {
  const { projectId: ctxProjectId, activeEpisode } = useStudio();
  const navigate = useNavigate();
  const setEpisode = useSelectionStore((state) => state.setEpisode);

  useEffect(() => {
    if (activeEpisode) setEpisode(activeEpisode.id);
  }, [activeEpisode?.id, setEpisode]);

  if (!activeEpisode) {
    return (
      <div className="empty-state studio-empty">
        <FilmStrip size={34} />
        <h2>添加第一个剧集</h2>
        <p>从左侧项目树建立剧集，然后导入小说开始 AI 分析。</p>
      </div>
    );
  }

  // After AI creates scenes for this episode, jump straight to the storyboard view.
  return (
    <EpisodePanel
      episode={activeEpisode}
      onScenesCreated={(sceneIds) => {
        const target = sceneIds[0];
        if (target) navigate(`/projects/${ctxProjectId}/storyboard/${target}`);
      }}
    />
  );
}

// ---------- Workspace: 分镜 (storyboard) ----------
export function StoryboardWorkspace() {
  const { sceneId = "" } = useParams();

  if (!sceneId) {
    return (
      <div className="empty-state studio-empty">
        <SquaresFour size={34} />
        <h2>选择一个场景</h2>
        <p>从左侧项目树选择场景查看分镜。</p>
      </div>
    );
  }

  return <StoryboardView sceneId={sceneId} />;
}

function useStudio(): StudioContext {
  return useOutletContext<StudioContext>();
}

// /projects/:projectId/storyboard/:sceneId → sceneId | undefined
function getStoryboardSceneId(pathname: string): string | undefined {
  const parts = pathname.split("/").filter(Boolean);
  // ["projects", projectId, "storyboard", sceneId]
  if (parts.length >= 4 && parts[0] === "projects" && parts[2] === "storyboard") {
    return parts[3];
  }
  return undefined;
}
