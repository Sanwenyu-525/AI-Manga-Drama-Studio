// ProvenancePanel (P3-T012/T013): an expandable card/drawer for an asset's provenance.
// GET /assets/{asset_id}/provenance → asset summary + producing generation + inputs + retry chain.
// Handles loading / error / empty states; generation.parameters is JSON-string parsed best-effort.

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, DotsThree, FlowArrow, GitFork, ImageSquare, TreeStructure, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import type { GenerationInputRead, ProvenanceRead } from "../../api/types";

interface ProvenancePanelProps {
  /** The asset (version) whose provenance to inspect. */
  assetId: string;
  /** Human label shown in the drawer header, e.g. "V2". */
  label?: string;
  open: boolean;
  onClose: () => void;
}

export function ProvenancePanel({ assetId, label, open, onClose }: ProvenancePanelProps) {
  // Return early BEFORE any query hook so a closed panel needs no QueryClient.
  if (!open) return null;
  return <ProvPanelBody assetId={assetId} label={label} onClose={onClose} />;
}

function ProvPanelBody({ assetId, label, onClose }: { assetId: string; label?: string; onClose: () => void }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.provenance(assetId),
    queryFn: () => api.get<ProvenanceRead>("/assets/" + assetId + "/provenance"),
  });

  return (
    <aside className="provenance-panel" aria-label="资产溯源">
      <header className="provenance-head">
        <div><span className="eyebrow">PROVENANCE</span><h2><TreeStructure size={17} /> 资产溯源{label ? ` · ${label}` : ""}</h2></div>
        <button type="button" className="icon-button" aria-label="关闭溯源" onClick={onClose}><X size={16} /></button>
      </header>

      {isLoading && <p className="muted provenance-loading">正在读取溯源链路…</p>}
      {isError && <div className="provenance-body"><ApiErrorPanel error={error} /></div>}

      {!isLoading && !isError && data && <ProvenanceContent data={data} />}
    </aside>
  );
}

function ProvenanceContent({ data }: { data: ProvenanceRead }) {
  const hasProvenance = !!data.generation || data.inputs.length > 0 || data.retry_of || data.parent_asset_id || data.ancestors.length > 0;
  if (!hasProvenance) {
    return (
      <div className="provenance-body">
        <div className="provenance-empty"><ImageSquare size={30} /><p>这个资产没有溯源记录。</p><span>它可能是直接导入或由系统生成的，未登记对应的生成链路。</span></div>
      </div>
    );
  }

  return (
    <div className="provenance-body">
      {/* asset basic info */}
      <section className="provenance-section">
        <h3>资产</h3>
        <div className="provenance-meta">
          <KV k="资产 ID" v={shortId(data.asset.id)} />
          <KV k="类型" v={data.asset.type ?? "—"} />
          <KV k="状态" v={data.asset.status ?? "—"} />
          <KV k="来源" v={data.asset.source_type ?? "—"} />
          <KV k="版本" v={data.asset.version_number != null ? `V${data.asset.version_number}` : "—"} />
          {data.asset.name && <KV k="名称" v={data.asset.name} />}
        </div>
      </section>

      {/* retry / ancestor chain */}
      {(data.ancestors.length > 0 || data.retry_of || data.parent_asset_id) && (
        <section className="provenance-section">
          <h3>来源链路</h3>
          <div className="provenance-chain">
            {data.ancestors.map((ancestorId) => (<ChainNode key={ancestorId} id={ancestorId} kind="ancestor" />))}
            {data.ancestors.length > 0 && <ChainArrow />}
            {data.retry_of && <ChainNode id={data.retry_of} kind="retry_from" />}
            {data.retry_of && <ChainArrow />}
            <ChainNode id={data.generation?.id ?? "current"} kind="this_generation" />
          </div>
          {data.parent_asset_id && <p className="provenance-note">父资产 <code>{shortId(data.parent_asset_id)}</code>（当前资产由它派生）</p>}
        </section>
      )}

      {/* producing generation block */}
      {data.generation && (
        <section className="provenance-section">
          <h3>生成记录</h3>
          <div className="provenance-generation">
            <div className="provenance-meta">
              <KV k="Generation" v={shortId(data.generation.id)} mono />
              <KV k="类型" v={data.generation.type ?? "—"} />
              <KV k="Provider" v={data.generation.provider ?? "—"} />
              {data.generation.model && <KV k="模型" v={data.generation.model} />}
              {data.generation.workflow_id && <KV k="Workflow" v={data.generation.workflow_id} />}
              {data.generation.prompt_version_id && <KV k="Prompt v" v={shortId(data.generation.prompt_version_id)} mono />}
              <KV k="状态" v={data.generation.status ?? "—"} />
              <KV k="开始" v={formatDate(data.generation.created_at)} />
              {data.generation.completed_at && <KV k="完成" v={formatDate(data.generation.completed_at)} />}
            </div>
            <ParametersPreview raw={data.generation.parameters} />
          </div>
        </section>
      )}

      {/* inputs */}
      <section className="provenance-section">
        <h3>输入 ({data.inputs.length})</h3>
        {data.inputs.length === 0 ? (
          <p className="muted small">无输入记录</p>
        ) : (
          <div className="provenance-inputs">
            {data.inputs.map((input) => <InputRow key={input.id} input={input} />)}
          </div>
        )}
      </section>
    </div>
  );
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="provenance-kv"><span>{k}</span><strong className={mono ? "mono" : ""}>{v}</strong></div>
  );
}

function ChainNode({ id, kind }: { id: string; kind: string }) {
  return (
    <span className={"provenance-chain-node " + kind}><GitFork size={13} />{shortId(id)}</span>
  );
}

function ChainArrow() {
  return <ArrowRight size={14} className="provenance-chain-arrow" />;
}

function InputRow({ input }: { input: GenerationInputRead }) {
  const referenceType = input.reference_type ?? input.input_type;
  return (
    <div className="provenance-input-row">
      <FlowArrow size={15} className="row-icon" />
      <div><strong>{input.role ?? referenceType}</strong><small>{referenceType}<span className="sep">·</span>{input.reference_id ? shortId(input.reference_id) : "—"}</small></div>
      {input.metadata_json && <DotsThree size={15} className="row-more" />}
    </div>
  );
}

function ParametersPreview({ raw }: { raw: string | null }) {
  if (!raw) return null;
  let parsed: unknown = raw;
  try { parsed = JSON.parse(raw); } catch { /* keep raw string */ }
  const text = typeof parsed === "string" ? parsed : JSON.stringify(parsed, null, 2);
  return (
    <details className="provenance-parameters">
      <summary>参数</summary>
      <pre>{text}</pre>
    </details>
  );
}

function shortId(value: string): string {
  return value.length > 8 ? value.slice(0, 8) + "…" : value;
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}