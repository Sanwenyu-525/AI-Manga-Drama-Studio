// AI Director panel (frontend-ux §14-21, agent-director §79-80): an AI Command Center,
// not a chat bubble. Shows selection context, plan, tool progress, approval-style result.

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { useAgentStore } from "../../stores/agentStore";
import { useSelectionStore } from "../../stores/selectionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import type { AgentRunRead } from "../../api/types";

const STATUS_LABELS: Record<string, string> = {
  idle: "待命",
  thinking: "理解意图…",
  planning: "制定计划…",
  executing: "执行中…",
  reviewing: "检查结果…",
  cancelling: "取消中…",
  cancelled: "已取消",
  completed: "完成",
  failed: "失败",
};

export function AIDirectorPanel() {
  const selection = useSelectionStore((s) => s.selection);
  const setRightPanelTab = useWorkspaceStore((s) => s.setRightPanelTab);
  const agent = useAgentStore();
  const [input, setInput] = useState("");
  const [submitError, setSubmitError] = useState<Error | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [agent.messages.length, agent.status]);

  const submitRun = useMutation({
    mutationFn: (message: string) =>
      api.post<AgentRunRead>("/agent/director/runs", {
        project_id: selection.projectId,
        message,
        selection: {
          workspace: selection.workspace,
          project_id: selection.projectId,
          episode_id: selection.episodeId,
          scene_id: selection.sceneId,
          shot_ids: selection.shotIds,
          asset_ids: selection.assetIds,
        },
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

  return (
    <div className="panel-tab-content">
      <div className="panel-tabs">
        <button className="tab" onClick={() => setRightPanelTab("inspector")}>
          Inspector
        </button>
        <button className="tab active">AI Director</button>
      </div>

      <div className="director">
        {/* selection context (frontend-ux §16, §46) */}
        <div className="director-context">
          <span className="muted small">
            当前：{selection.sceneId ? `Scene ${selection.sceneId.slice(-4)}` : "无场景"} ·{" "}
            {selection.shotIds.length > 0 ? `${selection.shotIds.length} 个镜头选中` : "未选中镜头"}
          </span>
          <span className={`agent-status ${agent.status}`}>{STATUS_LABELS[agent.status] ?? agent.status}</span>
        </div>

        {/* message + plan stream */}
        <div className="director-stream" ref={listRef}>
          {agent.messages.length === 0 && agent.status === "idle" && (
            <p className="muted small">
              选中一个镜头后对我说，例如：
              <br />「改成近景」「重新生成」「改成近景然后重新生成」
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
                  <span className="plan-icon">{tool.status === "done" ? "✓" : tool.status === "failed" ? "✗" : tool.status === "running" ? "●" : "○"}</span>
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
            placeholder="例如：把这个改成近景然后重新生成"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit();
            }}
            disabled={busy}
          />
          <button className="btn primary" onClick={handleSubmit} disabled={busy || !input.trim()}>
            {busy ? "…" : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
