// C2 一键成片（mvp-spec DOC-C2, api-event-contract §15.1）：episode 级流水线
// run(分析→确认) → confirm(出图) → finalize(排片渲染)。落库断点续跑（resume）。
// 挂载于故事页（EpisodePanel），分析确认复用现有 preview 展示卡（onShowPlans）。
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretRight, Check, FilmStrip, MagicWand, Play, Plus } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Operation, PipelineRead, PipelineRunRead, ScenePlan } from "../../api/types";
import { useOperationPolling } from "../ai/useOperationPolling";

const STAGE_LABELS: Record<string, string> = {
  analyze: "分析",
  shots: "分镜",
  images: "出图",
  timeline: "排片",
  render: "渲染",
};

interface PipelineBarProps {
  episode: Episode;
  onShowPlans: (plans: ScenePlan[], snapshotId: string | null) => void;
}

export function PipelineBar({ episode, onShowPlans }: PipelineBarProps) {
  const queryClient = useQueryClient();
  const [opId, setOpId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: pipeline } = useQuery({
    queryKey: queryKeys.pipeline(episode.id),
    queryFn: () => api.get<PipelineRead | null>(`/episodes/${episode.id}/pipeline/latest`),
    enabled: Boolean(episode.id),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(episode.id) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.generations });
    void queryClient.invalidateQueries({ queryKey: queryKeys.timeline(episode.id) });
  };

  // 202 + operation：run / confirm / resume 是异步长任务，完成后再读 latest。
  useOperationPolling(
    opId,
    (operation: Operation) => {
      const result = operation.result as PipelineRunRead | null | undefined;
      if (result?.pipeline.status === "waiting_confirm" && result.plans) {
        onShowPlans(result.plans, result.pipeline.snapshot_id ?? null);
        setNotice("分析完成，请确认场景计划后继续生产。");
      } else if (result?.pipeline.status === "running") {
        const n = result.pending_shot_ids?.length ?? 0;
        setNotice(n > 0 ? `已提交 ${n} 张图片生成，完成后可排片渲染。` : "流水线继续推进中…");
      }
      setOpId(null);
      invalidate();
    },
    (operation: Operation) => {
      setError(operation.error ?? "一键成片失败");
      setOpId(null);
      invalidate();
    },
  );

  const runMutation = useMutation({
    mutationFn: () => api.post<{ operation_id: string }>(`/episodes/${episode.id}/pipeline/run`),
    onSuccess: (r) => {
      setError(null);
      setNotice("AI 正在分析原文…");
      setOpId(r.operation_id);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "启动失败"),
  });

  const confirmMutation = useMutation({
    mutationFn: () => api.post<{ operation_id: string }>(`/episodes/${episode.id}/pipeline/${pipeline?.id}/confirm`),
    onSuccess: (r) => {
      setError(null);
      setNotice("正在生成分镜与图片…");
      setOpId(r.operation_id);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "确认失败"),
  });

  const finalizeMutation = useMutation({
    mutationFn: () =>
      api.post<PipelineRunRead>(`/episodes/${episode.id}/pipeline/${pipeline?.id}/finalize`),
    onSuccess: () => {
      setNotice("成片完成：已排片并提交渲染。");
      invalidate();
    },
    onError: (e) => setError(e instanceof Error ? e.message : "排片渲染失败"),
  });

  const resumeMutation = useMutation({
    mutationFn: () => api.post<{ operation_id: string }>(`/episodes/${episode.id}/pipeline/${pipeline?.id}/resume`),
    onSuccess: (r) => {
      setError(null);
      setNotice("正在从断点恢复…");
      setOpId(r.operation_id);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "恢复失败"),
  });

  const busy = runMutation.isPending || confirmMutation.isPending || finalizeMutation.isPending || resumeMutation.isPending || Boolean(opId);
  const status = pipeline?.status ?? "idle";

  return (
    <div className={`pipeline-bar pipeline-${status}`}>
      <div className="pipeline-title">
        <FilmStrip size={15} />
        <strong>一键成片</strong>
        <span className="pipeline-status-text">{statusText(status, pipeline)}</span>
      </div>

      <div className="pipeline-stages">
        {Object.entries(STAGE_LABELS).map(([stage, label]) => {
          const done = pipeline?.stages?.[stage] === "done";
          const active = pipeline?.current_stage === stage;
          return (
            <span key={stage} className={`pipeline-stage ${done ? "done" : ""} ${active ? "active" : ""}`}>
              {done ? <Check size={11} /> : <CaretRight size={11} />}
              {label}
            </span>
          );
        })}
      </div>

      <div className="pipeline-actions">
        {(status === "idle" || status === "completed") && (
          <button className="btn primary compact" disabled={busy} onClick={() => runMutation.mutate()} title="分析 → 确认 → 出图 → 排片 → 渲染">
            <MagicWand size={13} /> {busy ? "处理中…" : "一键成片"}
          </button>
        )}
        {status === "waiting_confirm" && (
          <button className="btn primary compact" disabled={busy} onClick={() => confirmMutation.mutate()}>
            <Play size={13} weight="fill" /> {busy ? "处理中…" : "确认计划并出图"}
          </button>
        )}
        {status === "running" && pipeline?.current_stage === "images" && (
          <button className="btn secondary compact" disabled={busy} onClick={() => finalizeMutation.mutate()}>
            <Plus size={13} /> {busy ? "处理中…" : "排片并渲染"}
          </button>
        )}
        {status === "failed" && (
          <button className="btn secondary compact" disabled={busy} onClick={() => resumeMutation.mutate()}>
            <Play size={13} weight="fill" /> {busy ? "处理中…" : "从断点恢复"}
          </button>
        )}
      </div>

      {notice && !error && <span className="pipeline-notice">{notice}</span>}
      {error && <span className="error-text pipeline-error">{error}</span>}
    </div>
  );
}

function statusText(status: string, pipeline?: PipelineRead | null): string {
  switch (status) {
    case "waiting_confirm":
      return "等待确认分析结果";
    case "running":
      return pipeline?.current_stage ? `正在${STAGE_LABELS[pipeline.current_stage] ?? pipeline.current_stage}` : "运行中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败（可恢复）";
    default:
      return "未开始";
  }
}
