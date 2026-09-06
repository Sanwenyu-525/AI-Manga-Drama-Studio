// P2-E2-T01 回收站：审阅软删除的剧集/场景/镜头/角色并逐行恢复。
// 恢复冲突（父级已删/编号被占）走 409 + ApiErrorPanel 可操作提示，不覆盖现存行。
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowCounterClockwise, Trash } from "@phosphor-icons/react";
import { ApiError, api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { TrashEntityType, TrashItem } from "../../api/types";

const entityLabel: Record<TrashEntityType, string> = {
  episode: "剧集",
  scene: "场景",
  shot: "镜头",
  character: "角色",
};

const restorePath: Record<TrashEntityType, (id: string) => string> = {
  episode: (id) => `/episodes/${id}/restore`,
  scene: (id) => `/scenes/${id}/restore`,
  shot: (id) => `/shots/${id}/restore`,
  character: (id) => `/characters/${id}/restore`,
};

function invalidateAfterRestore(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
  entityType: TrashEntityType,
) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.trash(projectId) });
  void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.trash });
  if (entityType === "shot") {
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard });
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.shots });
  } else if (entityType === "scene") {
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard });
  } else if (entityType === "episode") {
    void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.scenes });
    void queryClient.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard });
  } else {
    void queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) });
  }
}

export function TrashPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<Error | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: queryKeys.trash(projectId),
    queryFn: () => api.get<TrashItem[]>(`/projects/${projectId}/trash`),
  });

  const restore = useMutation({
    mutationFn: (item: TrashItem) => api.post(restorePath[item.entity_type](item.id)),
    onMutate: (item) => {
      setRestoringId(item.id);
      setError(null);
    },
    onSuccess: (_data, item) => {
      setRestoringId(null);
      invalidateAfterRestore(queryClient, projectId, item.entity_type);
    },
    onError: (err) => {
      setRestoringId(null);
      setError(err instanceof Error ? err : new Error(String(err)));
    },
  });

  if (isLoading) return <p className="muted small">正在读取回收站…</p>;
  if (!items?.length) return null;

  return (
    <section className="trash-panel" aria-label="回收站">
      <div className="section-kicker">
        <Trash size={14} /> 回收站 · {items.length} 项
      </div>
      <p className="muted small">删除的内容保留在此，可逐项恢复；编号被占用或父级已删时会明确提示，不覆盖现存内容。</p>
      {error && <ApiErrorPanel error={error} />}
      <ul className="trash-list">
        {items.map((item) => (
          <li key={`${item.entity_type}:${item.id}`} className="trash-row">
            <span className="trash-badge">{entityLabel[item.entity_type]}</span>
            <span className="trash-name">{item.name}</span>
            <button
              type="button"
              className="btn secondary compact"
              disabled={restoringId === item.id}
              title={`恢复${entityLabel[item.entity_type]}「${item.name}」`}
              onClick={() => restore.mutate(item)}
            >
              <ArrowCounterClockwise size={13} />
              {restoringId === item.id ? "恢复中…" : "恢复"}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** 409 冲突信息的人话提炼（ApiErrorPanel 之外，行内无需重复展示）。 */
export function isRestoreConflict(error: unknown): error is ApiError {
  return error instanceof ApiError && error.code === "CONFLICT";
}
