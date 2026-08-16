// P6-T016 Asset Browser + P6-T017 Asset Inspector — a project-scoped media gallery
// rendered in the studio workspace (/projects/:projectId/assets). The grid now lists
// the server-side project assets (GET /projects/{id}/assets, parallel backend task;
// {total, items}, type filter param). The inspector pulls the asset detail from
// GET /assets/{id} and reuses ProvenancePanel for the deep-dive drawer.
import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle, ImageSquare, FileImage, TreeStructure, VideoCamera, UsersThree, MapPin, SquaresFour, X, Star } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import { ProvenancePanel } from "../provenance/ProvenancePanel";
import type { AssetRead } from "../../api/types";
import { useProjectAssetLibrary, type AssetSource } from "./useProjectAssetLibrary";

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
  const [filter, setFilter] = useState<TypeFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [provenanceOpen, setProvenanceOpen] = useState(false);

  // Pass image/video to the server as the type filter; source groups refine client-side.
  const hookFilter = filter === "image" || filter === "video" ? filter : "all";
  const { assets, total, isLoading } = useProjectAssetLibrary(projectId, hookFilter);

  const filtered = useMemo(() => {
    return assets.filter((a) => {
      if (filter === "storyboard") return a.source === "storyboard";
      if (filter === "character") return a.source === "character";
      if (filter === "location") return a.source === "location";
      return true; // all / image / video already handled by server (image/video) or full list (all)
    });
  }, [assets, filter]);

  const selected = assets.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="asset-browser">
      <header className="asset-browser-head">
        <div>
          <span className="eyebrow">ASSET BROWSER</span>
          <h1>项目媒体库</h1>
          <p className="muted">{filtered.length} / {total} 个资产{isLoading ? " · 加载中…" : ""}</p>
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

      {isLoading && <div className="home-loading">正在加载项目资产…</div>}
      {!isLoading && filtered.length === 0 && (
        <div className="home-empty-card">
          <ImageSquare size={34} />
          <h2>这个视图还没有资产</h2>
          <p>先给镜头生成图片，或导入项目素材。</p>
        </div>
      )}

      {!isLoading && filtered.length > 0 && (
        <div className="asset-grid">
          {filtered.map((item) => (
            <button
              key={item.id}
              className={"asset-card" + (item.id === selectedId ? " selected" : "")}
              onClick={() => { setSelectedId(item.id); setProvenanceOpen(false); }}
              title={item.label + (item.versionNumber ? " · V" + item.versionNumber : "")}
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
  entry: { id: string; label: string; mediaType: string; versionNumber: number | null; source: AssetSource; checksum: string | null };
  open: boolean;
  onToggleProvenance: () => void;
  onClose: () => void;
  onDismiss: () => void;
}) {
  // P6: detail from GET /assets/{id} (full AssetRead).
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.asset(entry.id),
    queryFn: () => api.get<AssetRead>(`/assets/${entry.id}`),
  });

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
          <KV k="名称" v={data?.name ?? entry.label} />
          <KV k="类型" v={data?.type ?? entry.mediaType} />
          <KV k="状态" v={statusText(data?.status ?? "ready")} />
          <KV k="版本" v={data?.version_number != null ? `V${data.version_number}` : entry.versionNumber != null ? `V${entry.versionNumber}` : "—"} />
          <KV k="来源" v={data?.source_type ? sourceTypeText(data.source_type) : SOURCE_LABEL[entry.source]} />
          <KV k="尺寸" v={dimension(data?.width, data?.height)} />
          <KV k="文件大小" v={fileSize(data?.file_size)} mono />
          <KV k="文件" v={data?.mime_type ?? "—"} mono />
          <KV k="校验和" v={checksumShort(data?.checksum ?? entry.checksum)} mono />
        </div>
      )}

      <div className="asset-inspector-actions">
        <button type="button" className="btn secondary compact" onClick={onToggleProvenance} aria-expanded={open}>
          <TreeStructure size={15} /> {open ? "收起溯源" : "查看溯源"}
        </button>
      </div>

      <ProvenancePanel assetId={entry.id} label={entry.versionNumber != null ? `V${entry.versionNumber}` : entry.label} open={open} onClose={onClose} />
    </aside>
  );
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="provenance-kv"><span>{k}</span><strong className={mono ? "mono" : ""}>{v}</strong></div>
  );
}

function dimension(width: number | null | undefined, height: number | null | undefined): string {
  if (width != null && height != null) return width + " × " + height;
  return "—";
}

function fileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes < 0) return "—";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function checksumShort(c: string | null | undefined): string {
  return c ? c.slice(0, 16) : "—";
}

function statusText(s: string): string {
  return ({ ready: "就绪", active: "生效", stale: "旧版", missing: "缺失", archiving: "归档中" } as Record<string, string>)[s] ?? s;
}

function sourceTypeText(s: string): string {
  return ({ generated: "生成", imported: "导入", character_master: "角色参考", location_master: "地点参考" } as Record<string, string>)[s] ?? s;
}
