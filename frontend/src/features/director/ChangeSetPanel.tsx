// P2-E3-T03 — ChangeSet panel: lists the change sets a Director run applied,
// renders before→after field diffs (skipping the active-version pseudo field),
// offers per-row undo with 409-aware force restore, batch "撤销全部" with
// per-item results, and a jump-to-shot shortcut that drives the selection store.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowCounterClockwise, Crosshair, WarningCircle } from "@phosphor-icons/react";
import { api, ApiError } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { AgentChangeSet } from "../../api/types";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { useSelectionStore } from "../../stores/selectionStore";
import { changeSetToolLabel, fieldLabel, renderChangeValue, targetTypeLabel } from "../../lib/agentProposals";

interface ChangeSetPanelProps {
  runId: string;
}

/** One before→after diff row of a change set. */
interface ChangeSetDiffRow {
  field: string;
  from: unknown;
  to: unknown;
}

/** Per-item outcome of POST /agent/runs/{runId}/change-sets/undo. */
interface UndoResultEntry {
  change_set_id?: string | null;
  status?: string | null;
}

/** Pseudo field: generate_image change sets record an active-version switch. */
const VERSION_SWITCH_FIELD = "active_image_asset_id";

function normalizeChangeSets(payload: unknown): AgentChangeSet[] {
  if (Array.isArray(payload)) return payload as AgentChangeSet[];
  const record = payload as { items?: unknown; change_sets?: unknown } | null;
  if (record && Array.isArray(record.items)) return record.items as AgentChangeSet[];
  if (record && Array.isArray(record.change_sets)) return record.change_sets as AgentChangeSet[];
  return [];
}

function normalizeUndoResults(payload: unknown): UndoResultEntry[] {
  if (Array.isArray(payload)) return payload as UndoResultEntry[];
  const record = payload as { results?: unknown; items?: unknown } | null;
  if (record && Array.isArray(record.results)) return record.results as UndoResultEntry[];
  if (record && Array.isArray(record.items)) return record.items as UndoResultEntry[];
  return [];
}

function undoResultLabel(status: string | null | undefined): string {
  switch (status) {
    case "undone":
      return "已撤销";
    case "conflict":
      return "冲突";
    case "skipped":
      return "跳过";
    default:
      return status ?? "未知";
  }
}

/** Fields that conflicted with newer Project State, extracted from a 409 body.
 * The backend sends details.fields as {field: {expected, current, before}} — a dict
 * keyed by field; older/mocked shapes may use arrays. Both are handled. */
function conflictFields(details: Record<string, unknown>): string[] {
  const raw = details.conflicting_fields ?? details.conflict_fields ?? details.fields;
  if (Array.isArray(raw)) return raw.map((field) => String(field));
  if (raw && typeof raw === "object") return Object.keys(raw as Record<string, unknown>);
  return [];
}

function changeSetDiff(changeSet: AgentChangeSet): ChangeSetDiffRow[] {
  const before = changeSet.before ?? {};
  const after = changeSet.after ?? {};
  const rows: ChangeSetDiffRow[] = [];
  const fields = new Set([...Object.keys(before), ...Object.keys(after)]);
  for (const field of fields) {
    if (field === VERSION_SWITCH_FIELD) continue; // rendered as the note below
    const from = before[field];
    const to = after[field];
    if (JSON.stringify(from) === JSON.stringify(to)) continue;
    rows.push({ field, from, to });
  }
  return rows;
}

function hasVersionSwitch(changeSet: AgentChangeSet): boolean {
  return (
    (changeSet.before != null && VERSION_SWITCH_FIELD in changeSet.before) ||
    (changeSet.after != null && VERSION_SWITCH_FIELD in changeSet.after)
  );
}

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 4 ? id.slice(-4) : id;
}

export function ChangeSetPanel({ runId }: ChangeSetPanelProps) {
  const qc = useQueryClient();
  const [undoResults, setUndoResults] = useState<UndoResultEntry[] | null>(null);
  const changeSets = useQuery({
    queryKey: queryKeys.changeSetsForRun(runId),
    queryFn: () => api.get<unknown>(`/agent/change-sets?run_id=${runId}`),
    enabled: Boolean(runId),
  });
  const list = normalizeChangeSets(changeSets.data);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.prefixes.changeSets });
    void qc.invalidateQueries({ queryKey: queryKeys.changeSetsForRun(runId) });
    void qc.invalidateQueries({ queryKey: queryKeys.prefixes.storyboard });
    void qc.invalidateQueries({ queryKey: queryKeys.prefixes.shots });
  };

  const undoOne = useMutation({
    mutationFn: ({ id, force }: { id: string; force: boolean }) =>
      api.post(`/agent/change-sets/${id}/undo`, { force }),
    onSuccess: () => {
      setUndoResults(null);
      invalidate();
    },
  });
  const undoAll = useMutation({
    mutationFn: () => api.post<unknown>(`/agent/runs/${runId}/change-sets/undo`),
    onSuccess: (data) => {
      setUndoResults(normalizeUndoResults(data));
      invalidate();
    },
  });

  const onUndo = (id: string, force: boolean) => undoOne.mutate({ id, force });

  const jumpToShot = (shotId: string) => {
    window.dispatchEvent(new CustomEvent("studio:select-shot", { detail: { shotId } }));
    useSelectionStore.getState().selectShot(shotId);
  };

  const scrollToChangeSet = (id: string) => {
    const el = document.getElementById(`change-set-${id}`);
    // jsdom has no scrollIntoView — guard so tests and non-DOM envs stay no-ops.
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  // 变更集为空（且加载无错误）时整块不渲染；加载失败则保留面板以显示错误。
  if (list.length === 0 && !changeSets.isError) return null;
  const hasActive = list.some((cs) => !cs.undone);

  return (
    <div className="change-set-panel">
      <div className="change-set-head">
        <span className="proposal-title">变更记录 ChangeSet</span>
        <button
          type="button"
          className="btn tiny"
          onClick={() => undoAll.mutate()}
          disabled={undoAll.isPending || !hasActive}
          title="按逆序撤销本次运行的全部可撤销变更"
        >
          <ArrowCounterClockwise size={13} /> {undoAll.isPending ? "撤销中…" : "撤销全部"}
        </button>
      </div>
      {changeSets.isError && <ApiErrorPanel error={changeSets.error} className="proposal-error" />}
      {undoAll.isError && <ApiErrorPanel error={undoAll.error} className="proposal-error" />}
      {undoResults && undoResults.length > 0 && (
        <ul className="change-set-undo-results">
          {undoResults.map((result, i) => (
            <li key={result.change_set_id ?? i}>
              <span className="muted">{shortId(result.change_set_id)}</span>
              <span className={`undo-result ${result.status ?? ""}`}>{undoResultLabel(result.status)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="change-set-list">
        {list.map((cs) => {
          const rowFailed = undoOne.isError && undoOne.variables?.id === cs.id && undoOne.variables?.force === false;
          const rowError = rowFailed ? undoOne.error : null;
          return (
            <ChangeSetRow
              key={cs.id}
              changeSet={cs}
              undoPending={undoOne.isPending}
              rowError={rowError}
              onUndo={onUndo}
              onJumpToShot={jumpToShot}
              onScrollToChangeSet={scrollToChangeSet}
            />
          );
        })}
      </div>
    </div>
  );
}

function ChangeSetRow({
  changeSet,
  undoPending,
  rowError,
  onUndo,
  onJumpToShot,
  onScrollToChangeSet,
}: {
  changeSet: AgentChangeSet;
  undoPending: boolean;
  rowError: Error | null;
  onUndo: (id: string, force: boolean) => void;
  onJumpToShot: (shotId: string) => void;
  onScrollToChangeSet: (id: string) => void;
}) {
  const diffRows = changeSetDiff(changeSet);
  const conflict = rowError instanceof ApiError && rowError.status === 409;
  const fields = conflict ? conflictFields(rowError.details) : [];
  return (
    <div className={`change-set-row ${changeSet.undone ? "undone" : ""}`} id={`change-set-${changeSet.id}`}>
      <div className="change-set-row-head">
        <span className="proposal-tool">{changeSetToolLabel(changeSet.tool)}</span>
        <span className="change-set-row-badges">
          {changeSet.undone && <span className="change-set-undone">已撤销</span>}
          {changeSet.undone && changeSet.undone_by_change_set_id && (
            <button
              type="button"
              className="change-set-link"
              onClick={() => onScrollToChangeSet(changeSet.undone_by_change_set_id as string)}
              title="定位补偿此变更的撤销记录"
            >
              补偿变更 {shortId(changeSet.undone_by_change_set_id)}
            </button>
          )}
          {changeSet.entity_type === "shot" && (
            <button
              type="button"
              className="btn tiny"
              onClick={() => onJumpToShot(changeSet.entity_id)}
              title="在检查器中查看该镜头"
            >
              <Crosshair size={12} /> 跳转镜头
            </button>
          )}
          {!changeSet.undone && (
            <button
              type="button"
              className="btn tiny danger"
              onClick={() => onUndo(changeSet.id, false)}
              disabled={undoPending}
            >
              <ArrowCounterClockwise size={12} /> 撤销
            </button>
          )}
        </span>
      </div>
      <div className="change-set-meta">
        <span>
          目标：{targetTypeLabel(changeSet.entity_type)} {shortId(changeSet.entity_id)}
        </span>
        <span>
          版本：v{changeSet.revision_before} → v{changeSet.revision_after}
        </span>
      </div>
      {hasVersionSwitch(changeSet) && <span className="change-set-note">激活版本切换</span>}
      {diffRows.length > 0 && (
        <table className="change-set-diff">
          <thead>
            <tr>
              <th>字段</th>
              <th>变更前</th>
              <th>变更后</th>
            </tr>
          </thead>
          <tbody>
            {diffRows.map((row, i) => (
              <tr key={i}>
                <td>{fieldLabel(row.field)}</td>
                <td className="diff-from">{renderChangeValue(row.from)}</td>
                <td className="diff-to">{renderChangeValue(row.to)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rowError && conflict && (
        <div className="undo-force-row" role="alert">
          <WarningCircle size={13} weight="fill" />
          <span>撤销冲突{fields.length > 0 ? `：${fields.join("、")}` : "，镜头已被后续修改覆盖"}</span>
          <button
            type="button"
            className="btn tiny danger"
            onClick={() => onUndo(changeSet.id, true)}
            disabled={undoPending}
          >
            强制恢复
          </button>
        </div>
      )}
      {rowError && !conflict && <ApiErrorPanel error={rowError} className="proposal-error" />}
    </div>
  );
}
