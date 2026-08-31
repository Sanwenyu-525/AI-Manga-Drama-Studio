// Project Context Bar — 40px (DESIGN.md §4 / P0 frozen shell).
//
// Level-2 workspace switch [ 智能体工作区 | 漫剧工作区 ] lives here (only after the
// 漫剧智能体 mode is active). Same row shows the source↔project binding summary.
// 内容层级导航由 ContentBreadcrumb 承担（2026-08 改版：可点击面包屑 + 同级
// 悬停菜单）；段落一律从真实 Project State 推导 — 不伪造路径。

import { useState } from "react";
import { GearSix } from "@phosphor-icons/react";
import { useLocation, useNavigate } from "react-router-dom";
import { ProjectSettingsModal } from "../../features/settings/ProjectSettingsModal";
import { ContentBreadcrumb } from "./ContentBreadcrumb";

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

export function ProjectContextBar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const projectId = projectIdFromPath(pathname);
  // 项目设置入口：资源树移除后由上下文栏承载（原资源树标题栏的滑块按钮）。
  const [settingsOpen, setSettingsOpen] = useState(false);

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

      <ContentBreadcrumb />

      <span
        className="context-save-status"
        title={TAURI_RUNTIME ? "项目状态保存于本地 SQLite" : "项目状态由本地开发服务保存"}
      >
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
