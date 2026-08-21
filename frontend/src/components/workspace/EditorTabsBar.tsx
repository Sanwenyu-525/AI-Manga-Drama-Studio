// P6-T004 Editor Tabs — tab bar for the center workspace (IDE-style).
// The base `script` tab is non-closeable; scene/shot tabs can be closed. Clicking a
// tab activates it locally (the WorkspaceHost renders the active tab's content).

import { X } from "@phosphor-icons/react";
import { useLocation, useNavigate } from "react-router-dom";
import { editorTabPath, useStudioRoute } from "../../features/studio/studioRoute";
import { useEditorTabsStore } from "../../stores/editorTabsStore";
import { SCRIPT_TAB_ID } from "../../lib/editorTabs";

const KIND_LABEL: Record<string, string> = { script: "", scene: "Scene", shot: "Shot" };

export function EditorTabsBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const route = useStudioRoute();
  const open = useEditorTabsStore((s) => s.open);
  const activeTabId = useEditorTabsStore((s) => s.activeTabId);
  const activateTab = useEditorTabsStore((s) => s.activateTab);
  const closeTab = useEditorTabsStore((s) => s.closeTab);

  const navigateToTab = (id: string) => {
    const tab = useEditorTabsStore.getState().open.find((item) => item.id === id);
    const path = tab ? editorTabPath(tab, route) : null;
    if (path && path !== location.pathname) navigate(path);
  };

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
            onClick={() => {
              activateTab(tab.id);
              navigateToTab(tab.id);
            }}
          >
            <span className="editor-tab-title">{prefix}{tab.title}</span>
            {closable && (
              <button
                type="button"
                className="editor-tab-close"
                aria-label={`关闭 ${prefix}${tab.title}`}
                onClick={(e) => {
                  e.stopPropagation();
                  const wasActive = tab.id === activeTabId;
                  closeTab(tab.id);
                  if (wasActive) navigateToTab(useEditorTabsStore.getState().activeTabId ?? SCRIPT_TAB_ID);
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
