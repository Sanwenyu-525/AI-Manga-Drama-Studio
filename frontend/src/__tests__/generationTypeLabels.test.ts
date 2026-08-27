// TASK-012 — LiveGeneration merge semantics + zh type labels in the queue dock.
// Sparse generation events (started/progress) carry no `type`; the store must
// keep the type from generation.queued so the UI can label audio/render tasks.
import { afterEach, describe, expect, it } from "vitest";
import { useGenerationStore } from "../stores/generationStore";
import { generationTypeText } from "../features/generation/generationTypeText";

afterEach(() => {
  useGenerationStore.getState().clear();
});

describe("generationStore upsert merge", () => {
  it("preserves type across sparse follow-up events", () => {
    const { upsert } = useGenerationStore.getState();
    upsert({ id: "g1", shotId: null, progress: 0, stage: "queued", status: "queued", type: "audio" });
    upsert({ id: "g1", shotId: null, progress: 0, stage: null, status: "started", type: null });
    upsert({ id: "g1", shotId: null, progress: 40, stage: "synthesizing", status: "running", type: null });

    const entry = useGenerationStore.getState().live["g1"];
    expect(entry.type).toBe("audio");
    expect(entry.progress).toBe(40);
    expect(entry.status).toBe("running");
  });

  it("keeps entries independent and supports removal", () => {
    const { upsert, remove } = useGenerationStore.getState();
    upsert({ id: "a", shotId: null, progress: 0, stage: null, status: "queued", type: "audio" });
    upsert({ id: "b", shotId: "sh_1", progress: 0, stage: null, status: "queued", type: "image" });

    expect(useGenerationStore.getState().live["a"].type).toBe("audio");
    expect(useGenerationStore.getState().live["b"].type).toBe("image");

    remove("a");
    expect(useGenerationStore.getState().live["a"]).toBeUndefined();
    expect(useGenerationStore.getState().live["b"]).toBeDefined();
  });
});

describe("generationTypeText", () => {
  it("maps known kinds to zh labels and falls back to the raw id", () => {
    expect(generationTypeText("audio")).toBe("配音");
    expect(generationTypeText("render")).toBe("整集渲染");
    expect(generationTypeText("image")).toBe("图片");
    expect(generationTypeText(null)).toBe("图片");
    expect(generationTypeText("future_kind")).toBe("future_kind");
  });
});
