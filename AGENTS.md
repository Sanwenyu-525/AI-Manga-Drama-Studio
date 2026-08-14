# AGENTS.md

AI Manga Drama Studio — AI 原生漫剧制作 Studio（桌面级）。

> 本文件是 AI Agent（以及人类协作者）在本仓库工作的**入口文档**。
> 任何实现工作开始前，先读本文档，再按需读取对应的事实源文档。

---

## 1. 项目定位

**AI-native Manga Drama Production Studio**：以 AI Agent 为核心交互方式，以结构化项目系统（Project State）为记忆，以 Workflow Engine 为执行系统，以 ComfyUI 和生成模型为渲染后端的 AI 原生漫剧生产平台。

- 它不是聊天机器人，不是 ComfyUI 套壳。
- 核心资产 = **Project State + Production Graph + Workflow Engine**。
- Agent 负责决策（WHAT），Studio Service 负责执行（HOW）。
- 当前处于 **MVP 0.1**：打通 小说导入 → AI 分析 → Scene → Shot → Storyboard → AI Director 修改 → ComfyUI 生成 → Asset/Version 回填 的完整闭环。

---

## 2. 文档地图（事实源，先读再写）

| 文档 | 内容 | 何时使用 |
|---|---|---|
| `docs/prd-v0.1.md` | 需求定义、用户、产品定位 | 任何功能决策 |
| `docs/architecture-v0.1.md` | 总体架构、依赖关系、开发顺序 | 架构讨论 |
| `docs/database-v0.1.md` | 数据库 / ER 模型（MVP 三轮建表） | 建表、模型设计 |
| `docs/backend-architecture-v0.1.md` | **后端主架构**（LangChain/LangGraph 融合、三 Runtime） | 后端实现 |
| `docs/agent-director-v0.1.md` | AI Director 详细设计（Graph/State/风险/工具） | Agent 实现 |
| `docs/frontend-ux-v0.1.md` | 前端 UX / 信息架构（五区布局、组件、Store） | 前端实现 |
| `docs/api-event-contract-v0.1.md` | **API + Event 契约**（REST/WS/DTO/Error） | 前后端联调、接口实现 |
| `docs/mvp-technical-spec-v0.1.md` | **MVP 任务拆解**（10 Epic / 136 节 / 验收标准） | 当前开发执行清单 |

规则：**文档是事实源；代码与文档冲突时，先改文档（经确认）再改代码。**

---

## 3. 非协商性架构红线

来源：`backend-architecture-v0.1.md` §62、`api-event-contract-v0.1.md` §141。违反即返工。

1. LangChain / LangGraph **不能直接操作数据库**。
2. LangGraph 不能成为 Project State（Checkpoint ≠ Project DB）。
3. Agent **不能直接调用 ComfyUI**；前端也**不能直接调用 ComfyUI**。
4. 业务 Service **不能依赖 LangGraph**（删掉 AI 层，Domain/DB/ComfyUI 必须不受影响）。
5. ShotService 不能知道具体模型；GenerationService 不能知道剧情逻辑；Provider 不能知道 Episode/Scene/Shot 业务语义。
6. API Router 中**禁止业务逻辑**（禁止 `db.query()` 直接写业务）。必须 Router → Service → Repository。
7. 所有外部实现（ComfyUI / LangGraph / LangChain Message）必须先转成 **Studio Domain Contract** 再对外暴露；前端只见 `generation.progress`，永不见 `node_id` / ToolMessage / LangGraph 事件。
8. 长任务（Agent Run / Generation / Analyze）一律 **202 Accepted** + Event 驱动，不阻塞 HTTP。
9. Generation 与 Agent 生命周期严格分离；Generation 永不覆盖历史（版本不可变）。
10. 关键实体（Scene/Shot/Character/Workflow）支持 `revision` 乐观并发（409 Conflict）。
11. 数据库中的 **Project State 是唯一可信状态**；聊天记录、Prompt、LLM Context 都不是事实来源。

---

## 4. 分层与依赖方向

```
UI → Application API → Services → Domain/Repository → SQLite
                         ↑
AI Director (LangGraph) ─┘   （Agent 只能调用 Service）
GenerationService → Provider Interface → ComfyUI / API
```

- Agent 调用 Service，Service 不反向依赖 Agent。
- 业务逻辑不写在 Controller；SQL 不写在 Agent Tool。
- 事件：Service 提交 DB 后由 Event Bus 发布（先 commit 再 publish）。

---

## 5. 当前开发阶段

### 阶段路线（mvp-technical-spec §125）

| Stage | 内容 | 完成标志 |
|---|---|---|
| A | Core Studio（Project/Scene/Shot/Storyboard，无 AI） | 手动可完成创建/编辑，**未完成则不开 Agent** |
| B | AI Planning（小说 → Scene/Shot，Structured Output） | 1000–3000 字 → Scenes + Shots |
| C | Production（ComfyUI + Generation + Version） | 按钮生成 → 图片回填 → V1/V2 共存 |
| D | Agent（AI Director 三工具：get_shot/update_shot/generate_image） | "改成近景再生成" 一条链路稳定 |

### 状态

- ✅ 文档链完成（9 份，见 §2）
- ✅ **Stage A 完成（2026-08）**：monorepo 骨架 + FastAPI/SQLAlchemy/SQLite（Project/Episode/Scene/Shot 领域模型、Repository、Service、REST API、Alembic、事件总线、软删除、revision 乐观并发、pytest 12 项）+ React Studio Shell（五区布局、ProjectExplorer、Storyboard、ShotInspector）+ Tauri 2 壳（cargo check 通过）。无需 AI 即可创建/编辑项目与分镜。
- ✅ **Stage B 完成（2026-08）**：LLMGateway（LangChain `ChatOpenAI` OpenAI-compatible + `FakeLLMGateway`，`STUDIO_LLM_MODE=fake|openai` 切换）、ScenePlan/ShotPlan 结构化输出、Operation 机制（202 + `GET /operations/{id}` + 内存 Store + per-key 锁）、ScriptService（analyze_episode / preview_analysis / generate_shot_plans）、`POST /episodes/{id}/analyze`（202）与 `POST /scenes/{id}/generate-shots`（202）、前端 EpisodePanel（导入小说 → AI 预览 → 确认创建 Scenes）+ Storyboard「AI 生成分镜」按钮 + 轮询刷新。验收：小说 → Scenes + Shots → Storyboard 全链路（pytest 17 项）。
- ✅ **Stage C 完成（2026-08）**：assets/generations/media_versions 模型 + Alembic 迁移；ImageProvider 抽象（`STUDIO_IMAGE_PROVIDER=mock|comfyui`，MockImageProvider 默认 + ComfyUIClient/WorkflowMapper/WS 进度监控 + `workflows/default_image_api.json` 占位符模板）；GenerationService（create/retry/cancel/complete/fail）+ **DB-poll worker**（`generations` 表即队列，崩溃恢复免费，asyncio.Queue 跨线程不安全故弃用）；AssetService（项目相对存储 `EP01_SC03_SH005_IMG_V001`、缩略图、路径安全）；VersionService（**版本不可变**，V1/V2 共存，Set Active 只翻 is_active + shot.active_*_version_id）；API 全套（generations/assets/versions/providers/recent + `POST /providers/comfyui/test`）+ **WS `/api/v1/events` 网关**（EventBus→WS envelope+sequence）；前端 GenerationQueue（BottomDock）+ Inspector 生成按钮/版本浏览/大图预览 + WS EventRouter（Query invalidate）。验收：生成→回填 ShotCard→V2 共存（pytest 22 项）。
- ✅ **Stage D 完成（2026-08）— MVP 闭环达成**：LangGraph Director Graph（Understand→LoadContext→Plan→Execute→Review 五节点，**Structured Planner + Deterministic Executor** 模式，LangGraph 只做编排、不碰 DB/Service 反依赖）；FakeLLM 规则解析（近景/特写/时长/情绪关键词 + 组合意图）+ ProductionIntent/DirectorPlan 结构化 schema；ToolExecutor 三工具（get_shot/update_shot/generate_image，`shot_number:N` 引用解析，走 Service 红线）；ContextService（Selection-aware 最小上下文）；Agent Run 内存存储 + API（`POST /api/v1/agent/director/runs` 202、GET runs/{id}、cancel、resume 占位）+ agent 事件流（run.started/plan.created/tool.started/tool.completed/run.completed/failed）；前端功能版 AI Director 面板（Selection 自动附带、消息流、计划卡片、工具进度）。验收：Scenario A（选中镜头"改成近景"→close_up rev+1）、B（"改成近景再生成"→update+generation 落库）、C（无 selection 不猜、要求澄清）全部通过（pytest 27 项）。
- ⬜ **MVP 之后（Phase 2+）**：接真实 LLM（`STUDIO_LLM_MODE=openai`，LangChain ChatOpenAI 已就绪）；接真实 ComfyUI（`STUDIO_IMAGE_PROVIDER=comfyui`，workflow_mapper/WS 监控已就绪）；审批流（R2/R3 + interrupt + resume + ApprovalRequest）；ChangeSet/Undo；Continuity；Timeline；视频生成；多 Agent；云端

### MVP 三原则

1. **Make the Studio work.** → 2. **Make AI understand it.** → 3. **Make AI operate it.**
先做"没有 AI 的漫剧 Studio"，再接 AI。

---

## 6. 技术栈（MVP）

- **Desktop**：Tauri（MVP 默认；Electron 为备选，决策见 architecture §27–28）
- **Frontend**：React + TypeScript + Vite + Zustand（UI 状态）+ TanStack Query（Server State）+ WebSocket（事件）
- **Backend**：Python + FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic + SQLite（WAL）+ httpx + asyncio
- **AI**：LangChain（模型/Tool/Structured Output）+ LangGraph（Agent 编排，SQLite Checkpointer）
- **Generation**：asyncio.Queue + Generation Worker + ComfyUI Provider（外部 ComfyUI Server，用户自启）
- **不引入**（MVP）：Redis / Celery / Temporal / 多 Agent / MCP

---

## 7. 目标目录结构（monorepo）

```
ai-manga-studio/
├── apps/desktop/        # Tauri 壳
├── frontend/src/        # React（app/components/features/stores/api/events/types/routes）
├── backend/app/         # FastAPI（api/domain/db/repositories/services/agents/llm/providers/generations/events/core）
├── backend/tests/
├── workflows/           # ComfyUI workflow JSON（默认 default_image_api.json）
├── docs/                # 9 份事实源文档
└── README.md
```

后端分层结构见 `backend-architecture-v0.1.md` §9；前端结构见 `frontend-ux-v0.1.md` §79–82。

---

## 8. 关键契约速查

### API（MVP 必须，api-event-contract §142）

```
POST /api/v1/projects            GET /api/v1/projects/{id}/bootstrap
POST /api/v1/projects/{id}/episodes
POST /api/v1/episodes/{id}/analyze     (202 + operation_id)
GET  /api/v1/episodes/{id}/scenes
GET  /api/v1/scenes/{id}/storyboard    (聚合端点，避免 N+1)
GET  /api/v1/scenes/{id}/shots         PATCH /api/v1/shots/{id}
POST /api/v1/shots/{id}/generations    (202)
GET  /api/v1/generations/{id}          POST /api/v1/generations/{id}/retry|cancel
POST /api/v1/agent/director/runs       POST /api/v1/agent/runs/{id}/resume
GET  /api/v1/providers                 POST /api/v1/providers/comfyui/test
GET  /api/v1/health
```

### Event（MVP 必须，api-event-contract §143）

```
shot.updated · agent.run.started · agent.plan.created · agent.approval.required
agent.tool.started · agent.tool.completed · agent.run.completed · agent.run.failed
generation.queued · generation.started · generation.progress · generation.completed · generation.failed
asset.created · provider.connected · provider.disconnected
```

Event 统一 Envelope：`{event_id, event_type, event_version, project_id, entity_type, entity_id, timestamp, sequence, payload}`。

### 错误格式

```json
{ "error": { "code": "SHOT_NOT_FOUND", "message": "...", "details": {}, "request_id": "req_xxx" } }
```

### Agent Tool（MVP 只有 3 个 + 1 可选）

`get_shot` · `update_shot` · `generate_image`（可选 `get_scene_shots`）。Tool 参数/结果必须严格结构化（Pydantic），禁止自然语言参数。

---

## 9. 开发约定

- **DoD**：功能实现 + Error Handling + Loading State + Type Definition + API Contract + Basic Test + Logging。禁止"能跑就算完成"。
- **测试**：后端 pytest（Service 单测 + API 集成测试 + Agent Scenario A/B/C）；必须提供 `MockImageProvider`（固定测试图）与 `FakeLLMGateway`（固定 ScenePlan/ShotPlan/Intent），前端开发不依赖 GPU/真实模型。`APP_ENV=development` 可切换 Mock。
- **日志**：包含 `project_id / shot_id / run_id / generation_id / request_id`。
- **Git**：分支 `main` / `develop` / `feature/*`；一个 commit = 一个明确行为变化，`feat:` / `fix:` 前缀。
- **推送**：本机直连 GitHub 不稳定，仓库本地已配置 `socks5h://127.0.0.1:7897` 代理（`git config --local --get http.proxy` 可查；换端口需更新或 `--unset`）。
- **语言**：代码标识符、commit message 用英文；文档与 UI 文案可中文。

---

## 10. 给 Agent 的工作流程

1. 读本文档 → 定位涉及的事实源文档 → 读对应章节。
2. 明确当前 Stage（§5）与涉及 Epic/任务编号（mvp-spec）。
3. 实现顺序遵守依赖方向（§4）；不跨越 Stage。
4. 改动 API/DB/事件/工具时，同步更新契约文档（§2 表格中的对应文档）。
5. 提交前自查 §3 红线与 §9 DoD。
