// BatchActionBar (autonomous-iteration-02): bulk operations for multi-selected
// shots in the Storyboard. Appears when more than one shot is selected.
// Reuse map: batch generate → single-shot 202 loop with allSettled aggregation
// (409 idempotency gate = "in flight", not failed); batch update/delete → the
// additive scene-scoped batch endpoints; reorder → the existing
// PATCH /scenes/{id}/shots/reorder contract (block move, full-list semantics).

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Play, Trash, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { Shot, ShotBatchResult, ShotSummary } from "../../api/types";
import { SHOT_TYPES, SHOT_TYPE_LABELS } from "../../api/types";
import { useSelectionStore } from "../../stores/selectionStore";
import { generationBatchNotice, submitImageGenerations } from "../generation/batchSubmit";

interface BatchActionBarProps {
  sceneId: string;
  /** Full ordered scene list (storyboard order) — needed for block reorder. */
  shots: ShotSummary[];
  selectedIds: string[];
  onNotice: (text: string) => void;
}

/** Move the selected block one slot up/down within the full ordered list.
 * Returns the new full ordering, or null when the block sits at the edge. */
export function moveBlock(orderedIds: string[], selectedIds: string[], delta: -1 | 1): string[] | null {
  const selectedSet = new Set(selectedIds);
  const block = orderedIds.filter((id) => selectedSet.has(id));
  const rest = orderedIds.filter((id) => !selectedSet.has(id));
  if (!block.length || !rest.length) return null;
  const firstIdx = orderedIds.indexOf(block[0]);
  const posAmongRest = orderedIds
    .slice(0, firstIdx)
    .filter((id) => !selectedSet.has(id)).length;
  const insertAt = delta === -1 ? Math.max(0, posAmongRest - 1) : Math.min(rest.length, posAmongRest + 1);
  if (insertAt === posAmongRest) return null;
  return [...rest.slice(0, insertAt), ...block, ...rest.slice(insertAt)];
}

export function BatchActionBar({ sceneId, shots, selectedIds, onNotice }: BatchActionBarProps) {
  const queryClient = useQueryClient();
  const clearShots = useSelectionStore((s) => s.clearShots);
  const [shotTypeChoice, setShotTypeChoice] = useState("");

  const refreshStoryboard = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.shots(sceneId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
  };

  const generate = useMutation({
    mutationFn: () => {
      const selectedSet = new Set(selectedIds);
      return submitImageGenerations(shots.filter((shot) => selectedSet.has(shot.id)));
    },
    onSuccess: (summary) => {
      onNotice(generationBatchNotice(summary));
      void queryClient.invalidateQueries({ queryKey: queryKeys.storyboard(sceneId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.generations });
    },
  });

  const update = useMutation({
    mutationFn: (patch: { shot_type: string }) =>
      api.post<ShotBatchResult>(`/scenes/${sceneId}/shots/batch-update`, {
        shot_ids: selectedIds,
        patch,
      }),
    onSuccess: (result) => {
      const failed = result.failed ? `，${result.failed} 个失败` : "";
      onNotice(`已更新 ${result.succeeded}/${result.requested} 个镜头${failed}`);
      refreshStoryboard();
    },
    onSettled: () => setShotTypeChoice(""),
  });

  const remove = useMutation({
    mutationFn: () => api.post<ShotBatchResult>(`/scenes/${sceneId}/shots/batch-delete`, { shot_ids: selectedIds }),
    onSuccess: (result) => {
      onNotice(`已删除 ${result.succeeded} 个镜头`);
      clearShots();
      refreshStoryboard();
    },
  });

  const reorder = useMutation({
    mutationFn: (orderedIds: string[]) => api.patch<Shot[]>(`/scenes/${sceneId}/shots/reorder`, orderedIds),
    onSuccess: refreshStoryboard,
  });

  const busy = generate.isPending || update.isPending || remove.isPending || reorder.isPending;
  const error = generate.error ?? update.error ?? remove.error ?? reorder.error;

  const handleMove = (delta: -1 | 1) => {
    const orderedIds = shots.map((shot) => shot.id);
    const next = moveBlock(orderedIds, selectedIds, delta);
    if (!next) {
      onNotice("选中镜头已在一侧边界，无需移动");
      return;
    }
    reorder.mutate(next);
  };

  const handleDelete = () => {
    if (window.confirm(`确认删除选中的 ${selectedIds.length} 个镜头？（软删除，可从数据库恢复）`)) {
      remove.mutate();
    }
  };

  return (
    <div className="batch-bar" role="toolbar" aria-label="批量操作">
      <span className="batch-count">已选 {selectedIds.length} 镜</span>
      <button
        type="button"
        className="btn secondary compact"
        disabled={busy}
        onClick={() => generate.mutate()}
      >
        <Play size={13} weight="fill" /> 批量生成
      </button>
      <label className="batch-type">
        <select
          aria-label="批量改景别"
          value={shotTypeChoice}
          disabled={busy}
          onChange={(event) => {
            const value = event.target.value;
            if (value) update.mutate({ shot_type: value });
          }}
        >
          <option value="" disabled>
            改景别…
          </option>
          {SHOT_TYPES.map((type) => (
            <option key={type} value={type}>
              {SHOT_TYPE_LABELS[type]}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="btn secondary compact" disabled={busy} onClick={() => handleMove(-1)}>
        <ArrowUp size={13} /> 前移
      </button>
      <button type="button" className="btn secondary compact" disabled={busy} onClick={() => handleMove(1)}>
        <ArrowDown size={13} /> 后移
      </button>
      <button type="button" className="btn secondary compact batch-delete" disabled={busy} onClick={handleDelete}>
        <Trash size={13} /> 删除
      </button>
      <button type="button" className="btn secondary compact" onClick={clearShots} aria-label="清除选择">
        <X size={13} /> 清除选择
      </button>
      {error && <ApiErrorPanel error={error} />}
    </div>
  );
}
