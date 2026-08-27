// Activity Rail — fixed 188px column, frozen order across ALL pages (DESIGN.md §4,
// P0 验收清单：顺序在所有页面完全一致，不得增删、换序或改名).
//
// Navigation semantics map the frozen rail items onto real MVP capabilities:
// unimplemented modules render as locked items with an honest tooltip (the same
// honesty rule used since Pass 5) — never fake navigation that goes nowhere.

import { type ReactNode } from "react";
import {
  Brain,
  FilmStrip,
  FolderOpen,
  Gauge,
  GearSix,
  ImageSquare,
  ListChecks,
  LockSimple,
  MagicWand,
  Quotes,
  Scroll,
  ShieldCheck,
  SquaresFour,
  TreeStructure,
  UsersThree,
} from "@phosphor-icons/react";
import { Link, useLocation } from "react-router-dom";
import { canonicalShotPath, canonicalStoryboardPath } from "../../features/studio/studioRoute";
import { lastProjectId } from "../../lib/lastProject";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";

interface RailItem {
  id: string;
  label: string;
  icon: ReactNode;
  /** Where this item navigates; omit for honestly-locked modules. */
  to?: (ctx: RailContext) => string | null;
  /** Tooltip for enabled/disabled states. */
  hint?: (ctx: RailContext) => string;
  /** Route prefixes (regex source) marking the item active. */
  activePattern?: RegExp;
}

interface RailGroup {
  caption: string;
  items: RailItem[];
}

/** Shared navigation context resolved per render. */
interface RailContext {
  projectId: string | null;
}

const NO_PROJECT_HINT = "先打开一个项目（活动栏 · 项目）";

function latestSceneTab(projectId: string | null) {
  const open = useEditorTabsStore.getState().open ?? [];
  return [...open].reverse().find((tab) => tab.kind === "scene" && (!projectId || tab.projectId === projectId));
}

function latestShotTab(projectId: string | null) {
  const open = useEditorTabsStore.getState().open ?? [];
  return [...open].reverse().find((tab) => tab.kind === "shot" && (!projectId || tab.projectId === projectId));
}

// 冻结顺序（DESIGN.md §4 Frozen Activity Rail order）——不得换序、增删、改名。
export const RAIL_GROUPS: RailGroup[] = [
  {
    caption: "工作台",
    items: [
      {
        id: "projects",
        label: "项目",
        icon: <FolderOpen size={17} />,
        to: () => "/",
        activePattern: /^\/$|^\/projects\/new$/,
      },
      {
        id: "workspace",
        label: "工作区",
        icon: <Gauge size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/workspace` : null),
        hint: ({ projectId }) => (projectId ? "漫剧工作区 · 生产控制中心（P2）" : NO_PROJECT_HINT),
        activePattern: /\/workspace/,
      },
    ],
  },
  {
    caption: "创作",
    items: [
      {
        id: "director",
        label: "AI导演",
        icon: <MagicWand size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/script` : null),
        hint: ({ projectId }) =>
          projectId ? "在工作台右侧 Agent Dock 打开 AI 导演" : NO_PROJECT_HINT,
      },
      {
        id: "story",
        label: "故事",
        icon: <Scroll size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/script` : null),
        hint: ({ projectId }) => (projectId ? "剧集与场景剧本分析" : NO_PROJECT_HINT),
        activePattern: /(\/episodes\/[^/]+\/script|\/script$)/,
      },
      {
        id: "characters",
        label: "角色",
        icon: <UsersThree size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/script` : null),
        hint: ({ projectId }) => (projectId ? "角色库位于工作台资源树中" : NO_PROJECT_HINT),
      },
      {
        id: "storyboard",
        label: "分镜",
        icon: <SquaresFour size={17} />,
        to: ({ projectId }) => {
          if (!projectId) return null;
          const scene = latestSceneTab(projectId);
          if (scene?.episodeId && scene.sceneId) {
            return canonicalStoryboardPath(projectId, scene.episodeId, scene.sceneId);
          }
          // No scene visited yet → land on the story workspace where scenes are created.
          return `/projects/${projectId}/script`;
        },
        hint: ({ projectId }) => (projectId ? "镜头网格 · 未有记录时进入故事视图选择场景" : NO_PROJECT_HINT),
        activePattern: /\/storyboard\//,
      },
    ],
  },
  {
    caption: "管线",
    items: [
      {
        id: "workflows",
        label: "工作流",
        icon: <TreeStructure size={17} />,
        to: () => "/workflows",
        hint: () => "只读工作流模板目录",
        activePattern: /^\/workflows/,
      },
      {
        id: "assets",
        label: "资产",
        icon: <ImageSquare size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/assets` : "/assets"),
        hint: ({ projectId }) => (projectId ? "项目素材库" : "全局素材库"),
        activePattern: /^(\/assets|.*\/assets)/,
      },
      {
        id: "shot",
        label: "镜头",
        icon: <FilmStrip size={17} weight="bold" />,
        to: ({ projectId }) => {
          if (!projectId) return null;
          const shot = latestShotTab(projectId);
          if (shot?.episodeId && shot.sceneId && shot.shotId) {
            return canonicalShotPath(projectId, shot.episodeId, shot.sceneId, shot.shotId);
          }
          const scene = latestSceneTab(projectId);
          if (scene?.episodeId && scene.sceneId) {
            return canonicalStoryboardPath(projectId, scene.episodeId, scene.sceneId);
          }
          return `/projects/${projectId}/script`;
        },
        hint: ({ projectId }) => (projectId ? "镜头检查器（跟随最近浏览的镜头）" : NO_PROJECT_HINT),
        activePattern: /\/shots\//,
      },
    ],
  },
  {
    caption: "追溯",
    items: [
      {
        id: "prompts",
        label: "提示词历史",
        icon: <Quotes size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/prompts` : null),
        hint: ({ projectId }) => (projectId ? "项目提示词版本库（ADR-002）" : NO_PROJECT_HINT),
        activePattern: /\/prompts$/,
      },
      {
        id: "knowledge",
        label: "知识库",
        icon: <Brain size={17} />,
        hint: () => "知识图谱 / 规则引擎 · 模块规划中",
      },
      {
        id: "continuity",
        label: "连续性检查",
        icon: <ShieldCheck size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/script` : null),
        hint: ({ projectId }) => (projectId ? "场景连续性徽标位于故事视图资源树中" : NO_PROJECT_HINT),
      },
      {
        id: "timeline",
        label: "时间线",
        icon: <FilmStrip size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/timeline` : null),
        hint: ({ projectId }) => (projectId ? "逐集时间线装配与导出" : NO_PROJECT_HINT),
        activePattern: /\/timeline/,
      },
      {
        id: "log",
        label: "生产日志",
        icon: <ListChecks size={17} />,
        to: ({ projectId }) => (projectId ? `/projects/${projectId}/production-log` : null),
        hint: ({ projectId }) => (projectId ? "生成任务全量历史" : NO_PROJECT_HINT),
        activePattern: /production-log/,
      },
    ],
  },
  {
    caption: "系统",
    items: [
      {
        id: "settings",
        label: "设置",
        icon: <GearSix size={17} />,
        to: () => "/settings",
        hint: () => "Provider 与 LLM 配置",
        activePattern: /^\/settings/,
      },
    ],
  },
];

export function ActivityRail() {
  const { pathname } = useLocation();
  const setRightPanelTab = useWorkspaceStore((s) => s.setRightPanelTab);
  const ctx: RailContext = { projectId: pathname.startsWith("/projects/") ? (/^\/projects\/([^/]+)/.exec(pathname)?.[1] ?? null) : lastProjectId() };

  return (
    <nav className="activity-rail" aria-label="活动栏">
      {RAIL_GROUPS.map((group) => (
        <div className="rail-group" key={group.caption}>
          <div className="rail-caption">{group.caption}</div>
          <ul className="rail-items">
            {group.items.map((item) => {
              const active = item.activePattern?.test(pathname) === true;
              const target = item.to?.(ctx) ?? null;
              const title = item.hint ? item.hint(ctx) : item.label;

              if (!target) {
                return (
                  <li key={item.id}>
                    <span className={`rail-item locked ${active ? "active" : ""}`} role="link" aria-disabled="true" title={title}>
                      {item.icon}
                      <span className="rail-label">{item.label}</span>
                      <LockSimple size={11} weight="fill" className="rail-lock" aria-hidden />
                    </span>
                  </li>
                );
              }

              return (
                <li key={item.id}>
                  <Link
                    to={target}
                    className={`rail-item ${active ? "active" : ""}`}
                    aria-current={active ? "page" : undefined}
                    title={title}
                    onClick={() => {
                      if (item.id === "director") setRightPanelTab("director");
                      if (item.id === "shot") setRightPanelTab("inspector");
                    }}
                  >
                    {item.icon}
                    <span className="rail-label">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
