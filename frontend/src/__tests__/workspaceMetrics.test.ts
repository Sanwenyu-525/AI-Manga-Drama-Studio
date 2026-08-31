// P2 聚合指标纯函数测试（真实 Project State 形状，见 api/types.ts ShotTreeItem 等）。
import { describe, expect, it } from "vitest";
import { derivePipeline, percent, summarizeEpisodes } from "../lib/workspaceMetrics";
import type { Episode, ProjectTreeRead } from "../api/types";

function shot(partial: Partial<{ status: string; active_image_version: number | null }>) {
  return {
    id: `shot-${Math.random().toString(36).slice(2, 8)}`,
    shot_number: 1,
    shot_type: "wide",
    status: "draft",
    dirty_state: "clean",
    revision: 1,
    active_image_version: null,
    active_video_version: null,
    active_prompt_version_id: null,
    ...partial,
  };
}

const TREE: ProjectTreeRead = {
  project: { id: "p1", name: "测试项目" } as ProjectTreeRead["project"],
  episodes: [
    {
      id: "ep1",
      episode_number: 1,
      title: "第一集",
      scene_count: 2,
      scenes: [
        {
          id: "sc1",
          scene_number: 1,
          name: "A",
          shot_count: 2,
          shots: [shot({ active_image_version: 3, status: "image_ready" }), shot({ status: "failed" })],
        },
        { id: "sc2", scene_number: 2, name: "B", shot_count: 1, shots: [shot({ status: "draft" })] },
      ],
    },
    {
      id: "ep2",
      episode_number: 2,
      title: null,
      scene_count: 0,
      scenes: [],
    },
  ],
};

const EPISODES: Episode[] = [
  { id: "ep1", source_text: "第一章内容" } as Episode,
  { id: "ep2", source_text: "   " } as Episode,
];

describe("summarizeEpisodes", () => {
  it("统计每集 场/镜/已出图/失败 与原文标记", () => {
    const r = summarizeEpisodes(TREE, EPISODES);
    expect(r.episodes).toHaveLength(2);
    expect(r.episodes[0]).toMatchObject({
      sceneCount: 2,
      shotCount: 3,
      imageReadyCount: 1,
      failedCount: 1,
      hasSourceText: true,
    });
    expect(r.episodes[1]).toMatchObject({ sceneCount: 0, shotCount: 0, hasSourceText: false });
    expect(r).toMatchObject({ sceneCount: 2, shotCount: 3, imageReadyCount: 1, failedCount: 1 });
  });

  it("容忍缺失数据（undefined tree / episodes）", () => {
    const r = summarizeEpisodes(undefined, undefined);
    expect(r.episodes).toEqual([]);
    expect(r.shotCount).toBe(0);
  });
});

describe("derivePipeline", () => {
  it("空项目全等待", () => {
    const r = summarizeEpisodes(undefined, undefined);
    const stages = derivePipeline(r, false, false);
    expect(stages.every((s) => s.state === "waiting")).toBe(true);
  });

  it("原文+场景+分镜齐备且已有出图 → 时间线进行中", () => {
    const progress = summarizeEpisodes(TREE, EPISODES);
    const stages = derivePipeline(progress, false, false);
    const byKey = Object.fromEntries(stages.map((s) => [s.key, s.state]));
    expect(byKey.source).toBe("done");
    expect(byKey.scenes).toBe("done");
    expect(byKey.shots).toBe("done");
    expect(byKey.image).toBe("done");
    expect(byKey.timeline).toBe("running");
    expect(byKey.export).toBe("waiting");
  });

  it("只有分镜尚未出图 → 图片生成进行中", () => {
    const treeNoImage: ProjectTreeRead = {
      project: TREE.project,
      episodes: [
        {
          id: "ep1",
          episode_number: 1,
          title: null,
          scene_count: 1,
          scenes: [
            {
              id: "sc1",
              scene_number: 1,
              name: null,
              shot_count: 2,
              shots: [shot({ status: "draft" }), shot({ status: "failed" })],
            },
          ],
        },
      ],
    };
    const progress = summarizeEpisodes(treeNoImage, [{ id: "ep1", source_text: "x" } as Episode]);
    const byKey = Object.fromEntries(derivePipeline(progress, false, false).map((s) => [s.key, s.state]));
    expect(byKey.shots).toBe("done");
    expect(byKey.image).toBe("running");
    expect(byKey.timeline).toBe("waiting");
  });

  it("跳步：无原文但已有场景/分镜 → 各项独立 done，小说分析为当前行动点", () => {
    // TREE: scenes/shots 存在且 1 镜已出图，但对应 episode.source_text 为空
    const progress = summarizeEpisodes(TREE, [{ id: "ep1", source_text: "" } as Episode, { id: "ep2" } as Episode]);
    const byKey = Object.fromEntries(derivePipeline(progress, false, false).map((s) => [s.key, s.state]));
    expect(byKey.source).toBe("running"); // 当前行动点：导入原文
    expect(byKey.scenes).toBe("done"); // 独立判断，不因前序缺失而降级
    expect(byKey.shots).toBe("done");
    expect(byKey.image).toBe("done");
    expect(byKey.timeline).toBe("waiting");
  });

  it("全部完成后到导出，timeline 视探针结果", () => {
    const treeAllDone: ProjectTreeRead = {
      project: TREE.project,
      episodes: [
        {
          id: "ep1",
          episode_number: 1,
          title: null,
          scene_count: 1,
          scenes: [
            {
              id: "sc1",
              scene_number: 1,
              name: null,
              shot_count: 1,
              shots: [shot({ active_image_version: 1, status: "approved" })],
            },
          ],
        },
      ],
    };
    const progress = summarizeEpisodes(treeAllDone, [{ id: "ep1", source_text: "x" } as Episode]);
    const withoutTimeline = derivePipeline(progress, false, false);
    expect(Object.fromEntries(withoutTimeline.map((s) => [s.key, s.state])).timeline).toBe("running");

    const withExport = derivePipeline(progress, true, true);
    const states = Object.fromEntries(withExport.map((s) => [s.key, s.state]));
    expect(states.timeline).toBe("done");
    expect(states.export).toBe("done"); // 成片已产出 = 终态完成
  });
});

describe("percent", () => {
  it("常规/零分母/上限", () => {
    expect(percent(1, 3)).toBe(33);
    expect(percent(0, 0)).toBe(0);
    expect(percent(5, 3)).toBe(100);
  });
});
