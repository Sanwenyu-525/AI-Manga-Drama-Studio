// P6-T004: editor tabs — open/close/switch/restore, base-tab invariants.
import { describe, expect, it } from "vitest";
import type { EditorTab } from "../lib/editorTabs";
import {
  SCRIPT_TAB_ID,
  MAX_TABS,
  initialTabs,
  openSceneTab,
  openShotTab,
  activateTab,
  closeTab,
  ensureScriptTab,
  restoreTabs,
  tabId,
} from "../lib/editorTabs";
import { useEditorTabsStore } from "../stores/editorTabsStore";

describe("editorTabs — open", () => {
  it("opens + activates a scene tab", () => {
    const s = openSceneTab(initialTabs(), { projectId: "p1", sceneId: "s1", title: "Scene 1" });
    expect(s.open).toHaveLength(2);
    expect(s.activeTabId).toBe("scene:s1");
  });
  it("re-activating the same scene keeps one tab (idempotent)", () => {
    const first = openSceneTab(initialTabs(), { projectId: "p1", sceneId: "s1", title: "Scene 1" });
    const second = openSceneTab(first, { projectId: "p1", sceneId: "s1", title: "Scene 1" });
    expect(second.open).toHaveLength(2);
  });
  it("opens a shot tab with its own id", () => {
    const s = openShotTab(initialTabs(), { projectId: "p1", shotId: "shot_1", title: "Shot 001", sceneId: "s1" });
    expect(s.activeTabId).toBe("shot:shot_1");
    expect(s.open.find((t) => t.id === "shot:shot_1")?.sceneId).toBe("s1");
  });
  it("drops the oldest non-script tab when at capacity", () => {
    let s = initialTabs();
    for (let i = 0; i < MAX_TABS; i++) {
      s = openSceneTab(s, { projectId: "p1", sceneId: `s${i}`, title: `Scene ${i}` });
    }
    // Capacity is script + (MAX_TABS-1) scene tabs; one more evicts the oldest scene.
    s = openSceneTab(s, { projectId: "p1", sceneId: "sextra", title: "Scene extra" });
    expect(s.open.length).toBeLessThanOrEqual(MAX_TABS);
    expect(s.open.some((t) => t.id === "scene:sextra")).toBe(true);
  });
});

describe("editorTabs — activate / close", () => {
  it("activateTab focuses an existing tab", () => {
    const s = openSceneTab(initialTabs(), { projectId: "p1", sceneId: "s1", title: "Scene 1" });
    const activated = activateTab(s, SCRIPT_TAB_ID);
    expect(activated.activeTabId).toBe(SCRIPT_TAB_ID);
  });
  it("activateTab ignores unknown ids", () => {
    const s = activateTab(initialTabs(), "nope");
    expect(s.activeTabId).toBe(SCRIPT_TAB_ID);
  });
  it("closing an inactive tab does not change the active tab", () => {
    let s = openSceneTab(initialTabs(), { projectId: "p1", sceneId: "s1", title: "Scene 1" });
    s = openShotTab(s, { projectId: "p1", shotId: "shot_1", title: "Shot 1" });
    const after = closeTab(s, "scene:s1");
    expect(after.open.some((t) => t.id === "scene:s1")).toBe(false);
    expect(after.activeTabId).toBe("shot:shot_1");
  });
  it("closing the active tab activates the neighbor on the left", () => {
    let s = openSceneTab(initialTabs(), { projectId: "p1", sceneId: "s1", title: "Scene 1" });
    s = openShotTab(s, { projectId: "p1", shotId: "shot_1", title: "Shot 1" });
    const after = closeTab(s, "shot:shot_1");
    expect(after.activeTabId).toBe("scene:s1");
  });
  it("closing the sole scene tab falls back to the script tab", () => {
    const s = openSceneTab(initialTabs(), { projectId: "p1", sceneId: "s1", title: "Scene 1" });
    const after = closeTab(s, "scene:s1");
    expect(after.open).toHaveLength(1);
    expect(after.activeTabId).toBe(SCRIPT_TAB_ID);
  });
  it("the script base tab cannot be closed", () => {
    const s = closeTab(initialTabs(), SCRIPT_TAB_ID);
    expect(s).toEqual(initialTabs());
  });
});

describe("editorTabs — restore", () => {
  it("restores scene/shot tabs and the active id", () => {
    const s = restoreTabs(
      [
        { id: tabId("scene", "s1"), kind: "scene", title: "Scene 1", sceneId: "s1", projectId: "p1" } as EditorTab,
        { id: tabId("shot", "x"), kind: "shot", title: "Shot", shotId: "x", projectId: "p1" } as EditorTab,
      ],
      tabId("shot", "x"),
    );
    expect(s.open).toHaveLength(3);
    expect(s.activeTabId).toBe(tabId("shot", "x"));
  });
  it("ignores tabs without a valid resource ref and bad active id", () => {
    const s = restoreTabs([{ id: "scene:x", kind: "scene", title: "scene" } as never, null as never], "bogus");
    expect(s.open).toHaveLength(1);
    expect(s.open[0].id).toBe(SCRIPT_TAB_ID);
    expect(s.activeTabId).toBe(SCRIPT_TAB_ID);
  });
});

describe("editorTabsStore — integration", () => {
  it("openScene updates the live store", () => {
    useEditorTabsStore.setState(initialTabs());
    useEditorTabsStore.getState().openScene({ projectId: "p1", sceneId: "s1", title: "Scene 1" });
    expect(useEditorTabsStore.getState().activeTabId).toBe("scene:s1");
    useEditorTabsStore.getState().closeTab("scene:s1");
    expect(useEditorTabsStore.getState().open).toHaveLength(1);
  });
  it("ensureScriptTab re-inserts the base tab if missing", () => {
    const s = ensureScriptTab({
      open: [{ id: "scene:s1", kind: "scene", title: "Scene 1", sceneId: "s1" }],
      activeTabId: "scene:s1",
    });
    expect(s.open.some((t) => t.id === SCRIPT_TAB_ID)).toBe(true);
  });
});
