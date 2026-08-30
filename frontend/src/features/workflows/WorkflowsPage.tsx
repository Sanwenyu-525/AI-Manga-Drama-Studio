// Workflows page (功能版, read-only): lists the local ComfyUI workflow template
// catalog served by GET /api/v1/workflows — real files, real preflight metadata.
// Template editing/upload is out of MVP scope; templates live in the repo.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, FlowArrow, GearSix, ImageSquare, TreeStructure } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { lastProjectId } from "../../lib/lastProject";

interface WorkflowRead {
  id: string;
  file: string;
  is_default: boolean;
  output_node_class: string;
  required_placeholders: string[];
  exists: boolean;
  valid_json?: boolean;
  node_count?: number;
  node_types?: string[];
  placeholder_tokens?: string[];
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
            <p>{workflows?.length ?? 0} 个 ComfyUI 模板 · 只读目录（模板入库管理）</p>
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
            <p>将 ComfyUI 的 API 格式模板放入 workflows/ 目录后重启 Studio。</p>
          </div>
        )}

        {workflows && workflows.length > 0 && (
          <div className="workflow-layout">
            <div className="workflow-list">
              {workflows.map((w) => (
                <button
                  key={w.id}
                  type="button"
                  className={`workflow-card ${selected?.id === w.id ? "selected" : ""}`}
                  onClick={() => setSelectedId(w.id)}
                >
                  <span className="workflow-card-head">
                    <GearSix size={17} />
                    <strong>{w.id}</strong>
                    {w.is_default && <span className="badge neutral">默认</span>}
                  </span>
                  <small>
                    {w.file}
                    {w.exists ? "" : "（缺失）"}
                  </small>
                  <span className="workflow-meta">
                    <TreeStructure size={13} /> {w.node_count ?? "—"} 节点
                  </span>
                </button>
              ))}
            </div>
            <section className="workflow-detail">
              {selected ? (
                <>
                  <span className="eyebrow">模板详情</span>
                  <h2>{selected.id}</h2>
                  <div className="workflow-facts">
                    <div>
                      <span>模板文件</span>
                      <strong>{selected.file}</strong>
                    </div>
                    <div>
                      <span>节点数量</span>
                      <strong>{selected.node_count ?? "—"}</strong>
                    </div>
                    <div>
                      <span>输出节点</span>
                      <strong>{selected.output_node_class}</strong>
                    </div>
                    <div>
                      <span>状态</span>
                      <strong>
                        {selected.valid_json === false ? "无效 JSON" : selected.exists ? "可用" : "文件缺失"}
                      </strong>
                    </div>
                  </div>
                  <div className="workflow-section">
                    <span className="field-label">节点类型</span>
                    <div className="node-type-chips">
                      {(selected.node_types ?? []).map((t) => (
                        <span key={t} className="node-chip">
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="workflow-section">
                    <span className="field-label">占位符令牌</span>
                    <div className="node-type-chips">
                      {(selected.placeholder_tokens ?? []).map((t) => (
                        <code key={t} className="token-chip">
                          {t}
                        </code>
                      ))}
                    </div>
                    <p className="muted small">
                      Studio 仅注入 $PROMPT / $SEED / $WIDTH / $HEIGHT 等参数，不感知 KSampler/CLIP 等节点语义（契约
                      §42）。
                    </p>
                  </div>
                  <div className="workflow-section">
                    <span className="field-label">必需占位符（preflight）</span>
                    <p className="muted small">{selected.required_placeholders.join(" · ")}</p>
                  </div>
                </>
              ) : (
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
