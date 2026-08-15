import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, CheckCircle, ClockCounterClockwise, ImageSquare, MagicWand, SlidersHorizontal } from "@phosphor-icons/react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { AssetVersionRead, Project, Shot } from "../../api/types";

export function VersionReviewPage() {
  const { projectId = "", shotId = "" } = useParams();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: project } = useQuery({ queryKey: queryKeys.project(projectId), queryFn: () => api.get<Project>(`/projects/${projectId}`) });
  const { data: shot } = useQuery({ queryKey: queryKeys.shot(shotId), queryFn: () => api.get<Shot>(`/shots/${shotId}`) });
  const { data: versions, isLoading } = useQuery({ queryKey: ["versions", shotId], queryFn: () => api.get<AssetVersionRead[]>(`/shots/${shotId}/versions`) });

  useEffect(() => {
    if (!selectedId && versions?.length) setSelectedId((versions.find((version) => version.is_active) ?? versions[0]).id);
  }, [selectedId, versions]);

  const activate = useMutation({
    mutationFn: (versionId: string) => api.post<AssetVersionRead>(`/media-versions/${versionId}/activate`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["versions", shotId] });
      void queryClient.invalidateQueries({ queryKey: ["storyboard"] });
    },
  });

  const selected = versions?.find((version) => version.id === selectedId);
  const active = versions?.find((version) => version.is_active);
  // Back to the shot's own storyboard scene (URL-driven), not just the project root.
  const backToStoryboard = shot?.scene_id
    ? `/projects/${projectId}/storyboard/${shot.scene_id}`
    : `/projects/${projectId}`;

  return (
    <div className="version-review-page">
      <header className="review-topbar">
        <Link to={backToStoryboard} className="icon-button" aria-label="返回分镜"><ArrowLeft size={19} /></Link>
        <div><span className="eyebrow">VERSION REVIEW</span><strong>{project?.name ?? "项目"} · Shot {String(shot?.shot_number ?? 0).padStart(3, "0")}</strong></div>
        <div className="review-top-actions"><span><ClockCounterClockwise size={16} /> 版本不可变</span><Link className="btn secondary compact" to={backToStoryboard}>返回分镜</Link></div>
      </header>

      <main className="version-review-layout">
        <aside className="version-sidebar">
          <div className="version-sidebar-head"><div><span className="eyebrow">GENERATED VERSIONS</span><h1>审片与定版</h1></div><SlidersHorizontal size={19} /></div>
          {isLoading && <p className="muted">正在读取版本…</p>}
          {!isLoading && versions?.length === 0 && <div className="version-empty"><ImageSquare size={30} /><p>这个镜头还没有生成版本。</p><Link to={backToStoryboard} className="btn primary">返回生成图片</Link></div>}
          <div className="version-card-list">
            {versions?.map((version) => (
              <button key={version.id} className={`version-card ${selectedId === version.id ? "selected" : ""}`} onClick={() => setSelectedId(version.id)}>
                <img src={`/api/v1/assets/${version.asset_id}/thumbnail`} alt={`V${version.version_number}`} />
                <span><strong>V{version.version_number}</strong><small>{formatDate(version.created_at)}</small></span>
                {version.is_active && <span className="badge ok"><Check size={12} /> 当前</span>}
              </button>
            ))}
          </div>
        </aside>

        <section className="review-canvas">
          {selected ? (
            <>
              <div className="review-image-stage"><img src={`/api/v1/assets/${selected.asset_id}/content`} alt={`Shot 版本 V${selected.version_number}`} /></div>
              <div className="review-caption"><span>V{selected.version_number}</span><p>{selected.notes || "生成版本 · 原始资产保持不可变"}</p></div>
            </>
          ) : (
            <div className="review-canvas-empty"><ImageSquare size={36} /><p>选择一个版本开始审片</p></div>
          )}
        </section>

        <aside className="review-inspector">
          <span className="eyebrow">DECISION</span>
          <h2>{selected ? `V${selected.version_number}` : "未选择版本"}</h2>
          <div className={`review-status-card ${selected && !selected.is_active ? "candidate" : ""}`}>
            {selected?.is_active ? <><CheckCircle size={20} weight="fill" /><div><strong>当前生效版本</strong><span>Storyboard 已使用此版本</span></div></> : <><MagicWand size={20} /><div><strong>候选版本</strong><span>确认后只切换 active 指针</span></div></>}
          </div>
          <div className="review-meta-list">
            <div><span>镜头</span><strong>Shot {String(shot?.shot_number ?? 0).padStart(3, "0")}</strong></div>
            <div><span>景别</span><strong>{shot?.shot_type ?? "—"}</strong></div>
            <div><span>情绪</span><strong>{shot?.emotion ?? "—"}</strong></div>
            <div><span>生成 ID</span><strong>{selected?.generation_id?.slice(-8) ?? "—"}</strong></div>
          </div>
          <button className="btn primary full" disabled={!selected || selected.is_active || activate.isPending} onClick={() => selected && activate.mutate(selected.id)}>
            {selected?.is_active ? <><Check size={16} /> 已设为当前</> : activate.isPending ? "正在切换…" : "设为当前版本"}
          </button>
          {active && selected && active.id !== selected.id && <p className="review-note">当前为 V{active.version_number}。切换不会删除或覆盖任何历史版本。</p>}
        </aside>
      </main>
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}
