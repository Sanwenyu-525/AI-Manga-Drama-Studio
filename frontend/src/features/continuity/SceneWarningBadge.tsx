// P8-T020 — Scene Warning badge (frontend-ux §78):
// severity-tiered badge + count on the Storyboard scene view. Clicking expands a
// warning list (message/category/evidence) plus 重新计算 (recompute) and AI 语义检测
// (agent semantic check) actions.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MagicWand, Warning, WarningCircle, Info, ArrowsClockwise } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import type { AgentContinuityRun, ContinuitySceneRead, ContinuityWarning } from "../../api/types";
import { countByTier, sceneSeverityTier, severityTierLabel } from "../../lib/continuity";
import { ContinuityWarningList } from "./ContinuityWarningList";

export function SceneWarningBadge({ sceneId }: { sceneId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [checkNotice, setCheckNotice] = useState<string | null>(null);
  const [checkError, setCheckError] = useState<Error | null>(null);

  const { data: continuity, isLoading } = useQuery({
    queryKey: queryKeys.sceneContinuity(sceneId),
    queryFn: () => api.get<ContinuitySceneRead>(`/scenes/${sceneId}/continuity`),
  });

  // Agent semantic-warning list (separate read; refreshed by check / events).
  const { data: agentWarnings } = useQuery({
    queryKey: queryKeys.continuityWarnings(sceneId),
    queryFn: () => api.get<ContinuityWarning[]>(`/scenes/${sceneId}/continuity-warnings`),
  });

  // Merge rule warnings from the scene read (scene_warnings + per-shot warnings).
  const sceneWarnings: ContinuityWarning[] = [
    ...(continuity?.scene_warnings ?? []),
    ...(continuity?.shots ?? []).flatMap((s) => s.warnings ?? []),
  ];
  const allWarnings = mergeWarnings(sceneWarnings, agentWarnings ?? []);
  const tier = sceneSeverityTier(allWarnings);
  const counts = countByTier(allWarnings);
  const total = allWarnings.length;

  const recompute = useMutation({
    mutationFn: () => api.post(`/scenes/${sceneId}/continuity/recompute`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.sceneContinuity(sceneId) }),
  });

  const check = useMutation({
    mutationFn: () => api.post<AgentContinuityRun>("/agent/continuity/check", { scene_id: sceneId }),
    onSuccess: () => {
      setCheckError(null);
      setCheckNotice("已启动 AI 语义检测，完成后将刷新警告列表（可通过 WS 事件自动刷新）。");
      void qc.invalidateQueries({ queryKey: queryKeys.continuityWarnings(sceneId) });
    },
    onError: (e) => setCheckError(e instanceof Error ? e : new Error(String(e))),
  });

  if (isLoading && !continuity) {
    return <span className="scene-warning-badge muted" aria-busy>…</span>;
  }

  const icon = tier === "error" ? <WarningCircle size={14} weight="fill" /> : tier === "warning" ? <Warning size={14} weight="fill" /> : total > 0 ? <Info size={14} weight="fill" /> : <Info size={14} weight="fill" />;

  return (
    <div className="scene-warning" role="region" aria-label="场景连续性状态">
      <button
        type="button"
        className={"scene-warning-badge " + (tier || "info")}
        disabled={false}
        aria-expanded={open}
        title={tier ? `${severityTierLabel(tier)} ${total} 条连续性警告` : "暂无连续性警告"}
        onClick={() => setOpen((v) => !v)}
      >
        {icon}
        {total > 0 && <span className="scene-warning-count">{total}</span>}
        {tier ? <span className="scene-warning-tier">{severityTierLabel(tier)}</span> : <span className="scene-warning-tier">无警告</span>}
      </button>

      {open && (
        <div className="scene-warning-popover">
          <div className="scene-warning-popover-head">
            <span className="scene-warning-popover-title">场景连续性</span>
            <span className="scene-warning-sev-counts">
              {(["error", "warning", "info"] as const).map((t) => counts[t] > 0 && (<span key={t} className={"sev-count " + t}>{severityTierLabel(t)} {counts[t]}</span>))}
            </span>
          </div>
          <ContinuityWarningList warnings={allWarnings} sceneId={sceneId} />
          {allWarnings.length === 0 && <p className="muted small scene-warning-empty">当前没有连续性警告。</p>}
          <div className="scene-warning-popover-actions">
            <button type="button" className="btn secondary tiny" disabled={recompute.isPending} onClick={() => recompute.mutate()}>
              <ArrowsClockwise size={13} /> {recompute.isPending ? "重算中…" : "重新计算"}
            </button>
            <button type="button" className="btn primary tiny" disabled={check.isPending} onClick={() => check.mutate()}>
              <MagicWand size={13} /> {check.isPending ? "检测中…" : "AI 语义检测"}
            </button>
          </div>
          {checkNotice && <div className="continuity-fix-notice" role="status">{checkNotice}</div>}
          {checkError && <ApiErrorPanel error={checkError} />}
        </div>
      )}
    </div>
  );
}

/** Merge rule + agent warnings, deduped by id; agent (semantic) results win on ties. */
function mergeWarnings(rule: ContinuityWarning[], agent: ContinuityWarning[]): ContinuityWarning[] {
  const seen = new Set<string>();
  const out: ContinuityWarning[] = [];
  for (const w of [...agent, ...rule]) {
    const key = w.id ?? w.message + "|" + (w.category ?? "");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(w);
  }
  return out;
}