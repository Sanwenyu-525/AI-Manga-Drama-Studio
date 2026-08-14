// Operation polling hook (api-event-contract §15): background AI jobs return 202 + operation_id;
// this hook polls GET /operations/{id} until terminal, then calls onDone.

import { useEffect, useRef } from "react";
import { api } from "../../api/client";
import type { Operation } from "../../api/types";

const POLL_INTERVAL_MS = 500;

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

    const tick = async () => {
      try {
        const op = await api.get<Operation>(`/operations/${operationId}`);
        if (stopped) return;
        if (op.status === "completed") {
          onDoneRef.current(op);
          return;
        }
        if (op.status === "failed") {
          onErrorRef.current?.(op);
          return;
        }
        timer = window.setTimeout(tick, POLL_INTERVAL_MS);
      } catch {
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
