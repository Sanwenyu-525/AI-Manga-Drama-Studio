// P6-T016 Asset Browser + P6-T017 Asset Inspector — a project-scoped media gallery
// rendered in the studio workspace (/projects/:projectId/assets). The data is
// aggregated client-side from the tree + shot versions + character/location masters
// (see useProjectAssetLibrary for the source rationale and its limitation). The
// inspector pulls the asset's provenance detail on selection and reuses
// ProvenancePanel for the deep-dive drawer.
import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle, ImageSquare, TreeStructure, VideoCamera, UsersThree, MapPin, SquaresFour, X, Star, FileImage } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import { ProvenancePanel } from "../provenance/ProvenancePanel";
import type { ProvenanceRead } from "../../api/types";
import { useProjectAssetLibrary, type AssetSource, type ProjectAssetEntry } from "./useProjectAssetLibrary";

type TypeFilter = "all" | "image" | "video" | "storyboard" | "character" | "location";

const FILTERS: { key: TypeFilter; label: string; icon: ReactNode }[] = [
  { key: "all", label: "全部", icon: <ImageSquare size={14} /> },
  { key: "image", label: "图片", icon: <FileImage size={14} /> },
  { key: "video", label: "视频", icon: <VideoCamera size={14} /> },
  { key: "storyboard", label: "分镜", icon: <SquaresFour size={14} /> },
  { key: "character", label: "角色", icon: <UsersThree size={14} /> },
  { key: "location", label: "地点", icon: <MapPin size={14} /> },
];

const SOURCE_LABEL: Record<AssetSource, string> = {
  storyboard: "分镜生成",
  character: "角色参考",
  location: "地点参考",
};

export function AssetBrowserView({ projectId }: { projectId: string }) {
  const { assets, isLoading } = useProjectAssetLibrary(projectId);
  const [filter, setFilter] = useState<TypeFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [provenanceOpen, setProvenanceOpen] = useState(false);

  const filtered = useMemo(() => {
    return assets.filter((a) => {
      if (filter === "all") return true;
      if (filter === "image") return a.mediaType === "image";
      if (filter === "video") return a.mediaType === "video";
      return a.source === filter;
    });
  }, [assets, filter]);

  const selected = assets.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="asset-browser">
      <header className="asset-browser-head">
        <div>
          <span className="eyebrow">ASSET BROWSER</span>
          <h1>项目媒体库</h1>
          <p className="muted">{filtered.length} 个资产{isLoading ? " · 正在聚合…" : ""}</p>
        </div>
        <div className="asset-filters" role="tablist" aria-label="资产类型筛选">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={filter === f.key}
              className={"asset-filter" + (filter === f.key ? " active" : "")}
              onClick={() => setFilter(f.key)}
            >
              {f.icon} {f.label}
            </button>
          ))}
        </div>
      </header>

      {isLoading && <div className="home-loading">正在聚合项目资产…</div>}
      {!isLoading && filtered.length === 0 && (
        <div className="home-empty-card">
          <ImageSquare size={34} />
          <h2>这个视图还没有资产</h2>
          <p>先给镜头生成图片，或为角色/地点设置 MASTER 参考图。</p>
        </div>
      )}

      {!isLoading && filtered.length > 0 && (
        <div className="asset-grid">
          {filtered.map((item) => (
            <button
              key={item.id}
              className={"asset-card" + (item.id === selectedId ? " selected" : "")}
              onClick={() => { setSelectedId(item.id); setProvenanceOpen(false); }}
              title={item.label + " · V" + item.versionNumber}
            >
              <img loading="lazy" src={`/api/v1/assets/${item.id}/thumbnail`} alt={`资产 ${item.label}`} />
              {item.isMaster && <span className="master-badge asset-master-flag"><Star size={11} weight="fill" /> MASTER</span>}
              {item.isActive && <span className="asset-active-flag"><CheckCircle size={12} /> 当前</span>}
              <span className="asset-index">{item.label}</span>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <AssetInspector entry={selected} open={provenanceOpen} onToggleProvenance={() => setProvenanceOpen((o) => !o)} onClose={() => setProvenanceOpen(false)} onDismiss={() => setSelectedId(null)} />
      )}
    </div>
  );
}

function AssetInspector({
  entry,
  open,
  onToggleProvenance,
  onClose,
  onDismiss,
}: {
  entry: ProjectAssetEntry;
  open: boolean;
  onToggleProvenance: () => void;
  onClose: () => void;
  onDismiss: () => void;
}) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.provenance(entry.id),
    queryFn: () => api.get<ProvenanceRead>(`/assets/${entry.id}/provenance`),
  });
  const asset = data?.asset;

  return (
    <aside className="asset-inspector" aria-label="资产详情">
      <header className="asset-inspector-head">
        <div><span className="eyebrow">ASSET INSPECTOR</span><h2><FileImage size={16} /> 资产详情</h2></div>
        <button type="button" className="icon-button" aria-label="关闭资产详情" onClick={onDismiss}><X size={16} /></button>
      </header>

      <div className="asset-inspector-preview">
        <img src={`/api/v1/assets/${entry.id}/content`} alt={`资产 ${entry.label}`} />
      </div>

      {isLoading && <p className="muted">正在读取资产信息…</p>}
      {isError && error && <ApiErrorPanel error={error} />}

      {!isLoading && !isError && (
        <div className="provenance-meta asset-inspector-meta">
          <KV k="名称" v={asset?.name ?? entry.label} />
          <KV k="类型" v={asset?.type ?? entry.mediaType} />
          <KV k="来源" v={asset?.source_type ?? SOURCE_LABEL[entry.source]} />
          <KV k="版本" v={entry.versionNumber ? `V${entry.versionNumber}` : "—"} />
          <KV k="状态" v={asset?.status ?? (entry.isMaster ? "MASTER" : entry.isActive ? "active" : "stale")} />
          <KV k="尺寸" v={dimension(asset?.width, asset?.height)} />
          <KV k="文件" v={asset?.mime_type ?? "—"} mono />
          <KV k="校验和" v={entry.checksum ? entry.checksum.slice(0, 16) : "—"} mono />
          {entry.isMaster && <KV k="角色" v="★ MASTER 参考" />}
        </div>
      )}

      <div className="asset-inspector-actions">
        <button type="button" className="btn secondary compact" onClick={onToggleProvenance} aria-expanded={open} disabled={!data}>
          <TreeStructure size={15} /> {open ? "收起溯源" : "查看溯源"}
        </button>
      </div>

      <ProvenancePanel assetId={entry.id} label={`V${entry.versionNumber}`} open={open} onClose={onClose} />
    </aside>
  );
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="provenance-kv"><span>{k}</span><strong className={mono ? "mono" : ""}>{v}</strong></div>
  );
}

function dimension(width: number | null | undefined, height: number | null | undefined): string {
  if (width != null && height != null) return `${width} × ${height}`;
  return "—";
}
