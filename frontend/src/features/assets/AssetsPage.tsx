// Assets page (功能版): every produced image with an asset is a material.
// Data comes from GET /generations/recent (real backend state, Stage C); the
// grid shows thumbnails and a lightbox opens the full asset. No fake content.

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, ImageSquare } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { lastProjectId } from "../../lib/lastProject";
import { assetUrl } from "../../lib/mediaUrl";
import { formatDateTime } from "../../lib/format";
import { DownloadButton } from "../../components/DownloadButton";
import { Lightbox } from "../../components/Lightbox";
import type { GenerationRead, Project } from "../../api/types";

interface AssetItem {
  generationId: string;
  assetId: string;
  projectId: string;
  shotId: string | null;
  provider: string;
  model: string | null;
  createdAt: string;
}

export function AssetsPage() {
  const location = useLocation();
  const [preview, setPreview] = useState<AssetItem | null>(null);
  const backProjectId = (location.state as { fromProject?: string } | null)?.fromProject ?? lastProjectId();

  const {
    data: generations,
    isLoading,
    isError,
  } = useQuery({
    queryKey: queryKeys.recentGenerations,
    queryFn: () => api.get<GenerationRead[]>("/generations/recent"),
    refetchInterval: 15_000,
  });
  const { data: projects } = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<Project[]>("/projects"),
  });
  const projectNames = useMemo(() => new Map((projects ?? []).map((p) => [p.id, p.name])), [projects]);

  const assets = useMemo<AssetItem[]>(() => {
    const seen = new Set<string>();
    const items: AssetItem[] = [];
    for (const g of generations ?? []) {
      if (!g.output_asset_id || seen.has(g.output_asset_id)) continue;
      seen.add(g.output_asset_id);
      items.push({
        generationId: g.id,
        assetId: g.output_asset_id,
        projectId: g.project_id,
        shotId: g.shot_id,
        provider: g.provider,
        model: g.model,
        createdAt: g.created_at,
      });
    }
    return items;
  }, [generations]);

  return (
    <div className="project-console">
      <main className="project-home-main">
        <div className="page-heading">
          <div>
            <span className="eyebrow">素材库</span>
            <h1>素材</h1>
            <p>{assets.length} 个已生成素材 · 来自全部项目的生成记录</p>
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

        {isLoading && <div className="home-loading">正在读取素材…</div>}
        {isError && <div className="error-banner">素材读取失败，请确认 Studio Service 已启动。</div>}

        {!isLoading && assets.length === 0 && (
          <div className="home-empty-card">
            <ImageSquare size={32} />
            <h2>还没有生成素材</h2>
            <p>在 Storyboard 里选择镜头并点击「生成图片」，产出会出现在这里。</p>
            {backProjectId && (
              <Link to={`/projects/${backProjectId}`} className="btn secondary">
                <ArrowLeft size={15} /> 返回工作台
              </Link>
            )}
          </div>
        )}

        {assets.length > 0 && (
          <div className="asset-grid">
            {assets.map((item) => (
              <button key={item.assetId} className="asset-card" onClick={() => setPreview(item)} title="点击查看大图">
                <img
                  loading="lazy"
                  src={assetUrl(item.assetId, "thumbnail")}
                  alt={`素材 ${item.assetId.slice(0, 8)}`}
                />
                <span className="asset-index">{shotLabel(item.shotId)}</span>
                <span className="asset-card-meta">
                  <strong>{projectNames.get(item.projectId) ?? "未知项目"}</strong>
                  <small>{formatDateTime(item.createdAt)}</small>
                </span>
              </button>
            ))}
          </div>
        )}
      </main>

      <Lightbox
        open={preview !== null}
        onClose={() => setPreview(null)}
        src={preview ? assetUrl(preview.assetId, "content") : null}
        alt="素材大图预览"
        actions={
          preview && (
            <DownloadButton
              assetId={preview.assetId}
              label={shotLabel(preview.shotId)}
              mediaType="image"
            />
          )
        }
        caption={
          preview && (
            <>
              <strong>
                {projectNames.get(preview.projectId) ?? "项目"} · {shotLabel(preview.shotId)}
              </strong>
              <span>
                {preview.provider}
                {preview.model ? ` · ${preview.model}` : ""} · {formatDateTime(preview.createdAt)}
              </span>
            </>
          )
        }
      />
    </div>
  );
}

function shotLabel(shotId: string | null): string {
  return shotId ? `Shot ${shotId.slice(-4).toUpperCase()}` : "Project Task";
}
