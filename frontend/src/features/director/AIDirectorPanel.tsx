// AI Director panel (frontend-ux §14-21, agent-director §79-80): an AI Command Center,
// not a chat bubble. Shows selection context, plan, tool progress, approval-style result.

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, Circle, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { useAgentStore } from "../../stores/agentStore";
import type { AgentRunRead } from "../../api/types";
import { isWaitingHuman } from "../../lib/agentProposals";
import { ProposalReview } from "./ProposalReview";
import { useDirectorContext } from "./useDirectorContext";

const STATUS_LABELS: Record<string, string> = {
  idle: "待命",
  thinking: "理解意图…",
  planning: "制定计划…",
  executing: "执行中…",
  reviewing: "检查结果…",
  cancelling: "取消中…",
  cancelled: "已取消",
  WAITING_HUMAN: "等待审批",
  waiting_human: "等待审批",
  completed: "完成",
  failed: "失败",
};

export function AIDirectorPanel() {
  const context = useDirectorContext();
  const agent = useAgentStore();
  const [input, setInput] = useState("");
  const [submitError, setSubmitError] = useState<Error | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // jsdom (tests) has no scrollTo on elements; guard so the effect is a no-op there.
    if (typeof listRef.current?.scrollTo === "function") {
      listRef.current.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [agent.messages.length, agent.status]);

  const submitRun = useMutation({
    mutationFn: (message: string) =>
      api.post<AgentRunRead>("/agent/director/runs", {
        project_id: context.project_id,
        message,
        selection: context,
      }),
    onSuccess: (run) => {
      agent.startRun(run.id, input);
      setInput("");
      setSubmitError(null);
    },
    onError: (error) => setSubmitError(error instanceof Error ? error : new Error(String(error))),
  });

  const handleSubmit = () => {
    const message = input.trim();
    if (!message || submitRun.isPending) return;
    submitRun.mutate(message);
  };

  const busy = submitRun.isPending || ["thinking", "planning", "executing", "reviewing"].includes(agent.status);
  // P7-T019: true when the run is paused awaiting human approval (either backend casing).
  const waitingHuman = isWaitingHuman(agent.status);

  return (
    <div className="panel-tab-content director-tab">
      <div className="director">
        {/* selection context (frontend-ux §16, §46) */}
        <div className="director-context">
          <span className="muted small">
            当前：{context.scene_id ? `Scene ${context.scene_id.slice(-4)}` : "无场景"} ·{" "}
            {context.shot_ids.length > 0
              ? `${context.shot_ids.length} 个镜头选中`
              : context.asset_ids.length > 0
                ? `${context.asset_ids.length} 个素材选中`
                : "未选中对象"}
          </span>
          <span className={`agent-status ${waitingHuman ? "waiting_human" : agent.status}`}>
            {STATUS_LABELS[waitingHuman ? "WAITING_HUMAN" : agent.status] ?? agent.status}
          </span>
        </div>

        {/* P7-T019/020/021: proposal review (shown while waiting + non-empty list) */}
        {agent.runId && <ProposalReview runId={agent.runId} fallbackStatus={waitingHuman ? "WAITING_HUMAN" : null} />}

        {/* P7-T019: visible hint when the run is paused for human approval */}
        {waitingHuman && (
          <div className="director-waiting-hint" role="status">
            等待审批——请在上方 Proposal 卡片中批准或拒绝，或「继续执行」。
          </div>
        )}

        {/* message + plan stream */}
        <div className="director-stream" ref={listRef}>
          {agent.messages.length === 0 && agent.status === "idle" && (
            <p className="muted small">
              选中一个镜头后对我说，例如：
              <br />
              「改成近景」「重新生成」「改成近景然后重新生成」
            </p>
          )}

          {agent.messages.map((m, i) => (
            <div key={i} className={`director-msg ${m.role}`}>
              {m.content}
            </div>
          ))}

          {agent.objective && (
            <div className="director-plan">
              <div className="plan-title">计划：{agent.objective}</div>
              {agent.tools.map((tool, i) => (
                <div key={i} className={`plan-step ${tool.status}`}>
                  <span className="plan-icon">
                    {tool.status === "done" ? (
                      <Check size={12} weight="bold" />
                    ) : tool.status === "failed" ? (
                      <X size={12} weight="bold" />
                    ) : (
                      <Circle size={12} weight={tool.status === "running" ? "fill" : "regular"} />
                    )}
                  </span>
                  <span className="plan-tool">{tool.tool}</span>
                  {tool.detail && <span className="muted small">{tool.detail}</span>}
                </div>
              ))}
            </div>
          )}

          {submitError && <ApiErrorPanel error={submitError} />}
        </div>

        {/* input (frontend-ux §83) */}
        <div className="director-input">
          <input
            value={input}
            aria-label="发送给 AI Director 的指令"
            placeholder="例如：把这个改成近景然后重新生成"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit();
            }}
            disabled={busy}
          />
          <button className="btn primary" onClick={handleSubmit} disabled={busy || !input.trim()}>
            {busy ? "执行中…" : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
