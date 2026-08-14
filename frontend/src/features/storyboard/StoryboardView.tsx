import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Shot, Storyboard } from "../../api/types";
import { SHOT_TYPE_LABELS } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useOperationPolling } from "../ai/useOperationPolling";

// Storyboard card grid (frontend-ux §10-11): the most important workspace.
export function StoryboardView({ sceneId }: { sceneId: string }) {
  const queryClient = useQueryClient();
  const selectShot = useSelectionStore((s) => s.selectShot);
  const setActiveShot = useWorkspaceStore((s) => s.setActiveShot);
  const [planOpId, setPlanOpId] = useState<string | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);

  const { data: storyboard, isLoading } = useQuery({
    queryKey: queryKeys.storyboard(sceneId),
    queryFn: () => api.get<Storyboard>(`/scenes/${sceneId}/storyboard`),
  });

  const createShot = useMutation({
    mutationFn: () => api.post<Shot>(`/scenes/${sceneId}/shots`, { shot_type: "medium" }),
    onSuccess: (shot) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
      void queryClient.invalidateQueries({ queryKey: ["scenes"] });
      selectShot(shot.id);
      setActiveShot(shot.id);
    },
  });

  const generateShots = useMutation({
    mutationFn: () => api.post<{ operation_id: string; status: string }>(`/scenes/${sceneId}/generate-shots`),
    onSuccess: (resp) => {
      setPlanOpId(resp.operation_id);
      setPlanError(null);
    },
    onError: (error) => setPlanError(error instanceof Error ? error.message : String(error)),
  });

  useOperationPolling(
    planOpId,
    () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
      void queryClient.invalidateQueries({ queryKey: ["scenes"] });
      setPlanOpId(null);
    },
    (op) => {
      setPlanError(op.error ?? "AI 分镜生成失败");
      setPlanOpId(null);
    },
  );

  const handleSelect = (shotId: string) => {
    selectShot(shotId);
    setActiveShot(shotId);
  };

  return (
    <div className="storyboard">
      <div className="storyboard-head">
        <h2>{storyboard?.scene.name ?? "分镜"} · Scene {storyboard?.scene.scene_number}</h2>
        <div className="row gap">
          <button
            className="btn primary"
            disabled={generateShots.isPending || !!planOpId}
            onClick={() => generateShots.mutate()}
            title="AI 根据场景生成分镜镜头"
          >
            {generateShots.isPending || planOpId ? "AI 生成分镜中…" : "AI 生成分镜"}
          </button>
          <button className="btn" onClick={() => createShot.mutate()} disabled={createShot.isPending}>
            + 镜头
          </button>
        </div>
      </div>

      {planError && <p className="error-text">{planError}</p>}

      {isLoading && <p className="muted">加载中…</p>}

      {!isLoading && (!storyboard || storyboard.shots.length === 0) && (
        <div className="empty-state">
          <p>还没有分镜</p>
          <p className="muted">用 AI 根据场景生成镜头，或手动添加</p>
          <div className="row gap">
            <button className="btn primary" onClick={() => generateShots.mutate()}>
              AI 生成 Storyboard
            </button>
            <button className="btn" onClick={() => createShot.mutate()}>
              手动添加
            </button>
          </div>
        </div>
      )}

      <div className="shot-grid">
        {storyboard?.shots.map((shot) => (
          <button key={shot.id} className="shot-card" onClick={() => handleSelect(shot.id)}>
            <div className="shot-thumb">
              {shot.thumbnail_url ? (
                <img src={shot.thumbnail_url} alt={`Shot ${shot.shot_number}`} />
              ) : (
                <span className="shot-placeholder">No Image</span>
              )}
            </div>
            <div className="shot-meta">
              <span className="shot-number">Shot {String(shot.shot_number).padStart(3, "0")}</span>
              <span className={`badge ${shot.status}`}>{SHOT_TYPE_LABELS[shot.shot_type] ?? shot.shot_type}</span>
            </div>
            <div className="shot-meta small">
              <span className="muted">{shot.duration != null ? `${shot.duration.toFixed(1)}s` : "—"}</span>
              {shot.dirty_state !== "clean" && <span className="badge warn">Dirty</span>}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
