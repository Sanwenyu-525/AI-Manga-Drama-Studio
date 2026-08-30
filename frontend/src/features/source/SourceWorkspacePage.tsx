// P1 智能体工作区 — 源内容工作区（目标态落地版）。
// MVP 的「源内容」= 已导入 Project State 的剧集原文（Episode.source_text）与角色/地点库，
// 不是本地文件系统目录 —— 因此本页不伪造 D:\ 路径或文件树，而是呈现：
//   左：源内容库（剧集原文 + 角色/地点库入口）
//   中：选中剧集原文查看器 + 来源映射（本文 → EPxx / n 场 / m 镜，来自 project tree）
//   右：Agent Dock（AI导演，由 Studio 外壳提供）
// 「分析变化/影响分析」需要源目录监听能力，后端未接入 → 锁定并说明，不提供假按钮。

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowsLeftRight,
  BookOpen,
  CaretRight,
  LockSimple,
  Scroll,
  UsersThree,
} from "@phosphor-icons/react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, ProjectBootstrap, ProjectTreeRead } from "../../api/types";

interface SourceDoc {
  episodeId: string;
  episodeNumber: number;
  title: string | null;
  hasSource: boolean;
  charCount: number;
  sceneCount: number;
  shotCount: number;
}

export function SourceWorkspacePage({ projectId }: { projectId?: string }) {
  const params = useParams();
  const pid = projectId ?? params.projectId ?? "";
  const navigate = useNavigate();

  const { data: episodes } = useQuery({
    queryKey: queryKeys.episodes(pid),
    queryFn: () => api.get<Episode[]>(`/projects/${pid}/episodes`),
    enabled: Boolean(pid),
  });
  const { data: tree } = useQuery({
    queryKey: queryKeys.projectTree(pid),
    queryFn: () => api.get<ProjectTreeRead>(`/projects/${pid}/tree`),
    enabled: Boolean(pid),
  });
  const { data: bootstrap } = useQuery({
    queryKey: queryKeys.bootstrap(pid),
    queryFn: () => api.get<ProjectBootstrap>(`/projects/${pid}/bootstrap`),
    enabled: Boolean(pid),
    staleTime: 30_000,
  });

  const docs = useMemo<SourceDoc[]>(() => {
    const shotsByEpisode = new Map(
      (tree?.episodes ?? []).map((ep) => [
        ep.id,
        {
          sceneCount: ep.scenes.length,
          shotCount: ep.scenes.reduce((n, s) => n + s.shots.length, 0),
        },
      ]),
    );
    return (episodes ?? [])
      .slice()
      .sort((a, b) => a.episode_number - b.episode_number)
      .map((ep) => {
        const counts = shotsByEpisode.get(ep.id) ?? { sceneCount: 0, shotCount: 0 };
        return {
          episodeId: ep.id,
          episodeNumber: ep.episode_number,
          title: ep.title,
          hasSource: Boolean(ep.source_text?.trim()),
          charCount: ep.source_text?.length ?? 0,
          ...counts,
        };
      });
  }, [episodes, tree]);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    if (!selectedId && docs.length > 0) setSelectedId(docs[0].episodeId);
  }, [docs, selectedId]);

  const selectedDoc = docs.find((d) => d.episodeId === selectedId) ?? null;
  const selectedEpisode = episodes?.find((e) => e.id === selectedId) ?? null;

  if (!pid) return <div className="workspace-loading">未打开项目</div>;

  return (
    <div className="source-workspace">
      <div className="panel-head">
        <h1>源内容工作区</h1>
        <span className="muted small">智能体工作区 · 剧集原文 → 生产映射（源目录监听接入前以此为准）</span>
      </div>

      <div className="sw-columns">
        {/* ---- 左：源内容库 ---- */}
        <aside className="sw-library" aria-label="源内容库">
          <div className="sw-lib-group">
            <div className="sw-lib-caption">
              <BookOpen size={13} /> 剧集原文
            </div>
            <ul className="sw-doc-list">
              {docs.length === 0 && <li className="muted small ws-pad">还没有剧集 —— 先在剧本视图创建并导入原文。</li>}
              {docs.map((doc) => (
                <li key={doc.episodeId}>
                  <button
                    type="button"
                    className={`sw-doc ${doc.episodeId === selectedId ? "active" : ""} ${doc.hasSource ? "" : "empty"}`}
                    onClick={() => setSelectedId(doc.episodeId)}
                  >
                    <CaretRight size={11} weight="bold" aria-hidden />
                    <span className="sw-doc-name">
                      EP{String(doc.episodeNumber).padStart(2, "0")} · {doc.title || "未命名"}
                    </span>
                    <span className={`sw-doc-state ${doc.hasSource ? "ok" : ""}`}>{doc.hasSource ? "已导入" : "空"}</span>
                  </button>
                </li>
              ))}
            </ul>
            <Link className="text-link sw-lib-more" to={`/projects/${pid}/script`}>
              前往剧本视图导入 / 替换原文 →
            </Link>
          </div>

          <div className="sw-lib-group">
            <div className="sw-lib-caption">
              <UsersThree size={13} /> 设定库
            </div>
            <div className="sw-lib-stats muted small">
              角色 {bootstrap?.characters.length ?? 0} 个 · 场景 {progressSceneCount(tree)} 个
            </div>
            <Link className="text-link" to={`/projects/${pid}/characters`}>
              在「角色」页管理 →
            </Link>
          </div>
        </aside>

        {/* ---- 中：原文查看器 + 来源映射 ---- */}
        <section className="sw-editor" aria-label="原文查看器">
          {selectedEpisode && selectedDoc ? (
            <>
              <div className="sw-editor-head">
                <div>
                  <span className="eyebrow">剧集原文</span>
                  <h2>
                    EP{String(selectedDoc.episodeNumber).padStart(2, "0")} · {selectedDoc.title || "未命名"}
                  </h2>
                  <span className="muted small mono">
                    {selectedDoc.hasSource ? `${selectedEpisode.source_text?.length ?? 0} 字 · 只读` : "尚未导入原文"}
                  </span>
                </div>
              </div>

              {selectedDoc.hasSource ? (
                <article className="sw-prose">{selectedEpisode.source_text}</article>
              ) : (
                <div className="empty-state sw-prose-empty">
                  <Scroll size={30} />
                  <h3>该集还没有原文</h3>
                  <p>在剧本视图粘贴或替换原文后，这里会成为可追溯的源内容。</p>
                  <Link className="btn secondary compact" to={`/projects/${pid}/script`}>
                    去导入
                  </Link>
                </div>
              )}

              {/* 来源映射（P1 SOURCE-TO-PRODUCTION MAPPING，真实 tree 数据） */}
              <div className="sw-mapping">
                <div className="sw-mapping-head">
                  <ArrowsLeftRight size={14} weight="fill" aria-hidden />
                  <strong>来源映射</strong>
                  <span className="muted small">
                    本文已映射到 EP{String(selectedDoc.episodeNumber).padStart(2, "0")} / {selectedDoc.sceneCount} 场 /{" "}
                    {selectedDoc.shotCount} 镜
                  </span>
                </div>
                <div className="sw-mapping-actions">
                  <button
                    type="button"
                    className="btn secondary compact"
                    disabled={!selectedDoc.sceneCount}
                    title={selectedDoc.sceneCount ? "打开该集剧本（场景列表）" : "先分析出场景"}
                    onClick={() => navigate(`/projects/${pid}/script`)}
                  >
                    打开剧本
                  </button>
                  <button
                    type="button"
                    className="btn secondary compact"
                    disabled={!selectedDoc.shotCount}
                    title={selectedDoc.shotCount ? "在分镜板查看该集镜头" : "先创建场景与分镜"}
                    onClick={() => navigate(`/projects/${pid}/script`)}
                  >
                    查看分镜
                  </button>
                  <span className="sw-lock-note" title="源目录监听与影响分析尚未接入后端；接入后开放">
                    <LockSimple size={12} weight="fill" /> 分析变化（未接入）
                  </span>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state sw-prose-empty">
              <Scroll size={30} />
              <h3>还没有源内容</h3>
              <p>创建剧集并导入小说原文后，这里会显示原文与其到场景/镜头的映射。</p>
              <Link className="btn secondary compact" to={`/projects/${pid}/script`}>
                去剧本视图
              </Link>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function progressSceneCount(tree: ProjectTreeRead | undefined): number {
  return (tree?.episodes ?? []).reduce((n, ep) => n + ep.scenes.length, 0);
}
