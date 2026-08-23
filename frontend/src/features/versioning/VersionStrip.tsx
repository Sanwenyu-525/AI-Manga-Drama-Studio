// VersionStrip — pure presentational version rail (roadmap F041~F050 first batch).
// Displays each version row with a derived badge (ACTIVE / NEW / STALE / …) and lets
// the user select a version via onSelect(assetId). No data fetching, no mutations.
//
// "Latest" is a *view-layer* concept, NOT a backend fact: within each same group
// (grouped by media_type / purpose, ADR-001 §2.2) the highest version_number is
// treated as the newest candidate. is_active / status come straight from the DTO.
import type { AssetVersionRead } from "../../api/types";

export interface VersionBadge {
  /** stable key used for styling and tests */
  kind: string;
  /** human-safe text shown in the strip, e.g. "★ ACTIVE", "NEW", "⚠ STALE" */
  label: string;
  /** css tone class suffix: ok | warn | new | muted */
  tone: "ok" | "warn" | "new" | "muted";
}

// Status -> fallback label for versions that are neither active, latest nor 'stale'
// (ADR-001 §2.1 statuses: ready / processing / stale / missing / corrupted / failed / archived).
const STATUS_LABEL: Record<string, string> = {
  missing: "❌ MISSING",
  archived: "ARCHIVED",
  corrupted: "CORRUPTED",
  failed: "FAILED",
  processing: "PROCESSING",
};

/** Badges to draw for a version. ACTIVE always wins, then STALE; otherwise the newest
 *  (non-active) version of its group is flagged NEW, falling back to a status label. */
export function deriveVersionBadges(version: AssetVersionRead, isNewestInGroup: boolean): VersionBadge[] {
  const labels: VersionBadge[] = [];
  if (version.is_active) {
    labels.push({ kind: "active", label: "★ ACTIVE", tone: "ok" });
  }
  if (version.status === "stale") {
    labels.push({ kind: "stale", label: "⚠ STALE", tone: "warn" });
  } else if (!version.is_active && isNewestInGroup) {
    labels.push({ kind: "latest", label: "NEW", tone: "new" });
  } else {
    const fallback = STATUS_LABEL[version.status];
    if (fallback) labels.push({ kind: version.status, label: fallback, tone: "muted" });
  }
  return labels;
}

/** Newest asset id per version-group (group = same media_type purpose, ADR-001 §2.2). */
export function latestPerGroup(versions: AssetVersionRead[]): Map<string, string> {
  const latest = new Map<string, string>();
  for (const v of versions) {
    const current = latest.get(v.media_type);
    if (
      current === undefined ||
      v.version_number > (versions.find((x) => x.asset_id === current)?.version_number ?? 0)
    ) {
      latest.set(v.media_type, v.asset_id);
    }
  }
  return latest;
}

export interface VersionStripProps {
  versions: AssetVersionRead[];
  selectedId?: string | null;
  onSelect: (assetId: string) => void;
  title?: string;
}

/** Strip of version rows with derived badges. Used by ShotInspector + shared by the
 *  review page's label logic via deriveVersionBadges/latestPerGroup. */
export function VersionStrip({ versions, selectedId, onSelect, title = "版本" }: VersionStripProps) {
  const newest = latestPerGroup(versions);
  return (
    <div className="version-strip">
      {title && <div className="version-strip-title">{title}</div>}
      {versions.length === 0 ? (
        <p className="muted small version-strip-empty">还没有版本。</p>
      ) : (
        <div className="version-row-list">
          {versions.map((version) => {
            const labels = deriveVersionBadges(version, newest.get(version.media_type) === version.asset_id);
            const selected = selectedId === version.asset_id || (selectedId == null && version.is_active);
            return (
              <button
                key={version.id}
                type="button"
                className={`version-row version-strip-row ${selected ? "selected" : ""}`}
                aria-pressed={selected}
                title={`V${version.version_number}`}
                onClick={() => onSelect(version.asset_id)}
              >
                <img
                  className="version-thumb"
                  src={`/api/v1/assets/${version.asset_id}/thumbnail`}
                  alt={`V${version.version_number} thumbnail`}
                />
                <span className="version-label">V{version.version_number}</span>
                {labels.length > 0 && (
                  <span className="version-strip-badges">
                    {labels.map((badge) => (
                      <span key={badge.kind} className={`badge ${badge.tone}`}>
                        {badge.label}
                      </span>
                    ))}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
