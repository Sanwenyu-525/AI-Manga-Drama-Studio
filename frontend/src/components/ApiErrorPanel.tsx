// Shared error banner (P1-E4-T01): shows the safe API message and a copyable
// request_id so failures are traceable in backend logs (api-event-contract §6).
// The full unified error UI (toast/skeleton/retry) lands in P3-E1-T01.

import { useState } from "react";
import { ApiError } from "../api/client";

interface ApiErrorPanelProps {
  /** ApiError (recommended), any Error, or a plain string message. */
  error: unknown;
  className?: string;
}

export function ApiErrorPanel({ error, className }: ApiErrorPanelProps) {
  const [copied, setCopied] = useState(false);
  const apiError = error instanceof ApiError ? error : null;
  const message = apiError ? apiError.message : error instanceof Error ? error.message : String(error ?? "未知错误");
  const requestId = apiError?.requestId ?? null;

  const copy = async () => {
    if (!requestId) return;
    try {
      await navigator.clipboard.writeText(requestId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable (non-secure context): keep the id visible instead
    }
  };

  return (
    <div className={`error-banner ${className ?? ""}`} role="alert">
      <span>{message}</span>
      {requestId && (
        <button type="button" className="request-id-copy" onClick={copy} title="复制 request_id 以便排查">
          {copied ? "已复制" : `#${requestId.slice(0, 12)}`}
        </button>
      )}
    </div>
  );
}
