import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Aperture, ArrowLeft, BookOpenText, Check, Cpu, FileText, FilmStrip, ImageSquare } from "@phosphor-icons/react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Episode, Project } from "../../api/types";

type StartMode = "novel" | "script" | "blank" | "storyboard";

export function NewProjectPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("最后一种打法");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [fps, setFps] = useState(24);
  const [startMode, setStartMode] = useState<StartMode>("novel");

  const createProject = useMutation({
    mutationFn: async () => {
      const project = await api.post<Project>("/projects", {
        name: name.trim(),
        aspect_ratio: aspectRatio,
        fps,
        description: "AI 原生漫剧制作项目",
      });
      const episode = startMode === "novel" || startMode === "script"
        ? await api.post<Episode>(`/projects/${project.id}/episodes`, { title: "第 1 集" })
        : undefined;
      return { project, episodeId: episode?.id };
    },
    onSuccess: ({ project, episodeId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
      navigate(episodeId ? `/projects/${project.id}/episodes/${episodeId}/script` : `/projects/${project.id}/script`);
    },
  });

  return (
    <div className="new-project-page">
      <header className="new-project-header">
        <Link to="/" className="icon-button" aria-label="返回项目"><ArrowLeft size={19} /></Link>
        <span className="wordmark"><img src="/assets/logo.png" alt="" className="app-logo" /> AI MANGA DRAMA STUDIO</span>
        <h1>新建项目</h1>
        <span />
      </header>

      <main className="new-project-layout">
        <section className="project-form-column">
          <div className="stepper" aria-label="创建步骤">
            <span className="active">01 项目设置</span><i />
            <span>02 导入</span><i />
            <span>03 AI 分析</span>
          </div>

          <label className="field large-field">
            <span className="field-label">项目名称</span>
            <input value={name} onChange={(event) => setName(event.target.value)} autoFocus />
          </label>

          <div className="field large-field">
            <span className="field-label">画幅比例</span>
            <div className="segmented-control">
              {["9:16", "16:9", "1:1"].map((ratio) => (
                <button type="button" key={ratio} className={aspectRatio === ratio ? "active" : ""} onClick={() => setAspectRatio(ratio)}>
                  {ratio}
                </button>
              ))}
              <span>{aspectRatio === "9:16" ? "1080 × 1920" : aspectRatio === "16:9" ? "1920 × 1080" : "1080 × 1080"}</span>
            </div>
          </div>

          <div className="field large-field">
            <span className="field-label">帧率</span>
            <div className="segmented-control compact-segments">
              {[24, 25, 30].map((value) => (
                <button type="button" key={value} className={fps === value ? "active" : ""} onClick={() => setFps(value)}>{value} FPS</button>
              ))}
            </div>
          </div>

          <div className="field large-field">
            <span className="field-label">默认生成服务</span>
            <div className="provider-chip"><i /> ComfyUI <small>可在项目内切换 Mock</small></div>
          </div>

          <div className="form-divider" />

          <div className="field large-field">
            <span className="field-label">从哪里开始？</span>
            <div className="start-mode-grid">
              <StartModeCard active={startMode === "novel"} onClick={() => setStartMode("novel")} icon={<BookOpenText />} title="导入小说" description="将原文分析为结构化场景。" />
              <StartModeCard active={startMode === "script"} onClick={() => setStartMode("script")} icon={<FileText />} title="导入剧本" description="使用既有对白与动作线。" />
              <StartModeCard active={startMode === "blank"} onClick={() => setStartMode("blank")} icon={<FilmStrip />} title="空白项目" description="从空白场景开始导演。" />
              <StartModeCard active={startMode === "storyboard"} onClick={() => setStartMode("storyboard")} icon={<ImageSquare />} title="已有分镜" description="先建立项目，随后录入镜头。" />
            </div>
          </div>

          {createProject.isError && <p className="error-text">创建失败：{String(createProject.error)}</p>}

          <div className="form-actions">
            <Link to="/" className="btn secondary">取消</Link>
            <button className="btn primary" disabled={!name.trim() || createProject.isPending} onClick={() => createProject.mutate()}>
              {createProject.isPending ? "正在创建…" : startMode === "novel" ? "创建并导入小说" : "创建项目"}
            </button>
          </div>
        </section>

        <aside className="project-preview-panel">
          <div className="preview-frame">
            <img src="/assets/manga-shot.png" alt="项目封面预览" />
            <strong>{name || "未命名项目"}</strong>
          </div>
          <div className="preview-specs">
            <span><Aperture size={17} /> {aspectRatio}</span>
            <span><FilmStrip size={17} /> {fps} FPS</span>
            <span><Cpu size={17} /> ComfyUI</span>
          </div>
          <div className="flow-ribbon">
            <span className="active">{startMode === "novel" ? "小说" : "开始"}</span><b>→</b><span>场景</span><b>→</b><span>分镜</span><b>→</b><span>生成</span>
          </div>
        </aside>
      </main>
    </div>
  );
}

function StartModeCard({ active, onClick, icon, title, description }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string; description: string }) {
  return (
    <button type="button" className={`start-mode-card ${active ? "active" : ""}`} onClick={onClick}>
      <span className="mode-icon">{icon}</span>
      {active && <Check className="mode-check" size={15} weight="bold" />}
      <strong>{title}</strong>
      <small>{description}</small>
    </button>
  );
}
