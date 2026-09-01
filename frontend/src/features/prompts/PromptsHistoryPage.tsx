// 提示词历史（P7 lightweight page）：项目级 Prompt 版本库，真实数据来自
// GET /projects/{id}/prompts + GET /prompts/{id}/versions（ADR-002）。
// 渲染为 Studio 工作台画布内的子模块；支持按目标分组、展开查看版本链与当前激活版本。

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CaretDown, Quotes, Star } from "@phosphor-icons/react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { formatDateTime } from "../../lib/format";
import type { PromptRead, PromptVersionRead } from "../../api/types";

const PROMPT_TYPE_LABELS: Record<string, string> = {
  SHOT_IMAGE: "镜头图片",
  SHOT_VIDEO: "镜头视频",
  CHARACTER: "角色",
  SCENE: "场景",
};

export function PromptsHistoryPage({ projectId }: { projectId?: string }) {
  const params = useParams();
  const pid = projectId ?? params.projectId ?? "";
  const {
    data: prompts,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["prompts", "project", pid],
    queryFn: () => api.get<PromptRead[]>(`/projects/${pid}/prompts`),
    enabled: Boolean(pid),
    refetchInterval: 30_000,
  });

  const grouped = useMemo(() => {
    const map = new Map<string, PromptRead[]>();
    for (const prompt of prompts ?? []) {
      const key = prompt.target_type;
      map.set(key, [...(map.get(key) ?? []), prompt]);
    }
    return [...map.entries()];
  }, [prompts]);

  if (!pid) return <div className="workspace-loading">未打开项目</div>;

  return (
    <div className="prompts-page">
      <div className="panel-head">
        <h1>提示词历史</h1>
        <span className="muted small">Prompt Version 追溯 · 新版本通过生成与编辑动作自动产生，历史不可变</span>
      </div>

      {isLoading && <div className="workspace-loading">正在读取提示词…</div>}
      {isError && <ApiErrorPanel error={error as never} />}

      {!isLoading && !isError && (prompts ?? []).length === 0 && (
        <div className="empty-state">
          <Quotes size={32} />
          <h2>还没有提示词</h2>
          <p>首次在镜头检查器中执行图片生成后，对应 Prompt 版本会出现在这里。</p>
        </div>
      )}

      {grouped.map(([targetType, items]) => (
        <section className="prompt-group" key={targetType}>
          <h2 className="prompt-group-title">{PROMPT_TYPE_LABELS[targetType] ?? targetType}</h2>
          <ul className="prompt-list">
            {items.map((prompt) => (
              <PromptRow key={prompt.id} prompt={prompt} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function PromptRow({ prompt }: { prompt: PromptRead }) {
  const [open, setOpen] = useState(false);
  const { data: versions, isLoading } = useQuery({
    queryKey: ["prompts", "versions", prompt.id],
    queryFn: () => api.get<PromptVersionRead[]>(`/prompts/${prompt.id}/versions`),
    enabled: open,
  });
  const targetLabel = prompt.target_id
    ? `${prompt.target_type} ${prompt.target_id.slice(-6).toUpperCase()}`
    : prompt.prompt_type;

  return (
    <li className="prompt-row">
      <button type="button" className="prompt-row-head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <CaretDown size={13} weight="bold" className={`caret ${open ? "" : "collapsed"}`} aria-hidden />
        <span className="mono small">{targetLabel}</span>
        <span className="badge neutral">{prompt.versions_count} 个版本</span>
        <span className="muted small grow ellipsis">{prompt.active_positive_prompt ?? "—"}</span>
        <span className="muted small">{formatDate(prompt.updated_at)}</span>
      </button>

      {open && (
        <ol className="prompt-version-chain">
          {isLoading && <li className="muted small">正在读取版本…</li>}
          {(versions ?? [])
            .slice()
            .sort((a, b) => b.version_number - a.version_number)
            .map((version) => (
              <li key={version.id} className={`prompt-version ${version.is_active ? "active" : ""}`}>
                <span className="mono small">PV{String(version.version_number).padStart(2, "0")}</span>
                {version.is_active ? (
                  <Star size={11} weight="fill" className="accent-icon" aria-label="当前版本" />
                ) : null}
                <span className="muted tiny">{version.model ?? version.provider ?? "—"}</span>
                <span className="muted tiny">{formatDate(version.created_at)}</span>
                {version.positive_prompt && <p className="prompt-text">{version.positive_prompt}</p>}
              </li>
            ))}
        </ol>
      )}
    </li>
  );
}

function formatDate(value: string): string {
  return formatDateTime(value);
}
