// Phase 9 (P9-E2/E3) Timeline Workspace.
// Tracks (VIDEO/VOICE/MUSIC/SUBTITLE) + clip drag/trim + replace-version + preview + render/export.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowsClockwise,
  DownloadSimple,
  FilmStrip,
  Image as ImageIcon,
  ListBullets,
  MagicWand,
  Play,
  Plus,
  Rows,
  Trash,
  VideoCamera,
  X,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import type {
  AssetVersionRead,
  FinalVideoRead,
  Timeline,
  TimelineClip,
  TimelineRenderRead,
  TimelineTrack,
} from "../../api/types";
import {
  clipDuration,
  formatTime,
  pxToSeconds,
  secondsToPx,
  shiftedClip,
  snapTime,
  trimLeft,
  trimRight,
} from "./timelineMath";

const TRACK_LABELS: Record<string, string> = {
  VIDEO: "视频",
  VOICE: "对白",
  MUSIC: "音乐",
  SFX: "音效",
  SUBTITLE: "字幕",
};
const TRACK_ORDER = ["VIDEO", "VOICE", "MUSIC", "SFX", "SUBTITLE"];
const DEFAULT_ZOOM = 80;
const DEFAULT_CLIP_LEN = 3;

type DragMode = "move" | "left" | "right" | null;

interface DragState {
  clipId: string;
  mode: Exclude<DragMode, null>;
  startX: number;
  baseStart: number;
  baseEnd: number;
}

export function TimelineView({ projectId, episodeId }: { projectId: string; episodeId: string }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<TimelineClip | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const [overrides, setOverrides] = useState<Record<string, { start_time: number; end_time: number }>>({});
  const [pxPerSec, setPxPerSec] = useState(DEFAULT_ZOOM);
  const [playhead, setPlayhead] = useState<number>(0);
  const [sideTab, setSideTab] = useState<"clip" | "preview" | "media">("clip");
  const [previewTs, setPreviewTs] = useState(0);
  const [addToStart, setAddToStart] = useState<number | null>(null);

  const { data: timeline, isLoading, error } = useQuery({
    queryKey: queryKeys.timeline(episodeId),
    queryFn: () => api.get<Timeline>("/episodes/" + episodeId + "/timeline"),
    enabled: Boolean(episodeId),
  });

  const { data: finalVideo } = useQuery({
    queryKey: queryKeys.finalVideo(episodeId),
    queryFn: () => api.get<FinalVideoRead>("/episodes/" + episodeId + "/final-video"),
    enabled: Boolean(episodeId),
    retry: false,
  });

  const videoClipCount = useMemo(() => {
    if (!timeline) return 0;
    const videoTrack = timeline.tracks.find((t) => t.track_type === "VIDEO");
    if (!videoTrack) return 0;
    return timeline.clips.filter((c) => c.track_id === videoTrack.id && c.enabled).length;
  }, [timeline]);

  const createTimeline = useMutation({
    mutationFn: () => api.post<Timeline>("/episodes/" + episodeId + "/timeline"),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.timeline(episodeId) }),
  });

  const sequence = useMutation({
    mutationFn: (timelineId: string) => api.post<Timeline>("/timelines/" + timelineId + "/sequence-from-shots"),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.timeline(episodeId) }),
  });

  const render = useMutation({
    mutationFn: (timelineId: string) => api.post<TimelineRenderRead>("/timelines/" + timelineId + "/render"),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.timeline(episodeId) }),
  });

  const duration = Math.max(timeline?.duration ?? 0, 0.1);
  const totalWidth = duration * pxPerSec;

  const visibleClips = useMemo(() => {
    if (!timeline) return [];
    return timeline.clips.map((c) => (overrides[c.id] ? { ...c, ...overrides[c.id] } : c));
  }, [timeline, overrides]);

  const commitOverride = useCallback(
    (clipId: string) => {
      const ov = overrides[clipId];
      if (!ov) return;
      setOverrides((prev) => {
        const { [clipId]: _drop, ...rest } = prev;
        return rest;
      });
      void api
        .patch<TimelineClip>("/timeline-clips/" + clipId, {
          patch: { start_time: ov.start_time, end_time: ov.end_time },
        })
        .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.timeline(episodeId) }))
        .catch(() => queryClient.invalidateQueries({ queryKey: queryKeys.timeline(episodeId) }));
    },
    [overrides, queryClient, episodeId],
  );

  // global pointer listeners while dragging
  useEffect(() => {
    if (!dragRef.current || !timeline) return;
    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const delta = pxToSeconds(event.clientX - drag.startX, pxPerSec);
      setOverrides((prev) => {
        const clip = timeline.clips.find((c) => c.id === drag.clipId);
        if (!clip) return prev;
        let range: { start_time: number; end_time: number };
        if (drag.mode === "left") range = trimLeft({ start_time: drag.baseStart, end_time: drag.baseEnd }, delta);
        else if (drag.mode === "right") range = trimRight({ start_time: drag.baseStart, end_time: drag.baseEnd }, delta);
        else range = shiftedClip({ start_time: drag.baseStart, end_time: drag.baseEnd }, delta, Math.max(duration, clip.end_time));
        return { ...prev, [clip.id]: { start_time: range.start_time, end_time: range.end_time } };
      });
    };
    const onUp = () => {
      if (!dragRef.current) return;
      const clipId = dragRef.current.clipId;
      dragRef.current = null;
      commitOverride(clipId);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dragRef, timeline, pxPerSec, duration, commitOverride]);

  const startDrag = (event: React.PointerEvent, clip: TimelineClip, mode: Exclude<DragMode, null>) => {
    if (mode !== "move" && clip.asset?.type !== "image") return; // trims are image-clip only
    event.preventDefault();
    dragRef.current = { clipId: clip.id, mode, startX: event.clientX, baseStart: clip.start_time, baseEnd: clip.end_time };
    setSelected(clip);
  };

  if (isLoading) {
    return (
      <div className="empty-state studio-empty">
        <FilmStrip size={34} />
        <p>加载时间线…</p>
      </div>
    );
  }

  if (!timeline) {
    const is404 = error && (error as { code?: string }).code === "ENTITY_NOT_FOUND";
    return (
      <div className="empty-state studio-empty timeline-empty">
        <FilmStrip size={40} />
        <h2>为该集创建时间线</h2>
        <p>把生成好的镜头排成一条可预览、可导出的整集时间线（自动建 VIDEO / VOICE / MUSIC / SUBTITLE 四条轨道）。</p>
        {error && !is404 ? <ApiErrorPanel error={error} /> : null}
        <div className="timeline-empty-actions">
          <button className="btn primary" disabled={createTimeline.isPending} onClick={() => createTimeline.mutate()}>
            <Plus size={15} weight="bold" /> {createTimeline.isPending ? "创建中…" : "创建时间线"}
          </button>
        </div>
      </div>
    );
  }

  const tracks = [...timeline.tracks].sort((a, b) => {
    const ia = TRACK_ORDER.indexOf(a.track_type);
    const ib = TRACK_ORDER.indexOf(b.track_type);
    return ((ia < 0 ? 9 : ia) - (ib < 0 ? 9 : ib)) || a.order_index - b.order_index;
  });

  return (
    <div className="timeline-workspace">
      <header className="timeline-toolbar">
        <div className="timeline-title-group">
          <span className="eyebrow">EPISODE TIMELINE</span>
          <h1>时间线</h1>
          <span className={"timeline-status status-" + timeline.status.toLowerCase()}>{timeline.status}</span>
          <span className="muted">
            {" "}
            {formatTime(duration)} · {pxPerSec}px/s
          </span>
        </div>
        <div className="timeline-actions">
          <div className="seg-control" role="group" aria-label="时间轴缩放">
            {[30, 60, 100, 160, 240].map((z) => (
              <button key={z} className={pxPerSec === z ? "active" : ""} onClick={() => setPxPerSec(z)} title={String(z) + "px/秒"}>
                {z}
              </button>
            ))}
          </div>
          <button
            className="btn"
            disabled={!videoClipCount && !(timeline.clips.length === 0)}
            title="按镜头顺序自动排到 VIDEO 轨（含字幕轨）"
            onClick={() => sequence.mutate(timeline.id)}
          >
            <MagicWand size={15} /> {sequence.isPending ? "排片中…" : "一键排片"}
          </button>
          <button
            className="btn"
            onClick={() => {
              setSideTab("media");
              setAddToStart(snapTime(playhead));
            }}
            title="把项目素材加入时间线"
          >
            <Plus size={15} /> 添加素材
          </button>
          <button
            className="btn primary"
            disabled={!videoClipCount || render.isPending}
            onClick={() => render.mutate(timeline.id)}
            title="渲染导出整集视频（异步，走生成队列）"
          >
            <Play size={14} weight="fill" /> {render.isPending ? "提交中…" : "渲染 / 导出"}
          </button>
        </div>
      </header>

      {render.isError && (
        <div className="inline-error">
          <ApiErrorPanel error={render.error as never} />
        </div>
      )}

      <div className="timeline-body">
        <div className="timeline-lanes-wrap">
          <div className="timeline-ruler-row">
            <div className="timeline-track-label timeline-ruler-placeholder" />
            <div
              className="timeline-ruler"
              onClick={(e) => {
                const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                setPlayhead(Math.max(0, Math.min(duration, pxToSeconds(e.clientX - rect.left, pxPerSec))));
              }}
            >
              {Array.from({ length: Math.min(Math.ceil(duration) + 1, 400) }, (_, i) => i).map((second) => (
                <span key={second} className="tick" style={{ left: secondsToPx(second, pxPerSec) }}>
                  {second % 5 === 0 || duration <= 10 ? <em>{formatTime(second)}</em> : null}
                </span>
              ))}
              <span className="timeline-playhead" style={{ left: secondsToPx(playhead, pxPerSec) }} />
            </div>
          </div>

          <div className="timeline-lanes">
            {tracks.map((track) => (
              <TrackLane
                key={track.id}
                track={track}
                clips={visibleClips.filter((c) => c.track_id === track.id)}
                pxPerSec={pxPerSec}
                totalWidth={totalWidth}
                selectedId={selected?.id ?? null}
                onSelect={(c) => {
                  setSelected(c);
                  setSideTab("clip");
                }}
                onStartDrag={startDrag}
              />
            ))}
            {tracks.length === 0 && <div className="muted small timeline-no-tracks">还没有轨道</div>}
          </div>
        </div>

        <aside className="timeline-side">
          <div className="timeline-side-tabs" role="tablist">
            <button role="tab" aria-selected={sideTab === "clip"} className={sideTab === "clip" ? "active" : ""} onClick={() => setSideTab("clip")}>
              <ListBullets size={13} /> 片段
            </button>
            <button role="tab" aria-selected={sideTab === "preview"} className={sideTab === "preview" ? "active" : ""} onClick={() => setSideTab("preview")}>
              <VideoCamera size={13} /> 预览
            </button>
            <button role="tab" aria-selected={sideTab === "media"} className={sideTab === "media" ? "active" : ""} onClick={() => setSideTab("media")}>
              <ImageIcon size={13} /> 素材
            </button>
          </div>
          <div className="timeline-side-body">
            {sideTab === "clip" && selected && (
              <ClipInspectorPanel
                key={selected.id}
                clip={(visibleClips.find((c) => c.id === selected.id) ?? selected) as TimelineClip}
                onClose={() => setSelected(null)}
                onChanged={() => void queryClient.invalidateQueries({ queryKey: queryKeys.timeline(episodeId) })}
                onGoPreview={() => setSideTab("preview")}
              />
            )}
            {sideTab === "clip" && !selected && <div className="muted small timeline-side-hint">点击时间线上的片段查看/编辑（拖动位移、两端裁剪、替换版本）。</div>}
            {sideTab === "preview" && (
              <PreviewPanel
                timelineId={timeline.id}
                previewTs={previewTs}
                finalVideo={finalVideo ?? null}
                onRefresh={() => setPreviewTs((t) => t + 1)}
                onRender={() => render.mutate(timeline.id)}
                renderPending={render.isPending}
              />
            )}
            {sideTab === "media" && (
              <MediaLibrary
                projectId={projectId}
                timelineId={timeline.id}
                startTime={addToStart ?? playhead}
                onAdded={() => void queryClient.invalidateQueries({ queryKey: queryKeys.timeline(episodeId) })}
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------- lane

function TrackLane({
  track,
  clips,
  pxPerSec,
  totalWidth,
  selectedId,
  onSelect,
  onStartDrag,
}: {
  track: TimelineTrack;
  clips: TimelineClip[];
  pxPerSec: number;
  totalWidth: number;
  selectedId: string | null;
  onSelect: (clip: TimelineClip) => void;
  onStartDrag: (event: React.PointerEvent, clip: TimelineClip, mode: Exclude<DragMode, null>) => void;
}) {
  return (
    <div className="timeline-track">
      <div className="timeline-track-label">
        <Rows size={13} />
        <span>{track.name || TRACK_LABELS[track.track_type] || track.track_type}</span>
        {track.locked ? <span className="badge amber">锁定</span> : null}
        {track.muted ? <span className="badge">静音</span> : null}
      </div>
      <div className="timeline-lane" style={{ width: totalWidth }} data-track-type={track.track_type}>
        {clips.map((clip) => (
          <ClipBlock
            key={clip.id}
            clip={clip}
            pxPerSec={pxPerSec}
            selected={clip.id === selectedId}
            onSelect={() => onSelect(clip)}
            onStartDrag={onStartDrag}
          />
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------- clip

function ClipBlock({
  clip,
  pxPerSec,
  selected,
  onSelect,
  onStartDrag,
}: {
  clip: TimelineClip;
  pxPerSec: number;
  selected: boolean;
  onSelect: () => void;
  onStartDrag: (event: React.PointerEvent, clip: TimelineClip, mode: Exclude<DragMode, null>) => void;
}) {
  const left = secondsToPx(clip.start_time, pxPerSec);
  const width = secondsToPx(clipDuration(clip), pxPerSec);
  const kind = clip.asset?.type ?? "image";
  return (
    <div
      className={"timeline-clip " + (selected ? "selected " : " ") + (clip.enabled ? "" : "disabled ") + "clip-" + kind}
      style={{ left, width }}
      onPointerDown={(e) => {
        onSelect();
        onStartDrag(e, clip, "move");
      }}
      role="button"
      title={clip.start_time.toFixed(1) + "s – " + clip.end_time.toFixed(1) + "s" + (clip.text ? " · " + clip.text : "")}
    >
      {kind === "video" && clip.asset?.thumbnail_url ? (
        <img className="timeline-clip-thumb" src={clip.asset.thumbnail_url} alt="" draggable={false} />
      ) : null}
      <div className="timeline-clip-body">
        <span className="timeline-clip-label">{clip.shot_id ? "SHOT" : kind.toUpperCase()}</span>
        {clip.asset?.version_number != null && <span className="timeline-clip-v">V{clip.asset.version_number}</span>}
        {clip.text ? <em className="timeline-clip-text">{clip.text}</em> : null}
      </div>
      {kind === "image" && (
        <span
          className="trim-handle left"
          onPointerDown={(e) => {
            e.stopPropagation();
            onSelect();
            onStartDrag(e, clip, "left");
          }}
          title="裁剪左端"
        />
      )}
      {kind === "image" && (
        <span
          className="trim-handle right"
          onPointerDown={(e) => {
            e.stopPropagation();
            onSelect();
            onStartDrag(e, clip, "right");
          }}
          title="裁剪右端"
        />
      )}
    </div>
  );
}

// ----------------------------------------------------------- clip inspector

function ClipInspectorPanel({
  clip,
  onClose,
  onChanged,
  onGoPreview,
}: {
  clip: TimelineClip;
  onClose: () => void;
  onChanged: () => void;
  onGoPreview: () => void;
}) {
  const [start, setStart] = useState(String(clip.start_time.toFixed(1)));
  const [end, setEnd] = useState(String(clip.end_time.toFixed(1)));
  const [sourceIn, setSourceIn] = useState(String((clip.source_in ?? 0).toFixed(1)));

  const { data: versions } = useQuery({
    queryKey: ["shot", "versions", clip.shot_id ?? "none"],
    queryFn: () => api.get<AssetVersionRead[]>("/shots/" + clip.shot_id + "/versions"),
    enabled: Boolean(clip.shot_id),
  });
  const usable = useMemo(
    () => (versions ?? []).filter((v) => v.media_type === (clip.asset?.type ?? "image")),
    [versions, clip.asset?.type],
  );

  const updateClip = (patch: Record<string, number>) => {
    void api
      .patch<TimelineClip>("/timeline-clips/" + clip.id, { patch })
      .then(() => {
        onChanged();
        onGoPreview();
      })
      .catch(() => onChanged());
  };

  const replaceAsset = (assetId: string) => {
    void api
      .post<TimelineClip>("/timeline-clips/" + clip.id + "/replace-asset", { asset_id: assetId })
      .then(() => onChanged())
      .catch(() => onChanged());
  };

  const del = () => {
    void api
      .delete<{ id: string }>("/timeline-clips/" + clip.id)
      .then(() => onChanged())
      .catch(() => onChanged());
  };

  return (
    <div className="clip-inspector">
      <header>
        <h3>片段</h3>
        <button className="icon-button" onClick={onClose} aria-label="关闭">
          <X size={15} />
        </button>
      </header>
      <div className="clip-asset">
        {clip.asset?.thumbnail_url ? (
          <img src={clip.asset.thumbnail_url} alt="" />
        ) : (
          <div className="clip-asset-ph">
            <FilmStrip size={22} />
          </div>
        )}
        <div>
          <strong>{clip.asset?.name ?? "素材"}</strong>
          <span className="muted small">
            {clip.asset?.type} · V{clip.asset?.version_number ?? "?"}
            {clip.shot_id ? " · shot " + clip.shot_id.slice(-6) : ""}
          </span>
        </div>
      </div>
      <dl className="clip-fields">
        <div>
          <dt>开始</dt>
          <dd>
            <input value={start} onChange={(e) => setStart(e.target.value)} onBlur={() => updateClip({ start_time: snapTime(Number(start) || 0) })} />
          </dd>
        </div>
        <div>
          <dt>结束</dt>
          <dd>
            <input value={end} onChange={(e) => setEnd(e.target.value)} onBlur={() => updateClip({ end_time: snapTime(Number(end) || 0) })} />
          </dd>
        </div>
        <div>
          <dt>时长</dt>
          <dd className="muted">{clipDuration(clip).toFixed(1)}s</dd>
        </div>
        <div>
          <dt>源起点</dt>
          <dd>
            <input value={sourceIn} onChange={(e) => setSourceIn(e.target.value)} onBlur={() => updateClip({ source_in: snapTime(Number(sourceIn) || 0) })} />
          </dd>
        </div>
      </dl>
      <div className="clip-versions">
        <h4>替换版本（P9-T012）</h4>
        {clip.shot_id ? (
          usable.length ? (
            <div className="version-options">
              {usable.map((v) => (
                <button key={v.id} className={v.asset_id === clip.asset_id ? "active" : ""} onClick={() => replaceAsset(v.asset_id)}>
                  <strong>V{v.version_number}</strong>
                  {v.is_active ? <em>当前</em> : null}
                  <span className="muted small">{v.status}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="muted small">暂无同类型版本</div>
          )
        ) : (
          <div className="muted small">该片段未关联镜头，无法枚举版本</div>
        )}
      </div>
      <div className="clip-actions">
        <button className="btn danger compact" onClick={del}>
          <Trash size={14} /> 删除片段
        </button>
        <label className="toggle">
          <input
            type="checkbox"
            checked={Boolean(clip.enabled)}
            onChange={() => {
              const next = clip.enabled ? 0 : 1;
              void api
                .patch<TimelineClip>("/timeline-clips/" + clip.id, { patch: { enabled: next } })
                .then(onChanged)
                .catch(onChanged);
            }}
          />
          <span>启用</span>
        </label>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- preview

function PreviewPanel({
  timelineId,
  previewTs,
  finalVideo,
  onRefresh,
  onRender,
  renderPending,
}: {
  timelineId: string;
  previewTs: number;
  finalVideo: FinalVideoRead | null;
  onRefresh: () => void;
  onRender: () => void;
  renderPending: boolean;
}) {
  const previewUrl = "/api/v1/timelines/" + timelineId + "/preview?v=" + previewTs;
  const [previewOk, setPreviewOk] = useState(true);
  return (
    <div className="preview-panel">
      <header>
        <h3>非渲染预览</h3>
        <button className="icon-button" onClick={() => { setPreviewOk(true); onRefresh(); }} title="刷新">
          <ArrowsClockwise size={15} />
        </button>
      </header>
      <div className="preview-frame">
        {previewOk ? (
          <img src={previewUrl} onError={() => setPreviewOk(false)} alt="时间线帧条预览" />
        ) : (
          <div className="empty-state small">暂无素材可预览（先一键排片或添加素材）</div>
        )}
      </div>
      {finalVideo ? (
        <div className="final-video">
          <header>
            <h3>导出产物 FINAL_VIDEO V{finalVideo.version_number ?? 1}</h3>
            <span className="muted small">{(finalVideo.duration ?? 0).toFixed(1)}s</span>
          </header>
          {finalVideo.thumbnail_url ? <img src={finalVideo.thumbnail_url} alt="" /> : null}
          <div className="final-video-actions">
            <a className="btn" href={finalVideo.content_url} target="_blank" rel="noreferrer">
              <DownloadSimple size={14} /> 打开导出文件
            </a>
            <button className="btn" onClick={onRender} disabled={renderPending}>
              <Play size={14} weight="fill" /> 重新渲染
            </button>
          </div>
        </div>
      ) : (
        <div className="final-video empty">
          <h3>还没有导出产物</h3>
          <p className="muted small">点击「渲染 / 导出」把整集时间线编码成视频；进度显示在底部生成队列。</p>
          <button className="btn primary" onClick={onRender} disabled={renderPending}>
            {renderPending ? "提交中…" : "开始渲染"}
          </button>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- media lib

interface MediaItem {
  id: string;
  type: string;
  name: string | null;
  thumbnail_url: string | null;
  version_number: number | null;
  status: string;
}

function MediaLibrary({ projectId, timelineId, startTime, onAdded }: { projectId: string; timelineId: string; startTime: number; onAdded: () => void }) {
  const { data } = useQuery({
    queryKey: queryKeys.projectAssets(projectId, "image"),
    queryFn: () => api.get<{ total: number; items: MediaItem[] }>("/projects/" + projectId + "/assets?asset_type=image&limit=100"),
  });
  const items = data?.items ?? [];
  return (
    <div className="media-library">
      <header>
        <h3>素材库</h3>
        <span className="muted small">点击加入 VIDEO 轨（{startTime.toFixed(1)}s 起）</span>
      </header>
      <div className="media-grid">
        {items.map((a) => (
          <button
            key={a.id}
            className="media-item"
            onClick={() => {
              void addToVideoTrack(timelineId, a.id, startTime).then(onAdded);
            }}
          >
            {a.thumbnail_url ? <img src={a.thumbnail_url} alt="" /> : <div className="media-item-ph"><ImageIcon size={18} /></div>}
            <span>{a.name}</span>
          </button>
        ))}
        {items.length === 0 && <div className="muted small">该项目还没有图片素材，先去分镜生成。</div>}
      </div>
    </div>
  );
}

async function addToVideoTrack(timelineId: string, assetId: string, startTime: number) {
  const timeline = await api.get<Timeline>("/timelines/" + timelineId);
  const videoTrack = timeline.tracks.find((t) => t.track_type === "VIDEO");
  if (!videoTrack) return;
  const onTrack = timeline.clips.filter((c) => c.track_id === videoTrack.id && c.enabled);
  let t = snapTime(Math.max(startTime, 0));
  if (onTrack.some((c) => t < c.end_time)) {
    t = Math.max(...onTrack.map((c) => c.end_time));
  }
  await api.post<TimelineClip>("/timelines/" + timelineId + "/clips", {
    track_id: videoTrack.id,
    asset_id: assetId,
    start_time: t,
    end_time: t + DEFAULT_CLIP_LEN,
  });
}