// ContentBreadcrumb — 顶部内容层级路径（可点击面包屑，2026-08 交互定稿）。
//
// 与左侧活动栏的职责分界：活动栏 = 功能导航（我在做什么）；面包屑 = 内容层级
// 导航（我正在什么内容里）。交互模型：
//   一级  点击祖先段 → SPA 内跳转（只换工作区内容，壳/右侧面板不重载）；
//   二级  悬停有同级内容的段 → 同级菜单横向切换（项目↔项目 / 模块↔模块 /
//         EP↔EP / SC↔SC），不必一级级返回；
//   三级  末段（当前节点）只读高亮，不可点击；
//   四级  空间不足时首现 … 段，悬停展开完整层级菜单。
//
// 视觉上刻意不做文件管理器隐喻（无文件夹图标）；EP/SC/SH 段只由真实
// Project State（路由 + 查询缓存）推导，绝不伪造路径。
// 菜单经 portal 渲染到 body：40px 上下文栏是 overflow:hidden 的冻结壳，
// 行内绝对定位会被裁剪。

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { CaretDown, Check } from "@phosphor-icons/react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Project, Scene, Storyboard } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import {
  canonicalScriptPath,
  canonicalStoryboardPath,
  canonicalTimelinePath,
  useStudioRoute,
  type StudioRoute,
} from "../../features/studio/studioRoute";

type CrumbMenuKind = "project" | "module" | "episode" | "scene" | "overflow";

interface Crumb {
  key: string;
  label: string;
  title: string;
  /** 祖先段的点击跳转目标；末段/只读段为 null。 */
  to: string | null;
  /** 同级菜单数据源；末段为 null（当前节点不可点、无菜单）。 */
  menu: CrumbMenuKind | null;
}

interface MenuItem {
  key: string;
  code: string | null;
  label: string;
  active: boolean;
  onSelect: () => void;
}

const MENU_WIDTH = 300;
const CLOSE_DELAY_MS = 140;

/** 父层 openKey 的 setter（接受函数式更新，供悬停关闭定时器做 key 校验）。 */
type OpenKeySetter = (update: string | null | ((prev: string | null) => string | null)) => void;

const pad2 = (value: number) => String(value).padStart(2, "0");
const compactId = (value: string) => (value.length > 8 ? value.slice(-4).toUpperCase() : value.toUpperCase());

/** Current manga-project id parsed from URL (/projects/:projectId/...), else null. */
function projectIdFromPath(pathname: string): string | null {
  const match = /^\/projects\/([^/]+)/.exec(pathname);
  return match ? match[1] : null;
}

// 模块菜单与模块段的唯一事实源（与 ActivityRail 顺序保持一致的语义映射，
// 但面包屑只收内容模块；build 在有剧集上下文时直达该集的剧本/时间线）。
const MODULE_MENU: { key: string; label: string; build: (projectId: string, episodeId?: string) => string }[] = [
  { key: "workspace", label: "生产控制中心", build: (p) => `/projects/${p}/workspace` },
  { key: "source", label: "源内容工作区", build: (p) => `/projects/${p}/source` },
  { key: "director", label: "AI导演", build: (p) => `/projects/${p}/director` },
  { key: "script", label: "剧本", build: (p, ep) => (ep ? canonicalScriptPath(p, ep) : `/projects/${p}/script`) },
  { key: "storyboard", label: "分镜", build: (p) => `/projects/${p}/storyboard` },
  { key: "shots", label: "镜头", build: (p) => `/projects/${p}/shots` },
  { key: "characters", label: "角色", build: (p) => `/projects/${p}/characters` },
  { key: "assets", label: "素材库", build: (p) => `/projects/${p}/assets` },
  {
    key: "timeline",
    label: "时间线",
    build: (p, ep) => (ep ? canonicalTimelinePath(p, ep) : `/projects/${p}/timeline`),
  },
  { key: "continuity", label: "连续性检查", build: (p) => `/projects/${p}/continuity` },
  { key: "knowledge", label: "知识库", build: (p) => `/projects/${p}/knowledge` },
  { key: "prompts", label: "提示词历史", build: (p) => `/projects/${p}/prompts` },
  { key: "production-log", label: "生产日志", build: (p) => `/projects/${p}/production-log` },
];

// workspace → 模块菜单 key（storyboard-index/shot 归入「分镜」层级语义）。
const WORKSPACE_MODULE: Record<StudioRoute["workspace"], string> = {
  workspace: "workspace",
  source: "source",
  director: "director",
  script: "script",
  characters: "characters",
  "storyboard-index": "storyboard",
  storyboard: "storyboard",
  shot: "storyboard",
  shots: "shots",
  assets: "assets",
  prompts: "prompts",
  knowledge: "knowledge",
  continuity: "continuity",
  timeline: "timeline",
  "production-log": "production-log",
};

function moduleSegment(route: StudioRoute, pathname: string): { key: string; label: string; to: string } | null {
  const { projectId } = route;
  if (!projectId) return null;
  // 版本对比页在 StudioRoute 之外（parseStudioRoute 返回 null → legacy 兜底），
  // 单独识别，避免被误标成「剧本」。
  if (/^\/projects\/[^/]+\/shots\/[^/]+\/versions/.test(pathname)) {
    return { key: "shots", label: "版本对比", to: `/projects/${projectId}/shots` };
  }
  const mod = MODULE_MENU.find((item) => item.key === WORKSPACE_MODULE[route.workspace]);
  if (!mod) return null;
  return { key: mod.key, label: mod.label, to: mod.build(projectId, route.episodeId) };
}

export function ContentBreadcrumb() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const route = useStudioRoute();
  const projectId = projectIdFromPath(pathname);
  const selectedShotId = useSelectionStore((state) => state.selection.shotIds[0]);
  const clearShots = useSelectionStore((state) => state.clearShots);
  const [openKey, setOpenKey] = useState<string | null>(null);

  // 路由变化即收起菜单（点击菜单项的跳转也会经过这里）。
  useEffect(() => {
    setOpenKey(null);
  }, [pathname]);

  // 与页面共享同一批 query key → 缓存命中时零请求。
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
  // 同级数据懒加载：菜单首次悬停才请求（projects / scenes）。
  const { data: projects } = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<Project[]>("/projects"),
    enabled: openKey === "project",
    staleTime: 30_000,
  });
  const sceneMenuEpisodeId = openKey === "scene" ? route.episodeId : undefined;
  const { data: scenes } = useQuery({
    queryKey: queryKeys.scenes(sceneMenuEpisodeId ?? "__none__"),
    queryFn: () => api.get<Scene[]>(`/episodes/${sceneMenuEpisodeId}/scenes`),
    enabled: Boolean(sceneMenuEpisodeId),
    staleTime: 15_000,
  });

  const crumbs = useMemo<Crumb[]>(() => {
    if (!projectId || !project) return [];
    const list: Crumb[] = [
      {
        key: "project",
        label: project.name,
        title: `项目 · ${project.name}`,
        to: `/projects/${projectId}/workspace`,
        menu: "project",
      },
    ];
    const moduleSeg = moduleSegment(route, pathname);
    if (moduleSeg) {
      list.push({
        key: "module",
        label: moduleSeg.label,
        title: `模块 · ${moduleSeg.label}`,
        to: moduleSeg.to,
        menu: "module",
      });
    }
    const episode = episodes?.find((item) => item.id === route.episodeId);
    if (route.episodeId) {
      list.push({
        key: "episode",
        label: `EP${pad2(episode?.episode_number ?? 1)}`,
        title: `剧集 · ${episode?.title || "未命名"}`,
        // 该集主页 = 剧本工作区（场景列表与分镜入口都在这里）。
        to: canonicalScriptPath(projectId, route.episodeId),
        menu: "episode",
      });
    }
    // legacy /storyboard/:sceneId 瞬态缺 episodeId，canonical 跳转毫秒级完成，不渲染 SC/SH 段。
    if (route.sceneId && !route.legacy) {
      const sceneLabel = storyboard?.scene.scene_number
        ? `SC${pad2(storyboard.scene.scene_number)}`
        : compactId(route.sceneId);
      list.push({
        key: "scene",
        label: sceneLabel,
        title: `场景 · ${storyboard?.scene.name || "未命名场景"}`,
        to: canonicalStoryboardPath(projectId, route.episodeId ?? "", route.sceneId),
        menu: "scene",
      });
      const shotId = route.workspace === "shot" ? route.shotId : selectedShotId;
      const shot = shotId ? storyboard?.shots.find((item) => item.id === shotId) : undefined;
      const shotLabel = shot ? `SH${pad2(shot.shot_number)}` : shotId ? compactId(shotId) : null;
      if (shotLabel) {
        // 镜头是叶节点：仅显示当前位置，不提供点击/菜单（交互模型三级）。
        list.push({ key: "shot", label: shotLabel, title: `镜头 · ${shotLabel}`, to: null, menu: null });
      }
    }
    const last = list[list.length - 1];
    if (last) {
      last.to = null;
      last.menu = null;
    }
    return list;
  }, [projectId, project, route, pathname, episodes, storyboard, selectedShotId]);

  // 四级：空间不足（各段已缩到极限仍放不下）→ 首现 … 段展开完整层级。
  const navRef = useRef<HTMLElement | null>(null);
  const [overflowing, setOverflowing] = useState(false);
  useEffect(() => {
    const nav = navRef.current;
    if (!nav || typeof ResizeObserver === "undefined") return;
    const check = () => setOverflowing(nav.scrollWidth > nav.clientWidth + 1);
    check();
    const observer = new ResizeObserver(check);
    observer.observe(nav);
    return () => observer.disconnect();
  }, [crumbs]);

  const currentModuleKey = moduleSegment(route, pathname)?.key ?? null;

  const menuItems = useMemo<MenuItem[]>(() => {
    if (!openKey || !projectId) return [];
    if (openKey === "project") {
      return (projects ?? []).map((item) => ({
        key: item.id,
        code: null,
        label: item.name,
        active: item.id === projectId,
        onSelect: () => navigate(`/projects/${item.id}/workspace`),
      }));
    }
    if (openKey === "module") {
      return MODULE_MENU.map((mod) => ({
        key: mod.key,
        code: null,
        label: mod.label,
        active: mod.key === currentModuleKey,
        onSelect: () => navigate(mod.build(projectId, route.episodeId)),
      }));
    }
    if (openKey === "episode") {
      return [...(episodes ?? [])]
        .sort((a, b) => a.episode_number - b.episode_number)
        .map((item) => ({
          key: item.id,
          code: `EP${pad2(item.episode_number)}`,
          label: item.title || "未命名",
          active: item.id === route.episodeId,
          onSelect: () => navigate(canonicalScriptPath(projectId, item.id)),
        }));
    }
    if (openKey === "scene") {
      return [...(scenes ?? [])]
        .sort((a, b) => a.scene_number - b.scene_number)
        .map((item) => ({
          key: item.id,
          code: `SC${pad2(item.scene_number)}`,
          label: item.name || "未命名场景",
          active: item.id === route.sceneId,
          // 横切场景时清掉上一场景的镜头选择，右侧检查器不残留脏上下文。
          onSelect: () => {
            clearShots();
            navigate(canonicalStoryboardPath(projectId, route.episodeId ?? "", item.id));
          },
        }));
    }
    if (openKey === "overflow") {
      return crumbs
        .filter((crumb) => crumb.to)
        .map((crumb) => ({
          key: crumb.key,
          code: null,
          label: crumb.label,
          active: false,
          onSelect: () => navigate(crumb.to as string),
        }));
    }
    return [];
  }, [
    openKey,
    projectId,
    projects,
    currentModuleKey,
    route.episodeId,
    route.sceneId,
    episodes,
    scenes,
    crumbs,
    navigate,
    clearShots,
  ]);

  const menuStatus =
    openKey === "project"
      ? projects
        ? projects.length === 0
          ? "暂无项目"
          : null
        : "加载中…"
      : openKey === "episode"
        ? episodes
          ? episodes.length === 0
            ? "该项目还没有剧集"
            : null
          : "加载中…"
        : openKey === "scene"
          ? scenes
            ? scenes.length === 0
              ? "该集还没有场景"
              : null
            : "加载中…"
          : null;

  if (!projectId || !project) {
    const muted =
      pathname === "/projects/new"
        ? "正在创建新的漫剧项目"
        : pathname === "/" || pathname === ""
          ? "项目库"
          : "未打开项目";
    return (
      <nav className="context-breadcrumb" aria-label="项目上下文">
        <span className="context-muted">{muted}</span>
      </nav>
    );
  }

  const overflowCrumb: Crumb = { key: "__overflow__", label: "…", title: "完整层级路径", to: null, menu: "overflow" };

  return (
    <nav className="context-breadcrumb" aria-label="项目上下文" aria-live="polite" ref={navRef}>
      {overflowing && (
        <span className="crumb-item">
          <CrumbSegment
            crumb={overflowCrumb}
            open={openKey === overflowCrumb.key}
            items={menuItems}
            status={menuStatus}
            onOpenChange={setOpenKey}
          />
        </span>
      )}
      {crumbs.map((crumb, index) => (
        <span key={crumb.key} className="crumb-item">
          {index > 0 && <span className="context-separator">/</span>}
          <CrumbSegment
            crumb={crumb}
            open={openKey === crumb.key}
            items={crumb.menu === openKey ? menuItems : []}
            status={crumb.menu === openKey ? menuStatus : null}
            onOpenChange={setOpenKey}
          />
        </span>
      ))}
    </nav>
  );
}

interface SegmentProps {
  crumb: Crumb;
  open: boolean;
  items: MenuItem[];
  status: string | null;
  onOpenChange: OpenKeySetter;
}

function CrumbSegment({ crumb, open, items, status, onOpenChange }: SegmentProps) {
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const closeTimer = useRef<number | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const cancelClose = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };
  const scheduleClose = () => {
    cancelClose();
    // 函数式更新 + key 校验：悬停跨段时旧段的定时器不得关掉新段的菜单。
    closeTimer.current = window.setTimeout(
      () => onOpenChange((prev) => (prev === crumb.key ? null : prev)),
      CLOSE_DELAY_MS,
    );
  };
  const openMenu = () => {
    cancelClose();
    const rect = anchorRef.current?.getBoundingClientRect();
    if (rect) {
      setPos({
        top: rect.bottom + 6,
        left: Math.max(8, Math.min(rect.left, window.innerWidth - MENU_WIDTH - 8)),
      });
    }
    onOpenChange(crumb.key);
  };

  // 打开期间的全局关闭时机：Escape / 外部按下 / 滚动或缩放（菜单为瞬时层）。
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(null);
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (anchorRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      onOpenChange(null);
    };
    const onDismiss = () => onOpenChange(null);
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("scroll", onDismiss, true);
    window.addEventListener("resize", onDismiss);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("scroll", onDismiss, true);
      window.removeEventListener("resize", onDismiss);
    };
  }, [open, onOpenChange]);

  useEffect(() => cancelClose, []);

  const hasMenu = crumb.menu !== null;
  const anchorClass = `crumb-anchor${hasMenu ? " has-menu" : ""}`;

  return (
    <span
      className={anchorClass}
      ref={anchorRef}
      onMouseEnter={hasMenu ? openMenu : undefined}
      onMouseLeave={hasMenu ? scheduleClose : undefined}
    >
      {crumb.to ? (
        <Link
          to={crumb.to}
          className={`crumb ${crumb.key === "project" ? "crumb-root" : ""}`}
          title={crumb.title}
          aria-haspopup={hasMenu ? "menu" : undefined}
          aria-expanded={hasMenu ? open : undefined}
          onClick={() => onOpenChange(null)}
        >
          <span className="crumb-label">{crumb.label}</span>
          {hasMenu && <CaretDown size={9} weight="bold" className="crumb-caret" aria-hidden />}
        </Link>
      ) : hasMenu ? (
        <button
          type="button"
          className="crumb crumb-more"
          title={crumb.title}
          aria-label={crumb.title}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => (open ? onOpenChange(null) : openMenu())}
        >
          <span className="crumb-label">{crumb.label}</span>
        </button>
      ) : (
        <span className="crumb crumb-current" aria-current="location" title={crumb.title}>
          <span className="crumb-label">{crumb.label}</span>
        </span>
      )}
      {open &&
        createPortal(
          <div
            className="crumb-menu"
            role="menu"
            aria-label={`${crumb.label} · 同级内容`}
            ref={menuRef}
            style={{ top: pos?.top ?? 0, left: pos?.left ?? 0 }}
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
          >
            {status && <div className="crumb-menu-empty">{status}</div>}
            {items.map((item) => (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                className={`crumb-menu-item ${item.active ? "active" : ""}`}
                onClick={() => {
                  onOpenChange(null);
                  item.onSelect();
                }}
              >
                {item.code && <span className="crumb-menu-code mono">{item.code}</span>}
                <span className="crumb-menu-label">{item.label}</span>
                {item.active && <Check size={12} weight="bold" className="crumb-check" aria-hidden />}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </span>
  );
}
