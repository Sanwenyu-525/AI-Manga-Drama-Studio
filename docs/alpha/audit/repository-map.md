# 仓库结构扫描报告（P0-T001）

> 审查方式：glob/read 逐文件读取 backend/app 全部模块、frontend/src 全部源码、apps/desktop Tauri 壳、7 份 Alembic 迁移、18+ 份测试、workflows、docs。仅只读，未修改任何业务代码。
> **数量校准**（任务描述与事实不符处）：Alembic 迁移实为 **7 份**（非 8）；backend/tests/test_*.py 实为 **18 份**（另有 conftest.py 与 __init__.py，非 19）。

## 1. 顶层目录结构与用途

| 路径 | 用途 |
|---|---|
| backend/ | FastAPI + SQLAlchemy + SQLite 后端（pyproject.toml、alembic.ini、uv.lock、.venv、data/） |
| frontend/ | React 18 + TS + Vite + Zustand + TanStack Query 前端（src/、package.json） |
| apps/desktop/ | Tauri 2 壳（src-tauri/ Rust + dev-keepalive.cjs + package.json） |
| workflows/ | ComfyUI workflow 模板（default_image_api.json） |
| docs/ | 设计文档（含 audits/、architecture/、roadmap/、tasks/、incoming/） |
| scripts/ | scan-secrets.py（CI secret 扫描）、Enable/Disable-Startup-Restore.ps1 |
| .github/workflows/ci.yml | **Phase 1 已建 CI**（backend pytest+ruff、frontend build+test、desktop cargo check, secret scan） |
| AGENTS.md / README.md / design-qa.md / studio.ps1 / studio.bat | 入口/启动脚本 |

> ⚠️ 文档漂移：README.md 仍称项目为 Stage A；design-qa.md 仍称 Stage D 未接入；AGENTS.md 技术栈节仍写 asyncio.Queue（真实为 DB-poll worker）。审计见 docs/audits/post-mvp-audit.md §A-20/§8。

## 2. backend/app 模块职责与关键文件

| 模块 | 职责 | 关键文件 |
|---|---|---|
| main.py | 入口；CORS、统一错误 Envelope（StudioError/422/500/HTTP）、request-logging 中间件（X-Request-ID）、lifespan 启动 WS 网关 + Generation worker | main.py |
| api/ | 路由层（Router → Service，无业务 SQL）；统一 deps.py（get_db、get_llm） | router.py、deps.py、13 个路由文件 |
| core/ | 配置 config.py（pydantic-settings，前缀 STUDIO_）、错误层次 errors.py、日志 logging.py | config.py、errors.py |
| db/ | SQLite(WAL)+FK engine/session；models/ 8 个 ORM 模型 + columns.py(UUID TEXT PK/时间戳) | session.py、base.py、models/*.py |
| domain/ | 纯 Pydantic DTO/schema（LLM 结构化输出契约与 API 契约分离层） | analysis.py、agent.py、shot.py 等 |
| services/ | 业务服务：Project/Episode/Scene/Shot/Character/Script/Asset/Generation/Version/Context/PlanMapper | script_service.py、shot_service.py 等 |
| repositories/ | 薄数据访问层（唯一放 SQL 的 Service 边界） | base.py、__init__.py |
| llm/ | LLMGateway 抽象：gateway.py(Protocol)、factory.py(STUDIO_LLM_MODE) 、fake.py(Fake)、langchain_gateway.py(ChatOpenAI) | fake.py、factory.py |
| providers/ | Provider 抽象：image/(base+mock+comfyui)、comfyui/(client+workflow_mapper)、registry.py | registry.py、image/*、comfyui/* |
| agents/ | AI Director：tools.py(ToolExecutor 三工具)、fake_planner.py、director/(graph+runner) | director/graph.py、tools.py |
| events/ | bus.py(EventBus, commit-then-publish 红线)、ws.py(WS 网关 /api/v1/events, Envelope+sequence) | bus.py、ws.py |
| generations/ | state.py(状态机)、worker.py(DB-poll worker, atomic claim+lease) | worker.py |
| operations/ | OperationStore（内存，202 + 轮询，per-key 锁） | store.py |

## 3. backend 技术栈与启动入口

- **依赖**（pyproject.toml）：fastapi>=0.141、sqlalchemy>=2.0.52、alembic、pydantic-settings、uvicorn[standard]、httpx、websockets≥15（ComfyUI 显式运行时依赖）、langchain-core、langchain-openai、langgraph、pillow、python-multipart。dev：pytest、ruff、httpx。需 Python ≥3.13。
- **配置**（core/config.py，环境变量前缀 STUDIO_）：
  - STUDIO_APP_ENV(development|test|production)、STUDIO_PORT(默认 17820)、STUDIO_DATA_DIR
  - STUDIO_LLM_MODE=fake|openai（STUDIO_LLM_BASE_URL/API_KEY/MODEL/STRUCTURED_METHOD）
  - STUDIO_IMAGE_PROVIDER=mock|comfyui（STUDIO_COMFYUI_URL 默认 127.0.0.1:8188）
  - STUDIO_GENERATION_CONCURRENCY(强制=1)、MAX_ATTEMPTS(3)、LEASE_SECONDS(120)、RETRY_BACKOFF
  - STUDIO_WORKFLOWS_DIR(默认仓库根 workflows/)
- **启动**：uv run uvicorn app.main:app --host 127.0.0.1 --port 17820（Tauri backend.rs 用此命令自动拉起）。

## 4. frontend/src 模块结构与关键文件

| 模块 | 内容 |
|---|---|
| app/router.tsx | BrowserRouter；/(ProjectHome)、/projects/new、/assets、/settings、/workflows、/projects/:id(studio, /script+/storyboard/:sceneId)、/shots/:id/versions |
| api/ | client.ts(fetch 封装, ApiError 带 request_id, timeout+AbortSignal)、queryKeys.ts(集中 key)、types.ts(手写 DTO) |
| events/socket.ts | WebSocket 到 /api/v1/events；EventSocket→EventRouter；序列去重、指数退避重连；高频率事件(generation)写 store，资源事件 invalidate Query |
| stores/ | generationStore.ts(live 瞬时状态)、agentStore.ts(AgentRun 生命周期)、selectionStore.ts(Selection 单一事实源)、workspaceStore.ts(UI 布局) |
| components/ | TitleBar.tsx、ApiErrorPanel.tsx、NotFoundPage.tsx |
| features/ | project/(ProjectHome/NewProjectPage)、studio/(StudioPage/ProjectExplorer)、script/(EpisodePanel)、storyboard/(StoryboardView/ShotInspector/VersionReviewPage)、generation/(GenerationQueue)、director/(AIDirectorPanel)、assets/、workflows/、settings/、ai/(useOperationPolling) |
| main.tsx | QueryClientProvider + RouterProvider；staleTime 5s |

## 5. frontend 技术栈（package.json）

React 18.3 + react-router-dom 6.28（路由）+ zustand 5（UI 状态）+ @tanstack/react-query 5.62（Server State）+ @tauri-apps/api 2.11；无独立 HTTP 库（原生 fetch）；WebSocket 原生。字体 @fontsource geist、图标 @phosphor-icons。@vitejs/plugin-react、vitest+testing-library+jsdom 前端测试（4 个测试文件）。

## 6. apps/desktop 壳（Tauri 2）

- **tauri.conf.json**：devUrl http://127.0.0.1:17821；beforeBuildCommand 跑前端 build；frontendDist ../../frontend/dist；beforeDevCommand 跑 dev-keepalive.cjs（猜测保活后端/前端）；window 1440×900 无边框(decorations:false)；CSP null。
- **main.rs**：Windows 隐藏控制台 + 调 ai_manga_studio_lib::run()。
- **lib.rs**：Tauri Builder，BackendState(Mutex<Option<Child>>)，setup 调 ensure_backend；窗口销毁时 stop_spawned_backend（只杀自己 spawn 的，不动用户起动的）。
- **backend.rs**（DT-003）：探测 TCP 127.0.0.1:17820，空闲则 uv run uvicorn app.main:app --host 127.0.0.1 --port 17820（backend_dir() 用 CARGO_MANIFEST_DIR 向上 3 层定位仓库根），CREATE_NO_WINDOW，best-effort 启停。依赖源码目录 + 系统 uv，无 bundled runtime/sidecar（开发态）。

## 7. workflows/

仅 default_image_api.json：SD1.5/SDXL API 格式 workflow，节点 CheckpointLoaderSimple→CLIPTextEncode×2→EmptyLatentImage→KSampler→VAEDecode→SaveImage，含 $PROMPT/$NEGATIVE_PROMPT/$SEED/$WIDTH/$HEIGHT 占位符。WorkflowMapper 要求恰好一个 SaveImage 输出节点 + 必需 placeholder，缺失则 preflight 失败。

## 8. 数据库迁移（backend/alembic/versions，实为 7 份）

| 文件 | 内容 |
|---|---|
| 2d0cfc1bb995_initial_schema | Stage A：projects/episodes/scenes/shots，deleted_at 软删 |
| 395a4fdc3dfc_stage_c | Stage C：assets/generations/media_versions |
| 4073c8233eb9_characters | P1：characters 身份表 + shot_characters 多对多（含 continuity 字段） |
| e1f2a3b4c5d6_p1_e1_t01_analysis_keys | P1-E1-T01：episodes.analysis_key、scenes.analysis_key/storyboard_key（幂等键，nullable） |
| c1d2e3f4a5b6_p1_e2_t02_claim_lease | P1-E2-T02：generations.claim_token/claimed_at/lease_expires_at/next_attempt_at（原子认领+崩溃恢复） |
| b1e2f3a4c5d6_p1_e1_t02_invariants | P1-E1-T02：部分唯一索引（scenes/scene_number、shots/shot_number+order、shot_characters、media_versions 版本号/单 active）+ worker 索引 |
| 5f1c9a2b7d40_project_cover | P2：projects.cover_path（相对路径） |

（注：任务称 8 份，实际为以上 7 份。）

## 9. 测试布局（backend/tests，实为 18 份 test_*）

| 文件 | 测什么 |
|---|---|
| conftest.py | 每测隔离 SQLite + FastAPI TestClient + session 覆盖 |
| test_api.py | 全 CRUD 链（HTTP） |
| test_agent.py | Stage D 场景 A/B/C（FakeLLM planner） |
| test_agent_ownership.py | P1-E3-T01 ToolExecutor 防御（跨项目/伪造 id 拒绝） |
| test_characters.py | Character CRUD + Shot 关联 + revision |
| test_db_invariants.py | P1-E1-T02：原子 revision、安全 reorder、唯一约束 |
| test_episode_scene_crud.py | Episode/Scene CRUD 删除 |
| test_errors.py | P1-E4-T01 统一错误 Envelope + request_id + 不泄漏 |
| test_generation.py | Stage C 生成链（MockImageProvider） |
| test_generation_state.py | P1-E2-T02 状态机/原子认领/lease 崩溃恢复 |
| test_migrations.py | P1-E6：Alembic-from-zero/round-trip 迁移测试 |
| test_plan_mapper.py | P1-E1-T01 Plan↔Domain 显式映射无丢字段 |
| test_project_cover_delete.py | 封面上传 + Project 删除 |
| test_provider_contract.py | P1-E2-T01 provider/workflow 契约（无需 GPU） |
| test_script_planning.py | Stage B 小说→分析→分镜全链 |
| test_script_transactions.py | P1-E1：事务/幂等直连 DB 断言 |
| test_services.py | ShotService revision、SceneService 计数 |
| test_worker_loop.py | P1-E6：真实 worker DB-poll 循环 |
| test_workflows_api.py | workflow catalog 只读 API |

## 10. docs/ 审计与状态文档（有价值信息）

- **audits/post-mvp-audit.md**（2026-08-15，273 行）：**最值得继承**。列出 P0–P2 分级发现（A-00~A-20）。A-00 计划字段丢失/A-01 Generation 崩溃恢复/A-02 Agent ownership/A-03 ComfyUI 路径/A-04 DB 不变量/A-05 无安全边界/A-06 路由冲突/A-07 断线恢复……其中大部分已在 Phase 1 修复。
- **architecture/current-state.md**：真实运行架构图、模块成熟度表、数据语义/异步 Runtime/审计漂移清单。结论"功能闭环 Alpha，非生产版"。
- **tasks/completed.md**：记录 8 项 Post-MVP P1 任务完成（P1-E1-T01/T02、P1-E2-T01/T02、P1-E3-T01/T02、P1-E4-T01、P1-E6-T01）+ 历史 MVP 里程碑 A–P1。
- **tasks/current-sprint.md**：Sprint 01 已完成；遗留 P0：P1-E2-T03(Generation 完成链原子化)、P1-E4-T02(Event Gateway 鉴权/订阅)，P1 任务 P1-E4-T03(关联日志) 排入下一 Sprint。
- **roadmap/**：README 定义 Phase 1–6（Phase 1 = Current；优先级 P0/P1/P2/P3），phase-1-foundation.md 详述 Epic 1.1/1.2/1.3（含 Design Decision）。
