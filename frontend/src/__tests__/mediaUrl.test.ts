// mediaUrl token 附加策略（审计修复回归）：
// 1. 无 token（浏览器 dev）→ 原样返回
// 2. 有 token 且路径无 query → 追加 ?token=
// 3. 有 token 且路径已有 query（时间线预览的 ?v= 缓存参数）→ 追加 &token=，
//    双 `?` 会把 token 变成上一个参数的值的一部分，后端收到 401
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/session", () => ({
  getSessionToken: vi.fn(),
  initSessionToken: vi.fn(),
}));

import { getSessionToken } from "../lib/session";
import { assetUrl, mediaUrl } from "../lib/mediaUrl";

const mockedGetSessionToken = vi.mocked(getSessionToken);

beforeEach(() => {
  mockedGetSessionToken.mockReset();
});

describe("mediaUrl", () => {
  it("returns the path untouched when no session token is present", () => {
    mockedGetSessionToken.mockReturnValue(null);
    expect(mediaUrl("/api/v1/assets/a1/content")).toBe("/api/v1/assets/a1/content");
  });

  it("appends ?token= when the path has no query string", () => {
    mockedGetSessionToken.mockReturnValue("tok 1");
    expect(mediaUrl("/api/v1/assets/a1/content")).toBe(
      "/api/v1/assets/a1/content?token=tok%201",
    );
  });

  it("appends &token= when the path already carries a query (timeline preview ?v=)", () => {
    mockedGetSessionToken.mockReturnValue("t&ok");
    expect(mediaUrl("/api/v1/timelines/t1/preview?v=123")).toBe(
      "/api/v1/timelines/t1/preview?v=123&token=t%26ok",
    );
  });
});

describe("assetUrl", () => {
  it("routes to the asset content endpoint with the token", () => {
    mockedGetSessionToken.mockReturnValue("abc");
    expect(assetUrl("a1")).toBe("/api/v1/assets/a1/content?token=abc");
    expect(assetUrl("a1", "thumbnail")).toBe("/api/v1/assets/a1/thumbnail?token=abc");
  });
});
