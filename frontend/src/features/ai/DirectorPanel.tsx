import { BracketsCurly, ChatCenteredDots, CheckCircle, LockKey, MagicWand, PaperPlaneTilt, Sparkle } from "@phosphor-icons/react";
import { useSelectionStore } from "../../stores/selectionStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";

export function DirectorPanel() {
  const selection = useSelectionStore((state) => state.selection);
  const setRightPanelTab = useWorkspaceStore((state) => state.setRightPanelTab);
  const shotId = selection.shotIds[0];

  return (
    <div className="panel-tab-content director-panel">
      <div className="panel-tabs">
        <button className="tab" onClick={() => setRightPanelTab("inspector")}>镜头检查器</button>
        <button className="tab active">AI Director</button>
      </div>

      <div className="director-heading">
        <div className="director-avatar"><MagicWand size={19} weight="fill" /></div>
        <div><strong>AI Director</strong><span>Stage D · 待接入</span></div>
        <span className="badge neutral"><LockKey size={12} /> 未运行</span>
      </div>

      <div className="director-context-card">
        <span className="field-label">当前上下文</span>
        {shotId ? (
          <><strong>已选中 1 个镜头</strong><code>{shotId}</code></>
        ) : (
          <><strong>尚未选择镜头</strong><p>先在分镜画布中选择需要修改的 Shot。</p></>
        )}
      </div>

      <div className="director-roadmap">
        <div className="roadmap-row"><CheckCircle size={17} weight="fill" /><span><strong>Selection-aware</strong><small>项目、场景、镜头上下文已就绪</small></span></div>
        <div className="roadmap-row"><BracketsCurly size={17} /><span><strong>三项结构化工具</strong><small>get_shot · update_shot · generate_image</small></span></div>
        <div className="roadmap-row pending"><Sparkle size={17} /><span><strong>Director Graph</strong><small>Understand → Plan → Execute → Review</small></span></div>
      </div>

      <div className="director-suggestion">
        <ChatCenteredDots size={18} />
        <p>接入后可直接说：<q>把这个镜头改成近景，再生成一版。</q></p>
      </div>

      <div className="director-composer">
        <textarea rows={3} disabled placeholder="Stage D API 接入后可发送导演指令…" />
        <button className="icon-button" disabled aria-label="发送"><PaperPlaneTilt size={18} /></button>
      </div>
      <p className="director-footnote">这里不会伪造 Agent 结果；运行、审批与工具事件将在 Stage D 接真实事件流。</p>
    </div>
  );
}
