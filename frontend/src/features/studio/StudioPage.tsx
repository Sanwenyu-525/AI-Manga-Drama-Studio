import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretLineLeft, CaretLineRight, FilmStrip } from "@phosphor-icons/react";
import { Navigate, Outlet, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Scene, Storyboard } from "../../api/types";
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
import { canonicalScriptPath, canonicalStoryboardPath, canonicalTimelinePath, useStudioRoute } from "./studioRoute";

// Studio context handed to the workspace child routes (URL-driven views).
interface StudioContext {
  projectId: string;
  activeEpisode: Episode | undefined;
}

// ---------- Layout route: /projects/:projectId ----------
// Top bar + right panel + bottom dock stay mounted; the center is the
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
  const rightPanelCollapsed = useWorkspaceStore((state) => state.rightPanelCollapsed);
  const setRightPanelCollapsed = useWorkspaceStore((state) => state.setRightPanelCollapsed);
  const rightWidth = useWorkspaceStore((state) => state.rightWidth);
  const bottomDockHeight = useWorkspaceStore((state) => state.bottomDockHeight);
  const setPanelSize = useWorkspaceStore((state) => state.setPanelSize);
  const [compactLayout, setCompactLayout] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(max-width: 1100px)").matches === true,
  );
  const [compactPanel, setCompactPanel] = useState<"right" | null>(null);

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
    void startEventSocket();
    setEventRouter(new EventRouter(queryClient));
    return () => setEventRouter(null);
  }, [queryClient]);

  // Resize handlers (P6-T002): the handle reports a cumulative delta from the
  // drag start, so the baseline size is snapshotted from the store ONCE at
  // pointerdown (onDragStart) and frozen in a ref — deriving it from the
  // per-render width would re-apply the cumulative delta on every move and
  // slam the panel into its clamp.
  const dragStartRef = useRef({ right: 0, bottom: 0 });
  const setPanelResizing = useWorkspaceStore((state) => state.setPanelResizing);
  const panelResizing = useWorkspaceStore((state) => state.panelResizing);
  const beginPanelDrag = useCallback(() => {
    const snapshot = useWorkspaceStore.getState();
    dragStartRef.current = {
      right: snapshot.rightWidth,
      bottom: snapshot.bottomDockHeight,
    };
    setPanelResizing(true);
  }, [setPanelResizing]);
  const endPanelDrag = useCallback(() => setPanelResizing(false), [setPanelResizing]);
  const onRightDelta = useCallback(
    (delta: number) => setPanelSize("right", dragStartRef.current.right - delta),
    [setPanelSize],
  );
  const onBottomDelta = useCallback(
    (delta: number) => setPanelSize("bottom", dragStartRef.current.bottom + delta),
    [setPanelSize],
  );

  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => api.get<Episode[]>(`/projects/${projectId}/episodes`),
    enabled: Boolean(projectId),
  });

  const activeEpisode =
    episodes?.find((episode) => episode.id === route.episodeId) ?? (route.legacy ? episodes?.[0] : undefined);
  useEffect(() => {
    clearAssets();
    if (route.workspace === "shot" && route.shotId) selectShot(route.shotId);
    else if (route.workspace !== "storyboard") clearShots();
  }, [clearAssets, clearShots, projectId, route.episodeId, route.sceneId, route.shotId, route.workspace, selectShot]);

  const rightPanelHidden = rightPanelCollapsed || (compactLayout && compactPanel !== "right");

  // Layout CSS variables: widths/heights come from the (persisted) store. Collapsed
  // states keep the rail widths via CSS modifiers on the shell.
  const style = {
    "--right-w": `${rightWidth}px`,
    "--dock-h": `${bottomDockHeight}px`,
  } as React.CSSProperties;

  return (
    <div
      className={`app-shell ${dockExpanded ? "dock-expanded" : ""} ${rightPanelHidden ? "right-collapsed" : ""} ${panelResizing ? "is-resizing" : ""}`}
      style={style}
    >
      <main className="workspace">
        <Outlet context={{ projectId, activeEpisode } satisfies StudioContext} />
      </main>

      <ResizeHandle
        axis="vertical"
        label="调整右侧面板宽度"
        onDelta={onRightDelta}
        onDragStart={beginPanelDrag}
        onDragEnd={endPanelDrag}
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
        onDragStart={beginPanelDrag}
        onDragEnd={endPanelDrag}
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
  return <WorkspaceHost activeEpisode={activeEpisode} />;
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
  return <WorkspaceHost activeEpisode={activeEpisode} />;
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
        <p>先在故事模块创建剧集，再为其排时间线并导出。</p>
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
