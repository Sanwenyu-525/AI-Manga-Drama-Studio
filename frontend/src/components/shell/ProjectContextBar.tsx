// Project Context Bar — 40px (DESIGN.md §4 / P0 frozen shell).
//
// Level-2 workspace switch [ 智能体工作区 | 漫剧工作区 ] lives here (only after the
// 漫剧智能体 mode is active). Same row shows the source↔project binding summary.
// The source-workspace path is not part of MVP Project State, so we render the
// manga-project side only — never a fabricated path, never a parent-child breadcrumb.

import { useQuery } from "@tanstack/react-query";
import { ArrowsLeftRight } from "@phosphor-icons/react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Project } from "../../api/types";

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
  const projectId = projectIdFromPath(pathname);

  // Same cache key as StudioPage → free sharing; disabled without a project.
  const { data: project } = useQuery({
    queryKey: queryKeys.project(projectId ?? "__none__"),
    queryFn: () => api.get<Project>(`/projects/${projectId}`),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });

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

      <span className="binding-summary" aria-live="polite">
        <ArrowsLeftRight size={13} weight="fill" aria-hidden />
        {projectId && project ? (
          <>
            <span className="binding-project">漫剧项目《{project.name}》</span>
            <span className="binding-meta">{moduleLabel(pathname) && `· ${moduleLabel(pathname)}`}</span>
          </>
        ) : pathname === "/projects/new" ? (
          <span className="binding-meta">正在创建新的漫剧项目</span>
        ) : (
          <span className="binding-meta">未打开项目 · 从左侧活动栏进入项目</span>
        )}
      </span>

      <span className={`context-env ${TAURI_RUNTIME ? "" : "web"}`} title={TAURI_RUNTIME ? "桌面运行环境" : "浏览器预览环境"}>
        {TAURI_RUNTIME ? "桌面端" : "Web 预览"}
      </span>
    </div>
  );
}
