// P1-E6-T01: API client error contract — ApiError carries code/status/request_id;
// a CONFLICT (character/shot optimistic concurrency) surfaces as ApiError with code.
import { describe, expect, it, vi, afterEach } from "vitest";
import { ApiError, api } from "../api/client";

afterEach(() => vi.restoreAllMocks());

describe("ApiError", () => {
  it("parses the envelope and keeps request_id", () => {
    const err = new ApiError(409, {
      error: { code: "CONFLICT", message: "Character was modified by another writer.", details: { expected: 1, current: 2 }, request_id: "req_abc" },
    });
    expect(err.status).toBe(409);
    expect(err.code).toBe("CONFLICT"); // Character conflict case
    expect(err.message).toBe("Character was modified by another writer.");
    expect(err.requestId).toBe("req_abc");
    expect(err.details.expected).toBe(1);
  });

  it("falls back to the X-Request-ID response header", () => {
    const err = new ApiError(500, { error: { code: "INTERNAL_ERROR", message: "Internal server error.", details: {} } }, "req_from_header");
    expect(err.requestId).toBe("req_from_header");
  });
});

describe("api client", () => {
  it("throws ApiError with request_id on non-OK responses", async () => {
    const body = { error: { code: "ENTITY_NOT_FOUND", message: "Shot does not exist.", details: {}, request_id: "req_404" } };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), { status: 404, headers: { "Content-Type": "application/json" } }),
    );
    await expect(api.get("/shots/nope")).rejects.toMatchObject({ code: "ENTITY_NOT_FOUND", requestId: "req_404" });
  });

  it("throws ApiError on unparseable error bodies with HTTP code", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("boom", { status: 502 }));
    await expect(api.get("/x")).rejects.toMatchObject({ code: "HTTP_ERROR", status: 502 });
  });

  it("times out after timeoutMs and reports TIMEOUT", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          // stays pending until the client-side timeout aborts the request
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    await expect(api.get("/slow", { timeoutMs: 10 })).rejects.toMatchObject({ code: "TIMEOUT" });
  });
});
