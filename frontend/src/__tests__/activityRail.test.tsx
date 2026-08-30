import { describe, expect, it } from "vitest";
import { RAIL_GROUPS } from "../components/shell/ActivityRail";

const items = RAIL_GROUPS.flatMap((group) => group.items);

describe("Activity Rail", () => {
  it("keeps the frozen DESIGN.md order", () => {
    expect(items.map((item) => item.label)).toEqual([
      "项目",
      "工作区",
      "AI导演",
      "故事",
      "角色",
      "分镜",
      "工作流",
      "资产",
      "镜头",
      "提示词历史",
      "知识库",
      "连续性检查",
      "时间线",
      "生产日志",
      "设置",
    ]);
  });

  it("maps each project module to its own deterministic deep link", () => {
    const target = (id: string) => items.find((item) => item.id === id)?.to?.({ projectId: "p1" });

    expect(target("workspace")).toBe("/projects/p1/workspace");
    expect(target("director")).toBe("/projects/p1/director");
    expect(target("story")).toBe("/projects/p1/script");
    expect(target("characters")).toBe("/projects/p1/characters");
    expect(target("storyboard")).toBe("/projects/p1/storyboard");
    expect(target("assets")).toBe("/projects/p1/assets");
    expect(target("shot")).toBe("/projects/p1/shots");
    expect(target("prompts")).toBe("/projects/p1/prompts");
    expect(target("knowledge")).toBe("/projects/p1/knowledge");
    expect(target("continuity")).toBe("/projects/p1/continuity");
    expect(target("timeline")).toBe("/projects/p1/timeline");
    expect(target("log")).toBe("/projects/p1/production-log");
  });

  it("does not send project-only modules to unrelated pages without a project", () => {
    const target = (id: string) => items.find((item) => item.id === id)?.to?.({ projectId: null });
    for (const id of [
      "director",
      "story",
      "characters",
      "storyboard",
      "shot",
      "prompts",
      "knowledge",
      "continuity",
      "timeline",
      "log",
    ]) {
      expect(target(id)).toBeNull();
    }
  });
});
