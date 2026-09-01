// Provider-facing API helpers — P2-E4-T02（工作流 live 健康检查）首批抽出。
// 此前项目未设集中式 provider API 文件（各组件内联 api.get/post）；本文件沿用同一
// thin-wrapper 约定，session token / 超时 / 错误包装等横切逻辑仍全部由 client.ts
// 承担（不自造 HTTP 处理）。

import { api } from "./client";

/** GET /providers/comfyui/workflows 条目：本地 workflows/ 目录注册的 ComfyUI 模板。 */
export interface ComfyWorkflowEntry {
  id: string;
  filename: string;
  is_default: boolean;
}

/** validate 逐节点结果：ok / 缺节点 / 缺模型 / 断链。 */
export interface ComfyWorkflowNodeCheck {
  node_id: string;
  class_type: string;
  status: "ok" | "missing_node" | "missing_model" | "broken_link";
  detail: string | null;
  missing_choices: string[];
}

/** POST validate 响应 — 200 永不 500，健康与否看 status/ok 字段，不靠抛错表达失败。 */
export interface ComfyWorkflowValidateResult {
  workflow_id: string;
  status: "ok" | "invalid" | "unreachable" | "static_error";
  source: string | null;
  ok: boolean;
  nodes: ComfyWorkflowNodeCheck[];
  missing_nodes: string[];
  /** 形如 "x.safetensors (UNETLoader.unet_name)"。 */
  missing_models: string[];
  broken_links: string[];
  static_error: string | null;
  error: string | null;
}

/** GET /providers/comfyui/workflows — ComfyUI 工作流模板目录。 */
export function listComfyWorkflows(): Promise<{ workflows: ComfyWorkflowEntry[] }> {
  return api.get<{ workflows: ComfyWorkflowEntry[] }>("/providers/comfyui/workflows");
}

/** POST /providers/comfyui/workflows/{id}/validate — 逐节点 live 校验；baseUrl 可覆盖已存地址。 */
export function validateComfyWorkflow(workflowId: string, baseUrl?: string): Promise<ComfyWorkflowValidateResult> {
  return api.post<ComfyWorkflowValidateResult>(
    `/providers/comfyui/workflows/${encodeURIComponent(workflowId)}/validate`,
    baseUrl && baseUrl.trim() ? { base_url: baseUrl.trim() } : {},
  );
}
