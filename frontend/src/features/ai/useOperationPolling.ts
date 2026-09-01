// Operation polling hook (api-event-contract §15): background AI jobs return 202 + operation_id;
// this hook polls GET /operations/{id} until terminal, then calls onDone.

import { useEffect, useRef } from "react";
import { ApiError, api } from "../../api/client";
import type { Operation } from "../../api/types";

const POLL_INTERVAL_MS = 500;
/** Give up after this many consecutive failed polls (~5s): the operation store
 * is in-memory, so a 404 (backend restart) or a long outage means the result
 * will never arrive — surfacing an error beats polling forever with the button
 * stuck in its pending state. */
const MAX_CONSECUTIVE_ERRORS = 10;

export function useOperationPolling(
  operationId: string | null,
  onDone: (op: Operation) => void,
  onError?: (op: Operation) => void,
) {
  const onDoneRef = useRef(onDone);
  const onErrorRef = useRef(onError);
  onDoneRef.current = onDone;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!operationId) return;
    let stopped = false;
    let failures = 0;

    const giveUp = (message: string) => {
      onErrorRef.current?.({
        id: operationId,
        type: "operation",
        status: "failed",
        error: message,
      } as unknown as Operation);
    };

    const tick = async () => {
      try {
        const op = await api.get<Operation>(`/operations/${operationId}`);
        if (stopped) return;
        failures = 0;
        if (op.status === "completed") {
          onDoneRef.current(op);
          return;
        }
        if (op.status === "failed") {
          onErrorRef.current?.(op);
          return;
        }
        timer = window.setTimeout(tick, POLL_INTERVAL_MS);
      } catch (error) {
        if (stopped) return;
        failures += 1;
        // A 404 means the operation id no longer exists (backend restart lost the
        // in-memory store) — retrying a couple of times then reporting is enough.
        const gone = error instanceof ApiError && error.status === 404;
        if (gone && failures >= 3) {
          giveUp("操作记录已丢失（后端可能已重启），请重新发起任务。");
          return;
        }
        if (failures >= MAX_CONSECUTIVE_ERRORS) {
          giveUp("任务状态查询持续失败，请检查后端连接后重试。");
          return;
        }
        timer = window.setTimeout(tick, POLL_INTERVAL_MS);
      }
    };

    let timer = window.setTimeout(tick, 0);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [operationId]);
}
