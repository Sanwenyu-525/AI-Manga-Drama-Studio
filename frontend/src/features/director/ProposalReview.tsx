// P7-T019/020/021 — Proposal Review (frontend-ux §71-76):
// lists Director proposals awaiting/after human review, renders field from→to diffs,
// approve/reject actions, conflict notice + refresh, and a resume (继续执行) button
// once a WAITING_HUMAN run has no proposals left pending.
// P2-E3-T02: cards also surface risk metadata (risk_level / reason / estimated
// tasks / cost / deadline) and generate_image proposals explain the follow-up
// generation task instead of a field diff.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X, ArrowsClockwise, Play, WarningCircle } from "@phosphor-icons/react";
import { queryKeys } from "../../api/queryKeys";
import { api } from "../../api/client";
import type { AgentProposal, AgentRunRead } from "../../api/types";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { useAgentStore } from "../../stores/agentStore";
import {
  isWaitingHuman,
  normalizeProposalChanges,
  proposalStatusLabel,
  proposalTarget,
  proposalToolLabel,
  renderChangeValue,
  targetTypeLabel,
  fieldLabel,
  riskLevelLabel,
  formatDeadline,
} from "../../lib/agentProposals";

interface ProposalReviewProps {
  runId: string;
  fallbackStatus?: string | null;
}

export function ProposalReview({ runId, fallbackStatus }: ProposalReviewProps) {
  const qc = useQueryClient();
  const runDetail = useQuery({
    queryKey: queryKeys.agentRun(runId),
    queryFn: () => api.get<AgentRunRead>(`/agent/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: 4000,
  });
  const proposals = useQuery({
    queryKey: queryKeys.proposals(runId),
    queryFn: () => api.get<AgentProposal[]>(`/agent/runs/${runId}/proposals`),
    enabled: Boolean(runId),
  });
  const status = (runDetail.data?.status ?? fallbackStatus ?? null) as string | null;
  const waiting = isWaitingHuman(status);
  const runPendingProposals = runDetail.data?.pending_proposals ?? undefined;
  const list = proposals.data ?? runPendingProposals ?? [];
  // Avoid flashing "暂无提案" while the dedicated proposals query is still loading.
  const stillLoading = proposals.isLoading || (proposals.data === undefined && runDetail.data === undefined);
  const pending = list.filter((p) => p.status === "pending");
  const hasConflict = list.some((p) => p.status === "conflict");
  const canResume = waiting && pending.length === 0 && list.length > 0;
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.agentRun(runId) });
    void qc.invalidateQueries({ queryKey: queryKeys.proposals(runId) });
  };
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) =>
      api.post(`/agent/proposals/${id}/${decision === "approve" ? "approve" : "reject"}`),
    onSuccess: () => invalidate(),
  });
  const resume = useMutation({
    mutationFn: () => api.post(`/agent/runs/${runId}/resume`, { decision: "approve" }),
    onSuccess: () => {
      const agent = useAgentStore.getState();
      agent.resumeRun();
      invalidate();
    },
  });
  const refresh = () => {
    invalidate();
    void proposals.refetch();
    void runDetail.refetch();
  };
  if (!waiting && list.length === 0) return null;
  return (
    <div className="proposal-review">
      <div className="proposal-review-head">
        <span className="proposal-title">待审批 Proposal</span>
        <button
          type="button"
          className="btn tiny"
          onClick={refresh}
          disabled={Boolean(proposals.isFetching)}
          title="重新拉取 Proposal 与镜头当前值"
        >
          <ArrowsClockwise size={13} /> 刷新
        </button>
      </div>
      {proposals.isError && <ApiErrorPanel error={proposals.error} className="proposal-error" />}
      {runDetail.isError && <ApiErrorPanel error={runDetail.error} className="proposal-error" />}
      {hasConflict && (
        <div className="proposal-conflict" role="alert">
          <WarningCircle size={15} weight="fill" />
          <span>Shot 已被修改，proposal 冲突，无法直接应用。请刷新查看镜头当前值。</span>
        </div>
      )}
      {list.length === 0 ? (
        <p className="muted small proposal-empty">{stillLoading ? "加载中…" : "暂无提案"}</p>
      ) : (
        <div className="proposal-list">
          {list.map((p) => (
            <ProposalCard
              key={p.id}
              proposal={p}
              deciding={decide.isPending}
              onDecide={(d) => decide.mutate({ id: p.id, decision: d })}
            />
          ))}
        </div>
      )}
      {canResume && (
        <button
          type="button"
          className="btn primary resume-btn"
          onClick={() => resume.mutate()}
          disabled={resume.isPending}
        >
          <Play size={14} weight="fill" /> {resume.isPending ? "继续中…" : "继续执行"}
        </button>
      )}
      {resume.isError && <ApiErrorPanel error={resume.error} className="proposal-error" />}
      {/* P2-E3-T02: approve/reject rejected with 409 (proposal expired / base_revision conflict) */}
      {decide.isError && <ApiErrorPanel error={decide.error} className="proposal-error" />}
    </div>
  );
}

function ProposalCard({
  proposal,
  deciding,
  onDecide,
}: {
  proposal: AgentProposal;
  deciding: boolean;
  onDecide: (decision: "approve" | "reject") => void;
}) {
  const diffs = normalizeProposalChanges(proposal.changes);
  const resolved = proposal.status === "approved" || proposal.status === "rejected";
  const conflicted = proposal.status === "conflict";
  // P2-E3-T02: expired proposals are rejected by the backend with 409 — no actions.
  const expired = proposal.status === "expired";
  // P2-E3-T02: generate_image proposals create a generation task rather than a
  // field patch — explain the follow-up instead of rendering a (possibly empty) diff.
  const isGenerateImage = proposal.tool === "generate_image";
  const riskClass = `r${(proposal.risk_level ?? "").toLowerCase()}`;
  return (
    <div className={`proposal-card ${proposal.status}`}>
      <div className="proposal-card-head">
        <span className="proposal-tool">{proposalToolLabel(proposal.tool)}</span>
        <span className="proposal-card-badges">
          {proposal.risk_level != null && (
            <span className={`risk-badge ${riskClass}`}>{riskLevelLabel(proposal.risk_level)}</span>
          )}
          {proposal.irreversible && <span className="risk-badge r3">不可逆</span>}
          <span className={`proposal-status ${proposal.status}`}>{proposalStatusLabel(proposal.status)}</span>
        </span>
      </div>
      <div className="proposal-meta">
        <span>目标：{proposalTarget(proposal)}</span>
        <span>类型：{targetTypeLabel(proposal.target_type)}</span>
        {proposal.base_revision != null && <span>基准版本：v{proposal.base_revision}</span>}
        {proposal.estimated_tasks != null && <span>预计任务：{proposal.estimated_tasks}</span>}
        <span>费用：{proposal.estimated_cost == null ? "未知" : proposal.estimated_cost}</span>
        {proposal.expires_at && <span>截止：{formatDeadline(proposal.expires_at)}</span>}
      </div>
      {proposal.reason && <p className="proposal-reason">{proposal.reason}</p>}
      {conflicted && (
        <div className="proposal-card-conflict" role="alert">
          <WarningCircle size={13} weight="fill" /> 此提案基于旧版本，与当前镜头不一致
        </div>
      )}
      {isGenerateImage ? (
        <p className="proposal-generate-note">
          <WarningCircle size={13} weight="fill" /> 将创建图片生成任务
        </p>
      ) : (
        diffs.length > 0 && (
          <table className="proposal-diff">
            <thead>
              <tr>
                <th>字段</th>
                <th>当前</th>
                <th>提案</th>
              </tr>
            </thead>
            <tbody>
              {diffs.map((d, i) => (
                <tr key={i}>
                  <td>{fieldLabel(d.field)}</td>
                  <td className="diff-from">{renderChangeValue(d.from)}</td>
                  <td className="diff-to">{renderChangeValue(d.to)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
      {!resolved && !conflicted && !expired && (
        <div className="proposal-actions">
          <button type="button" className="btn tiny success" disabled={deciding} onClick={() => onDecide("approve")}>
            <Check size={13} weight="bold" /> 批准
          </button>
          <button type="button" className="btn tiny danger" disabled={deciding} onClick={() => onDecide("reject")}>
            <X size={13} weight="bold" /> 拒绝
          </button>
        </div>
      )}
    </div>
  );
}
