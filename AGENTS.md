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
| `docs/configuration-v0.1.md` | **配置矩阵**（env 变量/默认/secret/重启影响） | 配置、部署、环境判定 |
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
- ✅ **P1 收尾完成（2026-08）— MVP 交付范围全清**：**Character Management**（database §7/§11：characters 身份表 + shot_characters 中间表 + Alembic 迁移；CharacterService CRUD + revision 乐观并发 + 软删除 + character.created/updated/deleted 事件；Shot 支持 character_ids 创建/替换关联，Storyboard 回填 character_names，跨项目角色校验 422/404；前端 ProjectExplorer 角色区：内联创建/编辑/删除 + shot_count，ShotInspector 出场角色多选，WS 事件 invalidate；`GET /api/v1/projects/{id}/characters`、`POST`、`GET/PATCH/DELETE /api/v1/characters/{id}`）+ **Project Bootstrap**（`GET /projects/{id}/bootstrap`，契约 §103-104：project/episodes(scene_count)/characters/providers/active_generations/active_agent_runs，只返回摘要）。验收：角色 CRUD + 镜头关联回填 + bootstrap（pytest 31 项）。
- ✅ **P7（2026-08）— Director 持久化 + Proposal 审批流**：AgentRun 落库（agent_runs 表）；LangGraph SQLite Checkpointer（自定义 stdlib sqlite3 BaseCheckpointSaver，thread_id=run_id）；AgentGateway 形式化入口；ContextResolver + TokenBudget + ContextSchemas；**update_shot 改造为 Proposal 系统**（不再直写——生成 pending Proposal → run 进入 WAITING_HUMAN → agent.approval.required；approve 经 ShotService 应用 + base_revision 冲突守卫 → applied/conflict；reject 不应用）；resume 真实语义（approve/reject + proposal_ids）；proposal API（list/approve/reject）+ agent.proposal.* 事件。Scenario A/B 语义更新（update 需审批）。
- ✅ **P9（2026-08）— Timeline & Episode Render**：`timelines/timeline_tracks/timeline_clips` 三表（Alembic `c9d0e1f2a3b4`）；TimelineService（默认四轨 VIDEO/VOICE/MUSIC/SUBTITLE、clip 编辑、replace-asset 版本替换、一键 `sequence-from-shots`、非渲染帧条预览）；Timeline API（`GET/POST /episodes/{id}/timeline`、tracks/clips CRUD、`/timeline-clips/{id}/replace-asset`、`sequence-from-shots`、`/preview`、`POST /timelines/{id}/render` 202、`GET /episodes/{id}/final-video`）；**Episode Render**：`type=render` Generation（沿用生成队列=Job Queue）→ RenderProvider（`mock` 纯 Python+Pillow MJPEG AVI 真实可播放 + `ffmpeg` 时 REAL H.264 MP4；`STUDIO_RENDER_PROVIDER=auto|mock|ffmpeg`）→ 产物注册 `vg:episode:{episode_id}:FINAL_VIDEO` 不可变版本 + `timeline.rendered` 事件；前端时间线工作台（URL 路由 `/projects/:id/timeline`、编辑标签 时间线）：拖拽位移/两端裁剪、替换版本、素材拾取、非渲染预览、渲染/导出 + 生成队列进度（pytest 11 项新增，全套 314；前端 vitest 149 + build 通过；live E2E：排片→渲染→FINAL_VIDEO RIFF/AVI 落盘验证）。
- ✅ **P10（2026-08）— 音频链路（配音/混音/字幕，TASK-012+013）**：AudioProvider 适配器（registry `type=audio`：`mock` 确定性 WAV 纯 stdlib 合成（默认/CI）+ `edge` 高星 edge-tts 在线神经音色（`STUDIO_AUDIO_PROVIDER=edge`，dev/原型；生产默认留给云 API/本地 CosyVoice））；**配音全链路**：`POST /timeline-clips/{id}/generate-voiceover` 202（仅 VOICE 轨、text 取请求或 clip.text，clip create/patch 支持 text）→ `type=audio` Generation 走既有队列（claim/lease/cancel/retry 全套复用）→ AudioProvider 合成 → 产物注册 `vg:clip:{clip_id}:AUDIO` 不可变版本 + clip 回绑最新版（replace-asset 语义）+ `asset.created`（role=VOICEOVER）/`generation.*`/`timeline.clip.updated` 事件；**渲染混流（TASK-013）**：render plan 扩展收集未静音 VOICE/MUSIC/SFX clip 与 SUBTITLE clip（text），ffmpeg 渲染 `adelay+amix` 混音 + AAC + `subtitles` 滤镜烧录（SRT 由 SUBTITLE clip 生成，Windows 路径转义处理）；mock 渲染同步实现 AVI `auds/01wb` PCM 音轨（WAV 资产 stdlib 解码混音）+ 逐帧字幕绘制——纯 Python 可播放成片首次「有声有字幕」；**前端配音入口**：ClipInspector 对 VOICE 轨片段提供台词编辑（text PATCH）+「生成配音」按钮 + 音频试听 `<audio>`，SUBTITLE 轨文案编辑，队列 Dock 中文化类型标签（图片/整集渲染/配音）+ store 稀疏事件合并（pytest +14 项，全套 368；前端 vitest 168）
- ✅ **顶部内容面包屑（2026-08）**：上下文栏静态路径升级为**可点击面包屑**（`ContentBreadcrumb.tsx`，frontend-ux §76.2）：点击祖先段 SPA 内跳转（项目→首页 / 模块→职责页 / EP→该集剧本 / SC→该场景分镜板）；悬停展开**同级菜单**横向切换（项目↔项目、模块↔模块、EP↔EP、SC↔SC；菜单 portal 到 body 不受 40px 壳 overflow 裁剪，项目/场景列表懒加载）；末段（当前 SH）只读高亮不可点；跨场景切换清空 Selection 防检查器脏上下文；溢出时首现 `…` 展开完整层级。段落一律由真实 Project State 推导，无文件管理器隐喻（前端 vitest 205 项 + build 通过）
- ✅ **稳定化 Sprint 03（2026-08）— 本地安全与配置 Fail-closed（P1-E5-T01 + P1-E5-T02）**：**P1-E5-T01** `validate_startup_config`（lifespan 调用）——production 拒 fake/mock 提供器（llm/image/video/audio）；llm_mode/video_provider/app_env 转 Literal（启动即拒非法值）；图像/视频 provider 保存 422（不再静默回落）；新增 `backend/.env.example`（无真实 secret）+ `docs/configuration-v0.1.md` 配置矩阵；**P1-E5-T02** 本地会话 token（`STUDIO_SESSION_TOKEN`）：REST `X-Session-Token` + WS `?token=`（/health、/system/info 豁免），Tauri 壳 uuid v4 生成注入 spawn + `get_session_token` 命令 + `/health` 握手区分「本应用已运行 / 端口被其他进程占用 / 空闲」；WS Origin 白名单校验；Tauri `csp` 收紧（devCsp null 保开发流）；前端 `lib/session.ts` 传递 token。**Phase 1 全部 P0 关闭**。验证：pytest +23（test_config 12 + test_local_session 11）、vitest 202、ruff/eslint/tsc/cargo check 全绿
- ✅ **真实 LLM / 真实 ComfyUI（2026-08）**：`STUDIO_LLM_MODE=openai` 指向 Agnes `agnes-2.5-flash`；`STUDIO_IMAGE_PROVIDER=agnes`；本地 ComfyUI 0.33 + **Z-Image-Turbo int8** 模板已注册（`workflows/zimage_turbo.json` + `WORKFLOW_CATALOG["zimage_turbo"]`，UNETLoader + TextEncodeZImageOmni + qwen_3_4b CLIP，8 步 euler/cfg 2.5）
- ✅ **真实链路验证（Sprint 04，2026-08-31）**：40 张双引擎对跑 + 逐张快评，见 `docs/reports/real-chain-validation-report.md`。首可用率 Agnes 70% / ComfyUI 85%；结论=核心假设成立；Phase 2 重排：P2-E4-T01（Provider 工作区）升为头号 + prompt/Review Loop + reference 图机制预研
- ✅ **Sprint 05（2026-08-31）— P2-E4-T01 收敛版**：`GET /providers/comfyui/models` 返回分架构 `catalog`（checkpoints/unets/clips/vaes，DiT 模型可见）；WorkflowMapper catalog 目录自动发现（workflows/ drop-in 零代码注册）；前端 GenerationEnginePicker（单镜头生成显式选 provider+workflow）。剩余=图像 Provider Profile（镜像 /llm/profiles）
- ✅ **P2-E1-T01（2026-08-31）— Analysis Snapshot**：`analysis_snapshots` 表（Alembic `b7c9d1e3f5a7`）；preview 落库不可变快照（plan + source_hash + episode_revision + model/prompt/schema provenance）；confirm 只提交 snapshot_id——零二次 LLM（live 实证 preview 3.7s → confirm 0.0s），写入=预览逐项一致；幂等重放；原文/revision 变更后过期（operation failed + snapshot=expired）；`GET /episodes/{id}/analysis-snapshots/latest` 刷新水合；契约 §14.1。**K1（preview/confirm 不一致）机制缺口关闭**
- ✅ **P4-E3-T01（2026-08-31 核对）— Video Provider 与不可变视频版本（原 Phase 4 规划项，已由既有链路交付）**：`VideoProviderProtocol`（`providers/video/base.py`）+ 真实 AgnesVideoProvider（agnes-video-2.5-flash，text-to-video 任务创建/轮询/下载）+ mock 占位 VideoProviderUnavailable fail-fast；registry `video.mock`（`video_generation: False`）/`video.agnes`（`True`）；排队前 type ∈ image/video 校验 + 未知 provider 422 + capability 区分；Shot 可保留多个不可变视频版本并切换 active（`active_video_asset_id` + `GET/POST /shots/{id}/video-versions`）；cancel/retry/recovery 复用既有 Generation 状态机；前端 ShotInspector 视频入口 + 设置页视频 provider 配置
- ✅ **P4-E3-T02（2026-08-31）— Timeline 收尾（AC-2：转场 + revision + undo）**：`TimelineClip.transition`（cut/fade/dissolve）+ `revision` 乐观并发（原子条件更新 409）；ffmpeg 渲染 `xfade` 转场 / mock 渲染 PIL 交叉淡化；Timeline 编辑纳入 ChangeSet/Undo 体系（`agent_change_sets` source="timeline"，`POST /agent/change-sets/{id}/undo` 直接复用）；前端 Timeline 工作台转场选择 + revision 冲突处理 + 撤销入口
- ✅ **P2-E3-T02/T03（2026-08-31）— 风险分级 + Approval 过期 + ChangeSet/Undo**：**R0–R3 风险分级**（`app/agents/risk.py` 确定性分类器，agent-director §24）：R0 读 / **R1 update_shot 自动执行+ChangeSet**（不再为每次近景修改打断创作）/**R2 generate_image 审批前零 Generation 创建**（`STUDIO_AGENT_AUTO_APPROVE_R2` 可放开）/R3 未知工具一律审批；Proposal 携带 risk_level/reason/estimated_tasks/cost(null=诚实未知)/irreversible/**expires_at**（`STUDIO_AGENT_PROPOSAL_TTL_HOURS` 默认 24h；过期=终态，approve/reject 409，读路径懒扫描，全过期 run→failed 不悬挂）。**ChangeSet/Undo**：`agent_change_sets` 表（Alembic `c3d4e5f6a7b8`）记录每次已应用 Agent mutation 的最小 before/after patch（R1 自动应用 / proposal approve / worker active-version 切换——`generations.run_id` 溯源）；**Undo=新补偿变更**（ShotService/VersionService、revision+1、新 ChangeSet 链回原记录，历史永不改写；媒体版本只切 active 不删除）；同字段被覆盖→409+recovery（force=true 强制恢复路径）；批量 undo 逐项结果（undone|conflict|skipped）不半静默；graph resume 幂等（change set/proposal/generation 三重已存在检查，reject 后不重复提案）。API：`GET /agent/change-sets`、`POST /agent/change-sets/{id}/undo`、`POST /agent/runs/{id}/change-sets/undo`；事件 `agent.proposal.expired`、`agent.change_set.created/undone`。前端：ProposalReview 风险徽章/费用/截止展示 + generate_image 说明卡；ChangeSetPanel（变更记录、逐条/批量撤销、409 强制恢复、跳转镜头）。验证：后端 pytest 39 项 agent 相关新增/重写（全套 532）、前端 vitest 223、tsc/eslint/ruff 全绿
- ✅ **用户设想落地三方案（2026-08-31）**：**方案 A 设定文档库**（`source_documents` 表 + Alembic `e4f6a8c0d2e4`；DocumentService CRUD + 前端 DocumentsSection；Agent 上下文注入设定文档，analyze 幂等键纳入文档 hash——设定文档变更会使旧分析快照 409 过期）；**方案 B Tauri 真实本地导入**（`apps/desktop/src-tauri/src/local_fs.rs` 只读命令 + `lib.rs` 注册 + 前端 `lib/nativeDialog.ts` 桥接 + EpisodePanel 原稿目录/替换原文，浏览器开发流经动态 import 不加载 Tauri 模块）；**方案 C 一键成片**——**C1 整轨批量配音**（`POST /timelines/{id}/generate-voiceovers` 202：为所有有台词且未绑定音频的 VOICE 轨片段批量排队配音，TimelineView 计数/禁用态入口）+ **C2 Episode Pipeline**（`episode_pipelines` 表 + Alembic `f0b2c4d6e8f0`；`POST /episodes/{id}/pipeline/run|confirm|finalize|resume` + `GET /pipeline/latest`，契约 §15.1；阶段 analyze→shots→images→timeline→render，落库断点续跑、confirm 幂等重放；PipelineService 只编排、域写全走既有 Service 红线；前端 PipelineBar 挂载 EpisodePanel（一键成片→确认→排片渲染→恢复）+ `pipeline.updated` WS 事件）。验证：后端 pytest 9 项方案 C 相关（test_pipeline 4 + test_voiceover_batch）、前端 vitest 新增 7 项（PipelineBar 5 + TimelineView C1 2）全绿
- ✅ **P8 Continuity 引擎落地（此前漏记）**：两表 `scene_continuity_states`/`shot_continuity_states`（迁移 `a0b1c2d3e4f7`）+ `shot_transitions`/`continuity_warnings`（迁移 `a8b9c0d1e2f3`）+ 8 条确定性规则（COSTUME_CHANGED / CHARACTER_REFERENCE_OUTDATED / LOCATION_CHANGED / PROP_HOLDER_CHANGED / PROP_DISAPPEARED / TIME_OF_DAY_CHANGED / POSITION_JUMP / ORIENTATION_FLIP）+ STALE 集成（MASTER 切换标 stale，不自动重生成）+ Agent continuity check/fix（复用 Proposal 审批流）+ 前端 `features/continuity/`。**P4-E1-T01 的 Continuity State Domain 部分由此提前交付**，剩余收敛为视觉检查（P4-E1-T02）
- ✅ **P3 一致性引擎预研 + M1 开工（2026-08-31）**：报告 `docs/reports/p3-consistency-engine-preresearch.md`（Sprint 04 K2 实证 → 七断点盘点 → **Z-Image Omni 原生 3 参考图为主路线**，IPAdapter 系不兼容 DiT 弃用）；分期：M1=参考图管道接线（worker 桥接 / upload 接线 / `zimage_turbo_ref.json` 模板 / `GenerationCreate.reference_asset_ids`）；M2=`character_version_assets` 多参考图；M3=相似度评分 harness（Value Gate：≥20 问题样本 + 人工基线，只提示不拦截）；M4=Z-Image-Edit A/B / LoRA / Review Loop。M1 验收：mock 请求携带 reference_images + comfyui upload→mapper 注入单测 + pytest 全绿
- ✅ **审计与联调修复三连（2026-08-31，定点修复零重构、零 Breaking Change）**：**后端定点优化**（`BACKEND_AUDIT.md`/`BACKEND_OPTIMIZATION_REPORT.md`：P0×2——ComfyUI 客户端 6 处 httpx `trust_env=False` 防回环代理劫持、continuity 路由重复注册删除（OpenAPI 168 operations 零重复）；P1×8——`STUDIO_GENERATION_MAX_ATTEMPTS` 重试预算真正接通（1s/2s backoff + 崩溃 re-queue）、生成幂等 409 门（in-flight 查重 + pipeline resume 容忍）、correlation_id 日志链路（contextvar+Filter+中间件+worker `gen:{id}`）、Router 裸 SQL 迁入 ContinuityService、agents.py 改公开 `get_run()`、资产导入 MAX(suffix)+1 序号 + tmp+`os.replace` 原子写、render `output_extension` 能力声明化（worker 不感知具体 encoder）、HTTP 上传 1MB 分块流式；session token 比较改 `secrets.compare_digest`）→ **前端定点优化**（`docs/reports/FRONTEND_AUDIT.md`/`docs/reports/FRONTEND_OPTIMIZATION_REPORT.md`：P0×5——批量生成静默失败接 ApiErrorPanel、~12 处 mutation 错误反馈、审片页 `<video>` 分支可播放、AI Storyboard 防重复提交、**Tauri token 模式媒体全 401 生产 bug 修复**（middleware 接受 `?token=` query + `lib/mediaUrl.ts` 单一事实源替换 13 处媒体 URL 拼接，契约 §50/config 矩阵同步）；P1×9——产物下载闭环（`lib/download.ts`+DownloadButton ×5 处 + FINAL_VIDEO 下载成片 + 文件名推导）、统一 Lightbox、生成队列五态可区分 + `friendlyGenerationError` 六类中文映射、formatDate 收敛、lazy/preload/aria-label、TimelineView 吞错×6 修复）→ **全栈联调**（`docs/reports/FULLSTACK_INTEGRATION_AUDIT.md`/`docs/reports/FULLSTACK_INTEGRATION_REPORT.md`：4 P0+6 P1 契约断点修复——ContinuityWarningList 改调真实 `POST /agent/continuity/fix`、资产筛选 `asset_type` 参数名、mediaUrl 双 `?` 修复、项目封面 token、`AssetListItemRead` 增量补 name/source_type、provider `unavailable` 中文标签、useOperationPolling 失败上限（10 次/404 快速失败）解除按钮卡死、TimelineView 合并错误面板；**live HTTP smoke 14 步全链路通过**（`backend/scripts/smoke_fullstack.py`：建项目→分析快照 confirm 0.0s→AI 分镜→生成含双击 409 幂等验证→媒体访问→排片→配音→渲染 2.8MB FINAL_VIDEO→下载→契约路由验证））。验证：pytest 576（1 skip）/ vitest / tsc / eslint / ruff / build 全绿
- ✅ **自主迭代 01 — M1 前端闭环：参考图可见可控（2026-08-31，Post-MVP 自主迭代首轮）**：后端 M1 管道落地但前端零入口（P3 报告断点 4 前端侧）→ 本轮补全端到端体验。**后端**：`GET /shots/{id}/reference-images` 预览端点（与 create 自动解析同源，含 character_name；契约 §38）+ `GET /generations/{id}` 明细新增 `references` 溯源字段（auto/explicit + 角色名；列表端点保持 null 防 N+1；契约 §39）；Service 层 `preview_references`/`generation_references`（红线合规：Router 薄委派）。**前端**：`ReferenceImagePicker`（自动/手动/无三模式——自动=MASTER 解析预览缩略图+空态引导、手动=项目图片资产多选≤3 张按序注入、无=显式空数组；Provider 能力感知——引擎无 reference_image 能力时警告「生成时将忽略」；>3 张提示上限）接入 ShotInspector；生成请求携带 `reference_asset_ids`；版本区新增「生成所用参考图」溯源缩略图条（GenerationReferenceStrip）；生成 409 幂等门友好文案（后端报告建议 #1：任务进行中≠生成失败）。验证：pytest **575 passed +1 skip**（新增 6：预览同源/空态/404/明细溯源 auto+explicit/列表防 N+1）、vitest **258 passed**（新增 12：三模式交互/顺序上报/上限禁用/能力警告/409 文案）、tsc/eslint/ruff/cargo check 全绿 + uvicorn 真实冒烟（端点注册 + 404 语义）。机会台账 `PRODUCT_OPPORTUNITY_BACKLOG.md` + 能力地图 `FEATURE_MAP.md` 建立；报告 `docs/reports/autonomous-iteration-2026-08-31-refimages.md`
- ✅ **自主迭代 02 — 镜头多选批量操作（2026-09-01，Post-MVP 自主迭代第二轮）**：全仓此前无 multiSelect，批量改景别/删除/重排/生图只能逐个点。**后端（纯增量零 Schema 变更）**：`POST /scenes/{scene_id}/shots/batch-update`（`{shot_ids, patch}`，**批量覆盖语义**——服务端取每镜头当前 revision，逐镜头复用 `update_shot`：revision+1 / dirty_state / PromptVersion / `shot.updated` 事件 / continuity 重算与单编辑完全一致）+ `POST /scenes/{scene_id}/shots/batch-delete`（逐镜头复用 `delete_shot` 软删除+事件）；**逐项结果** `{requested, succeeded, failed, results[{shot_id, status, error_code?}]}`——部分失败仍 200（对齐 ChangeSet undo 逐项模式），重复 id/空 patch 422、场景 404、跨场景/未知 id 计入项级 failed；契约 §19 批量操作段。**前端**：selectionStore `toggleShot`/`setShotIds`（`selectShot` 单选语义不变）；网格 Ctrl/Cmd 切换 + Shift 范围选（锚点=最近单击）+ 悬停 checkbox（stopPropagation）；**BatchActionBar**（选中>1 浮出：批量生成 / 改景别下拉 / 前移后移（`moveBlock` 整块位移复用既有 reorder 契约）/ 删除 confirm / 清除选择）；**批量生成去掉 Promise.all fail-fast** → `Promise.allSettled` 逐项聚合（409 幂等门=「已在进行中」非失败，诚实计数+首错原因），既有待生成/失败/整场景批量菜单同路径受益；错误走 ApiErrorPanel + 聚合 notice。验证：pytest **617 passed +1 skip**（新增 5）、vitest **276 passed**（新增 selectionStore/batchSubmit/batchActionBar/网格多选）、tsc/eslint/ruff/build 全绿；报告 `docs/reports/autonomous-iteration-2026-09-01-batch-shot-operations.md`
- ✅ **P2-E4-T02 — ComfyUI 检查通道：workflow live 诊断 + Comfy MCP 双通道（2026-09-01，Post-MVP）**：确立「ComfyUI API=确定性生产执行层 / 检查通道=理解·诊断层」双通道架构（红线合规：检查通道只读，Agent/API 经 `WorkflowDiagnosticsService`，不直调 ComfyUI/MCP）。**后端**：`WorkflowIntrospector` 契约（`providers/workflow/introspection.py`：查询式 `resolve_choices`，对 beta 工具面友好的关键设计）+ 双实现——`ComfyUIIntrospector`（native，直连全量 `/object_info`，client 新增 async+sync twin）与 `ComfyMCPIntrospector`（mcp sdk stdio → 用户自装 comfy-mcp，**动态工具匹配**应对 beta 工具面漂移，缺失/连接失败 `ProviderUnavailableError` → 服务自动回落 native；mcp sdk 入依赖，comfy-mcp 不打包不分发规避 AGPL 义务）；`WorkflowDiagnosticsService`（async=API/前端，sync=排队守卫+Agent 工具；object_info 60s TTL 缓存）；`GET /providers/comfyui/workflows` + `POST /providers/comfyui/workflows/{id}/validate`（永 200，未知 id 422；契约 §48.2b）；**排队前 fail-fast**：image+comfyui 且诊断 invalid（缺节点/缺模型/断链）→ 422，unreachable 照常 202（检查通道降级绝不阻断生产通道）；`$PROMPT` 等占位符（含 LoadImage 参考图槽位）豁免 live 枚举校验。**Agent**：R0 工具 `check_workflow`（人话 summary：缺节点/缺模型/断链）+ `inspect_comfy`（可达性/节点数/模板清单）。**前端**：SettingsPage ComfyUI 卡「工作流检查」面板（模板下拉 + 逐节点 ✅/❌/⚠ 结果）。配置：`STUDIO_COMFY_INTROSPECTION=native|mcp` + `STUDIO_COMFY_MCP_COMMAND`（configuration 矩阵 + .env.example）。验证：pytest **617 passed +1 skip**（新增 37：client/枚举投影/诊断四态/fail-fast 守卫/API/Agent 工具/MCP 动态匹配与回落；全套中 1 例既有 flaky `test_generation_atomicity` 单跑通过）、vitest **280 passed**（新增 4）、tsc/eslint/ruff 全绿
- ✅ **自主迭代 03 — 场景一致性闭环：地点库 + 场景绑定 + 生成注入地点参考图（2026-09-01，Post-MVP）**：Location 后端（LocationService/VersionService/API/事件/契约）早已 100% 落地但前端零入口、`scene.location_id` 为自由文本、M1 参考图管道只解析角色 → 本轮把地点变成和角色一致的可复用一致性资产。**后端（纯增量零 Schema）**：`_location_references`（shot → scene.location_id → Location MASTER → active LocationVersion asset）+ create_generation 自动路径在角色参考后追加 `role=location_reference`（order_index 4000 > 角色 3000.x → worker 取前 3 时角色优先、地点兜底；显式 `reference_asset_ids` REPLACE 全部自动解析含地点）；`preview_references`/`generation_references` 返回地点引用（location_id/name）；worker `_load_reference_asset_ids` 过滤含 location_reference；DTO `ShotReferenceRead`/`GenerationReferenceRead` 增 location 字段；`INPUT_ROLES` 补 LOCATION_REFERENCE；契约 §35 更新。**前端**：**活动栏新增「地点」模块**（LocationsWorkspacePage + LocationsSection：列表/内联创建编辑删除 + EntityVersionBlock(kind="location") 视觉版本链 + 关联设定文档，镜像 CharactersSection）+ **StoryboardView 场景头部地点绑定选择器**（PATCH scene.location_id，has-location accent 态，invalid 重构各级查询）+ **ReferenceImagePicker 自动模式区分角色/地点参考**（「场景」徽标 + accent 描边）。验证：pytest **623 passed +1 skip**（新增 7：地点参考写入/纯地点/未绑定与无 MASTER 跳过/显式替换含地点/预览含地点名/明细溯源/worker 路径注入；全套中 1 例既有 flaky 单跑通过）、vitest **285 passed**（新增 5：LocationsSection 3 + ReferenceImagePicker 地点 2；activityRail 冻结序同步「地点」）、tsc/eslint/ruff/build 全绿 + live smoke `scripts/smoke_location_ref.py` 7 步全通（创建→版本→MASTER→绑定→预览→溯源→明细）。报告 `docs/reports/autonomous-iteration-2026-09-01-location-consistency.md`
- ✅ **自主迭代 04 — 生产就绪度：让一致性缺口在生成前可见（2026-09-01，Post-MVP）**：工作区概览此前只报错（反应式「需要处理」），不显示**前瞻式**就绪缺口——角色无 MASTER / 场景未绑定地点或地点无 MASTER 时，生成无法注入一致性参考图（正是 Sprint 04 K2 头号痛点），本轮把「这部作品还差什么」显性化。**后端（纯增量零 Schema）**：`ProjectReadinessService`（确定性聚合无 LLM：characters {total/ready/missing} + scene_binding {scenes_total/bound/bound_with_master/unbound} + continuity_open，均来自真实 Project State）+ `GET /projects/{id}/readiness`（Router 薄委派；契约 §103.1）+ 测试 5 项（空项目全零/角色覆盖/场景绑定三态/连续性计数/404）。**前端**：工作区新增「生产就绪度」面板（三指标缺口卡片 + 点击跳转角色/分镜/连续性 + 全就绪干净态 + readiness queryKey；CSS 全 token 复用）。验证：pytest **628 passed +1 skip**（新增 5；全套中 1 例既有 flaky `test_generation_atomicity` 单跑通过）、vitest **289 passed**（新增 4）、tsc/eslint/ruff/build 全绿 + live smoke `scripts/smoke_location_ref.py` 扩至 8 步（step 8 验证 readiness 聚合与前述状态一致）。报告 `docs/reports/autonomous-iteration-2026-09-01-production-readiness.md`
- ✅ **自主迭代 05 — AI Director 刷新恢复：会话在刷新/重开后可水合（2026-09-01，Post-MVP）**：agentStore 纯内存，刷新即丢对话流/计划/结果（Feature Map 🔶 部分完成）；后端 `agent_runs` 已持久化 input/plan/result 但 `messages_json` 列从未写入、无列表端点、DTO 无 messages → 本轮把「Agent 上下文可恢复」补成闭环。**后端（纯增量零 Schema）**：`AgentRunRead.messages`（`_transcript` 从 input+result+status 确定性计算，零新增写入——user 指令 + assistant 摘要/澄清 + waiting_human 审批提示 + failed 错误）+ `GET /agent/runs?project_id=&limit=`（最近会话倒序，runner.list_runs + gateway 薄委派；契约 §25.1）+ 测试 4 项（completed 转录/列表新在前/WAITING_HUMAN 转录/transcript failed+clarification 边界）。**前端**：`agentStore.hydrate(run)`（runId/status/messages/plan/result 水合，后端状态归一 running→executing）+ `queryKeys.agentRuns` + **AIDirectorPanel 挂载时空闲自动取 limit=1 水合上次会话**（水合后 runId 置位 → 查询自动停用不循环）。验证：pytest **633 passed +1 skip**（新增 4；既有 flaky 本轮通过）、vitest **294 passed**（新增 5：agentStore hydrate 3 + 面板水合/空历史 2）、tsc/eslint/ruff/build 全绿 + live smoke `scripts/smoke_agent_refresh.py` 5 步全通（跑会话→completed→messages 转录→列表新在前）。报告 `docs/reports/autonomous-iteration-2026-09-01-agent-refresh-recovery.md`
- ⬜ **MVP 之后（Phase 2+ 剩余）**：图像 Provider Profile；Continuity 深化（P4-E1-*）；多 Agent；云端

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
GET  /api/v1/agent/runs/{id}/proposals  POST /api/v1/agent/proposals/{id}/approve|reject
POST /api/v1/episodes/{id}/pipeline/run|confirm|finalize|resume   GET /api/v1/episodes/{id}/pipeline/latest
POST /api/v1/timelines/{id}/generate-voiceovers
GET  /api/v1/providers                 POST /api/v1/providers/comfyui/test
GET  /api/v1/health
```

### Event（MVP 必须，api-event-contract §143）

```
shot.updated · agent.run.started · agent.plan.created · agent.approval.required
agent.tool.started · agent.tool.completed · agent.run.completed · agent.run.failed
agent.proposal.created · agent.proposal.approved · agent.proposal.rejected · agent.proposal.conflict
generation.queued · generation.started · generation.progress · generation.completed · generation.failed
asset.created · provider.connected · provider.disconnected
pipeline.updated
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
- **复用优先（禁止重复造轮子）**：任何功能实现前，先排查本仓库已有代码（成品组件/Service/Repository/领域模型/契约）与可用的开源 / GitHub 现成方案，优先复用或改造而非从零新写；确无合适现成实现时才新写，并在代码注释或 commit 说明沿用/新增理由。
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