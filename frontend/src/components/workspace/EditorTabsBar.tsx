// P6-T004 Editor Tabs — tab bar for the center workspace (IDE-style).
// The base `script` tab is non-closeable; scene/shot tabs can be closed. Clicking a
// tab activates it locally (the WorkspaceHost renders the active tab's content).

import { X } from "@phosphor-icons/react";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { SCRIPT_TAB_ID } from "../../lib/editorTabs";

const KIND_LABEL: Record<string, string> = { script: "", scene: "Scene", shot: "Shot" };

export function EditorTabsBar() {
  const open = useEditorTabsStore((s) => s.open);
  const activeTabId = useEditorTabsStore((s) => s.activeTabId);
  const activateTab = useEditorTabsStore((s) => s.activateTab);
  const closeTab = useEditorTabsStore((s) => s.closeTab);

  if (open.length <= 1) return null;

  return (
    <div className="editor-tabs" role="tablist" aria-label="编辑标签页">
      {open.map((tab) => {
        const closable = tab.id !== SCRIPT_TAB_ID;
        const prefix = KIND_LABEL[tab.kind] ? `${KIND_LABEL[tab.kind]} ` : "";
        return (
          <div
            key={tab.id}
            role="tab"
            aria-selected={tab.id === activeTabId}
            className={`editor-tab${tab.id === activeTabId ? " active" : ""}`}
            onClick={() => activateTab(tab.id)}
          >
            <span className="editor-tab-title">{prefix}{tab.title}</span>
            {closable && (
              <button
                type="button"
                className="editor-tab-close"
                aria-label={`关闭 ${prefix}${tab.title}`}
                onClick={(e) => {
                  e.stopPropagation();
                  closeTab(tab.id);
                }}
              >
                <X size={12} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}