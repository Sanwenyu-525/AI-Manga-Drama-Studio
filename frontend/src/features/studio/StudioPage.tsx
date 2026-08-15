import { useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretLineLeft, CaretLineRight, Circle, ImageSquare, MagicWand, Play, Scroll, SquaresFour } from "@phosphor-icons/react";
import { Link, Outlet, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, GenerationRead, Project, ProviderStatus } from "../../api/types";
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
import { ProjectExplorer } from "./ProjectExplorer";

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
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const setProject = useSelectionStore((state) => state.setProject);
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
  const selection = useSelectionStore((state) => state.selection);
  const setEpisode = useSelectionStore((state) => state.setEpisode);
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

  useEffect(() => {
    setProject(projectId);
  }, [projectId, setProject]);

  // Resize handlers (P6-T002): each reports a delta from the drag start; the
  // clamp + persistence live in the store / persistence layer.
  const startLeft = explorerWidth;
  const startRight = rightWidth;
  const onExplorerDelta = useMemo(() => (delta: number) => setPanelSize("explorer", startLeft + delta), [setPanelSize, startLeft]);
  const onRightDelta = useMemo(() => (delta: number) => setPanelSize("right", startRight - delta), [setPanelSize, startRight]);
  const onBottomDelta = useMemo(() => (delta: number) => setPanelSize("bottom", bottomDockHeight + delta), [setPanelSize, bottomDockHeight]);

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
  const storyboardSceneId = getStoryboardSceneId(location.pathname);
  const storyboardPath = storyboardSceneId ? `/projects/${projectId}/storyboard/${storyboardSceneId}` : null;
  const onStoryboard = Boolean(storyboardSceneId);

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
        <Link to="/" className="studio-project-name"><img src="/assets/logo.png" alt="" className="app-logo" /> {project?.name ?? "AI Manga Drama Studio"}</Link>
        <nav className="studio-nav" aria-label="工作台导航">
          <Link to={scriptPath} className={!onStoryboard ? "active" : ""}><Scroll size={17} /> 剧本</Link>
          <Link
            to={storyboardPath ?? scriptPath}
            className={onStoryboard ? "active" : ""}
            aria-disabled={!storyboardPath}
            onClick={(event) => { if (!storyboardPath) event.preventDefault(); }}
            title={storyboardPath ? "返回分镜视图" : "先选择一个场景"}
          ><SquaresFour size={17} /> 分镜</Link>
          <button className={rightPanelTab === "director" ? "active" : ""} onClick={() => setRightPanelTab("director")} title="打开 AI Director"><MagicWand size={17} /> 导演画布</button>
          <button onClick={() => navigate("/assets", { state: { fromProject: projectId } })} title="全局素材库"><ImageSquare size={17} /> 素材</button>
        </nav>
        <div className="studio-statuses">
          <span className="connection-status"><Circle size={9} weight="fill" /> {provider?.name ?? "Provider"}</span>
          <span className="director-status"><Circle size={9} weight="fill" /> AI 导演 {rightPanelTab === "director" ? "已打开" : "空闲"}</span>
          <button className="btn primary compact" disabled={!selectedShotId || generateSelectedShot.isPending} onClick={() => generateSelectedShot.mutate()} title={selectedShotId ? "为当前镜头提交图片生成任务" : "先选择一个镜头"}><Play size={14} weight="fill" /> {generateSelectedShot.isPending ? "提交中…" : "生成图片"}</button>
          {generateSelectedShot.isError && (<span className="error-text studio-generate-error" title={generateSelectedShot.error instanceof Error ? generateSelectedShot.error.message : String(generateSelectedShot.error)}>{generateSelectedShot.error instanceof Error ? generateSelectedShot.error.message : String(generateSelectedShot.error)}</span>)}
        </div>
      </header>

      <aside className="explorer">
        {explorerCollapsed ? (
          <button type="button" className="panel-rail-btn" title="展开资源树" aria-label="展开资源树" onClick={() => setExplorerCollapsed(false)}><CaretLineRight size={16} /></button>
        ) : (<ProjectExplorer projectId={projectId} onCollapse={() => setExplorerCollapsed(true)} />)}
      </aside>

      <ResizeHandle axis="vertical" label="调整左侧面板宽度" onDelta={onExplorerDelta} disabled={explorerCollapsed} />

      <main className="workspace">
        <Outlet context={{ projectId, activeEpisode } satisfies StudioContext} />
      </main>

      <ResizeHandle axis="vertical" label="调整右侧面板宽度" onDelta={onRightDelta} disabled={rightPanelCollapsed} variant="right" />

      <aside className="right-panel">
        {rightPanelCollapsed ? (<button type="button" className="panel-rail-btn" title="展开检查器" aria-label="展开检查器" onClick={() => setRightPanelCollapsed(false)}><CaretLineLeft size={16} /></button>)
        : rightPanelTab === "inspector" ? <ShotInspector /> : <AIDirectorPanel />}
      </aside>

      <footer className="bottom-dock"><GenerationQueue /></footer>
      <ResizeHandle axis="horizontal" label="调整底部面板高度" onDelta={onBottomDelta} onDragEnd={undefined} disabled={dockExpanded} />
    </div>
  );
}

// ---------- Workspace: 剧本 (script analysis) ----------
// The URL route owns which base tab is active; the tabbed WorkspaceHost renders it.
export function ScriptWorkspace() {
  const { projectId: ctxProjectId, activeEpisode } = useStudio();
  const navigate = useNavigate();
  const setEpisode = useSelectionStore((state) => state.setEpisode);
  const openScene = useEditorTabsStore((state) => state.openScene);
  const activateTab = useEditorTabsStore((state) => state.activateTab);
  useEffect(() => { if (activeEpisode) setEpisode(activeEpisode.id); }, [activeEpisode?.id, setEpisode]);
  useEffect(() => {
    // Navigating to /script makes the script base tab the active center view.
    activateTab("script");
  }, [activateTab]);
  return (
    <WorkspaceHost
      projectId={ctxProjectId}
      activeEpisode={activeEpisode}
      onScenesCreated={(sceneIds) => {
        const target = sceneIds[0];
        if (target) {
          openScene({ projectId: ctxProjectId, sceneId: target, title: `Scene ${target.slice(-2)}` });
          navigate(`/projects/${ctxProjectId}/storyboard/${target}`);
        }
      }}
    />
  );
}

// ---------- Workspace: 分镜 (storyboard) ----------
export function StoryboardWorkspace() {
  const { sceneId = "" } = useParams();
  const { projectId } = useStudio();
  const openScene = useEditorTabsStore((state) => state.openScene);
  useEffect(() => {
    if (sceneId && projectId) openScene({ projectId, sceneId, title: `Scene ${sceneId.slice(-2)}` });
  }, [sceneId, projectId, openScene]);
  if (!sceneId) return <SceneEmptyState />;
  return <WorkspaceHost projectId={projectId} activeEpisode={undefined} />;
}

function useStudio(): StudioContext {
  return useOutletContext<StudioContext>();
}

// /projects/:projectId/storyboard/:sceneId → sceneId | undefined
function getStoryboardSceneId(pathname: string): string | undefined {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length >= 4 && parts[0] === "projects" && parts[2] === "storyboard") return parts[3];
  return undefined;
}