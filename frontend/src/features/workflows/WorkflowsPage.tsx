// Workflows page (功能版, read-only): lists the local ComfyUI workflow template
// catalog served by GET /api/v1/workflows — real files, real preflight metadata.
// Template editing/upload is out of MVP scope; templates live in the repo.
//
// 派生信息（纯前端，不改后端契约）：
// - 可用性状态：exists + valid_json + 必需占位符齐全 → 可用；缺必需占位符 → 待修复；
//   无效 JSON / 文件缺失 → 不可用。状态与文字/图标同时展示（DESIGN.md §2）。
// - 占位符分类：schema 已知且 Studio 可注入的令牌（$PROMPT 等）与模板自定义令牌分开，
//   复现 workflow_schema.py 的 IMAGE_PARAMETERS/RESERVED_PARAMETERS（契约 §42）。

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowLeft,
  Circle,
  FlowArrow,
  GearSix,
  ImageSquare,
  Plus,
  TreeStructure,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { lastProjectId } from "../../lib/lastProject";

interface WorkflowRead {
  id: string;
  file: string | null;
  is_default: boolean;
  workflow_type: string;
  active_version_number: number | null;
  file_hash: string | null;
  output_node_class: string;
  required_placeholders: string[];
  exists: boolean;
  valid_json?: boolean;
  node_count?: number;
  node_types?: string[];
  placeholder_tokens?: string[];
}

// Studio schema 已知会注入的参数令牌（workflow_schema.py IMAGE_PARAMETERS）。
const INJECTABLE_TOKENS = new Set([
  "$PROMPT",
  "$NEGATIVE_PROMPT",
  "$SEED",
  "$WIDTH",
  "$HEIGHT",
  "$REFERENCE_IMAGE",
  "$CHECKPOINT",
]);

// 预留的视频参数（RESERVED_PARAMETERS，MVP 图片链路不注入）。
const RESERVED_TOKENS = new Set(["$DURATION", "$RESOLUTION"]);
const KNOWN_TOKENS = new Set([...INJECTABLE_TOKENS, ...RESERVED_TOKENS]);

type WorkflowStatusKind = "ok" | "warn" | "error";

interface WorkflowStatus {
  kind: WorkflowStatusKind;
  label: string;
}

function workflowStatus(w: WorkflowRead): WorkflowStatus {
  if (!w.exists) return { kind: "error", label: "文件缺失" };
  if (w.valid_json === false) return { kind: "error", label: "无效 JSON" };
  const missingRequired = (w.required_placeholders ?? []).filter(
    (token) => !(w.placeholder_tokens ?? []).includes(token),
  );
  if (missingRequired.length > 0) return { kind: "warn", label: `缺少 ${missingRequired.length} 个必需占位符` };
  return { kind: "ok", label: "可用" };
}

function workflowTypeLabel(type: string): string {
  if (type === "image") return "图片";
  if (type === "video") return "视频";
  return type || "—";
}

function shortHash(hash: string | null): string {
  return hash ? hash.slice(0, 8) : "—";
}

export function WorkflowsPage() {
  const location = useLocation();
  const backProjectId = (location.state as { fromProject?: string } | null)?.fromProject ?? lastProjectId();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const {
    data: workflows,
    isLoading,
    isError,
  } = useQuery({
    queryKey: queryKeys.workflows,
    queryFn: () => api.get<WorkflowRead[]>("/workflows"),
  });
  // 未手动选择时默认选中第一个模板，避免右侧详情长期空置。
  const selected = workflows?.find((w) => w.id === selectedId) ?? workflows?.[0] ?? null;

  return (
    <div className="project-console">
      <main className="project-home-main">
        <div className="page-heading">
          <div>
            <span className="eyebrow">工作流目录</span>
            <h1>工作流</h1>
            <p>
              {workflows?.length ?? 0} 个 ComfyUI 模板 · 只读目录
              {workflows?.some((w) => workflowStatus(w).kind !== "ok") ? " · 存在待修复模板" : " · 全部可用"}
            </p>
          </div>
          {backProjectId ? (
            <Link to={`/projects/${backProjectId}`} className="btn secondary compact">
              <ArrowLeft size={15} /> 返回工作台
            </Link>
          ) : (
            <Link to="/" className="btn secondary compact">
              <ArrowLeft size={15} /> 返回项目
            </Link>
          )}
        </div>

        {isLoading && <div className="home-loading">正在读取工作流…</div>}
        {isError && <div className="error-banner">工作流读取失败，请确认 Studio Service 已启动。</div>}

        {!isLoading && (!workflows || workflows.length === 0) && (
          <div className="home-empty-card">
            <FlowArrow size={32} />
            <h2>还没有工作流模板</h2>
            <p>将 ComfyUI 的 API 格式模板放入 workflows/ 目录后重启 Studio，会自动注册到目录。</p>
          </div>
        )}

        {workflows && workflows.length > 0 && (
          <div className="workflow-layout">
            <div className="workflow-list">
              {workflows.map((w) => {
                const status = workflowStatus(w);
                return (
                  <button
                    key={w.id}
                    type="button"
                    aria-pressed={selected?.id === w.id}
                    className={`workflow-card ${selected?.id === w.id ? "selected" : ""}`}
                    onClick={() => setSelectedId(w.id)}
                  >
                    <span className="workflow-card-head">
                      <GearSix size={17} />
                      <strong>{w.id}</strong>
                      {w.is_default && <span className="badge neutral">默认</span>}
                    </span>
                    <span className="workflow-card-status">
                      <Circle
                        size={7}
                        weight="fill"
                        className={`status-dot ${status.kind === "ok" ? "ok" : status.kind === "warn" ? "warn" : "bad"}`}
                        aria-hidden
                      />
                      {status.label}
                    </span>
                    <small title={w.file ?? undefined}>
                      {w.file ?? "—"}
                      {!w.exists ? "（缺失）" : ""}
                    </small>
                    <span className="workflow-meta">
                      <TreeStructure size={13} /> {w.node_count ?? "—"} 节点 · {workflowTypeLabel(w.workflow_type)}
                    </span>
                  </button>
                );
              })}
            </div>
            <section className="workflow-detail" aria-live="polite">
              {selected ? <WorkflowDetail w={selected} /> : (
                <div className="review-canvas-empty">
                  <ImageSquare size={34} />
                  <p>选择一个模板查看详情</p>
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function WorkflowDetail({ w }: { w: WorkflowRead }) {
  const status = workflowStatus(w);
  const missingRequired = (w.required_placeholders ?? []).filter(
    (token) => !(w.placeholder_tokens ?? []).includes(token),
  );
  const injectable = (w.placeholder_tokens ?? []).filter((t) => INJECTABLE_TOKENS.has(t));
  const custom = (w.placeholder_tokens ?? []).filter((t) => !KNOWN_TOKENS.has(t));

  return (
    <>
      <span className="eyebrow">模板详情</span>
      <div className="workflow-detail-head">
        <h2>{w.id}</h2>
        <span className={`workflow-status-badge ${status.kind}`}>
          <Circle size={8} weight="fill" aria-hidden />
          {status.label}
        </span>
      </div>
      <div className="workflow-facts">
        <div>
          <span>模板文件</span>
          <strong className="mono-ellipsis" title={w.file ?? undefined}>{w.file ?? "—"}</strong>
        </div>
        <div>
          <span>节点数量</span>
          <strong>{w.node_count ?? "—"}</strong>
        </div>
        <div>
          <span>输出节点</span>
          <strong>{w.output_node_class}</strong>
        </div>
        <div>
          <span>类型 / 版本</span>
          <strong>
            {workflowTypeLabel(w.workflow_type)}
            {w.active_version_number ? ` · v${w.active_version_number}` : ""}
          </strong>
        </div>
        <div>
          <span>当前指纹</span>
          <strong className="mono-value" title={w.file_hash ?? undefined}>{shortHash(w.file_hash)}</strong>
        </div>
        <div>
          <span>状态</span>
          <strong>{status.label}</strong>
        </div>
      </div>

      {status.kind === "warn" && missingRequired.length > 0 && (
        <div className="workflow-callout warn">
          模板缺少必需占位符：{missingRequired.join(" · ")}。Studio 在生成时会拒绝注入，请补充后重启再扫描。
        </div>
      )}
      {status.kind === "error" && (
        <div className="workflow-callout error">
          {w.exists ? "模板 JSON 无法解析，生成链路不可用。" : "模板文件不存在，生成链路不可用。"}
        </div>
      )}

      <div className="workflow-section">
        <span className="field-label">节点类型</span>
        {(w.node_types ?? []).length > 0 ? (
          <div className="node-type-chips">
            {(w.node_types ?? []).map((t) => (
              <span key={t} className="node-chip">
                {t}
              </span>
            ))}
          </div>
        ) : (
          <p className="muted small">未解析到节点信息</p>
        )}
      </div>

      <div className="workflow-section">
        <span className="field-label">占位符令牌 · Studio 可注入（{injectable.length}）</span>
        {injectable.length > 0 ? (
          <div className="node-type-chips">
            {injectable.map((t) => (
              <code key={t} className="token-chip injectable">
                {t}
              </code>
            ))}
          </div>
        ) : (
          <p className="muted small">模板未使用任何 Studio 注入参数</p>
        )}
        <p className="muted small">
          Studio 注入 $PROMPT / $SEED / $WIDTH / $HEIGHT / $NEGATIVE_PROMPT 等参数，不感知 KSampler/CLIP
          等节点语义（契约 §42）。
        </p>
      </div>

      {custom.length > 0 && (
        <div className="workflow-section">
          <span className="field-label">自定义令牌 · Studio 不注入（{custom.length}）</span>
          <div className="node-type-chips">
            {custom.map((t) => (
              <code key={t} className="token-chip custom">
                {t}
              </code>
            ))}
          </div>
          <p className="muted small">这些令牌不在 Studio 注入契约内，需要模板自带默认值或由外部运行时提供。</p>
        </div>
      )}

      <div className="workflow-section">
        <span className="field-label">必需占位符（preflight）</span>
        <p className="muted small">
          {(w.required_placeholders ?? []).join(" · ") || "— 无"}
          {missingRequired.length > 0 && (
            <WarnNote missing={missingRequired} />
          )}
        </p>
      </div>

      <div className="workflow-detail-foot">
        <Plus size={13} />
        添加新模板：将 API 格式 JSON 放入 workflows/ 目录，重启 Studio 后自动注册（含版本快照）。
      </div>
    </>
  );
}

function WarnNote({ missing }: { missing: string[] }) {
  if (missing.length === 0) return null;
  return (
    <span className="warn-inline">
      {" "}· 缺失：{missing.join(", ")}
    </span>
  );
}