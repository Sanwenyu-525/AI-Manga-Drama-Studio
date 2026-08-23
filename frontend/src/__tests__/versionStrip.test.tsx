// P3-VS-T01: VersionStrip label derivation (ACTIVE/NEW/STALE + status fallback),
// click-to-select callback, and empty-list rendering. Pure view-layer semantics —
// "latest" is derived client-side from the max version_number within a media group.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssetVersionRead } from "../api/types";
import { deriveVersionBadges, latestPerGroup, VersionStrip } from "../features/versioning/VersionStrip";

function version(partial: Partial<AssetVersionRead> & { asset_id: string }): AssetVersionRead {
  return {
    id: partial.asset_id, // ADR-001: asset id is self-versioned (id == asset_id)
    shot_id: "shot_1",
    media_type: "image",
    version_number: 1,
    generation_id: "gen_1",
    is_active: false,
    status: "ready",
    notes: null,
    created_at: "2026-08-01T00:00:00Z",
    ...partial,
  };
}

// Vitest globals are disabled here, so RTL's automatic per-test cleanup is not installed;
// unmount explicitly to keep each test on a fresh DOM.
afterEach(() => cleanup());

describe("deriveVersionBadges", () => {
  it("flags the active version as ★ ACTIVE even when it is also the newest", () => {
    const badges = deriveVersionBadges(version({ asset_id: "a1", is_active: true }), true);
    expect(badges.map((b) => b.kind)).toEqual(["active"]);
    expect(badges[0].label).toBe("★ ACTIVE");
    expect(badges[0].tone).toBe("ok");
  });

  it("flags a stale, active version with both ACTIVE and ⚠ STALE", () => {
    const badges = deriveVersionBadges(version({ asset_id: "a1", is_active: true, status: "stale" }), true);
    expect(badges.map((b) => b.kind)).toEqual(["active", "stale"]);
    expect(badges[1].label).toBe("⚠ STALE");
  });

  it("flags the newest non-active version as NEW", () => {
    const badges = deriveVersionBadges(version({ asset_id: "a2", version_number: 2 }), true);
    expect(badges.map((b) => b.kind)).toEqual(["latest"]);
    expect(badges[0].label).toBe("NEW");
    expect(badges[0].tone).toBe("new");
  });

  it("does NOT flag an older superseded version when it is not the newest", () => {
    const badges = deriveVersionBadges(version({ asset_id: "a1", version_number: 1 }), false);
    expect(badges).toEqual([]);
  });

  it("maps stale / missing / non-ready statuses to fallback labels", () => {
    expect(deriveVersionBadges(version({ asset_id: "a1", status: "stale" }), false).map((b) => b.kind)).toEqual([
      "stale",
    ]);
    expect(deriveVersionBadges(version({ asset_id: "a2", status: "missing" }), false).map((b) => b.label)).toEqual([
      "❌ MISSING",
    ]);
    expect(deriveVersionBadges(version({ asset_id: "a3", status: "archived" }), false).map((b) => b.label)).toEqual([
      "ARCHIVED",
    ]);
  });
});

describe("latestPerGroup", () => {
  it("resolves the max version_number per media_type group", () => {
    const list = [
      version({ asset_id: "img1", media_type: "image", version_number: 1 }),
      version({ asset_id: "img2", media_type: "image", version_number: 3 }),
      version({ asset_id: "vid1", media_type: "video", version_number: 2 }),
    ];
    const newest = latestPerGroup(list);
    expect(newest.get("image")).toBe("img2");
    expect(newest.get("video")).toBe("vid1");
  });
});

describe("VersionStrip", () => {
  const list = [
    version({ asset_id: "a1", version_number: 1, is_active: true, status: "stale" }),
    version({ asset_id: "a2", version_number: 2 }),
  ];

  it("renders a row per version with its labels and selects the active one by default", () => {
    render(<VersionStrip versions={list} selectedId={null} onSelect={() => {}} title="版本条" />);
    expect(screen.getByText("V1")).toBeTruthy();
    expect(screen.getByText("V2")).toBeTruthy();
    expect(screen.getByText("★ ACTIVE")).toBeTruthy();
    expect(screen.getByText("NEW")).toBeTruthy();
    // default highlight falls on the active row (aria-pressed)
    expect(screen.getByText("V1").closest("button")?.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("V2").closest("button")?.getAttribute("aria-pressed")).toBe("false");
  });

  it("calls onSelect with the asset id when a row is clicked", () => {
    const onSelect = vi.fn();
    render(<VersionStrip versions={list} selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("V2"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("a2");
  });

  it("highlights the row matching the controlled selectedId", () => {
    render(<VersionStrip versions={list} selectedId="a2" onSelect={() => {}} />);
    expect(screen.getByText("V2").closest("button")?.getAttribute("aria-pressed")).toBe("true");
  });

  it("renders an empty state when there are no versions", () => {
    render(<VersionStrip versions={[]} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText("还没有版本。")).toBeTruthy();
  });
});
