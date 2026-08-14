import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Clock, FolderOpen, Plus, Play, SlidersHorizontal } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { Project } from "../../api/types";

const statusLabel: Record<string, string> = {
  active: "制作中",
  draft: "准备中",
  completed: "已完成",
  archived: "已归档",
};

export function ProjectHome() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const { data: projects, isLoading, isError } = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<Project[]>("/projects"),
  });

  useEffect(() => {
    if (!activeId && projects?.[0]) setActiveId(projects[0].id);
  }, [activeId, projects]);

  const activeProject = useMemo(
    () => projects?.find((project) => project.id === activeId) ?? projects?.[0],
    [activeId, projects],
  );

  return (
    <div className="project-console">
      <header className="console-topbar">
        <Link to="/" className="wordmark">AI MANGA DRAMA STUDIO</Link>
        <nav className="console-nav" aria-label="主导航">
          <span className="active">项目</span>
          <span>素材</span>
          <span>工作流</span>
          <span>设置</span>
        </nav>
        <Link to="/projects/new" className="btn primary compact">
          <Plus size={16} weight="bold" /> 新建项目
        </Link>
      </header>

      <main className="project-home-main">
        <div className="page-heading">
          <div>
            <span className="eyebrow">DIRECTOR'S CONSOLE</span>
            <h1>项目</h1>
            <p>{projects?.length ?? 0} 个项目 · 选择一个项目继续制作</p>
          </div>
          <SlidersHorizontal size={20} aria-hidden />
        </div>

        {isLoading && <div className="home-loading">正在读取项目…</div>}
        {isError && <div className="error-banner">项目读取失败，请确认 Studio Service 已启动。</div>}

        {!isLoading && projects?.length === 0 && (
          <section className="home-empty-card">
            <FolderOpen size={32} />
            <h2>建立第一部漫剧</h2>
            <p>创建项目后导入小说，AI 会把文本拆成场景与镜头。</p>
            <Link to="/projects/new" className="btn primary"><Plus size={16} /> 新建项目</Link>
          </section>
        )}

        {activeProject && (
          <div className="project-overview-grid">
            <aside className="recent-projects-panel">
              <div className="section-kicker">最近项目</div>
              <div className="recent-project-list">
                {projects?.map((project) => (
                  <button
                    key={project.id}
                    className={`recent-project ${project.id === activeProject.id ? "active" : ""}`}
                    onClick={() => setActiveId(project.id)}
                  >
                    <span>
                      <strong>《{project.name}》</strong>
                      <small>{project.aspect_ratio ?? "未设置"} · {project.fps ?? 24} FPS</small>
                    </span>
                    <span className={`project-status status-${project.status}`}>
                      <i /> {statusLabel[project.status] ?? project.status}
                    </span>
                  </button>
                ))}
              </div>
              <Link to="/projects/new" className="panel-footer-link"><Plus size={15} /> 新建另一个项目</Link>
            </aside>

            <section className="project-feature-card">
              <div className="project-cover-wrap">
                <img src="/assets/manga-shot.png" alt="黑白日系写实漫剧镜头" className="project-cover" />
                <span className="cover-caption">{activeProject.aspect_ratio ?? "9:16"}</span>
              </div>
              <div className="project-feature-content">
                <div className="project-title-row">
                  <h2>《{activeProject.name}》</h2>
                  <span className={`project-status status-${activeProject.status}`}>
                    {statusLabel[activeProject.status] ?? activeProject.status}
                  </span>
                </div>
                <p className="project-description">
                  {activeProject.description || "从小说到分镜、生成与版本回填，所有制作状态都保存在 Project State。"}
                </p>

                <div className="project-facts">
                  <div><span>画幅</span><strong>{activeProject.aspect_ratio ?? "9:16"}</strong></div>
                  <div><span>帧率</span><strong>{activeProject.fps ?? 24} FPS</strong></div>
                  <div><span>状态</span><strong>{statusLabel[activeProject.status] ?? activeProject.status}</strong></div>
                  <div><span>最近更新</span><strong>{formatDate(activeProject.updated_at)}</strong></div>
                </div>

                <div className="project-actions">
                  <Link to={`/projects/${activeProject.id}`} className="btn primary">
                    <Play size={16} weight="fill" /> 继续分镜
                  </Link>
                  <Link to={`/projects/${activeProject.id}`} className="btn secondary">
                    打开工作台 <ArrowRight size={16} />
                  </Link>
                </div>

                <div className="recent-activity">
                  <div className="section-kicker">制作流程</div>
                  <div className="activity-row"><Clock size={16} /><span>剧本 → 场景 → 分镜 → 生成 → 版本</span><small>Project State</small></div>
                </div>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}
