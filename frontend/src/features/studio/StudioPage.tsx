import { useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CaretLineLeft,
  CaretLineRight,
  Circle,
  FilmStrip,
  ImageSquare,
  MagicWand,
  Play,
  Scroll,
  SquaresFour,
} from "@phosphor-icons/react";
import { Link, Navigate, Outlet, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, GenerationRead, Project, ProviderStatus, Scene, Storyboard } from "../../api/types";
import { EventRouter, setEventRouter, startEventSocket } from "../../events/socket";
import { useSelectionStore } from "../../stores/selectionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { applyWorkspace, attachWorkspacePersistence, hydrateWorkspace } from "../../stores/persistence";
import { ResizeHandle } from "../../components/resizable/ResizeHandle";
import { WorkspaceHost, SceneEmptyState } from "../../components/workspace/WorkspaceHost";
import { AIDirectorPanel } from "../director/AIDirectorPanel";
import { GenerationQueue } from "../generation/GenerationQueue";
import { ShotInspector } from "../storyboard/ShotInspector";
import { AssetBrowserView } from "../assets/AssetBrowserView";
import { TimelineView } from "../timeline/TimelineView";
import { ProjectExplorer } from "./ProjectExplorer";
import { canonicalScriptPath, canonicalStoryboardPath, canonicalTimelinePath, useStudioRoute } from "./studioRoute";

// Studio context handed to the workspace child routes (URL-driven views).
interface StudioContext {
  projectId: string;
  activeEpisode: Episode | undefined;
}

// ---------- Layout route: /projects/:projectId ----------
// Top bar + explorer + right panel + bottom dock stay mounted; the center is the
// tabbed WorkspaceHost (P6-T004), and panel widths/heights are resizable + persisted.
export function StudioPage() {
  const { projectId = "" } = useParams();
  const route = useStudioRoute();
  const queryClient = useQueryClient();
  const clearShots = useSelectionStore((state) => state.clearShots);
  const selectShot = useSelectionStore((state) => state.selectShot);
  const clearAssets = useSelectionStore((state) => state.clearAssets);
  const rightPanelTab = useWorkspaceStore((state) => state.rightPanelTab);
  const setRightPanelTab = useWorkspaceStore((state) => state.setRightPanelTab);
  const dockExpanded = useWorkspaceStore((state) => state.bottomDockExpanded);
  const explorerCollapsed = useWorkspaceStore((state) => state.explorerCollapsed);
  const setExplorerCollapsed = useWorkspaceStore((state) => state.setExplorerCollapsed);
  const rightPanelCollapsed = useWorkspaceStore((state) => state.rightPanelCollapsed);
  const setRightPanelCollapsed = useWorkspaceStore((state) => state.setRightPanelCollapsed);
  const explorerWidth = useWorkspaceStore((state) => state.explorerWidth);
  const rightWidth = useWorkspaceStore((state) => state.rightWidth);
  const bottomDockHeight = useWorkspaceStore((state) => state.bottomDockHeight);
  const setPanelSize = useWorkspaceStore((state) => state.setPanelSize);
  // P6-T003: hydrate persisted workspace once, then keep saving on any change.
  useEffect(() => {
    applyWorkspace(hydrateWorkspace());
    return attachWorkspacePersistence();
  }, []);

  useEffect(() => {
    startEventSocket();
    setEventRouter(new EventRouter(queryClient));
    return () => setEventRouter(null);
  }, [queryClient]);

  // Resize handlers (P6-T002): each reports a delta from the drag start; the
  // clamp + persistence live in the store / persistence layer.
  const startLeft = explorerWidth;
  const startRight = rightWidth;
  const onExplorerDelta = useMemo(
    () => (delta: number) => setPanelSize("explorer", startLeft + delta),
    [setPanelSize, startLeft],
  );
  const onRightDelta = useMemo(
    () => (delta: number) => setPanelSize("right", startRight - delta),
    [setPanelSize, startRight],
  );
  const onBottomDelta = useMemo(
    () => (delta: number) => setPanelSize("bottom", bottomDockHeight + delta),
    [setPanelSize, bottomDockHeight],
  );

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

  const activeEpisode =
    episodes?.find((episode) => episode.id === route.episodeId) ?? (route.legacy ? episodes?.[0] : undefined);
  const provider =
    providers?.find((item) => item.status === "active") ?? providers?.find((item) => item.status === "connected");
  const selectedShotId = useSelectionStore((state) => state.selection.shotIds[0]);

  useEffect(() => {
    clearAssets();
    if (route.workspace === "shot" && route.shotId) selectShot(route.shotId);
    else if (route.workspace !== "storyboard") clearShots();
  }, [clearAssets, clearShots, projectId, route.episodeId, route.sceneId, route.shotId, route.workspace, selectShot]);

  const generateSelectedShot = useMutation({
    mutationFn: () => {
      if (!selectedShotId) throw new Error("请先选择镜头");
      return api.post<GenerationRead>(`/shots/${selectedShotId}/generations`, { type: "image" });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["generations"] }),
  });

  const routeEpisodeId = route.episodeId ?? activeEpisode?.id;
  const scriptPath = routeEpisodeId ? canonicalScriptPath(projectId, routeEpisodeId) : `/projects/${projectId}/script`;
  const storyboardPath =
    route.sceneId && route.episodeId ? canonicalStoryboardPath(projectId, route.episodeId, route.sceneId) : null;
  const onScript = route.workspace === "script";
  const onStoryboard = route.workspace === "storyboard" || route.workspace === "shot";

  // Layout CSS variables: widths/heights come from the (persisted) store. Collapsed
  // states keep the rail widths via CSS modifiers on the shell.
  const style = {
    "--explorer-w": `${explorerWidth}px`,
    "--right-w": `${rightWidth}px`,
    "--dock-h": `${bottomDockHeight}px`,
  } as React.CSSProperties;

  return (
    <div
      className={`app-shell ${dockExpanded ? "dock-expanded" : ""} ${explorerCollapsed ? "explorer-collapsed" : ""} ${rightPanelCollapsed ? "right-collapsed" : ""}`}
      style={style}
    >
      <header className="top-bar">
        <Link to="/" className="studio-project-name">
          <img src="/assets/logo.png" alt="" className="app-logo" /> {project?.name ?? "AI Manga Drama Studio"}
        </Link>
        <nav className="studio-nav" aria-label="工作台导航">
          <Link to={scriptPath} className={onScript ? "active" : ""}>
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
          <Link
            to={`/projects/${projectId}/assets`}
            className={route.workspace === "assets" ? "active" : ""}
            title="项目资产库"
          >
            <ImageSquare size={17} /> 素材
          </Link>
          <Link
            to={routeEpisodeId ? canonicalTimelinePath(projectId, routeEpisodeId) : `/projects/${projectId}/timeline`}
            className={route.workspace === "timeline" ? "active" : ""}
            title="逐集时间线与导出"
          >
            <FilmStrip size={17} /> 时间线
          </Link>
          <button
            className={rightPanelTab === "director" ? "active" : ""}
            onClick={() => setRightPanelTab("director")}
            title="打开 AI Director"
          >
            <MagicWand size={17} /> AI Director
          </button>
        </nav>
        <div className="studio-statuses">
          <span className="connection-status">
            <Circle size={9} weight="fill" /> {provider?.name ?? "Provider"}
          </span>
          <span className="director-status">
            <Circle size={9} weight="fill" /> AI 导演 {rightPanelTab === "director" ? "已打开" : "空闲"}
          </span>
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
              title={
                generateSelectedShot.error instanceof Error
                  ? generateSelectedShot.error.message
                  : String(generateSelectedShot.error)
              }
            >
              {generateSelectedShot.error instanceof Error
                ? generateSelectedShot.error.message
                : String(generateSelectedShot.error)}
            </span>
          )}
        </div>
      </header>

      <aside className="explorer">
        {explorerCollapsed ? (
          <button
            type="button"
            className="panel-rail-btn"
            title="展开资源树"
            aria-label="展开资源树"
            onClick={() => setExplorerCollapsed(false)}
          >
            <CaretLineRight size={16} />
          </button>
        ) : (
          <ProjectExplorer projectId={projectId} onCollapse={() => setExplorerCollapsed(true)} />
        )}
      </aside>

      <ResizeHandle axis="vertical" label="调整左侧面板宽度" onDelta={onExplorerDelta} disabled={explorerCollapsed} />

      <main className="workspace">
        <Outlet context={{ projectId, activeEpisode } satisfies StudioContext} />
      </main>

      <ResizeHandle
        axis="vertical"
        label="调整右侧面板宽度"
        onDelta={onRightDelta}
        disabled={rightPanelCollapsed}
        variant="right"
      />

      <aside className="right-panel">
        {rightPanelCollapsed ? (
          <button
            type="button"
            className="panel-rail-btn"
            title="展开检查器"
            aria-label="展开检查器"
            onClick={() => setRightPanelCollapsed(false)}
          >
            <CaretLineLeft size={16} />
          </button>
        ) : rightPanelTab === "inspector" ? (
          <ShotInspector />
        ) : (
          <AIDirectorPanel />
        )}
      </aside>

      <footer className="bottom-dock">
        <GenerationQueue projectId={projectId} />
      </footer>
      <ResizeHandle
        axis="horizontal"
        label="调整底部面板高度"
        onDelta={onBottomDelta}
        onDragEnd={undefined}
        disabled={dockExpanded}
      />
    </div>
  );
}

// ---------- Workspace: 剧本 (script analysis) ----------
// The URL route owns which base tab is active; the tabbed WorkspaceHost renders it.
export function ScriptWorkspace() {
  const { projectId: ctxProjectId, activeEpisode } = useStudio();
  const navigate = useNavigate();
  const openScene = useEditorTabsStore((state) => state.openScene);
  const activateTab = useEditorTabsStore((state) => state.activateTab);
  useEffect(() => {
    // URL owns the center view; the tab is only a synchronized affordance.
    activateTab("script");
  }, [activateTab]);
  return (
    <WorkspaceHost
      projectId={ctxProjectId}
      activeEpisode={activeEpisode}
      onScenesCreated={(sceneIds) => {
        const target = sceneIds[0];
        if (target && activeEpisode) {
          openScene({
            projectId: ctxProjectId,
            episodeId: activeEpisode.id,
            sceneId: target,
            title: `Scene ${target.slice(-2)}`,
          });
          navigate(canonicalStoryboardPath(ctxProjectId, activeEpisode.id, target));
        }
      }}
    />
  );
}

// ---------- Workspace: 分镜 (storyboard) ----------
export function StoryboardWorkspace() {
  const { sceneId = "", episodeId = "" } = useParams();
  const { projectId, activeEpisode } = useStudio();
  const openScene = useEditorTabsStore((state) => state.openScene);
  const { data: storyboard } = useQuery({
    queryKey: queryKeys.storyboard(sceneId),
    queryFn: () => api.get<Storyboard>(`/scenes/${sceneId}/storyboard`),
    enabled: Boolean(sceneId),
  });
  useEffect(() => {
    if (sceneId && projectId && episodeId) {
      const number = storyboard?.scene.scene_number;
      const name = storyboard?.scene.name;
      openScene({
        projectId,
        episodeId,
        sceneId,
        title: number ? `SC${String(number).padStart(2, "0")} · ${name ?? "场景"}` : `Scene ${sceneId.slice(-2)}`,
      });
    }
  }, [episodeId, openScene, projectId, sceneId, storyboard]);
  if (!sceneId) return <SceneEmptyState />;
  return <WorkspaceHost projectId={projectId} activeEpisode={activeEpisode} />;
}

export function ShotDetailWorkspace() {
  const { projectId, activeEpisode } = useStudio();
  const { episodeId = "", sceneId = "", shotId = "" } = useParams();
  const openShot = useEditorTabsStore((state) => state.openShot);
  useEffect(() => {
    if (projectId && episodeId && sceneId && shotId) {
      openShot({ projectId, episodeId, sceneId, shotId, title: `Shot ${shotId.slice(-4)}` });
    }
  }, [episodeId, openShot, projectId, sceneId, shotId]);
  return <WorkspaceHost projectId={projectId} activeEpisode={activeEpisode} />;
}

// ---------- Workspace: 资产浏览 (asset browser + inspector, P6-T016/T017) ----------
export function AssetWorkspace() {
  const { projectId = "" } = useParams();
  return <AssetBrowserView projectId={projectId} />;
}

// ---------- Workspace: 时间线 (Phase 9 — timeline + episode render) ----------
// URL-driven like the asset workspace; episode comes from the active selection.
export function TimelineWorkspace() {
  const { projectId = "" } = useParams();
  const { activeEpisode } = useStudio();
  if (!activeEpisode) {
    return (
      <div className="empty-state studio-empty">
        <FilmStrip size={34} />
        <h2>选择一集</h2>
        <p>从左侧项目树建立剧集后，可为其排时间线并导出。</p>
      </div>
    );
  }
  return <TimelineView projectId={projectId} episodeId={activeEpisode.id} />;
}

export function LegacyEpisodeRoute({ workspace }: { workspace: "script" | "timeline" }) {
  const { projectId = "" } = useParams();
  const { data: episodes, isLoading } = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => api.get<Episode[]>(`/projects/${projectId}/episodes`),
    enabled: Boolean(projectId),
  });
  if (isLoading) return <div className="workspace-loading">正在确定默认剧集…</div>;
  const first = [...(episodes ?? [])].sort((a, b) => a.episode_number - b.episode_number)[0];
  if (!first) return workspace === "timeline" ? <TimelineWorkspace /> : <ScriptWorkspace />;
  return (
    <Navigate
      to={
        workspace === "script" ? canonicalScriptPath(projectId, first.id) : canonicalTimelinePath(projectId, first.id)
      }
      replace
    />
  );
}

export function LegacyStoryboardRoute() {
  const { projectId = "", sceneId = "" } = useParams();
  const {
    data: scene,
    isLoading,
    error,
  } = useQuery({
    queryKey: queryKeys.scene(sceneId),
    queryFn: () => api.get<Scene>(`/scenes/${sceneId}`),
    enabled: Boolean(sceneId),
  });
  if (isLoading) return <div className="workspace-loading">正在确定场景所属剧集…</div>;
  if (error || !scene) {
    return (
      <div className="workspace-loading">
        <ApiErrorPanel error={error as never} />
      </div>
    );
  }
  return <Navigate to={canonicalStoryboardPath(projectId, scene.episode_id, scene.id)} replace />;
}

function useStudio(): StudioContext {
  return useOutletContext<StudioContext>();
}
