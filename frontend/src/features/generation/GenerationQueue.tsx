// Generation + Job bottom dock (frontend-ux §65-67, §198; App=P6-T021/022/023/024).
// Two concerns share the dock:
//   - Generation Queue/History (existing): live generation progress + persisted recent.
//   - Jobs (P6-T022/023/024): scene-generation jobs (P5-E1/E2) with detail, per-status
//     controls and recovery flags for interrupted/paused jobs.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowsClockwise,
  CaretDown,
  CaretUp,
  CheckCircle,
  ClockCounterClockwise,
  HourglassMedium,
  ListBullets,
  Pause,
  Play,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import type { GenerationRead, JobRead, JobSummaryRead } from "../../api/types";
import { queryKeys } from "../../api/queryKeys";
import { useGenerationStore } from "../../stores/generationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";

const JOB_STATUS_TEXT: Record<string, string> = {
  queued: "排队中",
  running: "进行中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
const JOB_TYPE_TEXT: Record<string, string> = { scene_generation: "场景生成" };

export function GenerationQueue({ projectId }: { projectId?: string }) {
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

  const { data: jobs } = useQuery({
    queryKey: queryKeys.jobs(projectId ?? ""),
    queryFn: () => api.get<JobSummaryRead[]>(`/projects/${projectId}/jobs`),
    enabled: Boolean(projectId),
    refetchInterval: 5000,
  });

  const retryGeneration = useMutation({
    mutationFn: (generationId: string) => api.post<GenerationRead>(`/generations/${generationId}/retry`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["generations"] }),
  });
  const cancelGeneration = useMutation({
    mutationFn: (generationId: string) => api.post<GenerationRead>(`/generations/${generationId}/cancel`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["generations"] }),
  });

  return (
    <div className="queue-dock">
      <div className="queue-header">
        <div className="queue-tabs">
          <button className={tab === "queue" ? "active" : ""} onClick={() => setTab("queue")}>
            <ListBullets size={16} /> 生成队列 <span>{Object.keys(live).length}</span>
          </button>
          <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
            <ClockCounterClockwise size={16} /> 历史记录
          </button>
          <button className={tab === "jobs" ? "active" : ""} onClick={() => setTab("jobs")} title="场景生成任务队列">
            <ListBullets size={16} /> 任务 <span>{jobs?.length ?? 0}</span>
          </button>
        </div>
        {tab === "jobs" ? <JobSummary jobs={jobs} /> : <GenerationSummary live={live} history={history} />}
        <button
          className="icon-button dock-toggle"
          onClick={() => setExpanded(!expanded)}
          aria-label={expanded ? "收起" : "展开"}
        >
          {expanded ? <CaretDown size={18} /> : <CaretUp size={18} />}
        </button>
      </div>

      <div className="queue-body">
        {tab === "jobs" ? (
          <JobsPanel projectId={projectId} jobs={jobs} expanded={expanded} />
        ) : (
          <>
            {tab === "queue" &&
              Object.keys(live).map((key) => {
                const generation = live[key];
                return (
                  <div key={generation.id} className="queue-item running">
                    <HourglassMedium size={18} className="queue-status-icon" />
                    <div className="queue-primary">
                      <strong>{shotLabel(generation.shotId)}</strong>
                      <span>{generation.stage ?? "图片生成"}</span>
                    </div>
                    <div className="progress-track">
                      <div className="progress-fill" style={{ width: `${generation.progress}%` }} />
                    </div>
                    <span className="queue-percent">{generation.progress}%</span>
                    <button
                      className="icon-button"
                      onClick={() => cancelGeneration.mutate(generation.id)}
                      title="取消任务"
                    >
                      <X size={15} />
                    </button>
                  </div>
                );
              })}

            {(() => {
              const runningIds = new Set(Object.values(live).map((item) => item.id));
              const persisted = (history ?? []).filter((item) => !runningIds.has(item.id));
              const visible =
                tab === "queue"
                  ? persisted.filter((item) => item.status !== "completed")
                  : persisted.filter((item) => item.status === "completed");
              return visible.slice(0, expanded ? 10 : 3).map((generation) => (
                <div key={generation.id} className={`queue-item ${generation.status}`}>
                  {generation.status === "failed" ? (
                    <WarningCircle size={18} className="queue-status-icon" />
                  ) : (
                    <CheckCircle size={18} weight="fill" className="queue-status-icon" />
                  )}
                  <div className="queue-primary">
                    <strong>{shotLabel(generation.shot_id)}</strong>
                    <span>
                      {generation.type} · {generation.provider}
                    </span>
                  </div>
                  <span className={`badge ${generation.status}`}>{generationStatusText(generation.status)}</span>
                  <span className="queue-message" title={generation.error_message ?? undefined}>
                    {generation.error_message || formatTime(generation.completed_at ?? generation.created_at)}
                  </span>
                  {generation.status === "failed" && (
                    <button
                      className="btn secondary compact"
                      onClick={() => retryGeneration.mutate(generation.id)}
                      disabled={retryGeneration.isPending}
                    >
                      <ArrowsClockwise size={14} /> 重试
                    </button>
                  )}
                </div>
              ));
            })()}

            {(() => {
              const runningIds = new Set(Object.values(live).map((item) => item.id));
              const persisted = (history ?? []).filter((item) => !runningIds.has(item.id));
              const hasQueue =
                tab === "queue"
                  ? Object.values(live).length + persisted.filter((item) => item.status !== "completed").length
                  : persisted.filter((item) => item.status === "completed").length;
              if (tab === "queue" && Object.values(live).length === 0 && hasQueue === 0) {
                return (
                  <div className="queue-empty">
                    <CheckCircle size={17} /> 当前没有待处理的生成任务
                  </div>
                );
              }
              if (tab === "history" && persisted.length === 0) {
                return (
                  <div className="queue-empty">
                    <CheckCircle size={17} /> 还没有已完成记录
                  </div>
                );
              }
              return null;
            })()}
          </>
        )}
      </div>
    </div>
  );
}

function GenerationSummary({ live, history }: { live: Record<string, { id: string }>; history?: GenerationRead[] }) {
  const runningIds = new Set(Object.values(live).map((item) => item.id));
  const persisted = (history ?? []).filter((item) => !runningIds.has(item.id));
  const failedCount = persisted.filter((item) => item.status === "failed").length;
  return (
    <div className="queue-summary">
      <span>排队 {Object.values(live).length}</span>
      {failedCount > 0 && <span className="failed-summary">失败 {failedCount}</span>}
    </div>
  );
}

// P6-T024: bottom dock task-count summary for the Jobs tab (running/queued/failed).
function JobSummary({ jobs }: { jobs?: JobSummaryRead[] }) {
  const list = jobs ?? [];
  const byStatus = (s: string) => list.filter((job) => job.status === s).length;
  const runningCount = byStatus("running");
  const queuedCount = byStatus("queued");
  const failedCount = byStatus("failed") + byStatus("interrupted");
  return (
    <div className="queue-summary job-summary">
      {runningCount > 0 && <span>进行中 {runningCount}</span>}
      {queuedCount > 0 && <span>排队 {queuedCount}</span>}
      {failedCount > 0 && <span className="failed-summary">失败 {failedCount}</span>}
    </div>
  );
}

// P6-T022 Job list + P6-T023 controls + P6-T024 recovery marker.
function JobsPanel({ projectId, jobs, expanded }: { projectId?: string; jobs?: JobSummaryRead[]; expanded: boolean }) {
  const list = (jobs ?? []).slice(0, expanded ? 20 : 8);
  if ((jobs ?? []).length === 0) {
    return (
      <div className="queue-empty">
        <CheckCircle size={17} /> 暂无生成任务
      </div>
    );
  }
  return (
    <div className="jobs-list">
      {list.map((job) => (
        <JobRow key={job.id} projectId={projectId} job={job} />
      ))}
    </div>
  );
}

function JobRow({ projectId, job }: { projectId?: string; job: JobSummaryRead }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const detail = useQuery({
    queryKey: queryKeys.job(job.id),
    queryFn: () => api.get<JobRead>(`/jobs/${job.id}`),
    enabled: open,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.jobs(projectId ?? "") });
    void queryClient.invalidateQueries({ queryKey: queryKeys.job(job.id) });
  };
  // P6-T023 per-status control availability.
  const canPause = job.status === "running" || job.status === "queued";
  const canResume = job.status === "paused" || job.status === "interrupted";
  const canCancel = job.status !== "completed" && job.status !== "cancelled";
  const canRetry = job.status === "failed" || job.status === "completed" || job.status === "interrupted";

  const pause = useMutation({ mutationFn: () => api.post<JobRead>(`/jobs/${job.id}/pause`), onSuccess: invalidate });
  const resume = useMutation({ mutationFn: () => api.post<JobRead>(`/jobs/${job.id}/resume`), onSuccess: invalidate });
  const cancel = useMutation({ mutationFn: () => api.post<JobRead>(`/jobs/${job.id}/cancel`), onSuccess: invalidate });
  const retry = useMutation({ mutationFn: () => api.post<JobRead>(`/jobs/${job.id}/retry`), onSuccess: invalidate });

  return (
    <div className={`job-row ${job.status} ${open ? "open" : ""}`}>
      <div
        className="job-head"
        onClick={() => setOpen((o) => !o)}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
      >
        <span className="job-chevron">{open ? <CaretUp size={14} /> : <CaretDown size={14} />}</span>
        <div className="job-title">
          <strong>{job.name || JOB_TYPE_TEXT[job.job_type] || job.job_type}</strong>
          <span>
            {JOB_TYPE_TEXT[job.job_type] ?? job.job_type} · {job.task_count} 任务 · {formatTime(job.created_at)}
          </span>
        </div>
        {isInterrupted(job.status) && (
          <span className="badge warn recovery-badge">
            <WarningCircle size={12} weight="fill" /> 已中断 · 可恢复
          </span>
        )}
        <div className="progress-track job-progress">
          <div className="progress-fill" style={{ width: `${job.progress}%` }} />
        </div>
        <span className="queue-percent">{job.progress}%</span>
        <span className={`badge ${job.status}`}>{JOB_STATUS_TEXT[job.status] ?? job.status}</span>
      </div>

      <div className="job-detail">
        <div className="job-actions-row">
          <JobActions
            canPause={canPause}
            canResume={canResume}
            canCancel={canCancel}
            canRetry={canRetry}
            onPause={() => pause.mutate()}
            onResume={() => resume.mutate()}
            onCancel={() => cancel.mutate()}
            onRetry={() => retry.mutate()}
            pending={pause.isPending || resume.isPending || cancel.isPending || retry.isPending}
          />
          {isRecoverable(job.status) && (
            <span className="recovery-hint">
              <WarningCircle size={14} /> 已中断/暂停 · 可恢复
            </span>
          )}
        </div>
        {open && <JobTasks detail={detail.data} />}
      </div>
    </div>
  );
}

function JobActions({
  canPause,
  canResume,
  canCancel,
  canRetry,
  onPause,
  onResume,
  onCancel,
  onRetry,
  pending,
}: {
  canPause: boolean;
  canResume: boolean;
  canCancel: boolean;
  canRetry: boolean;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  onRetry: () => void;
  pending: boolean;
}) {
  return (
    <div className="job-actions">
      {canPause && (
        <button className="btn secondary compact" onClick={onPause} disabled={pending}>
          <Pause size={14} /> 暂停
        </button>
      )}
      {canResume && (
        <button className="btn primary compact" onClick={onResume} disabled={pending}>
          <Play size={14} weight="fill" /> 恢复
        </button>
      )}
      {canCancel && (
        <button className="btn secondary compact" onClick={onCancel} disabled={pending}>
          <X size={14} /> 取消
        </button>
      )}
      {canRetry && (
        <button className="btn secondary compact" onClick={onRetry} disabled={pending}>
          <ArrowsClockwise size={14} /> 重试失败任务
        </button>
      )}
    </div>
  );
}

function JobTasks({ detail }: { detail?: JobRead }) {
  if (!detail) return <div className="jobs-empty">正在加载任务详情…</div>;
  if (detail.tasks.length === 0) return <div className="jobs-empty">该任务没有子任务</div>;
  return (
    <table className="job-tasks">
      <thead>
        <tr>
          <th>类型</th>
          <th>目标镜头</th>
          <th>状态</th>
          <th>进度</th>
          <th>生成</th>
          <th>错误</th>
        </tr>
      </thead>
      <tbody>
        {detail.tasks.map((task) => (
          <tr key={task.id} className={task.status}>
            <td>{task.task_type === "video" ? "视频" : "图片"}</td>
            <td className="mono">{task.shot_id ? `Shot ${task.shot_id.slice(-4).toUpperCase()}` : "—"}</td>
            <td>
              <span className={`badge ${task.status}`}>{generationStatusText(task.status)}</span>
            </td>
            <td className="task-progress">
              <span className="progress-track">
                <span className="progress-fill" style={{ width: `${task.progress}%` }} />
              </span>
              {task.progress}%
            </td>
            <td className="mono muted">{task.generation_id ? task.generation_id.slice(-8) : "—"}</td>
            <td className="job-error" title={task.error_message ?? undefined}>
              {task.error_message || "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function isInterrupted(status: string): boolean {
  return status === "interrupted";
}
function isRecoverable(status: string): boolean {
  return status === "interrupted" || status === "paused";
}

function shotLabel(shotId: string | null): string {
  return shotId ? `Shot ${shotId.slice(-4).toUpperCase()}` : "Project Task";
}

function generationStatusText(status: string): string {
  return (
    (
      {
        failed: "失败",
        completed: "完成",
        cancelled: "已取消",
        queued: "排队中",
        running: "生成中",
        retrying: "重试中",
        paused: "已暂停",
        interrupted: "已中断",
        skipped: "已跳过",
        dependency_failed: "依赖失败",
      } as Record<string, string>
    )[status] ?? status
  );
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(date);
}
