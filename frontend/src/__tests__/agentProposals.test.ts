// P2-E3-T02/T03 — proposal risk / change-set label helpers:
//   1. proposalStatusLabel labels the new "expired" status in Chinese
//   2. riskLevelLabel maps R0..R3 (+ lowercase / unknown fallbacks)
//   3. changeSetToolLabel maps change-set tools incl. undo: compensations
//   4. formatDeadline renders a locale-free YYYY-MM-DD HH:mm deadline
import { describe, expect, it } from "vitest";
import { changeSetToolLabel, formatDeadline, proposalStatusLabel, riskLevelLabel } from "../lib/agentProposals";

describe("proposalStatusLabel (P2-E3-T02)", () => {
  it("labels the expired status in Chinese", () => {
    expect(proposalStatusLabel("expired")).toBe("已过期");
  });

  it("keeps the existing statuses", () => {
    expect(proposalStatusLabel("pending")).toBe("待审批");
    expect(proposalStatusLabel("approved")).toBe("已批准");
    expect(proposalStatusLabel("rejected")).toBe("已拒绝");
    expect(proposalStatusLabel("conflict")).toBe("冲突");
  });
});

describe("riskLevelLabel (P2-E3-T02)", () => {
  it("maps R0..R3 to Chinese risk labels", () => {
    expect(riskLevelLabel("R0")).toBe("只读");
    expect(riskLevelLabel("R1")).toBe("可逆编辑");
    expect(riskLevelLabel("R2")).toBe("昂贵操作");
    expect(riskLevelLabel("R3")).toBe("破坏性");
  });

  it("accepts lowercase levels and falls back for unknown/null", () => {
    expect(riskLevelLabel("r2")).toBe("昂贵操作");
    expect(riskLevelLabel("RX")).toBe("RX");
    expect(riskLevelLabel(null)).toBe("未知");
    expect(riskLevelLabel(undefined)).toBe("未知");
  });
});

describe("changeSetToolLabel (P2-E3-T03)", () => {
  it("maps change-set tools to Chinese labels", () => {
    expect(changeSetToolLabel("update_shot")).toBe("修改镜头");
    expect(changeSetToolLabel("generate_image")).toBe("生成图片（版本切换）");
    expect(changeSetToolLabel("get_shot")).toBe("读取镜头");
  });

  it("labels undo compensations regardless of the wrapped tool", () => {
    expect(changeSetToolLabel("undo:update_shot")).toBe("撤销操作");
    expect(changeSetToolLabel("undo:generate_image")).toBe("撤销操作");
  });
});

describe("formatDeadline (P2-E3-T02)", () => {
  it("formats an ISO deadline as YYYY-MM-DD HH:mm (local, locale-free)", () => {
    const iso = new Date(2026, 7, 31, 9, 5).toISOString();
    expect(formatDeadline(iso)).toBe("2026-08-31 09:05");
  });

  it("returns a dash for empty and the raw string for invalid input", () => {
    expect(formatDeadline(null)).toBe("—");
    expect(formatDeadline(undefined)).toBe("—");
    expect(formatDeadline("not-a-date")).toBe("not-a-date");
  });
});
