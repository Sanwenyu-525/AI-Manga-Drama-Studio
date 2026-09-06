// AI Director panel (frontend-ux §14-21, agent-director §79-80): an AI Command Center,
// not a chat bubble. Shows selection context, plan, tool progress, approval-style result.

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUp, Check, Circle, Stop, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { AGENT_STAGE_LABELS, useAgentStore } from "../../stores/agentStore";
import { useSelectionStore } from "../../stores/selectionStore";
import type { AgentRunRead, Shot } from "../../api/types";
import { queryKeys } from "../../api/queryKeys";
import { changeSetToolLabel, isWaitingHuman } from "../../lib/agentProposals";
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
    // 智能跟随：仅当用户已在底部附近才自动滚（不抢夺历史阅读）；
    // 尊重 prefers-reduced-motion；jsdom 无 scrollTo 时 no-op。
    const el = listRef.current;
    if (typeof el?.scrollTo !== "function") return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (!nearBottom) return;
    const reduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduced ? "auto" : "smooth" });
  }, [agent.messages.length, agent.status, agent.streamText]);

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

  // 自主迭代 05（刷新恢复）：面板空闲且无 run 时，取项目最近一次 director 会话并水合，
  // 刷新/重开后对话流可恢复。水合后 runId 置位 → 该查询自动停用（不会循环）。
  const { data: latestRuns } = useQuery({
    queryKey: context.project_id ? queryKeys.agentRuns(context.project_id) : ["agentRuns", "none"],
    queryFn: () => api.get<AgentRunRead[]>(`/agent/runs?project_id=${context.project_id}&limit=1`),
    enabled: Boolean(context.project_id) && agent.status === "idle" && !agent.runId,
    staleTime: 30_000,
  });
  useEffect(() => {
    if (!latestRuns || latestRuns.length === 0) return;
    if (useAgentStore.getState().status !== "idle" || useAgentStore.getState().runId) return;
    useAgentStore.getState().hydrate(latestRuns[0]);
  }, [latestRuns]);

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

  const cancelRun = useMutation({
    mutationFn: () => api.post<AgentRunRead>(`/agent/runs/${agent.runId}/cancel`),
    onSuccess: () => useAgentStore.getState().runCancelled(),
  });

  const handleRetry = () => {
    const lastUser = [...agent.messages].reverse().find((m) => m.role === "user");
    if (lastUser && !submitRun.isPending) submitRun.mutate(lastUser.content);
  };

  const handleNewSession = () => {
    useAgentStore.getState().reset();
    setInput("");
    setSubmitError(null);
  };

  const busy = submitRun.isPending || ["thinking", "planning", "executing", "reviewing"].includes(agent.status);
  const terminal = ["completed", "failed", "cancelled"].includes(agent.status);
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
        {hasShotSelection || context.scene_id ? (
          <>
            <div className="director-context">
              <div className="director-context-identity">
                <span className="eyebrow">当前</span>
                <strong>{contextLine}</strong>
              </div>
              <span className="director-head-actions">
                <span className={`agent-status ${waitingHuman ? "waiting_human" : agent.status}`}>
                  {STATUS_LABELS[waitingHuman ? "WAITING_HUMAN" : agent.status] ?? agent.status}
                </span>
                {busy && agent.runId && (
                  <button
                    type="button"
                    className="btn tiny danger"
                    onClick={() => cancelRun.mutate()}
                    disabled={cancelRun.isPending}
                    title="中断本次运行（已提交的修改不回滚，可到变更记录撤销）"
                  >
                    <Stop size={12} weight="fill" /> {cancelRun.isPending ? "取消中…" : "取消"}
                  </button>
                )}
                {terminal && (
                  <button type="button" className="btn tiny" onClick={handleNewSession} title="清空对话开始新会话">
                    新会话
                  </button>
                )}
              </span>
            </div>
            <div className="director-brief">
              <div>
                <span className="director-brief-label">画面意图</span>
                <p>{shot?.action || shot?.emotion || "镜头意图待补充"}</p>
              </div>
              <div className="director-quick-actions">
                {["优化镜头描述", "优化生成提示词", "创建变体", "检查连续性"].map((action) => (
                  <button key={action} type="button" onClick={() => quickAction(action)} disabled={busy}>
                    {action}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="director-empty">
            <span className="director-empty-mark">—</span>
            <strong>未选择场景</strong>
            <p>选中场景或镜头后下达指令；场景级如「把这场戏改成夜晚」不需要选中镜头。</p>
            {agent.status !== "idle" && (
              <span className="director-head-actions">
                <span className={`agent-status ${waitingHuman ? "waiting_human" : agent.status}`}>
                  {STATUS_LABELS[waitingHuman ? "WAITING_HUMAN" : agent.status] ?? agent.status}
                </span>
                {busy && agent.runId && (
                  <button
                    type="button"
                    className="btn tiny danger"
                    onClick={() => cancelRun.mutate()}
                    disabled={cancelRun.isPending}
                    title="中断本次运行"
                  >
                    <Stop size={12} weight="fill" /> {cancelRun.isPending ? "取消中…" : "取消"}
                  </button>
                )}
                {terminal && (
                  <button type="button" className="btn tiny" onClick={handleNewSession} title="清空对话开始新会话">
                    新会话
                  </button>
                )}
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

        {/* message + plan stream：思考时间线 + 打字机增量对读屏可见 */}
        <div className="director-stream" ref={listRef} role="log" aria-live="polite" aria-label="AI Director 会话">
          {(hasShotSelection || context.scene_id) && agent.messages.length === 0 && agent.status === "idle" && (
            <p className="muted small">
              对我说，例如：
              <br />
              「改成近景」「重新生成」「把这场戏改成夜晚」
            </p>
          )}

          {(busy || agent.streamText) && (
            <div className="director-thinking">
              <div className="thinking-steps">
                {agent.stages
                  .filter((s) => s.status !== "pending")
                  .map((s) => (
                    <span key={s.stage} className={`thinking-step ${s.status}`} title={s.detail}>
                      {AGENT_STAGE_LABELS[s.stage]}
                    </span>
                  ))}
              </div>
              {agent.streamText && (
                <p className="thinking-stream">
                  {agent.streamText}
                  {!agent.streamDone && <span className="thinking-caret" aria-hidden="true">
                    ▍
                  </span>}
                </p>
              )}
            </div>
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
                  <span className="plan-icon" aria-hidden="true">
                    {tool.status === "done" ? (
                      <Check size={12} weight="bold" />
                    ) : tool.status === "failed" ? (
                      <X size={12} weight="bold" />
                    ) : (
                      <Circle size={12} weight={tool.status === "running" ? "fill" : "regular"} />
                    )}
                  </span>
                  <span className="plan-tool">{changeSetToolLabel(tool.tool)}</span>
                  {tool.detail && <span className="muted small">{tool.detail.slice(-4)}</span>}
                </div>
              ))}
            </div>
          )}

          {agent.status === "failed" && (
            <button type="button" className="btn tiny" onClick={handleRetry} disabled={submitRun.isPending}>
              重试上一次指令
            </button>
          )}

          {submitError && <ApiErrorPanel error={submitError} />}
        </div>

        {/* input (frontend-ux §83)：发送按钮收进输入框右端 */}
        <div className="director-input">
          <div className="director-input-box">
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
            <button
              type="button"
              className="director-send"
              aria-label="发送"
              title="发送"
              onClick={handleSubmit}
              disabled={busy || !input.trim()}
            >
              <ArrowUp size={15} weight="bold" aria-hidden />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
