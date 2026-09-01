// P2 漫剧工作区 — 制作控制台（信息架构重排版）。
// 结构（自上而下）：当前生产状态区（EP + 管线合并，主按钮「继续制作」）→
// 最近生成（缩略图流）→ 剧集工作卡 | 需要处理（异常驱动）。
// 「快捷入口」已删除（与左侧 Rail 重复导航）；「需要关注」只出现真实异常与运行中任务，
// 空闲时显示「当前没有需要处理的问题」。数据全部来自真实 Project State：
// GET /projects/{id}/tree · GET /projects/{id}/bootstrap · GET /generations/recent。

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle,
  Circle,
  FilmStrip,
  MusicNote,
  Play,
  Scroll,
  Warning,
} from "@phosphor-icons/react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { assetUrl } from "../../lib/mediaUrl";
import type { Episode, GenerationRead, ProjectBootstrap, ProjectTreeRead } from "../../api/types";
import {
  percent,
  derivePipeline,
  episodeAction,
  pickCurrentEpisode,
  primaryStageKey,
  summarizeEpisodes,
  type EpisodeAction,
  type EpisodeProgress,
} from "../../lib/workspaceMetrics";
import { generationTypeText } from "../generation/generationTypeText";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import {
  canonicalScriptPath,
  canonicalShotPath,
  canonicalStoryboardPath,
  canonicalTimelinePath,
} from "../studio/studioRoute";

interface RecentOutput {
  assetId: string;
  shotId: string | null;
  provider: string;
  model: string | null;
  createdAt: string;
  type: string;
}

/** 单集卡片状态短语（比裸百分比更接近「下一步该干什么」）。 */
function episodeStatusText(ep: EpisodeProgress, action: EpisodeAction): string {
  switch (action.kind) {
    case "start":
      return "尚未开始";
    case "produce":
      return `图片 ${ep.imageReadyCount}/${ep.shotCount}`;
    case "timeline":
      return "出图完成 · 待排片";
    case "render":
      return "已排片 · 待渲染";
    case "review":
      return "已导出成片";
  }
}

export function WorkspaceOverviewPage({ projectId }: { projectId?: string }) {
  const params = useParams();
  const pid = projectId ?? params.projectId ?? "";

  const setBottomDockExpanded = useWorkspaceStore((s) => s.setBottomDockExpanded);
  const setBottomDockTab = useWorkspaceStore((s) => s.setBottomDockTab);
  const setRightPanelCollapsed = useWorkspaceStore((s) => s.setRightPanelCollapsed);
  const setRightPanelTab = useWorkspaceStore((s) => s.setRightPanelTab);

  const { data: tree } = useQuery({
    queryKey: queryKeys.projectTree(pid),
    queryFn: () => api.get<ProjectTreeRead>(`/projects/${pid}/tree`),
    enabled: Boolean(pid),
  });
  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(pid),
    queryFn: () => api.get<Episode[]>(`/projects/${pid}/episodes`),
    enabled: Boolean(pid),
  });
  const { data: bootstrap } = useQuery({
    queryKey: queryKeys.bootstrap(pid),
    queryFn: () => api.get<ProjectBootstrap>(`/projects/${pid}/bootstrap`),
    enabled: Boolean(pid),
    staleTime: 10_000,
  });
  const { data: recent } = useQuery({
    queryKey: queryKeys.recentGenerations,
    queryFn: () => api.get<GenerationRead[]>("/generations/recent"),
    refetchInterval: 15_000,
    enabled: Boolean(pid),
  });

  const progress = useMemo(() => summarizeEpisodes(tree, episodes), [tree, episodes]);

  // 管线探针（contract §103）：bootstrap 每集携带 has_timeline / has_final_video。
  const bootstrapById = useMemo(
    () => new Map((bootstrap?.episodes ?? []).map((b) => [b.id, b])),
    [bootstrap],
  );
  const stageFlags = {
    timeline: (bootstrap?.episodes ?? []).some((ep) => ep.has_timeline),
    finalVideo: (bootstrap?.episodes ?? []).some((ep) => ep.has_final_video),
  };

  // shot → 所属场景/剧集（缩略图点击直达镜头详情；不在树中的 shot 退回资产库）。
  const shotLocation = useMemo(() => {
    const map = new Map<string, { episodeId: string; sceneId: string }>();
    for (const ep of tree?.episodes ?? []) {
      for (const sc of ep.scenes) {
        for (const sh of sc.shots) map.set(sh.id, { episodeId: ep.id, sceneId: sc.id });
      }
    }
    return map;
  }, [tree]);

  // 场景级定位：首个没分镜的场景 / 首个有镜头未出图的场景（继续制作落点）。
  const sceneIndex = useMemo(
    () =>
      (tree?.episodes ?? []).flatMap((ep) =>
        ep.scenes.map((sc) => ({
          episodeId: ep.id,
          sceneId: sc.id,
          hasShots: sc.shots.length > 0,
          allReady: sc.shots.length > 0 && sc.shots.every((sh) => sh.active_image_version != null || sh.status === "image_ready" || sh.status === "approved"),
          firstFailedShotId: sc.shots.find((sh) => sh.status === "failed")?.id ?? null,
        })),
      ),
    [tree],
  );

  const outputs = useMemo<RecentOutput[]>(() => {
    const seen = new Set<string>();
    const items: RecentOutput[] = [];
    for (const g of recent ?? []) {
      if (g.project_id !== pid || !g.output_asset_id || seen.has(g.output_asset_id)) continue;
      seen.add(g.output_asset_id);
      items.push({
        assetId: g.output_asset_id,
        shotId: g.shot_id,
        provider: g.provider,
        model: g.model,
        createdAt: g.created_at,
        type: g.type,
      });
      if (items.length >= 8) break;
    }
    return items;
  }, [recent, pid]);

  const failedRecent = (recent ?? []).filter((g) => g.project_id === pid && g.status === "failed").length;
  const activeGens = bootstrap?.active_generations ?? 0;
  const activeRuns = bootstrap?.active_agent_runs ?? 0;

  const pipeline = derivePipeline(progress, stageFlags.timeline, stageFlags.finalVideo);
  const runningStage = pipeline.find((stage) => stage.state === "running");
  const current = pickCurrentEpisode(progress, bootstrap?.episodes);
  const currentFlags = current ? bootstrapById.get(current.episodeId) : undefined;
  const currentAction = current
    ? episodeAction(current, currentFlags && { hasTimeline: currentFlags.has_timeline, hasFinalVideo: currentFlags.has_final_video })
    : null;
  const imagePct = percent(progress.imageReadyCount, progress.shotCount);

  /** 集级动作跳转：开始→剧本视图；继续→首个未出图场景的分镜板；收尾→时间线。 */
  const episodeTarget = (ep: EpisodeProgress, action: EpisodeAction): string => {
    if (action.kind === "start") return canonicalScriptPath(pid, ep.episodeId);
    if (action.kind === "produce") {
      const scene = sceneIndex.find((s) => s.episodeId === ep.episodeId && !s.allReady && s.hasShots);
      const fallback = sceneIndex.find((s) => s.episodeId === ep.episodeId);
      const target = scene ?? fallback;
      return target
        ? canonicalStoryboardPath(pid, target.episodeId, target.sceneId)
        : canonicalScriptPath(pid, ep.episodeId);
    }
    return canonicalTimelinePath(pid, ep.episodeId);
  };

  /** 管线阶段跳转（状态区阶段条可点）。 */
  const stageTarget = (key: string): string => {
    const eps = progress.episodes;
    switch (key) {
      case "source":
        return eps.length > 0
          ? canonicalScriptPath(pid, (eps.find((e) => !e.hasSourceText) ?? eps[0]).episodeId)
          : `/projects/${pid}/script`;
      case "scenes": {
        const ep = eps.find((e) => e.sceneCount === 0 && e.hasSourceText) ?? current;
        return ep ? canonicalScriptPath(pid, ep.episodeId) : `/projects/${pid}/script`;
      }
      case "shots": {
        const scene = sceneIndex.find((s) => !s.hasShots);
        if (scene) return canonicalStoryboardPath(pid, scene.episodeId, scene.sceneId);
        return eps.length > 0 ? canonicalScriptPath(pid, eps[0].episodeId) : `/projects/${pid}/script`;
      }
      case "image": {
        const scene = sceneIndex.find((s) => !s.allReady);
        if (scene) return canonicalStoryboardPath(pid, scene.episodeId, scene.sceneId);
        return eps.length > 0
          ? canonicalTimelinePath(pid, (current ?? eps[0]).episodeId)
          : `/projects/${pid}/script`;
      }
      default: {
        const needTimeline = key === "timeline";
        const ep =
          eps.find((e) => {
            const flags = bootstrapById.get(e.episodeId);
            return needTimeline ? !flags?.has_timeline : !flags?.has_final_video;
          }) ?? current ?? eps[0];
        return ep ? canonicalTimelinePath(pid, ep.episodeId) : `/projects/${pid}/script`;
      }
    }
  };

  const primaryKind = progress.episodes.length === 0 ? "start" : primaryStageKey(pipeline);
  const primaryTarget = primaryKind === "start" ? `/projects/${pid}/script` : stageTarget(primaryKind);
  const primaryLabel = primaryKind === "start" ? "开始制作" : "继续制作";

  // 异常驱动「需要处理」：只列真实失败/进行中，常态入口一律不进。
  const attention = useMemo(() => {
    const items: {
      key: string;
      tone: "bad" | "info";
      text: string;
      action: { label: string; to?: string; onClick?: () => void };
    }[] = [];
    if (failedRecent > 0) {
      items.push({
        key: "failed-generations",
        tone: "bad",
        text: `${failedRecent} 条生成失败`,
        action: { label: "查看日志", to: `/projects/${pid}/production-log` },
      });
    }
    if (progress.failedCount > 0) {
      const failedScene = sceneIndex.find((s) => s.firstFailedShotId);
      const target = failedScene
        ? canonicalStoryboardPath(pid, failedScene.episodeId, failedScene.sceneId)
        : `/projects/${pid}/production-log`;
      items.push({
        key: "failed-shots",
        tone: "bad",
        text: `${progress.failedCount} 个镜头出图失败`,
        action: { label: "去修复", to: target },
      });
    }
    if (activeGens > 0) {
      items.push({
        key: "running-generations",
        tone: "info",
        text: `${activeGens} 个生成任务运行中`,
        action: {
          label: "展开队列",
          onClick: () => {
            setBottomDockTab("queue");
            setBottomDockExpanded(true);
          },
        },
      });
    }
    if (activeRuns > 0) {
      items.push({
        key: "running-agent",
        tone: "info",
        text: `${activeRuns} 个 AI 导演任务运行中`,
        action: {
          label: "查看",
          onClick: () => {
            setRightPanelTab("director");
            setRightPanelCollapsed(false);
          },
        },
      });
    }
    return items;
  }, [activeGens, activeRuns, failedRecent, pid, progress.failedCount, sceneIndex, setBottomDockExpanded, setBottomDockTab, setRightPanelCollapsed, setRightPanelTab]);

  if (!pid) return <div className="workspace-loading">未打开项目</div>;

  return (
    <div className="ws-overview">
      <div className="panel-head">
        <h1>漫剧工作区</h1>
        <span className="muted small">制作控制台</span>
        <span className="grow" />
        <Link className="btn secondary compact" to={`/projects/${pid}/source`}>
          <Scroll size={14} /> 源内容工作区
        </Link>
      </div>

      <div className="ws-grid">
        {/* ---- 当前生产状态区（剧集进度 + 生产管线合并，主行动按钮） ---- */}
        <section className="ws-panel ws-panel-status" aria-label="当前生产状态">
          <div className="ws-status-top">
            <div className="ws-status-id">
              <h2>
                {current
                  ? `EP${String(current.episodeNumber).padStart(2, "0")} · ${current.title || "未命名"}`
                  : "还没有剧集"}
              </h2>
              <span className="muted small">
                {runningStage ? `当前阶段：${runningStage.label}` : "等待开始"}
                {current && currentAction && (
                  <>
                    {" · "}
                    {episodeStatusText(current, currentAction)}
                  </>
                )}
              </span>
            </div>
            <Link className="btn primary ws-continue" to={primaryTarget}>
              {primaryLabel} <ArrowRight size={14} weight="bold" />
            </Link>
          </div>
          <div className="ws-status-progress">
            <span className="mono small">
              {progress.imageReadyCount} / {progress.shotCount} 镜头
            </span>
            <span
              className={`ws-progress ${progress.failedCount > 0 ? "has-failed" : ""}`}
              aria-label={`项目出图进度 ${imagePct}%`}
            >
              <i style={{ width: `${imagePct}%` }} />
            </span>
            <span className="mono small ws-status-pct">{imagePct}%</span>
          </div>
          <ol className="ws-stage-strip">
            {pipeline.map((stage) => (
              <li key={stage.key} className={`ws-stage-chip ${stage.state}`}>
                <Link to={stageTarget(stage.key)} title={`打开「${stage.label}」`}>
                  <span className="ws-stage-icon">
                    {stage.state === "done" ? (
                      <CheckCircle size={13} weight="fill" />
                    ) : stage.state === "running" ? (
                      <Circle size={11} weight="fill" />
                    ) : (
                      <Circle size={11} weight="regular" />
                    )}
                  </span>
                  {stage.label}
                  {stage.detail && <span className="ws-stage-detail mono">{stage.detail}</span>}
                </Link>
              </li>
            ))}
          </ol>
        </section>

        {/* ---- 最近生成（视觉产出缩略图流，点击直达镜头/资产） ---- */}
        <section className="ws-panel ws-panel-outputs" aria-label="最近生成">
          <div className="ws-panel-head">
            <h2 className="ws-panel-title">最近生成</h2>
            <Link className="text-link small" to={`/projects/${pid}/assets`}>
              查看全部资产
            </Link>
          </div>
          {outputs.length === 0 ? (
            <p className="muted small ws-pad">
              还没有生成产出 —— 在分镜板选择镜头并执行「生成图片」，产出会出现在这里。
            </p>
          ) : (
            <ul className="ws-output-grid">
              {outputs.map((o) => {
                const loc = o.shotId ? shotLocation.get(o.shotId) : undefined;
                const to = loc && o.shotId ? canonicalShotPath(pid, loc.episodeId, loc.sceneId, o.shotId) : `/projects/${pid}/assets`;
                const label = o.shotId ? `SHOT ${o.shotId.slice(-4).toUpperCase()}` : generationTypeText(o.type);
                return (
                  <li key={o.assetId} className="ws-output-card">
                    <Link to={to} title={`打开 ${label}`}>
                      {o.type === "image" ? (
                        <img loading="lazy" src={assetUrl(o.assetId, "thumbnail")} alt={`镜头 ${label} 的生成图片`} />
                      ) : (
                        <span className={`ws-output-thumb type-${o.type}`}>
                          {o.type === "audio" ? <MusicNote size={22} /> : <FilmStrip size={22} />}
                        </span>
                      )}
                      <span className="ws-output-meta">
                        <span className="mono tiny">{label}</span>
                        <span className="muted tiny ellipsis">
                          {generationTypeText(o.type)}
                          {o.provider ? ` · ${o.provider}` : ""}
                        </span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* ---- 剧集工作卡（整卡可点 = 下一步动作） ---- */}
        <section className="ws-panel ws-panel-episodes" aria-label="剧集">
          <div className="ws-panel-head">
            <h2 className="ws-panel-title">剧集</h2>
            <Link className="text-link small" to={`/projects/${pid}/script`}>
              + 新建剧集
            </Link>
          </div>
          {progress.episodes.length === 0 ? (
            <div className="ws-empty">
              <p>还没有剧集。</p>
              <Link className="btn secondary compact" to={`/projects/${pid}/script`}>
                <Scroll size={14} /> 去剧本视图创建
              </Link>
            </div>
          ) : (
            <ul className="ws-ep-cards">
              {progress.episodes.map((ep) => {
                const flags = bootstrapById.get(ep.episodeId);
                const action = episodeAction(ep, flags && { hasTimeline: flags.has_timeline, hasFinalVideo: flags.has_final_video });
                const target = episodeTarget(ep, action);
                const isCurrent = current?.episodeId === ep.episodeId;
                return (
                  <li key={ep.episodeId}>
                    <Link
                      to={target}
                      className={`ws-ep-card ${isCurrent ? "is-current" : ""}`}
                      aria-label={`${action.label}：EP${String(ep.episodeNumber).padStart(2, "0")}`}
                    >
                      <span className="ws-ep-row">
                        <span className="ws-ep-name">
                          EP{String(ep.episodeNumber).padStart(2, "0")} · {ep.title || "未命名"}
                        </span>
                        <span className={`btn tiny ${isCurrent ? "primary" : "secondary"}`}>{action.label}</span>
                      </span>
                      <span className="ws-ep-row muted small">
                        <span>
                          {ep.sceneCount} 场 · {ep.shotCount} 镜头
                          {ep.failedCount > 0 && <span className="ws-ep-failed"> · {ep.failedCount} 失败</span>}
                        </span>
                        <span>{episodeStatusText(ep, action)}</span>
                      </span>
                      {ep.shotCount > 0 && (
                        <span
                          className={`ws-progress ${ep.failedCount > 0 ? "has-failed" : ""}`}
                          aria-label={`出图进度 ${percent(ep.imageReadyCount, ep.shotCount)}%`}
                        >
                          <i style={{ width: `${percent(ep.imageReadyCount, ep.shotCount)}%` }} />
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* ---- 需要处理（异常驱动：失败/进行中，空闲=干净态） ---- */}
        <section className="ws-panel ws-panel-attention" aria-label="需要处理">
          <div className="ws-panel-head">
            <h2 className="ws-panel-title">需要处理</h2>
            {attention.length > 0 && <span className="ws-attn-count">{attention.length}</span>}
          </div>
          {attention.length === 0 ? (
            <div className="ws-attn-clean">
              <CheckCircle size={15} weight="fill" />
              <span>当前没有需要处理的问题</span>
            </div>
          ) : (
            <ul className="ws-attention-list">
              {attention.map((item) => {
                const body = (
                  <>
                    {item.tone === "bad" ? (
                      <Warning size={14} weight="fill" />
                    ) : (
                      <Play size={12} weight="fill" />
                    )}
                    <span className="ws-attn-text">{item.text}</span>
                    <span className="text-link">{item.action.label}</span>
                  </>
                );
                return (
                  <li key={item.key} className={`attn ${item.tone}`}>
                    {item.action.to ? (
                      <Link to={item.action.to} className="ws-attn-row">
                        {body}
                      </Link>
                    ) : (
                      <button type="button" className="ws-attn-row" onClick={item.action.onClick}>
                        {body}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
