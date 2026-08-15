// P6-T013/T014/T015 — badge derivation for Character/Location library versions:
// MASTER always wins, STALE is additive, otherwise ACTIVE / NEW / status fallback.
import { describe, expect, it } from "vitest";
import { deriveEntityVersionBadges, newestVersionId, type EntityVersion } from "../features/libraries/libraryBadges";

function version(partial: Partial<EntityVersion> & { id: string; version_number: number }): EntityVersion {
  return {
    character_id: "char_1",
    location_id: "loc_1",
    asset_id: "ast_" + partial.version_number,
    name: null,
    description: null,
    status: "stale",
    checksum: null,
    is_master: false,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...partial,
  } as unknown as EntityVersion;
}

describe("deriveEntityVersionBadges", () => {
  it("flags the MASTER version with ★ MASTER", () => {
    const badges = deriveEntityVersionBadges(version({ id: "v2", version_number: 2, is_master: true, status: "active" }), false);
    expect(badges.map((b) => b.kind)).toContain("master");
    expect(badges.find((b) => b.kind === "master")?.label).toBe("★ MASTER");
  });

  it("yet still warns a MASTER that became stale (★ MASTER + ⚠ STALE)", () => {
    const badges = deriveEntityVersionBadges(version({ id: "v1", version_number: 1, is_master: true, status: "stale" }), false);
    expect(badges.map((b) => b.kind)).toEqual(["master", "stale"]);
  });

  it("labels a non-master active version ACTIVE", () => {
    const badges = deriveEntityVersionBadges(version({ id: "v1", version_number: 1, status: "active" }), false);
    expect(badges.map((b) => b.kind)).toEqual(["active"]);
    expect(badges[0].label).toBe("ACTIVE");
  });

  it("flags the newest non-active, non-active-status version as NEW", () => {
    const badges = deriveEntityVersionBadges(version({ id: "v3", version_number: 3, status: "ready" }), true);
    expect(badges.map((b) => b.kind)).toContain("latest");
    expect(badges.find((b) => b.kind === "latest")?.label).toBe("NEW");
  });

  it("falls back to a status label for archived versions", () => {
    const badges = deriveEntityVersionBadges(version({ id: "v1", version_number: 1, status: "archived" }), false);
    expect(badges.map((b) => b.label)).toEqual(["ARCHIVED"]);
  });
});

describe("newestVersionId", () => {
  it("resolves the highest version_number", () => {
    const list = [
      version({ id: "v1", version_number: 1 }),
      version({ id: "v3", version_number: 3 }),
      version({ id: "v2", version_number: 2 }),
    ];
    expect(newestVersionId(list)).toBe("v3");
  });

  it("returns null for an empty list", () => {
    expect(newestVersionId([])).toBeNull();
  });
});
