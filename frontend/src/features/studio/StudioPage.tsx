import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CaretLineLeft,
  CaretLineRight,
  FilmStrip,
  Play,
} from "@phosphor-icons/react";
import { Link, Navigate, Outlet, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, GenerationRead, Project, Scene, Storyboard } from "../../api/types";
import { EventRouter, setEventRouter, startEventSocket } from "../../events/socket";
import { useSelectionStore } from "../../stores/selectionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { applyWorkspace, attachWorkspacePersistence, hydrateWorkspace } from "../../stores/persistence";
import { rememberProject } from "../../lib/lastProject";
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
  const [compactLayout, setCompactLayout] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(max-width: 1100px)").matches === true,
  );
  const [compactPanel, setCompactPanel] = useState<"explorer" | "right" | null>(null);

  // At the desktop window minimum, both fixed sidebars would leave almost no
  // usable workspace. Compact mode keeps them available as rails and opens one
  // at a time without overwriting the user's persisted wide-screen layout.
  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 1100px)");
    if (!media) return;
    const sync = () => {
      setCompactLayout(media.matches);
      if (!media.matches) setCompactPanel(null);
    };
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  // P6-T003: hydrate persisted workspace once, then keep saving on any change.
  useEffect(() => {
    applyWorkspace(hydrateWorkspace());
    return attachWorkspacePersistence();
  }, []);

  // D：进入工作台时记住该项目，供 /assets /settings /workflows 返回时直达工作台。
  useEffect(() => {
    if (projectId) rememberProject(projectId);
  }, [projectId]);

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

  const activeEpisode =
    episodes?.find((episode) => episode.id === route.episodeId) ?? (route.legacy ? episodes?.[0] : undefined);
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
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.generations }),
  });

  const routeEpisodeId = route.episodeId ?? activeEpisode?.id;
  void routeEpisodeId;
  const explorerHidden = explorerCollapsed || (compactLayout && compactPanel !== "explorer");
  const rightPanelHidden = rightPanelCollapsed || (compactLayout && compactPanel !== "right");

  // Layout CSS variables: widths/heights come from the (persisted) store. Collapsed
  // states keep the rail widths via CSS modifiers on the shell.
  const style = {
    "--explorer-w": `${explorerWidth}px`,
    "--right-w": `${rightWidth}px`,
    "--dock-h": `${bottomDockHeight}px`,
  } as React.CSSProperties;

  return (
    <div
      className={`app-shell ${dockExpanded ? "dock-expanded" : ""} ${explorerHidden ? "explorer-collapsed" : ""} ${rightPanelHidden ? "right-collapsed" : ""}`}
      style={style}
    >
      {/* Canvas toolbar: module navigation moved to the global Activity Rail;
          this bar carries project identity + primary production action. */}
      <header className="top-bar">
        <Link to="/" className="studio-project-name">
          {project?.name ?? "漫剧工作台"}
        </Link>
        <span className="muted small top-bar-hint">{activeEpisode ? "剧集已打开 · 从活动栏切换模块" : "从资源树新建剧集后开始生产"}</span>
        <div className="grow" />
        <div className="studio-statuses">
          <span
            className="studio-generate-wrap"
            title={
              generateSelectedShot.isPending
                ? "正在提交生成任务…"
                : selectedShotId
                  ? "为当前镜头提交图片生成任务"
                  : "先选择一个镜头（点左侧树里的场景，再点它的镜头）"
            }
          >
            <button
              className="btn primary compact"
              disabled={!selectedShotId || generateSelectedShot.isPending}
              onClick={() => generateSelectedShot.mutate()}
            >
              <Play size={14} weight="fill" /> {generateSelectedShot.isPending ? "提交中…" : "生成图片"}
            </button>
          </span>
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
        {explorerHidden ? (
          <button
            type="button"
            className="panel-rail-btn"
            title="展开资源树"
            aria-label="展开资源树"
            onClick={() => {
              setExplorerCollapsed(false);
              if (compactLayout) setCompactPanel("explorer");
            }}
          >
            <CaretLineRight size={16} />
          </button>
        ) : (
          <ProjectExplorer
            projectId={projectId}
            onCollapse={() => {
              setExplorerCollapsed(true);
              setCompactPanel(null);
            }}
          />
        )}
      </aside>

      <ResizeHandle axis="vertical" label="调整左侧面板宽度" onDelta={onExplorerDelta} disabled={explorerHidden} />

      <main className="workspace">
        <Outlet context={{ projectId, activeEpisode } satisfies StudioContext} />
      </main>

      <ResizeHandle
        axis="vertical"
        label="调整右侧面板宽度"
        onDelta={onRightDelta}
        disabled={rightPanelHidden}
        variant="right"
      />

      {/* Agent Dock（DESIGN.md §4：右侧固定 Agent 容器，页面 Inspector 作为 Tab）
          外壳统管 tab 切换与收起；面板内容各自滚动。 */}
      <aside className="right-panel agent-dock">
        {rightPanelHidden ? (
          <button
            type="button"
            className="panel-rail-btn"
            title="展开面板"
            aria-label="展开右侧面板"
            onClick={() => {
              setRightPanelCollapsed(false);
              if (compactLayout) setCompactPanel("right");
            }}
          >
            <CaretLineLeft size={16} />
          </button>
        ) : (
          <>
            <div className="panel-tabs" role="tablist" aria-label="右侧面板">
              <button
                type="button"
                role="tab"
                aria-selected={rightPanelTab === "director"}
                className={`tab ${rightPanelTab === "director" ? "active" : ""}`}
                onClick={() => setRightPanelTab("director")}
              >
                AI导演
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={rightPanelTab === "inspector"}
                className={`tab ${rightPanelTab === "inspector" ? "active" : ""}`}
                onClick={() => setRightPanelTab("inspector")}
              >
                镜头检查器
              </button>
              <button
                type="button"
                className="panel-collapse-tab"
                title="收起右侧面板"
                aria-label="收起右侧面板"
                onClick={() => setRightPanelCollapsed(true)}
              >
                <CaretLineRight size={15} />
              </button>
            </div>
            {rightPanelTab === "inspector" ? <ShotInspector /> : <AIDirectorPanel />}
          </>
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
  const setRightPanelTab = useWorkspaceStore((state) => state.setRightPanelTab);
  useEffect(() => {
    if (projectId && episodeId && sceneId && shotId) {
      openShot({ projectId, episodeId, sceneId, shotId, title: `Shot ${shotId.slice(-4)}` });
      // URL 直达镜头 → Agent Dock 切到镜头检查器（P6 职责边界）
      setRightPanelTab("inspector");
    }
  }, [episodeId, openShot, projectId, sceneId, setRightPanelTab, shotId]);
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
