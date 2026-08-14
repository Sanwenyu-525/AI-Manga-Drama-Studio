// API client — thin fetch wrapper around the Studio REST contract (api-event-contract §6).
// All types are hand-written against the backend OpenAPI DTOs (contract §135).

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

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "ApiError";
    this.code = body.error.code;
    this.status = status;
    this.details = body.error.details;
  }
}

const BASE = "/api/v1";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let errorBody: ApiErrorBody;
    try {
      errorBody = (await response.json()) as ApiErrorBody;
    } catch {
      throw new ApiError(response.status, {
        error: { code: "HTTP_ERROR", message: `HTTP ${response.status}`, details: {} },
      });
    }
    throw new ApiError(response.status, errorBody);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};
