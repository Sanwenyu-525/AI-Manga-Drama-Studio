// Batch generation submission aggregation (autonomous-iteration-02):
// 409 idempotency-gate responses count as "in flight", never fail the batch.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { ApiError, api } from "../api/client";
import { generationBatchNotice, submitImageGenerations } from "../features/generation/batchSubmit";
import type { ShotSummary } from "../api/types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function makeShot(id: string): ShotSummary {
  return {
    id,
    shot_number: 1,
    shot_type: "medium",
    duration: null,
    status: "draft",
    dirty_state: "clean",
    thumbnail_url: null,
    character_names: [],
    active_generation: null,
  };
}

function conflictError(): ApiError {
  return new ApiError(409, { error: { code: "CONFLICT", message: "任务进行中", details: {} } });
}

describe("submitImageGenerations", () => {
  it("aggregates submitted / in-flight (409) / failed without fail-fast", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockResolvedValueOnce({ id: "g1" })
      .mockRejectedValueOnce(conflictError())
      .mockRejectedValueOnce(new ApiError(422, { error: { code: "PROVIDER_UNKNOWN", message: "未知引擎", details: {} } }))
      .mockResolvedValueOnce({ id: "g2" });

    const summary = await submitImageGenerations([makeShot("a"), makeShot("b"), makeShot("c"), makeShot("d")]);

    expect(post).toHaveBeenCalledTimes(4);
    expect(summary).toEqual({
      total: 4,
      submitted: 2,
      inFlight: 1,
      failed: 1,
      firstErrorMessage: "未知引擎",
    });
  });

  it("all-success batch reports full submission", async () => {
    vi.spyOn(api, "post").mockResolvedValue({ id: "g" });
    const summary = await submitImageGenerations([makeShot("a"), makeShot("b")]);
    expect(summary.submitted).toBe(2);
    expect(summary.inFlight).toBe(0);
    expect(summary.failed).toBe(0);
  });

  it("notice text distinguishes in-flight from failed", () => {
    expect(generationBatchNotice({ total: 4, submitted: 2, inFlight: 1, failed: 1, firstErrorMessage: "未知引擎" })).toBe(
      "已提交 2/4 个生成任务，1 个已在进行中，1 个提交失败（未知引擎）",
    );
    expect(generationBatchNotice({ total: 2, submitted: 2, inFlight: 0, failed: 0, firstErrorMessage: null })).toBe(
      "已提交 2/2 个生成任务",
    );
  });
});
