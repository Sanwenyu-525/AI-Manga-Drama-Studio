// P8-T020 — Continuity helpers (frontend-ux §47/77-80):
// severity tiers/colors, Chinese field labels for the JSON state shapes, and a stable
// Open Shot / category label for warning cards. Centralized so the Scene Warning badge
// and the Shot Inspector continuity panel share the same taxonomy.

import type { CharacterState, ContinuityState, ContinuityWarning, EnvironmentState, PropState } from "../api/types";

/** Minimal warning shape consumed by severity/count helpers. */
export type SeveritySource = Partial<ContinuityWarning> & { severity?: ContinuityWarning["severity"] | string | null };

/** Highest severity across a warning list (drives the scene badge tier + color). */
export type SeverityTier = "info" | "warning" | "error";

const SEVERITY_ORDER: Record<SeverityTier, number> = { info: 0, warning: 1, error: 2 };

export function severityTier(severity: ContinuityWarning["severity"] | string | undefined | null): SeverityTier {
  return severity === "error" ? "error" : severity === "warning" ? "warning" : "info";
}

/** Rank a tier for ordering / picking the highest. */
export function tierRank(tier: SeverityTier): number {
  return SEVERITY_ORDER[tier];
}

/** Highest tier present in a list ("" when none). */
export function sceneSeverityTier(warnings: SeveritySource[] | undefined | null): SeverityTier | "" {
  let best: SeverityTier | "" = "";
  let bestRank = -1;
  for (const w of warnings ?? []) {
    const t = severityTier(w.severity);
    if (tierRank(t) > bestRank) {
      best = t;
      bestRank = tierRank(t);
    }
  }
  return best;
}

export function countByTier(warnings: SeveritySource[] | undefined | null): Record<SeverityTier, number> {
  const counts: Record<SeverityTier, number> = { info: 0, warning: 0, error: 0 };
  for (const w of warnings ?? []) counts[severityTier(w.severity)]++;
  return counts;
}

/** Chinese label for a warning severity tier. */
export function severityTierLabel(tier: SeverityTier): string {
  return ({ info: "提示", warning: "警告", error: "错误" } as Record<SeverityTier, string>)[tier];
}

/** Whether a warning is still actionable (not acknowledged / fixed). */
export function isOpenWarning(warning: SeveritySource): boolean {
  const status = warning.status?.toLowerCase();
  return status !== "acknowledged" && status !== "fixed";
}

/** Short Chinese label for a warning category. */
export function categoryLabel(category: string | undefined | null): string {
  return (
    (
      {
        costume: "换装",
        prop: "道具",
        position: "位置",
        orientation: "朝向",
        action: "动作",
        emotion: "情绪",
        weather: "天气",
        lighting: "灯光",
        time_of_day: "时段",
        character_version: "角色版本",
        location: "场景地点",
        continuity: "连续性",
      } as Record<string, string>
    )[category?.toLowerCase() ?? ""] ??
    category ??
    "连续性"
  );
}

export const CHARACTER_STATE_LABELS: Record<string, string> = {
  character_id: "角色",
  character_version_id: "版本",
  costume_id: "服装",
  position: "位置",
  orientation: "朝向",
  action: "动作",
  emotion: "情绪",
};

export const ENVIRONMENT_STATE_LABELS: Record<string, string> = {
  location_id: "地点",
  time_of_day: "时段",
  lighting: "灯光",
  weather: "天气",
  mood: "氛围",
};

export const PROP_STATE_LABELS: Record<string, string> = {
  prop_id: "道具",
  holder_character_id: "持有者",
  visible: "可见",
};

/** Format one continuity-state field value for the inspector summary (— when empty). */
export function stateValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") {
    try {
      const json = JSON.stringify(value);
      return json.length > 48 ? json.slice(0, 48) + "…" : json;
    } catch {
      return String(value);
    }
  }
  return String(value);
}

/** Flatten characters from either array or id->state map shape. */
export function characterEntries(state: ContinuityState | null | undefined): Array<[string, CharacterState]> {
  const chars = state?.characters;
  if (Array.isArray(chars)) {
    return chars.map((c) => [c.character_id ?? "", c] as [string, CharacterState]).filter(([id]) => id !== "");
  }
  if (chars && typeof chars === "object") {
    return Object.entries(chars as Record<string, CharacterState>);
  }
  return [];
}

/** Flatten props from either array or id->state map shape. */
export function propEntries(state: ContinuityState | null | undefined): Array<[string, PropState]> {
  const props = state?.props;
  if (Array.isArray(props)) {
    return props.map((p) => [p.prop_id ?? "", p] as [string, PropState]).filter(([id]) => id !== "");
  }
  if (props && typeof props === "object") {
    return Object.entries(props as Record<string, PropState>);
  }
  return [];
}

export function environmentState(state: ContinuityState | null | undefined): EnvironmentState | null | undefined {
  return state?.environment;
}
