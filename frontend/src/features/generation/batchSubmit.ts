// Batch generation submission (autonomous-iteration-02).
// The per-shot 202 endpoint has an idempotency gate (same shot+type in flight → 409
// CONFLICT), so batch submission must NOT use Promise.all fail-fast: a 409 means
// "already generating", not "failed". allSettled + per-item aggregation gives an
// honest summary (submitted / in-flight / failed) for the notice.

import { ApiError, api } from "../../api/client";
import type { GenerationRead, ShotSummary } from "../../api/types";

export interface GenerationBatchSummary {
  total: number;
  submitted: number;
  /** 409 CONFLICT from the idempotency gate — a task is already running. */
  inFlight: number;
  failed: number;
  /** First non-conflict error message, for surfacing the actual cause. */
  firstErrorMessage: string | null;
}

export function isConflictError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

export async function submitImageGenerations(targets: ShotSummary[]): Promise<GenerationBatchSummary> {
  const settled = await Promise.allSettled(
    targets.map((shot) => api.post<GenerationRead>(`/shots/${shot.id}/generations`, { type: "image" })),
  );
  let submitted = 0;
  let inFlight = 0;
  let failed = 0;
  let firstErrorMessage: string | null = null;
  for (const result of settled) {
    if (result.status === "fulfilled") {
      submitted += 1;
    } else if (isConflictError(result.reason)) {
      inFlight += 1;
    } else {
      failed += 1;
      firstErrorMessage ??= result.reason instanceof Error ? result.reason.message : String(result.reason);
    }
  }
  return { total: targets.length, submitted, inFlight, failed, firstErrorMessage };
}

export function generationBatchNotice(summary: GenerationBatchSummary): string {
  const parts = [`已提交 ${summary.submitted}/${summary.total} 个生成任务`];
  if (summary.inFlight) parts.push(`${summary.inFlight} 个已在进行中`);
  if (summary.failed) parts.push(`${summary.failed} 个提交失败（${summary.firstErrorMessage ?? "未知错误"}）`);
  return parts.join("，");
}
