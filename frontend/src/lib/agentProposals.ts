// P7-T020/021 — Director proposal helpers (frontend-ux §71-76):
// normalize the `changes` payload to a flat list of field diffs regardless of which
// backend shape ships, and provide Chinese labels for fields / status / tools.

import type { AgentProposal, AgentProposalChanges, AgentProposalFieldChange } from "../api/types";

/** True when the run's persisted status (either casing) means "waiting on human". */
export function isWaitingHuman(status: string | null | undefined): boolean {
  return status === "WAITING_HUMAN" || status === "waiting_human";
}

/**
 * Normalize a proposal `changes` payload into a flat list of {field, from, to}.
 * Supports both agreed backend shapes:
 *   1. object map   { image_prompt: { from, to } }
 *   2. single item  { field: "image_prompt", from, to }
 */
export function normalizeProposalChanges(changes: AgentProposalChanges | undefined | null): AgentProposalFieldChange[] {
  if (!changes || typeof changes !== "object") return [];
  const record = changes as Record<string, unknown>;

  // Shape 2: a bare { field, from, to } object (single field change). Detect it by
  // the presence of a string "field" key rather than by entry count, because such an
  // object has three keys (field/from/to), not one.
  if (typeof record.field === "string") {
    return [{ field: record.field, from: record.from as unknown, to: record.to as unknown }];
  }

  // Shape 1: { <field>: { from, to } }.
  return Object.entries(record)
    .map(([field, value]) => {
      if (!value || typeof value !== "object") return null;
      const diff = value as { from?: unknown; to?: unknown };
      return { field, from: diff.from as unknown, to: diff.to as unknown };
    })
    .filter((item): item is AgentProposalFieldChange => item !== null);
}

/** Short human label for a proposal's target type ("shot" → "镜头"). */
export function targetTypeLabel(targetType: string | undefined | null): string {
  switch (targetType) {
    case "shot":
      return "镜头";
    case "scene":
      return "场景";
    case "character":
      return "角色";
    default:
      return targetType ?? "目标";
  }
}

/** Short "Shot id" reference shown on a proposal card. */
export function proposalTarget(proposal: AgentProposal): string {
  const id = proposal.target_id ?? "";
  const short = id.length > 4 ? id.slice(-4) : id;
  return targetTypeLabel(proposal.target_type) + " " + (short || "—");
}

/** Chinese label for a proposal status (await + resolved). */
export function proposalStatusLabel(status: AgentProposal["status"] | string | undefined): string {
  switch (status) {
    case "pending":
      return "待审批";
    case "approved":
      return "已批准";
    case "rejected":
      return "已拒绝";
    case "conflict":
      return "冲突";
    default:
      return status ?? "未知";
  }
}

/** Chinese label for a proposal's tool. */
export function proposalToolLabel(tool: string | undefined | null): string {
  switch (tool) {
    case "update_shot":
      return "修改镜头";
    case "get_shot":
      return "读取镜头";
    case "generate_image":
      return "生成图片";
    default:
      return tool ?? "未知工具";
  }
}

/** Chinese field label for a shot field in a diff table. */
export const SHOT_FIELD_LABELS: Record<string, string> = {
  shot_type: "镜头类型",
  camera_angle: "机位角度",
  camera_movement: "运镜",
  lens: "焦段",
  duration: "时长",
  action: "动作",
  emotion: "情绪",
  dialogue: "台词",
  image_prompt: "画面提示词",
  negative_prompt: "负向提示词",
  status: "状态",
  dirty_state: "脏状态",
  character_ids: "出场角色",
  shot_number: "镜头号",
};

export function fieldLabel(field: string): string {
  return SHOT_FIELD_LABELS[field] ?? field;
}

/** Render one value for a diff cell (survives objects / arrays). */
export function renderChangeValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}
