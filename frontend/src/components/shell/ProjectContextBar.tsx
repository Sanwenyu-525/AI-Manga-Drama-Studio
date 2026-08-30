// Project Context Bar — 40px (DESIGN.md §4 / P0 frozen shell).
//
// Level-2 workspace switch [ 智能体工作区 | 漫剧工作区 ] lives here (only after the
// 漫剧智能体 mode is active). Same row shows the source↔project binding summary.
// The source-workspace path is not part of MVP Project State, so we render the
// manga-project side only — never a fabricated path, never a parent-child breadcrumb.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GearSix } from "@phosphor-icons/react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Project, Storyboard } from "../../api/types";
import { ProjectSettingsModal } from "../../features/settings/ProjectSettingsModal";
import { useSelectionStore } from "../../stores/selectionStore";
import { useStudioRoute } from "../../features/studio/studioRoute";

const TAURI_RUNTIME = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** Current manga-project id parsed from URL (/projects/:projectId/...), else null. */
function projectIdFromPath(pathname: string): string | null {
  const match = /^\/projects\/([^/]+)/.exec(pathname);
  return match ? match[1] : null;
}

/** 当前处于哪一级工作区（P0 二级工作区语义）。 */
function activeWorkspace(pathname: string): "agent" | "manga" {
  return /\/source$/.test(pathname) ? "agent" : "manga";
}

/** Human label for the active center-canvas workspace module. */
function moduleLabel(pathname: string): string {
  if (pathname === "/" || pathname === "") return "项目库";
  if (pathname.startsWith("/projects/new")) return "新建项目";
  if (pathname.endsWith("/source")) return "源内容工作区";
  if (pathname.endsWith("/workspace")) return "生产控制中心";
  if (pathname.endsWith("/director")) return "AI导演";
  if (pathname.endsWith("/characters")) return "角色库";
  if (/^\/projects\/[^/]+\/storyboard$/.test(pathname)) return "分镜索引";
  if (/^\/projects\/[^/]+\/shots$/.test(pathname)) return "镜头索引";
  if (pathname.endsWith("/knowledge")) return "知识库";
  if (pathname.endsWith("/continuity")) return "连续性检查";
  if (/(storyboard|shots)/.test(pathname)) return "分镜 / 镜头";
  if (pathname.includes("/assets")) return "素材库";
  if (pathname.includes("/timeline")) return "时间线";
  if (pathname.endsWith("/prompts")) return "提示词历史";
  if (pathname.includes("production-log")) return "生产日志";
  if (pathname.startsWith("/workflows")) return "工作流目录";
  if (pathname.startsWith("/settings")) return "设置";
  if (pathname.includes("/script") || pathname.startsWith("/projects/")) return "故事 · 剧集";
  return "";
}

export function ProjectContextBar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const route = useStudioRoute();
  const projectId = projectIdFromPath(pathname);
  const selectedShotId = useSelectionStore((state) => state.selection.shotIds[0]);
  // 项目设置入口：资源树移除后由上下文栏承载（原资源树标题栏的滑块按钮）。
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Same cache key as StudioPage → free sharing; disabled without a project.
  const { data: project } = useQuery({
    queryKey: queryKeys.project(projectId ?? "__none__"),
    queryFn: () => api.get<Project>(`/projects/${projectId}`),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(projectId ?? "__none__"),
    queryFn: () => api.get<Episode[]>(`/projects/${projectId}/episodes`),
    enabled: Boolean(projectId && route.episodeId),
    staleTime: 30_000,
  });
  const { data: storyboard } = useQuery({
    queryKey: route.sceneId ? queryKeys.storyboard(route.sceneId) : ["storyboard", "none"],
    queryFn: () => api.get<Storyboard>(`/scenes/${route.sceneId}/storyboard`),
    enabled: Boolean(route.sceneId),
    staleTime: 15_000,
  });

  const episode = episodes?.find((item) => item.id === route.episodeId);
  const selectedShot = storyboard?.shots.find((shot) => shot.id === (route.shotId ?? selectedShotId));
  const storyboardContext = [
    project?.name ?? "漫剧项目",
    "分镜",
    route.episodeId ? `EP${String(episode?.episode_number ?? 1).padStart(2, "0")}` : null,
    route.sceneId
      ? `SC${String(storyboard?.scene.scene_number ?? compactId(route.sceneId)).padStart(2, "0")}`
      : null,
    selectedShot ? `SH${String(selectedShot.shot_number).padStart(2, "0")}` : route.shotId ? compactId(route.shotId) : null,
  ].filter((value): value is string => Boolean(value));
  const isStoryboard = ["storyboard", "storyboard-index", "shot", "shots"].includes(route.workspace);
  const contextSegments = isStoryboard
    ? storyboardContext
    : [project?.name ?? "漫剧项目", moduleLabel(pathname)].filter(Boolean);

  return (
    <div className="app-context-bar">
      <div className="workspace-switch" role="tablist" aria-label="工作区">
        <button
          type="button"
          className={`workspace-item ${activeWorkspace(pathname) === "agent" ? "active" : ""}`}
          disabled={!projectId}
          title={projectId ? "智能体工作区 · 源内容与生产映射（P1）" : "先打开一个项目"}
          aria-current={activeWorkspace(pathname) === "agent" ? "page" : undefined}
          onClick={() => projectId && navigate(`/projects/${projectId}/source`)}
        >
          智能体工作区
        </button>
        <button
          type="button"
          className={`workspace-item ${activeWorkspace(pathname) === "manga" ? "active" : ""}`}
          disabled={!projectId}
          title={projectId ? "漫剧工作区 · 生产控制中心（P2）" : "先打开一个项目"}
          aria-current={activeWorkspace(pathname) === "manga" ? "page" : undefined}
          onClick={() => projectId && navigate(`/projects/${projectId}/workspace`)}
        >
          漫剧工作区
        </button>
      </div>

      <nav className="context-breadcrumb" aria-label="项目上下文" aria-live="polite">
        {projectId && project ? (
          contextSegments.map((segment, index) => (
            <span key={`${segment}-${index}`} className={index === contextSegments.length - 1 ? "current" : undefined}>
              {index > 0 && <span className="context-separator">/</span>}
              {segment}
            </span>
          ))
        ) : pathname === "/projects/new" ? (
          <span className="context-muted">正在创建新的漫剧项目</span>
        ) : (
          <span className="context-muted">未打开项目</span>
        )}
      </nav>

      <span className="context-save-status" title={TAURI_RUNTIME ? "项目状态保存于本地 SQLite" : "项目状态由本地开发服务保存"}>
        <span className="context-status-dot" aria-hidden />
        {projectId ? "已保存 · SQLite" : "等待项目"}
      </span>

      {projectId && (
        <>
          <button
            type="button"
            className="context-gear"
            title="项目设置"
            aria-label="项目设置"
            aria-haspopup="dialog"
            onClick={() => setSettingsOpen(true)}
          >
            <GearSix size={14} />
          </button>
          <ProjectSettingsModal projectId={projectId} open={settingsOpen} onClose={() => setSettingsOpen(false)} />
        </>
      )}
    </div>
  );
}

function compactId(value: string): string {
  return value.length > 8 ? value.slice(-4).toUpperCase() : value.toUpperCase();
}
