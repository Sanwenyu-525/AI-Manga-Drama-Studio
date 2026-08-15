// P1-E6-T01: error panel renders message + copyable request_id (P1-E4-T01 contract).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { ApiErrorPanel } from "../components/ApiErrorPanel";

describe("ApiErrorPanel", () => {
  it("shows the safe message and the request id", () => {
    const err = new ApiError(409, {
      error: { code: "CONFLICT", message: "Shot was modified by another writer.", details: {}, request_id: "req_abc123" },
    });
    render(<ApiErrorPanel error={err} />);
    expect(screen.getByText("Shot was modified by another writer.")).toBeTruthy();
    expect(screen.getByTitle(/request_id/)).toBeTruthy();
    expect(screen.getByText("#req_abc123")).toBeTruthy();
  });

  it("falls back to the plain message for non-ApiError", () => {
    render(<ApiErrorPanel error="自定义失败信息" />);
    expect(screen.getByText("自定义失败信息")).toBeTruthy();
  });
});
