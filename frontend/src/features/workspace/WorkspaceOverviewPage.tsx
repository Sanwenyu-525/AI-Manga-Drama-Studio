// P2 漫剧工作区 — 生产控制中心（目标态落地版）。
// 回答：做到哪（管线/每集进度）、AI 在做什么（活跃任务）、哪里有风险（失败/连续性入口）、
// 最近产出是什么（真实生成记录）。数据全部来自真实 Project State：
// GET /projects/{id}/tree · GET /projects/{id}/bootstrap · GET /generations/recent。
// 渲染于 Studio 画布（Agent Dock 自动可用）；无巨大营销图、无 SaaS KPI 卡。

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle,
  Circle,
  FilmStrip,
  ImageSquare,
  ListChecks,
  MagnifyingGlass,
  Play,
  Quotes,
  Scroll,
  ShieldCheck,
  Warning,
} from "@phosphor-icons/react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, GenerationRead, ProjectBootstrap, ProjectTreeRead } from "../../api/types";
import { percent, derivePipeline, summarizeEpisodes } from "../../lib/workspaceMetrics";
import { canonicalScriptPath } from "../studio/studioRoute";

interface RecentOutput {
  assetId: string;
  shotId: string | null;
  provider: string;
  model: string | null;
  createdAt: string;
  type: string;
}

export function WorkspaceOverviewPage({ projectId }: { projectId?: string }) {
  const params = useParams();
  const pid = projectId ?? params.projectId ?? "";

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

  // 管线探针（contract §103）：bootstrap 每集携带 has_timeline / has_final_video，
  // 任一集为真即该阶段已达成 —— 替代逐集 404 探测。
  const stageFlags = {
    timeline: (bootstrap?.episodes ?? []).some((ep) => ep.has_timeline),
    finalVideo: (bootstrap?.episodes ?? []).some((ep) => ep.has_final_video),
  };

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
      if (items.length >= 6) break;
    }
    return items;
  }, [recent, pid]);

  const failedRecent = (recent ?? []).filter((g) => g.project_id === pid && g.status === "failed").length;
  const activeGens = bootstrap?.active_generations ?? 0;
  const activeRuns = bootstrap?.active_agent_runs ?? 0;
  const pipeline = derivePipeline(progress, stageFlags.timeline, stageFlags.finalVideo);
  const imagePct = percent(progress.imageReadyCount, progress.shotCount);

  if (!pid) return <div className="workspace-loading">未打开项目</div>;

  return (
    <div className="ws-overview">
      <div className="panel-head">
        <h1>漫剧工作区</h1>
        <span className="muted small">生产控制中心 · 真实 Project State 聚合</span>
        <span className="grow" />
        <Link className="btn secondary compact" to={`/projects/${pid}/source`}>
          <Scroll size={14} /> 源内容工作区
        </Link>
      </div>

      <div className="ws-grid">
        {/* ---- 剧集进度（P2 Episode rows） ---- */}
        <section className="ws-panel ws-panel-episodes" aria-label="剧集进度">
          <h2 className="ws-panel-title">剧集进度</h2>
          {progress.episodes.length === 0 && (
            <div className="ws-empty">
              <p>还没有剧集。</p>
              <Link className="btn secondary compact" to={`/projects/${pid}/script`}>
                <Scroll size={14} /> 去剧本视图创建
              </Link>
            </div>
          )}
          <ul className="ws-episode-list">
            {progress.episodes.map((ep) => (
              <li key={ep.episodeId} className="ws-episode-row">
                <span className="ws-ep-name">
                  EP{String(ep.episodeNumber).padStart(2, "0")} · {ep.title || "未命名"}
                </span>
                <span className="muted small">
                  {ep.sceneCount} 场 · {ep.shotCount} 镜头
                </span>
                <span className="ws-ep-images mono small">
                  图片 {ep.imageReadyCount}/{ep.shotCount}
                </span>
                <span
                  className={`ws-progress ${ep.failedCount > 0 ? "has-failed" : ""}`}
                  aria-label={`出图进度 ${percent(ep.imageReadyCount, ep.shotCount)}%`}
                >
                  <i style={{ width: `${percent(ep.imageReadyCount, ep.shotCount)}%` }} />
                </span>
                <Link
                  className="icon-button ws-ep-open"
                  to={canonicalScriptPath(pid, ep.episodeId)}
                  title="打开该集剧本"
                >
                  <ArrowRight size={14} />
                </Link>
              </li>
            ))}
          </ul>
          <div className="ws-total-line muted small">
            合计：{progress.sceneCount} 场 · {progress.shotCount} 镜头 · 已出图 {progress.imageReadyCount}（{imagePct}
            %）
          </div>
        </section>

        {/* ---- 生产管线（P2 PRODUCTION PIPELINE） ---- */}
        <section className="ws-panel ws-panel-pipeline" aria-label="生产管线">
          <h2 className="ws-panel-title">生产管线</h2>
          <ol className="ws-pipeline">
            {pipeline.map((stage) => (
              <li key={stage.key} className={`ws-stage ${stage.state}`}>
                <span className="ws-stage-icon">
                  {stage.state === "done" ? (
                    <CheckCircle size={15} weight="fill" />
                  ) : stage.state === "running" ? (
                    <Circle size={13} weight="fill" />
                  ) : (
                    <Circle size={13} weight="regular" />
                  )}
                </span>
                <span className="ws-stage-label">{stage.label}</span>
                {stage.detail && <span className="muted tiny mono">{stage.detail}</span>}
                <span className="ws-stage-state">
                  {stage.state === "done" ? "已完成" : stage.state === "running" ? "进行中" : "等待"}
                </span>
              </li>
            ))}
          </ol>
        </section>

        {/* ---- 最近输出（P2 RECENT OUTPUT，缩略图非宣传图） ---- */}
        <section className="ws-panel ws-panel-outputs" aria-label="最近输出">
          <h2 className="ws-panel-title">最近输出</h2>
          {outputs.length === 0 ? (
            <p className="muted small ws-pad">
              还没有生成产出 —— 在分镜板选择镜头并执行「生成图片」，产出会出现在这里。
            </p>
          ) : (
            <ul className="ws-output-grid">
              {outputs.map((o) => (
                <li key={o.assetId} className="ws-output-card">
                  <img
                    loading="lazy"
                    src={`/api/v1/assets/${o.assetId}/thumbnail`}
                    alt={`产出 ${o.assetId.slice(0, 6)}`}
                  />
                  <span className="ws-output-meta">
                    <span className="mono tiny">
                      {o.shotId ? `Shot ${o.shotId.slice(-4).toUpperCase()}` : "项目任务"}
                    </span>
                    <span className="muted tiny ellipsis">
                      {o.provider}
                      {o.model ? ` · ${o.model}` : ""}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ---- 注意力（P2 ATTENTION：风险与待办，带入口） ---- */}
        <section className="ws-panel ws-panel-attention" aria-label="需要关注">
          <h2 className="ws-panel-title">需要关注</h2>
          <ul className="ws-attention-list">
            <li className={failedRecent > 0 ? "attn bad" : "attn"}>
              <Warning size={14} weight={failedRecent > 0 ? "fill" : "regular"} />
              <span>{failedRecent > 0 ? `${failedRecent} 条生成失败` : "暂无失败生成"}</span>
              <Link to={`/projects/${pid}/production-log`} className="text-link">
                生产日志
              </Link>
            </li>
            <li className={activeGens > 0 ? "attn running" : "attn"}>
              <Play size={13} weight={activeGens > 0 ? "fill" : "regular"} />
              <span>{activeGens > 0 ? `${activeGens} 个生成任务进行中` : "生成队列空闲"}</span>
              <span className="muted tiny">底部队列</span>
            </li>
            <li className={activeRuns > 0 ? "attn running" : "attn"}>
              <ListChecks size={14} />
              <span>{activeRuns > 0 ? `${activeRuns} 个 AI 导演任务运行中` : "AI 导演空闲"}</span>
              <span className="muted tiny">右侧面板</span>
            </li>
            <li className="attn">
              <ShieldCheck size={14} />
              <span>连续性检查</span>
              <Link to={`/projects/${pid}/continuity`} className="text-link">
                打开检查页
              </Link>
            </li>
            <li className="attn">
              <Quotes size={14} />
              <span>提示词版本库</span>
              <Link to={`/projects/${pid}/prompts`} className="text-link">
                查看
              </Link>
            </li>
          </ul>
        </section>

        {/* ---- 快捷入口（P2 快捷入口建议） ---- */}
        <section className="ws-panel ws-panel-shortcuts" aria-label="快捷入口">
          <h2 className="ws-panel-title">快捷入口</h2>
          <div className="ws-shortcut-row">
            <Link className="btn secondary compact" to={`/projects/${pid}/script`}>
              <Scroll size={14} /> 剧本 / 生成分镜
            </Link>
            <Link className="btn secondary compact" to={`/projects/${pid}/timeline`}>
              <FilmStrip size={14} /> 时间线装配
            </Link>
            <Link className="btn secondary compact" to={`/projects/${pid}/assets`}>
              <ImageSquare size={14} /> 项目素材库
            </Link>
            <Link className="btn secondary compact" to={`/workflows`}>
              <MagnifyingGlass size={14} /> 工作流目录
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
