// P6-T013/T014/T015 — badge derivation for Character/Location visual-version
// libraries. Mirrors the existing version-strip semantics (VersionStrip.tsx) but
// against the entity-version DTOs (CharacterVersion / LocationVersion): a version
// flagged is_master is the authoritative MASTER pointer; otherwise ACTIVE / STALE
// come from status and the newest non-active version is marked NEW.
import type { CharacterVersion, LocationVersion } from "../../api/types";

export type EntityVersion = CharacterVersion | LocationVersion;
export type LibraryKind = "character" | "location";

export interface LibraryBadge {
  /** stable key used for styling and tests */
  kind: string;
  /** human-safe text shown in the UI */
  label: string;
  /** css tone suffix: ok | warn | new | muted */
  tone: "ok" | "warn" | "new" | "muted";
}

const STATUS_LABEL: Record<string, string> = {
  archived: "ARCHIVED",
  missing: "❌ MISSING",
  corrupted: "CORRUPTED",
};

/** Badges for an entity version. MASTER always wins; a stale, master version shows
 *  both ★ MASTER and ⚠ STALE; otherwise ACTIVE, then NEW for the newest, else a
 *  status fallback. */
export function deriveEntityVersionBadges(version: EntityVersion, isNewest: boolean): LibraryBadge[] {
  const labels: LibraryBadge[] = [];
  if (version.is_master) {
    labels.push({ kind: "master", label: "★ MASTER", tone: "ok" });
  } else if (version.status === "active") {
    labels.push({ kind: "active", label: "ACTIVE", tone: "ok" });
  }
  if (version.status === "stale") {
    labels.push({ kind: "stale", label: "⚠ STALE", tone: "warn" });
  } else if (!version.is_master && !version.status.startsWith("active") && isNewest) {
    labels.push({ kind: "latest", label: "NEW", tone: "new" });
  } else {
    const fallback = STATUS_LABEL[version.status];
    if (fallback) labels.push({ kind: version.status, label: fallback, tone: "muted" });
  }
  return labels;
}

/** Highest version_number among the versions (view-layer "newest" concept). */
export function newestVersionId(versions: EntityVersion[]): string | null {
  let newest: EntityVersion | null = null;
  for (const v of versions) {
    if (newest === null || v.version_number > newest.version_number) newest = v;
  }
  return newest ? newest.id : null;
}
