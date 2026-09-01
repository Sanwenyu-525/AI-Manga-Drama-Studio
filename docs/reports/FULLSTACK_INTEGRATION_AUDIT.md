# FULLSTACK_INTEGRATION_AUDIT.md — 全栈联调审计（2026-08-31）

> 审计目标：验证「前端认为系统怎样工作」与「后端实际怎样工作」是否完全一致。
> 配套修复结果见 [FULLSTACK_INTEGRATION_REPORT.md](FULLSTACK_INTEGRATION_REPORT.md)。
> 前置输入：[BACKEND_AUDIT.md](../../BACKEND_AUDIT.md)、[FRONTEND_AUDIT.md](FRONTEND_AUDIT.md)（前两轮单侧审计）。

---

# Executive Summary

对 AI 漫剧工作台执行端到端全栈联调审计：**163 处前端 API 调用 vs 27 个后端路由模块（OpenAPI 168 operations）全量比对**，覆盖 DTO 字段、枚举/状态机、时间格式、Null 语义、异步任务链路、文件 URL/下载、Provider 配置链、错误信封、缓存同步。

**结论：契约总体对齐度高（约 97%），但存在 4 个 P0 断点——全部集中在「前端调用了后端不存在的形状」或「后端返回了前端消费不到的字段」，其中 3 个只在 Tauri 壳（带 session token）或特定筛选路径下才暴露**，属于典型的"浏览器 dev 模式测不出来"的联调问题。本次全部修复并以 live HTTP smoke（14 步主链路）+ 双侧测试套件验证。

# System Architecture

```
Tauri 壳 (apps/desktop, 17820 注入 session token)
  └─ React SPA (frontend, Vite dev 17821 → proxy /api → 17820)
       ├─ api/client.ts (统一 fetch 封装: /api/v1 + X-Session-Token + 30s 超时 + ApiError)
       ├─ TanStack Query (Server State) + Zustand (瞬态: selection/generation/agent/workspace)
       ├─ events/socket.ts (WS /api/v1/events?token=, 序号闸门 + 断线 reconcile)
       └─ lib/mediaUrl.ts (<img>/<video>/<audio> 的 ?token= 透传)
  └─ FastAPI (backend, 127.0.0.1:17820)
       ├─ api/ 27 模块 → services/ 35 → domain/ + repositories/ → SQLite (Alembic 27 迁移)
       ├─ generations/worker (DB-poll 队列, claim/lease/退避重试) + jobs/scheduler
       ├─ providers/ 五类 Protocol (image: mock|comfyui|agnes, video: mock|agnes,
       │   render: auto|mock|ffmpeg, audio: mock|edge, llm: fake|openai)
       ├─ events/bus → ws 网关 (per-connection sequence, 背压 256)
       └─ 文件: {data_dir}/projects/{pid}/... 仅存相对路径, 经 /assets/{id}/content 出口
```

# Frontend Modules

| 模块 | 位置 | 职责 |
|---|---|---|
| Project Home / New | features/project | 项目 CRUD、封面上传、bootstrap/tree 聚合 |
| Script / Episode | features/script | 原文编辑、AI 分析（preview→快照 confirm）、场景创建 |
| Storyboard / Shot | features/storyboard | 分镜网格、镜头检查器、生成入口、版本切换 |
| Generation Queue | features/generation | BottomDock 队列（live WS 瞬态 + /generations/recent 持久态 5s 轮询）、Job 管理 |
| Assets Browser | features/assets | 项目资产库（筛选/检查器/溯源/下载） |
| Timeline | features/timeline | 四轨剪辑、配音、渲染、成片导出 |
| AI Director | features/director | Agent 对话、Proposal 审批、ChangeSet 撤销 |
| Continuity | features/continuity | 连续性警告、重新计算、AI 语义检测/修复 |
| Libraries | features/libraries | 角色/位置/服装/设定文档 + 视觉版本库 |
| Settings | features/settings | LLM/图像/视频/Provider 配置、模型扫描导入、本地探测 |
| Pipeline | features/pipeline | 一键成片（run/confirm/finalize/resume） |
| Prompts / Provenance / Log | features/prompts, provenance, log | Prompt 版本、资产溯源、生产日志 |

# Backend Modules

26 个路由模块（projects/episodes/scenes/shots/characters/locations/costumes/documents/operations/pipelines/generations/llm/image_settings/assets/providers/agents/prompts/provenance/workflows/timelines/continuity/readmodels/jobs/health/WS 网关）+ 35 Service + 五类 Provider + DB-poll 任务系统。详见 [BACKEND_OPTIMIZATION_REPORT.md](../../BACKEND_OPTIMIZATION_REPORT.md)。

# API Contract Matrix

比对方法：前端 163 处 `api.*` 调用点（含请求体字段与响应消费字段）逐条对照后端路由签名 + DTO。**抽样完整矩阵节选**（OK = 方法/路径/请求/响应/状态码全对齐；完整清单见源码审计记录）：

| Frontend 消费点 | Method | Endpoint | Backend | 请求/响应对齐 | 状态 |
|---|---|---|---|---|---|
| ProjectHome / NewProjectPage | POST/GET/PATCH/DELETE | /projects, /projects/{id} | projects.py | ProjectCreate↔{name,aspect_ratio,fps,description}；revision 信封 409 | OK |
| ProjectHome / 各页 | GET | /projects/{id}/bootstrap, /tree | readmodels.py | ProjectBootstrap/ProjectTreeRead | OK |
| EpisodePanel | POST | /episodes/{id}/analyze/preview | episodes.py | 无 body → AnalysisPreview{snapshot_id, plans} | OK |
| EpisodePanel | POST | /episodes/{id}/analyze | episodes.py | {snapshot_id} → 202 {operation_id} | OK |
| StoryboardView | POST | /scenes/{id}/generate-shots | scenes.py | 无 body → 202 {operation_id} | OK |
| ShotInspector | POST | /shots/{id}/generations | generations.py | {type,provider?,workflow_id?,seconds?} → 202 GenerationRead | OK |
| ShotInspector | GET | /shots/{id}/generations, /versions | generations.py | 轮询 + AssetVersionRead[] | OK |
| ShotInspector / VersionReview | POST | /media-versions/{asset_id}/activate | generations.py | legacy 端点 200 | OK |
| GenerationQueue | POST | /generations/{id}/retry, /cancel | generations.py | retry 202（新建行 retry_of）/ cancel 200 | OK |
| GenerationQueue | GET/POST | /projects/{id}/jobs, /jobs/{id}/{pause,resume,cancel,retry} | jobs.py | JobSummaryRead/JobRead | OK |
| AIDirectorPanel | POST | /agent/director/runs | agents.py | {project_id,message,selection:DirectorSelection} → 202 AgentRunRead | OK |
| ProposalReview | GET/POST | /agent/runs/{id}, /proposals, /resume | agents.py | ProposalResumeRequest{decision,proposal_ids} | OK |
| ChangeSetPanel | GET/POST | /agent/change-sets (+/undo, 批量 undo) | agents.py | query run_id/entity_id；UndoRequest{force} | OK |
| TimelineView | 全套 | /timelines/*, /timeline-clips/* | timelines.py | clip PATCH revision 409 守卫；render 202 | OK |
| TimelineView | POST | /timeline-clips/{id}/generate-voiceover | generations.py | {text?,provider?,voice?,rate?} → 202 | OK |
| PipelineBar | POST/GET | /episodes/{id}/pipeline/* | pipelines.py | ConfirmRequest 可省略 body | OK |
| SettingsPage | 全套 | /llm/*, /image/*, /providers/* | llm.py, image_settings.py, providers.py | profiles 返回 {profiles,active_profile_id,task_bindings,task_fallbacks,tasks} 与前端 LLMProfilesResponse 一致 | OK |
| **ContinuityWarningList** | POST | **/agent/continuity/runs** | **agents.py — 不存在** | 前端发送 {scene_id}，后端只有 /agent/continuity/fix{warning_id} | **BROKEN (P0)** |
| **useProjectAssetLibrary** | GET | /projects/{id}/assets**?type=** | assets.py | 后端参数是 **asset_type**；`?type=` 被 FastAPI 静默忽略，筛选失效 | **BROKEN (P0)** |
| **ProjectHome 封面** | img src | /api/v1/projects/{id}/cover | projects.py | 后端返回相对路径，前端未经 mediaUrl() 包 token → Tauri 壳 401 | **BROKEN (P0, 仅壳内)** |
| **TimelineView 预览** | img src | /timelines/{id}/preview?v=… | timelines.py | mediaUrl() 追加 `?token=` 产生双 `?` → token 失效 401 | **BROKEN (P0, 仅壳内)** |
| **AssetBrowserView** | GET | /projects/{id}/assets | assets.py | 前端消费 item.name/source_type 做分组与 MASTER 徽章，后端 AssetListItemRead **不返回这两个字段** | **DEGRADED (P1)** |

后端已实现、前端未接的端点（预留/冗余，不删除）：`GET /shots/{id}/inspector`、`GET /scenes/{id}/editor`、`PATCH /llm/profiles/{id}`、`POST /shots/{id}/image-versions/{aid}/activate`（shot 限定变体）、`GET /generations/{id}/inputs|outputs`、`GET /scenes/{id}/transitions`、`GET /assets/{id}/provenance` 的 ancestors 深链、`POST /projects/{id}/assets/check-missing`。

## Enum / 状态机比对

| 枚举 | 后端 | 前端 | 结论 |
|---|---|---|---|
| Generation status | created/queued/running/retrying/cancelling/completed/failed/cancelled/interrupted（9 值状态机，非法转移 409） | 消费 queued/running/retrying/completed/failed/cancelled/interrupted；`generationStatusText` 全覆盖 | OK |
| Operation status | queued/running/completed/failed | 同（OperationStatus union） | OK |
| Agent run status | created/running/waiting_approval/waiting_human/completed/failed/cancelled/cancelling | 双 casing 兼容（WAITING_HUMAN + waiting_human） | OK |
| Proposal status | pending/approved/rejected/conflict/expired（expired 终态 409） | 同 + expired | OK |
| Provider status | connected/active/unknown/**unavailable** | 映射表含 connected/active/unknown/disconnected/error，**缺 unavailable**（显示英文原文） | **P1 → 已修** |
| Shot/Scene/Episode/Project status | domain/common.py Literal 全集 | 分散消费（statusLabel 等） | OK |
| Timeline track/transition | VIDEO/VOICE/MUSIC/SFX/SUBTITLE；cut/fade/dissolve | 同 | OK |
| 时间格式 | ISO 8601 UTC 字符串（created_at 等） | 字符串直传 formatDateTime | OK（无 Unix/Local 混用） |
| Null 语义 | DTO `str | None`，列表空数组默认 | 对应 `| null` + `?? []` 兜底 | OK |

# Main Business Flows

主链路（用户视角）：**项目 → 剧本导入/原文 → AI 分析（快照确认）→ 场景 → AI 分镜 → 镜头（角色/提示词绑定）→ 图片生成 → 版本/激活 → 时间线排片 → 配音 → 渲染 → 成片预览/下载**；并行链路：AI Director（R0-R3 风险分级 + Proposal 审批 + ChangeSet 撤销）、Continuity（规则 + 语义检测 + 修复提案）、Pipeline 一键成片（断点续跑）。

# Integration Boundaries

1. **鉴权边界**：REST header / 媒体标签 `?token=` / WS `?token=` 三通道（本次修复 2 处媒体标签 token 透传缺陷）。
2. **异步边界**：长任务一律 202 + operation/generation id；前端 operation 轮询（500ms）+ WS 事件双通道；本次为轮询补了失败上限。
3. **文件边界**：唯一出口 `/assets/{id}/content|thumbnail`（FileResponse + Range）；DB 只存项目相对路径。
4. **Provider 边界**：前端选择 canonical id（mock/comfyui/agnes），展示层 id（comfyui_local 等）只作展示；未知 provider 422 fail-fast。

# Integration Problems

## P0（4，全部已修复，验证见配套报告）

1. **Continuity「AI 修复」按钮调用不存在的端点** — 前端 `POST /agent/continuity/runs` {scene_id}，后端无此路由（404 NOT_FOUND 信封），功能整体死路；且 mutation 无 onError，点击后无任何反馈。
2. **资产库类型筛选参数名漂移** — 前端 `?type=`，后端 `asset_type`；FastAPI 静默忽略未知 query 参数 → 图片/视频筛选完全不生效（返回全部）。同页 TimelineView 素材拾取器用的却是正确的 `asset_type`，同仓两种写法并存。
3. **Tauri 壳内项目封面 401** — 后端 cover_url 返回 `/api/v1/projects/{id}/cover`，前端 `<img src>` 直用，未经 `mediaUrl()` 附 token，壳内（session token 启用时）封面必然 401 显示破图。
4. **Tauri 壳内时间线预览 401 + 参数污染** — 预览 URL 自带 `?v={ts}`，`mediaUrl()` 无条件再拼 `?token=` → `...?v=123?token=x`，token 变成 v 参数的一部分；壳内预览 401 且被误导为"暂无素材可预览"。

## P1（6，全部已修复）

5. **资产列表 DTO 缺前端消费字段** — `AssetListItemRead` 无 `name`/`source_type`，导致资产浏览器"角色/场景"来源分组永远为空（全部落 storyboard）、MASTER 徽章永不显示、名称退化为"id 后六位"。
6. **Provider 状态映射缺 `unavailable`** — 后端 `video_mock` 返回 unavailable，前端标签表缺失显示英文原文，无对应 CSS 状态色。
7. **operation 轮询无失败上限** — 后端重启（内存 operation store 丢失）或长时间断网时 500ms 无限重试，按钮永久停留"创建中…"。
8. **TimelineView 创建时间线/一键排片失败完全静默** — 无错误面板（渲染有、创建/排片没有）；另有一处 `as never` 类型断言绕过检查。
9. **Continuity 修复失败静默** — 见 P0-1 的 onError 缺失部分。
10. **（审计确认项）ShotContinuityCard 冗余请求** — 为传 sceneId 给修复调用而额外请求 `GET /shots/{id}`；修复改按 warning_id 后该请求删除。

## P2（记录，未在本次修改）

11. `agent.run.cancelled` WS 事件前端已处理但契约文档事件清单未列（文档漂移）。
12. 前端 GenerationQueue 状态映射含后端不存在的 paused/skipped/dependency_failed 标签（死映射，无害）。
13. `useProjectAssetLibrary` 的 `status === "active"` 死分支（后端只有 ready/missing）。
14. EpisodePanel/AIDirectorPanel 存在绕过 queryKeys.ts 单点约定的手写 query key（`["analysis-snapshot", …]`）。
15. `/assets/{id}/content` 无 `Content-Disposition: attachment` 变体（当前 inline 预览语义 + `<a download>` 同源可用；如需强制下载语义需后端加 `?download=1`）。
16. thumbnail 端点媒体类型硬编码 image/png，渲染 poster 实为 jpg（浏览器容错）。
17. AI Director 刷新后消息流不恢复（agentStore 纯内存，后端无消息持久化端点）——设计层面 Known Limitation。

# Proposed Fixes

全部 P0/P1 修复方案与实施见 [FULLSTACK_INTEGRATION_REPORT.md](FULLSTACK_INTEGRATION_REPORT.md)。核心策略：**优先改消费方、最小修改、零 Breaking Change**（唯一后端改动为 DTO 增量字段，纯 additive）。

# Risks

- 本次未触碰 Rust 壳（无变更）；后端改动仅 2 个文件（DTO + 映射），风险面极小。
- Live smoke 在 mock/fake provider 下验证内部链路；真实 Agnes/ComfyUI 链路引用 Sprint 04 双引擎对跑结论（Agnes 70% / ComfyUI 85% 首可用率），未重复消耗配额。
- `test_generation_atomicity` 在全量套件下有 1 例 provider_ref 时序偶发（隔离复跑通过，与本次改动无关——改动不触及 worker/provider_ref 路径）。
