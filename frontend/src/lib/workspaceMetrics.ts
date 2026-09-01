// P2 漫剧工作区聚合指标 — 纯函数（可单测，无 DOM / 无请求）。
// 数据全部来自真实 Project State：project tree（episodes→scenes→shots 摘要）
// 与 episodes 列表（source_text 是否已导入）。不假设、不伪造任何进度。

import type { Episode, EpisodeTreeItem, ProjectTreeRead } from "../api/types";

/** 单集制作进度（DESIGN.md P2 Episode 行）。 */
export interface EpisodeProgress {
  episodeId: string;
  episodeNumber: number;
  title: string | null;
  sceneCount: number;
  shotCount: number;
  imageReadyCount: number; // active_image_version 存在 = 已出图
  failedCount: number;
  hasSourceText: boolean;
}

/** 全项目聚合。 */
export interface ProjectProgress {
  episodes: EpisodeProgress[];
  shotCount: number;
  imageReadyCount: number;
  failedCount: number;
  sceneCount: number;
}

/** 生产管线阶段状态（P2 PRODUCTION PIPELINE）。 */
export type StageState = "done" | "running" | "waiting";

export interface PipelineStage {
  key: string;
  label: string;
  state: StageState;
  detail?: string;
}

const isImageReady = (shot: { active_image_version: number | null; status: string }): boolean =>
  shot.active_image_version != null || shot.status === "image_ready" || shot.status === "approved";

/** 从 project tree + episodes 列表聚合每集进度。 */
export function summarizeEpisodes(tree: ProjectTreeRead | undefined, episodes: Episode[] | undefined): ProjectProgress {
  const sourceByText = new Map((episodes ?? []).map((e) => [e.id, Boolean(e.source_text?.trim())]));
  const result: EpisodeProgress[] = (tree?.episodes ?? []).map((ep: EpisodeTreeItem) => {
    const shots = ep.scenes.flatMap((s) => s.shots);
    return {
      episodeId: ep.id,
      episodeNumber: ep.episode_number,
      title: ep.title,
      sceneCount: ep.scenes.length,
      shotCount: shots.length,
      imageReadyCount: shots.filter(isImageReady).length,
      failedCount: shots.filter((s) => s.status === "failed").length,
      hasSourceText: sourceByText.get(ep.id) ?? false,
    };
  });

  return {
    episodes: result,
    sceneCount: result.reduce((n, e) => n + e.sceneCount, 0),
    shotCount: result.reduce((n, e) => n + e.shotCount, 0),
    imageReadyCount: result.reduce((n, e) => n + e.imageReadyCount, 0),
    failedCount: result.reduce((n, e) => n + e.failedCount, 0),
  };
}

/**
 * 由真实数据推导管线阶段（P2 PRODUCTION PIPELINE）。
 * 语义对齐设计：✓=该阶段真实完成（各项独立判断，允许跳步，如直接建分镜的场景）；
 * ●=首个未完成阶段（当前行动点）；其余=等待。全空项目全部等待。
 */
export function derivePipeline(
  progress: ProjectProgress,
  hasTimeline: boolean,
  hasFinalVideo: boolean,
): PipelineStage[] {
  const stages: PipelineStage[] = [
    { key: "source", label: "小说分析", state: "waiting" },
    { key: "scenes", label: "剧本 · 场景", state: "waiting" },
    { key: "shots", label: "分镜", state: "waiting" },
    { key: "image", label: "图片生成", state: "waiting" },
    { key: "timeline", label: "时间线", state: "waiting" },
    { key: "export", label: "导出", state: "waiting" },
  ];
  const started = progress.episodes.length > 0;
  if (!started) return stages;

  const marks: boolean[] = [
    progress.episodes.some((e) => e.hasSourceText),
    progress.sceneCount > 0,
    progress.shotCount > 0,
    progress.imageReadyCount > 0,
    hasTimeline,
    hasFinalVideo,
  ];
  const reached = marks.findIndex((m) => !m); // 首个未完成 = 当前行动点
  return stages.map((stage, i) => ({
    ...stage,
    state: marks[i] ? ("done" as const) : i === reached ? ("running" as const) : ("waiting" as const),
    detail:
      stage.key === "image" && progress.shotCount > 0
        ? `${progress.imageReadyCount}/${progress.shotCount}`
        : stage.key === "scenes" && progress.sceneCount > 0
          ? `${progress.sceneCount} 场`
          : undefined,
  }));
}

/** 百分比（0–100，整数）；分母 0 时返回 0。 */
export function percent(part: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.round((part / total) * 100));
}

/** 当前行动点（首个未完成管线阶段）的 key；全部完成时返回最后阶段。 */
export function primaryStageKey(pipeline: PipelineStage[]): string {
  return (pipeline.find((stage) => stage.state === "running") ?? pipeline[pipeline.length - 1])?.key ?? "source";
}

/** 集级下一步动作（EP 工作卡按钮 + 继续制作跳转依据）。 */
export type EpisodeActionKind = "start" | "produce" | "timeline" | "render" | "review";

export interface EpisodeAction {
  kind: EpisodeActionKind;
  /** 按钮文案：未开始=开始制作；制作中=继续制作；收尾=排片/渲染；完成=查看。 */
  label: string;
}

/** 由单集真实进度推导下一步动作（bootstrap flags 缺省视为未达成，不伪造完成）。 */
export function episodeAction(
  ep: EpisodeProgress,
  flags: { hasTimeline: boolean; hasFinalVideo: boolean } | undefined,
): EpisodeAction {
  if (!ep.hasSourceText || ep.sceneCount === 0) return { kind: "start", label: "开始制作" };
  if (ep.imageReadyCount < ep.shotCount) return { kind: "produce", label: "继续制作" };
  if (!flags?.hasTimeline) return { kind: "timeline", label: "排片装配" };
  if (!flags?.hasFinalVideo) return { kind: "render", label: "渲染导出" };
  return { kind: "review", label: "查看成片" };
}

/**
 * 当前工作集：正在出图的那集优先，其次未开始的一集，
 * 最后是尚未排片/出片的最靠后一集（收尾推进）。全空返回 null。
 */
export function pickCurrentEpisode(
  progress: ProjectProgress,
  bootstrapEpisodes: { id: string; has_timeline: boolean; has_final_video: boolean }[] | undefined,
): EpisodeProgress | null {
  const eps = progress.episodes;
  if (eps.length === 0) return null;
  const inProduction = eps.find((ep) => ep.sceneCount > 0 && ep.imageReadyCount < ep.shotCount);
  if (inProduction) return inProduction;
  const notStarted = eps.find((ep) => !ep.hasSourceText || ep.sceneCount === 0);
  if (notStarted) return notStarted;
  const flagsById = new Map((bootstrapEpisodes ?? []).map((b) => [b.id, b]));
  const pendingExport = [...eps]
    .reverse()
    .find((ep) => {
      const flags = flagsById.get(ep.episodeId);
      return !flags || !flags.has_timeline || !flags.has_final_video;
    });
  return pendingExport ?? eps[0];
}
