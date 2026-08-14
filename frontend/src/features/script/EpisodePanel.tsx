// Episode AI panel (mvp-spec §58-60, frontend-ux §8-9):
// import novel text → AI analyze preview → user confirms → create Scenes (202 operation).

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Operation, ScenePlan } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { useOperationPolling } from "../ai/useOperationPolling";

export function EpisodePanel({ episode }: { episode: Episode }) {
  const queryClient = useQueryClient();
  const setScene = useSelectionStore((s) => s.setScene);

  const [sourceText, setSourceText] = useState(episode.source_text ?? "");
  const [preview, setPreview] = useState<ScenePlan[] | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [createOpId, setCreateOpId] = useState<string | null>(null);

  const saveSource = useMutation({
    mutationFn: () => api.patch<Episode>(`/episodes/${episode.id}`, { source_text: sourceText }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(episode.project_id) });
    },
  });

  const runPreview = useMutation({
    mutationFn: () => api.post<ScenePlan[]>(`/episodes/${episode.id}/analyze/preview`),
    onSuccess: (plans) => {
      setPreview(plans);
      setPreviewError(null);
    },
    onError: (error) => setPreviewError(error instanceof Error ? error.message : String(error)),
  });

  const createScenes = useMutation({
    mutationFn: () => api.post<{ operation_id: string; status: string }>(`/episodes/${episode.id}/analyze`),
    onSuccess: (resp) => setCreateOpId(resp.operation_id),
  });

  useOperationPolling(
    createOpId,
    (op: Operation) => {
      const ids = (op.result?.created_scene_ids as string[]) ?? [];
      void queryClient.invalidateQueries({ queryKey: queryKeys.scenes(episode.id) });
      if (ids.length > 0) setScene(ids[0]);
      setCreateOpId(null);
    },
    () => setCreateOpId(null),
  );

  const dirty = sourceText !== (episode.source_text ?? "");

  return (
    <div className="episode-panel">
      <h2>EP{String(episode.episode_number).padStart(2, "0")} {episode.title ?? ""} — 剧本</h2>

      <label className="field">
        <span className="field-label">小说 / 剧本原文</span>
        <textarea
          rows={10}
          value={sourceText}
          placeholder="粘贴小说章节（1000-3000 字效果最佳）…"
          onChange={(e) => setSourceText(e.target.value)}
        />
      </label>

      <div className="row gap">
        <button className="btn" disabled={!dirty || saveSource.isPending} onClick={() => saveSource.mutate()}>
          {saveSource.isPending ? "保存中…" : dirty ? "保存剧本" : "已保存"}
        </button>
        <button
          className="btn primary"
          disabled={!sourceText.trim() || runPreview.isPending}
          onClick={() => runPreview.mutate()}
        >
          {runPreview.isPending ? "AI 分析中…" : "AI 分析"}
        </button>
      </div>

      {previewError && <p className="error-text">{previewError}</p>}

      {runPreview.isPending && <p className="muted">正在分析剧情结构…</p>}

      {preview && !runPreview.isPending && (
        <div className="preview-block">
          <h3>AI 分析结果（{preview.length} 个场景）</h3>
          <ul className="preview-list">
            {preview.map((plan) => (
              <li key={plan.scene_number} className="preview-item">
                <strong>SC{String(plan.scene_number).padStart(2, "0")} {plan.title}</strong>
                <span className="muted">
                  {plan.location} · {plan.time ?? "—"} · {plan.mood ?? "—"}
                </span>
                <p className="small">{plan.description}</p>
              </li>
            ))}
          </ul>
          <button className="btn primary" disabled={createScenes.isPending} onClick={() => createScenes.mutate()}>
            {createScenes.isPending || createOpId ? "创建中…" : "创建这些场景"}
          </button>
        </div>
      )}

      {episode.source_text && episode.source_text.length > 0 && (
        <p className="muted small">已保存 {episode.source_text.length} 字。重新分析会重复创建场景（后续版本将支持替换）。</p>
      )}
    </div>
  );
}
