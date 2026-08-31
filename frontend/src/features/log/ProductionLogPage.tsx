// 生产日志（P11 lightweight page）：全量生成任务时间线（真实数据 = GET
// /generations/recent 按项目过滤 + generation store 实时状态合并）。
// 状态语言遵循 DESIGN.md §7：等待/排队中/运行中/已完成/失败。

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ListChecks } from "@phosphor-icons/react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { GenerationRead } from "../../api/types";
import { useGenerationStore } from "../../stores/generationStore";

const STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

type StatusFilter = "all" | "running" | "completed" | "failed";

export function ProductionLogPage({ projectId }: { projectId?: string }) {
  const params = useParams();
  const pid = projectId ?? params.projectId ?? "";
  const [filter, setFilter] = useState<StatusFilter>("all");

  const {
    data: generations,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: [...queryKeys.prefixes.generations, "recent"],
    queryFn: () => api.get<GenerationRead[]>("/generations/recent"),
    refetchInterval: 15_000,
    enabled: Boolean(pid),
  });

  const live = useGenerationStore((state) => state.live);

  const rows = useMemo(() => {
    const list: GenerationRead[] = [];
    for (const g of generations ?? []) {
      if (g.project_id !== pid) continue;
      const running = live[g.id];
      list.push(running ? { ...g, status: running.status, progress: running.progress, stage: running.stage } : g);
    }
    return list.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [generations, live, pid]);

  const counts = useMemo(() => {
    let completed = 0;
    let failed = 0;
    for (const row of rows) {
      if (row.status === "completed") completed += 1;
      else if (row.status === "failed") failed += 1;
    }
    return { completed, failed, running: rows.length - completed - failed };
  }, [rows]);

  const filtered = rows.filter((row) => {
    if (filter === "all") return true;
    if (filter === "completed") return row.status === "completed";
    if (filter === "failed") return row.status === "failed" || row.status === "cancelled";
    return row.status !== "completed" && row.status !== "failed" && row.status !== "cancelled";
  });

  if (!pid) return <div className="workspace-loading">未打开项目</div>;

  return (
    <div className="log-page">
      <div className="panel-head">
        <h1>生产日志</h1>
        <span className="muted small">
          共 {rows.length} 条 · 已完成 {counts.completed} · 运行中/排队 {Math.max(counts.running, 0)} · 失败{" "}
          {counts.failed}
        </span>
        <div className="segmented-control" role="tablist" aria-label="日志筛选">
          {(
            [
              ["all", "全部"],
              ["running", "运行中"],
              ["completed", "已完成"],
              ["failed", "失败"],
            ] as [StatusFilter, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={filter === key}
              className={filter === key ? "active" : ""}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <div className="workspace-loading">正在读取生成记录…</div>}
      {isError && <ApiErrorPanel error={error as never} />}

      {!isLoading && !isError && filtered.length === 0 && (
        <div className="empty-state">
          <ListChecks size={32} />
          <h2>{rows.length === 0 ? "还没有生成任务" : "该筛选条件下暂无记录"}</h2>
          <p>
            {rows.length === 0
              ? "在分镜视图选择镜头并生成图片后，这里会出现完整的生产事件流。"
              : "切换筛选条件查看其他状态的任务。"}
          </p>
        </div>
      )}

      <ul className="log-list">
        {filtered.map((row) => (
          <li key={row.id} className={`log-row status-${row.status}`}>
            <span className="mono small log-time">{formatDate(row.created_at)}</span>
            <span className={`badge ${statusClass(row.status)}`}>{STATUS_LABELS[row.status] ?? row.status}</span>
            <span className="log-type">{typeLabel(row.type)}</span>
            <span className="muted small mono">{row.model ?? row.provider}</span>
            {row.shot_id && <span className="muted small mono">Shot {row.shot_id.slice(-4).toUpperCase()}</span>}
            <span className="grow ellipsis muted small log-error" title={row.error_message ?? undefined}>
              {row.error_message ?? ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function statusClass(status: string): string {
  switch (status) {
    case "completed":
      return "ok";
    case "failed":
      return "bad";
    case "queued":
      return "neutral";
    default:
      return "info";
  }
}

function typeLabel(type: string): string {
  if (type === "image") return "图片生成";
  if (type === "video") return "视频生成";
  if (type === "render") return "成片渲染";
  return type;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}
