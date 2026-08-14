import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Shot, Storyboard } from "../../api/types";
import { SHOT_TYPE_LABELS } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";

// Storyboard card grid (frontend-ux §10-11): the most important workspace.
export function StoryboardView({ sceneId }: { sceneId: string }) {
  const queryClient = useQueryClient();
  const selectShot = useSelectionStore((s) => s.selectShot);
  const setActiveShot = useWorkspaceStore((s) => s.setActiveShot);

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

  const handleSelect = (shotId: string) => {
    selectShot(shotId);
    setActiveShot(shotId);
  };

  return (
    <div className="storyboard">
      <div className="storyboard-head">
        <h2>{storyboard?.scene.name ?? "分镜"} · Scene {storyboard?.scene.scene_number}</h2>
        <button className="btn" onClick={() => createShot.mutate()} disabled={createShot.isPending}>
          + 镜头
        </button>
      </div>

      {isLoading && <p className="muted">加载中…</p>}

      {!isLoading && (!storyboard || storyboard.shots.length === 0) && (
        <div className="empty-state">
          <p>还没有分镜</p>
          <p className="muted">先手动添加一个镜头（Stage B 将支持 AI 拆分 Scene → Shot）</p>
          <button className="btn primary" onClick={() => createShot.mutate()}>
            添加第一个镜头
          </button>
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
