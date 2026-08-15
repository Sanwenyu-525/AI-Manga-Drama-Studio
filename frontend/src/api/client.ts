// API client — thin fetch wrapper around the Studio REST contract (api-event-contract §6).
// All types are hand-written against the backend OpenAPI DTOs (contract §135).
// P1-E4-T01: every ApiError carries the backend request_id (traceable errors);
// requests support timeout + external AbortSignal (cancel).

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id?: string;
  };
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;
  requestId: string | null;

  constructor(status: number, body: ApiErrorBody, requestId: string | null = null) {
    super(body.error.message);
    this.name = "ApiError";
    this.code = body.error.code;
    this.status = status;
    this.details = body.error.details;
    this.requestId = requestId ?? body.error.request_id ?? null;
  }
}

export interface RequestOptions {
  /** Abort the request after this many ms (default 30s). */
  timeoutMs?: number;
  /** External cancellation signal (caller-controlled abort). */
  signal?: AbortSignal;
}

const BASE = "/api/v1";
const DEFAULT_TIMEOUT_MS = 30_000;

async function request<T>(method: string, path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timer = window.setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), timeoutMs);
  const onExternalAbort = () => controller.abort();
  options.signal?.addEventListener("abort", onExternalAbort);
  try {
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    const response = await fetch(`${BASE}${path}`, {
      method,
      headers: body !== undefined && !isFormData ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? (isFormData ? body : JSON.stringify(body)) : undefined,
      signal: controller.signal,
    });
    if (!response.ok) {
      let errorBody: ApiErrorBody;
      try {
        errorBody = (await response.json()) as ApiErrorBody;
      } catch {
        throw new ApiError(
          response.status,
          { error: { code: "HTTP_ERROR", message: `HTTP ${response.status}`, details: {} } },
          response.headers.get("X-Request-ID"),
        );
      }
      throw new ApiError(response.status, errorBody, response.headers.get("X-Request-ID"));
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (options.signal?.aborted) throw error; // caller-initiated cancel: rethrow as-is
    if (controller.signal.aborted) {
      throw new ApiError(0, {
        error: { code: "TIMEOUT", message: "请求超时，请重试。", details: {} },
      });
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
    options.signal?.removeEventListener("abort", onExternalAbort);
  }
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>("POST", path, body, options),
  put: <T>(path: string, body: unknown, options?: RequestOptions) => request<T>("PUT", path, body, options),
  patch: <T>(path: string, body: unknown, options?: RequestOptions) => request<T>("PATCH", path, body, options),
  delete: <T>(path: string, options?: RequestOptions) => request<T>("DELETE", path, undefined, options),
  /** Multipart upload (P6 / P3-T003): the body is a FormData carrying the file
   *  plus its form fields. request() detects FormData and omits Content-Type so
   *  the browser sets the multipart boundary automatically. */
  upload: <T>(path: string, form: FormData, options?: RequestOptions) => request<T>("POST", path, form, options),
};
