// P8-T020 — Shared continuity warning list (frontend-ux §79-80, §47):
// severity-coloured rows, expandable evidence, acknowledge + AI-fix actions. Shared by
// the Scene Warning badge popover and the Shot Inspector continuity panel so both views
// present warnings identically.

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CaretDown, CaretRight, MagicWand } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { AgentRunRead, ContinuityWarning } from "../../api/types";
import { categoryLabel, severityTier, severityTierLabel } from "../../lib/continuity";

interface ContinuityWarningListProps {
  warnings: ContinuityWarning[];
  showAcknowledge?: boolean;
  showFix?: boolean;
  onFixed?: () => void;
}

export function ContinuityWarningList({
  warnings,
  showAcknowledge = true,
  showFix = true,
  onFixed,
}: ContinuityWarningListProps) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <div className="continuity-warning-list" role="list" aria-label="连续性警告">
      {warnings.map((w) => (
        <ContinuityWarningRow
          key={w.id ?? w.message}
          warning={w}
          showAcknowledge={showAcknowledge}
          showFix={showFix}
          onFixed={onFixed}
        />
      ))}
    </div>
  );
}

function ContinuityWarningRow({
  warning,
  showAcknowledge,
  showFix,
  onFixed,
}: {
  warning: ContinuityWarning;
  showAcknowledge: boolean;
  showFix: boolean;
  onFixed?: () => void;
}) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [fixNotice, setFixNotice] = useState<string | null>(null);
  const tier = severityTier(warning.severity);
  const acknowledged = warning.status?.toLowerCase() === "acknowledged";

  const acknowledge = useMutation({
    mutationFn: (id: string) => api.post(`/continuity-warnings/${id}/acknowledge`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.prefixes.continuityWarnings });
      void qc.invalidateQueries({ queryKey: queryKeys.prefixes.sceneContinuity });
      void qc.invalidateQueries({ queryKey: queryKeys.prefixes.shotContinuity });
      onFixed?.();
    },
  });

  const fix = useMutation({
    // Contract (backend app/api/agents.py): POST /agent/continuity/fix with the
    // warning id creates a continuity_fix run parked in WAITING_HUMAN — the fix
    // itself is applied only after the user approves the proposal there.
    mutationFn: (warningId: string) =>
      api.post<AgentRunRead>("/agent/continuity/fix", { warning_id: warningId, patch: {} }),
    onSuccess: () => setFixNotice("已提交修复请求，请在导演面板审批。"),
    onError: (error) =>
      setFixNotice(error instanceof Error ? `修复请求失败：${error.message}` : "修复请求失败，请重试。"),
  });

  const evidence =
    typeof warning.evidence === "string" ? warning.evidence : warning.evidence ? trimJson(warning.evidence) : null;
  const openId = warning.id;
  return (
    <div className={"continuity-warning-row " + tier} role="listitem">
      <div className="continuity-warning-row-head">
        <span className={"continuity-warning-sev " + tier} title={severityTierLabel(tier)}>
          {severityTierLabel(tier)}
        </span>
        <span className="continuity-warning-cat">{categoryLabel(warning.category)}</span>
        <span className="continuity-warning-msg">{warning.message}</span>
        <span className="continuity-warning-actions">
          {showAcknowledge && openId && !acknowledged && (
            <button
              type="button"
              className="btn tiny"
              disabled={acknowledge.isPending}
              onClick={() => acknowledge.mutate(openId)}
              title="标记为已读"
            >
              {acknowledge.isPending ? "…" : "标记已读"}
            </button>
          )}
          {acknowledged && <span className="continuity-warning-ack-tag">已读</span>}
          {showFix && openId && (
            <button
              type="button"
              className="btn tiny"
              disabled={fix.isPending}
              onClick={() => fix.mutate(openId)}
              title="交给 AI 修复（需在导演面板审批）"
            >
              <MagicWand size={12} /> {fix.isPending ? "提交中…" : "AI 修复"}
            </button>
          )}
          {evidence && (
            <button
              type="button"
              className="icon-button continuity-warning-expand"
              aria-expanded={expanded}
              aria-label={expanded ? "收起证据" : "展开证据"}
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? <CaretDown size={13} /> : <CaretRight size={13} />}
            </button>
          )}
        </span>
      </div>
      {expanded && evidence && <pre className="continuity-warning-evidence">{evidence}</pre>}
      {fixNotice && (
        <div className="continuity-fix-notice" role="status">
          {fixNotice}
        </div>
      )}
    </div>
  );
}

function trimJson(value: unknown): string {
  try {
    const s = JSON.stringify(value, null, 2);
    return s.length > 600 ? s.slice(0, 600) + "\n…" : s;
  } catch {
    return String(value);
  }
}
