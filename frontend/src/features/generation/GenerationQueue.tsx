// Generation Queue (frontend-ux §30-31): live task list in the bottom dock.
// Live progress from the WS store; persisted statuses from the server on demand.

import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useGenerationStore } from "../../stores/generationStore";
import type { GenerationRead } from "../../api/types";

export function GenerationQueue() {
  const live = useGenerationStore((s) => s.live);

  // recent finished generations (server truth) for history rows
  const { data: history } = useQuery({
    queryKey: ["generations", "recent"],
    queryFn: () => api.get<GenerationRead[]>("/generations/recent"),
    refetchInterval: 5000,
  });

  const liveEntries = Object.values(live);
  const finished = (history ?? []).filter((g) => g.status !== "queued" && g.status !== "running");

  return (
    <div className="queue">
      {liveEntries.length === 0 && finished.length === 0 && (
        <span className="muted small">暂无生成任务 —— 选中一个镜头点击「生成图片」开始</span>
      )}

      {liveEntries.map((gen) => (
        <div key={gen.id} className="queue-item">
          <span className="queue-label">
            {gen.shotId ? `Shot ${gen.shotId.slice(-4)}` : "—"} · {gen.stage ?? gen.status}
          </span>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${gen.progress}%` }} />
          </div>
          <span className="queue-percent">{gen.progress}%</span>
        </div>
      ))}

      {finished.slice(0, 4).map((gen) => (
        <div key={gen.id} className={`queue-item done ${gen.status}`}>
          <span className="queue-label">
            {gen.shot_id ? `Shot ${gen.shot_id.slice(-4)}` : "—"} · {gen.type}
          </span>
          <span className={`badge ${gen.status}`}>{gen.status}</span>
          {gen.status === "failed" && gen.error_message && (
            <span className="muted small queue-error" title={gen.error_message}>
              {gen.error_message.slice(0, 60)}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
