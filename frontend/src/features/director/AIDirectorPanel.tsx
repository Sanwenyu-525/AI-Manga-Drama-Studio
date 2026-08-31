// AI Director panel (frontend-ux §14-21, agent-director §79-80): an AI Command Center,
// not a chat bubble. Shows selection context, plan, tool progress, approval-style result.

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Circle, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { useAgentStore } from "../../stores/agentStore";
import { useSelectionStore } from "../../stores/selectionStore";
import type { AgentRunRead, Shot } from "../../api/types";
import { queryKeys } from "../../api/queryKeys";
import { isWaitingHuman } from "../../lib/agentProposals";
import { ProposalReview } from "./ProposalReview";
import { ChangeSetPanel } from "./ChangeSetPanel";
import { useDirectorContext } from "./useDirectorContext";

function compactId(value: string): string {
  return value.length > 8 ? value.slice(-4).toUpperCase() : value.toUpperCase();
}

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
  const selectedShotId = context.shot_ids[0];
  const hasShotSelection = Boolean(selectedShotId);
  const { data: shot } = useQuery({
    queryKey: selectedShotId ? queryKeys.shot(selectedShotId) : ["shot", "none"],
    queryFn: () => api.get<Shot>(`/shots/${selectedShotId}`),
    enabled: hasShotSelection,
  });

  useEffect(() => {
    // jsdom (tests) has no scrollTo on elements; guard so the effect is a no-op there.
    if (typeof listRef.current?.scrollTo === "function") {
      listRef.current.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [agent.messages.length, agent.status]);

  // P2-E3-T03: jump-to-shot requests (e.g. ChangeSetPanel rows) drive the shared
  // selection store so the ShotInspector context follows the referenced shot.
  useEffect(() => {
    const onSelectShot = (event: Event) => {
      const shotId = (event as CustomEvent<{ shotId?: string }>).detail?.shotId;
      if (shotId) useSelectionStore.getState().selectShot(shotId);
    };
    window.addEventListener("studio:select-shot", onSelectShot);
    return () => window.removeEventListener("studio:select-shot", onSelectShot);
  }, []);

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
  const shotLabel = shot
    ? `SH${String(shot.shot_number).padStart(2, "0")}`
    : selectedShotId
      ? `SH${selectedShotId.slice(-4).toUpperCase()}`
      : "未选择镜头";

  // EP/SC numbers share the ProjectContextBar cache keys → no extra fetches.
  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(context.project_id ?? "__none__"),
    queryFn: () => api.get<unknown[]>(`/projects/${context.project_id}/episodes`),
    enabled: hasShotSelection && Boolean(context.project_id && context.episode_id),
    staleTime: 30_000,
  });
  const { data: storyboard } = useQuery({
    queryKey: context.scene_id ? queryKeys.storyboard(context.scene_id) : ["storyboard", "none"],
    queryFn: () => api.get<{ scene: { scene_number: number } }>(`/scenes/${context.scene_id}/storyboard`),
    enabled: hasShotSelection && Boolean(context.scene_id),
    staleTime: 15_000,
  });
  const episodeNumber = (episodes as Array<{ id: string; episode_number: number }> | undefined)?.find(
    (item) => item.id === context.episode_id,
  )?.episode_number;
  const contextLine = [
    context.episode_id ? `EP${String(episodeNumber ?? 1).padStart(2, "0")}` : null,
    context.scene_id
      ? `SC${String(storyboard?.scene.scene_number ?? compactId(context.scene_id)).padStart(2, "0")}`
      : null,
    shotLabel,
  ]
    .filter(Boolean)
    .join(" / ");

  const quickAction = (message: string) => {
    setInput(message);
    setSubmitError(null);
  };

  return (
    <div className="panel-tab-content director-tab">
      <div className="director">
        {hasShotSelection ? (
          <>
            <div className="director-context">
              <div className="director-context-identity">
                <span className="eyebrow">当前</span>
                <strong>{contextLine}</strong>
              </div>
              <span className={`agent-status ${waitingHuman ? "waiting_human" : agent.status}`}>
                {STATUS_LABELS[waitingHuman ? "WAITING_HUMAN" : agent.status] ?? agent.status}
              </span>
            </div>
            <div className="director-brief">
              <div>
                <span className="director-brief-label">画面意图</span>
                <p>{shot?.action || shot?.emotion || "镜头意图待补充"}</p>
              </div>
              <div>
                <span className="director-brief-label">AI 建议</span>
                <p>加强主体动作与镜头构图之间的视觉关联。</p>
              </div>
              <div className="director-quick-actions">
                {["优化镜头描述", "优化生成提示词", "创建变体", "检查连续性"].map((action) => (
                  <button key={action} type="button" onClick={() => quickAction(action)}>
                    {action}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="director-empty">
            <span className="director-empty-mark">—</span>
            <strong>未选择镜头</strong>
            <p>选择一个 Shot 后，AI 导演会基于当前镜头提供建议。</p>
            {agent.status !== "idle" && (
              <span className={`agent-status ${waitingHuman ? "waiting_human" : agent.status}`}>
                {STATUS_LABELS[waitingHuman ? "WAITING_HUMAN" : agent.status] ?? agent.status}
              </span>
            )}
          </div>
        )}

        {/* P7-T019/020/021: proposal review (shown while waiting + non-empty list) */}
        {agent.runId && <ProposalReview runId={agent.runId} fallbackStatus={waitingHuman ? "WAITING_HUMAN" : null} />}

        {/* P2-E3-T03: applied change sets of this run (hidden while the list is empty) */}
        {agent.runId && <ChangeSetPanel runId={agent.runId} />}

        {/* P7-T019: visible hint when the run is paused for human approval */}
        {waitingHuman && (
          <div className="director-waiting-hint" role="status">
            等待审批——请在上方 Proposal 卡片中批准或拒绝，或「继续执行」。
          </div>
        )}

        {/* message + plan stream */}
        <div className="director-stream" ref={listRef}>
          {hasShotSelection && agent.messages.length === 0 && agent.status === "idle" && (
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
