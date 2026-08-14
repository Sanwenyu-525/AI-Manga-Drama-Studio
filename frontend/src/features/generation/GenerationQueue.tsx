import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowsClockwise, CaretDown, CaretUp, CheckCircle, ClockCounterClockwise, HourglassMedium, ListBullets, WarningCircle, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import type { GenerationRead } from "../../api/types";
import { useGenerationStore } from "../../stores/generationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";

export function GenerationQueue() {
  const live = useGenerationStore((state) => state.live);
  const tab = useWorkspaceStore((state) => state.bottomDockTab);
  const setTab = useWorkspaceStore((state) => state.setBottomDockTab);
  const expanded = useWorkspaceStore((state) => state.bottomDockExpanded);
  const setExpanded = useWorkspaceStore((state) => state.setBottomDockExpanded);
  const queryClient = useQueryClient();

  const { data: history } = useQuery({
    queryKey: ["generations", "recent"],
    queryFn: () => api.get<GenerationRead[]>("/generations/recent"),
    refetchInterval: 5000,
  });

  const retry = useMutation({
    mutationFn: (generationId: string) => api.post<GenerationRead>(`/generations/${generationId}/retry`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["generations"] }),
  });
  const cancel = useMutation({
    mutationFn: (generationId: string) => api.post<GenerationRead>(`/generations/${generationId}/cancel`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["generations"] }),
  });

  const liveEntries = Object.values(live);
  const runningIds = new Set(liveEntries.map((item) => item.id));
  const persisted = (history ?? []).filter((item) => !runningIds.has(item.id));
  const failedCount = persisted.filter((item) => item.status === "failed").length;
  const visible = tab === "queue" ? persisted.filter((item) => item.status !== "completed") : persisted.filter((item) => item.status === "completed");

  return (
    <div className="queue-dock">
      <div className="queue-header">
        <div className="queue-tabs">
          <button className={tab === "queue" ? "active" : ""} onClick={() => setTab("queue")}><ListBullets size={16} /> 生成队列 <span>{liveEntries.length}</span></button>
          <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}><ClockCounterClockwise size={16} /> 历史记录</button>
        </div>
        <div className="queue-summary"><span>排队 {liveEntries.length}</span>{failedCount > 0 && <span className="failed-summary">失败 {failedCount}</span>}</div>
        <button className="icon-button dock-toggle" onClick={() => setExpanded(!expanded)} aria-label={expanded ? "收起生成队列" : "展开生成队列"}>
          {expanded ? <CaretDown size={18} /> : <CaretUp size={18} />}
        </button>
      </div>

      <div className="queue-body">
        {tab === "queue" && liveEntries.map((generation) => (
          <div key={generation.id} className="queue-item running">
            <HourglassMedium size={18} className="queue-status-icon" />
            <div className="queue-primary"><strong>{shotLabel(generation.shotId)}</strong><span>{generation.stage ?? "图片生成"}</span></div>
            <div className="progress-track"><div className="progress-fill" style={{ width: `${generation.progress}%` }} /></div>
            <span className="queue-percent">{generation.progress}%</span>
            <button className="icon-button" onClick={() => cancel.mutate(generation.id)} title="取消任务"><X size={15} /></button>
          </div>
        ))}

        {visible.slice(0, expanded ? 10 : 3).map((generation) => (
          <div key={generation.id} className={`queue-item ${generation.status}`}>
            {generation.status === "failed" ? <WarningCircle size={18} className="queue-status-icon" /> : <CheckCircle size={18} weight="fill" className="queue-status-icon" />}
            <div className="queue-primary"><strong>{shotLabel(generation.shot_id)}</strong><span>{generation.type} · {generation.provider}</span></div>
            <span className={`badge ${generation.status}`}>{statusText(generation.status)}</span>
            <span className="queue-message" title={generation.error_message ?? undefined}>{generation.error_message || formatTime(generation.completed_at ?? generation.created_at)}</span>
            {generation.status === "failed" && <button className="btn secondary compact" onClick={() => retry.mutate(generation.id)} disabled={retry.isPending}><ArrowsClockwise size={14} /> 重试</button>}
          </div>
        ))}

        {liveEntries.length === 0 && visible.length === 0 && (
          <div className="queue-empty"><CheckCircle size={17} /> {tab === "queue" ? "当前没有待处理的生成任务" : "还没有已完成记录"}</div>
        )}
      </div>
    </div>
  );
}

function shotLabel(shotId: string | null): string {
  return shotId ? `Shot ${shotId.slice(-4).toUpperCase()}` : "Project Task";
}

function statusText(status: string): string {
  return ({ failed: "失败", completed: "完成", cancelled: "已取消", queued: "排队中", running: "生成中", retrying: "重试中" } as Record<string, string>)[status] ?? status;
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(date);
}
