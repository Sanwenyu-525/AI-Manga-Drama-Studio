# 当前架构状态（Post-MVP）

> 审计基准：2026-08-15。本文描述当前真实代码，不以 README 的阶段声明代替代码事实。

## 1. 结论

项目已经形成可运行的桌面级晚期 MVP：Project State、小说分析、分镜编辑、图片生成、版本回填和 AI Director 的 happy path 均已有代码与后端测试。当前成熟度更接近“功能闭环 Alpha”，尚不是可交付给真实用户长期使用的生产版本。

主要差距不在页面数量，而在任务恢复、跨项目数据边界、事务一致性、真实适配器验证、错误契约、客户端恢复和发行工程。

## 2. 运行架构

```text
React / TanStack Query / Zustand
          │ REST + WebSocket
          ▼
FastAPI Router
          ▼
Service ── Repository ── SQLAlchemy / SQLite (WAL)
   │
   ├── ScriptService ── LLMGateway (Fake / OpenAI-compatible)
   ├── Director Runner ── LangGraph ── ToolExecutor ── Service
   └── GenerationService ── DB-poll Worker ── ImageProvider
                                      ├── Mock
                                      └── ComfyUI

Tauri 壳：从源码目录调用 uv 启动 Uvicorn，再加载 Vite/静态前端
```

依赖方向总体遵守 `UI → API → Service → Repository/DB` 与 `Agent → Service`。但 `backend/app/api/generations.py`、`backend/app/api/assets.py` 仍存在 Router 直接查询数据库的局部红线违例。

## 3. 模块成熟度

| Module | 当前能力 | 成熟度 | 主要证据与限制 |
|---|---|---|---|
| Project / Episode / Scene / Shot | CRUD 主路径、软删除、Shot revision、Storyboard 聚合 | MVP+ | `backend/app/services/shot_service.py`；Scene 缺 revision，生命周期与 restore/batch 不完整 |
| Character | CRUD、Shot 关联、revision | MVP+ | `character_service.py`；缺批量、搜索与完整恢复路径 |
| Script Planning | Preview、异步确认、Scene/Shot 计划 | MVP | `script_service.py`、`operations/store.py`；Operation 仅内存，确认时可能重跑而非提交已审阅计划 |
| Generation | DB 队列、retry/cancel API、Asset/Version 回填 | MVP | `generations/worker.py`；running 任务重启后滞留，完成链非原子，provider provenance 不可靠 |
| Image Provider | Mock 与 ComfyUI Adapter | Mock 可用，真实 Adapter 未达可交付 | 默认 workflow 路径与仓库布局不一致；取消引用未持久化；自定义 workflow 约束弱 |
| Version / Asset | 图片不可变版本、激活版本、文件安全路径 | MVP | `version_service.py`、`asset_service.py`；版本号并发竞争、元数据非标准 JSON、缺资产库 |
| AI Director | Understand→Context→Plan→Execute→Review、三工具 | MVP | Fake 场景测试通过；Run 内存存储、取消非协作式、无审批/ChangeSet、跨项目 ownership 校验不足 |
| Event / WebSocket | 统一 Envelope、sequence、前端 query invalidate | MVP | 进程内 EventBus；无鉴权、项目订阅、回放与 gap reconcile；客户端类型断言多于验证 |
| Frontend Shell | 五区布局、Explorer、Storyboard、Inspector、Queue、Director | MVP+ | 核心可操作；无统一 Toast/Skeleton/Error Boundary，部分按钮为惰性或错误承诺，无前端测试 |
| Desktop Shell | Tauri 开发壳、后端子进程启停 | 开发级 | `apps/desktop/src-tauri/src/backend.rs` 依赖源码布局与外部 `uv`，未形成可发布 sidecar/迁移/回滚流程 |

## 4. 关键数据与运行语义

### Project State

SQLite 是当前业务事实源，方向正确。LangGraph checkpoint 没有替代项目数据库，Agent 工具也通过 Service 操作数据。

需要优先修复的事实源风险：

- `Scene` 没有架构红线要求的 revision；部分写操作没有乐观并发。
- Scene/Shot/Version 的 `MAX + 1` 编号策略在并发下可能重复。
- Shot reorder 接受部分 ID 时可能产生重复序号，缺完整集合与唯一性校验。
- 多个 provenance 字段为弱引用文本，数据库无法阻止悬空引用。
- Asset → Version → Generation 完成流程跨多次 commit，进程崩溃可留下半完成状态。

### 异步 Runtime

- Operation Store 与 Agent Run Store 均为进程内字典，重启即丢失。
- Generation 使用数据库轮询是合适的本地桌面方案，但只认领 `queued/retrying`；已标为 `running` 的任务无法自动恢复。
- Worker 配置暴露 concurrency，但当前循环串行执行。
- Event sequence 是进程内计数；服务重启后归零，前端没有 REST 对账恢复。

### 外部 Adapter

`ImageProvider` 是合理的 Seam，Mock 和 ComfyUI 两个 Implementation 已证明抽象有实际价值。但 Seam 尚不够深：Provider 选择、持久化的 provider 名称、provider_ref、能力协商和 workflow 校验散落在 Service、Worker、Registry 与 Adapter 内，调用者仍需理解实现细节。

## 5. 前端状态模型

- TanStack Query 承载 Server State、Zustand 承载选择/工作区/事件临时状态，方向正确。
- `selectionStore` 与 `workspaceStore.activeShotId` 形成两个可能漂移的 UI 事实源。
- EventSocket 是模块级单例，离开页面后仍会重连；没有按 project 订阅或销毁生命周期。
- 手写 `frontend/src/api/types.ts` 与 Pydantic DTO 重复，存在契约漂移。
- Queue 与 Agent live store 无启动水合与 missed-event recovery；刷新或断线后可能卡在旧状态。

## 6. 工程与交付状态

| 项目 | 当前状态 |
|---|---|
| 后端测试 | 31 项通过，覆盖核心 Service/API/Agent happy path |
| 前端测试 | 无 |
| E2E | 无 |
| 前端构建 | `npm run build` 通过 |
| Tauri 检查 | `cargo check` 通过 |
| Lint / format / type gate | 未形成统一仓库门禁 |
| CI/CD | 无 `.github/workflows` |
| Docker | 无；当前桌面产品不应仅为“架构完整”强行引入 |
| 发布打包 | 未包含 Python Runtime、迁移、签名、升级与回滚闭环 |
| 日志/监控 | 基础文本日志；无结构化上下文、指标、错误追踪 |
| 安全 | 本地端口无会话认证，WS 全量广播，Tauri CSP 为 `null` |

## 7. 架构深度评估

当前有四个值得加深的 Module，均由真实重复或故障边界驱动：

1. **Generation Completion Module**：把任务认领、Asset 创建、Version 激活、Generation 完成放在一个可恢复的业务事务边界内。
2. **Project Ownership Module**：统一跨 Shot/Scene/Episode/Project 的归属验证，避免每个 Service 重写查询链并遗漏隔离检查。
3. **Studio Contract Module**：由 OpenAPI/Event schema 生成或校验前端类型，减少手写 DTO 和宽泛事件断言。
4. **Provider Runtime Module**：统一 provider 解析、能力、preflight、provenance、cancel reference 与运行状态。

这些 Module 的目标是提高 Locality 与 Leverage，而不是增加层数。单次使用、没有变化轴的逻辑不应再抽象。

## 8. 事实源漂移（P1-E6-T02 已关闭，2026-09-06）

- ~~根 `README.md` 仍把项目描述为 Stage A~~ → 已修正：README 现声明 MVP+/Alpha 闭环 + 能力矩阵（含默认模式与真实验证状态）。
- ~~`design-qa.md` 仍称 Stage D 未接入~~ → 已修正：两处改为历史记录口径（QA 当时未接，现已接 live Director API）。
- ~~`AGENTS.md` 技术栈小节仍写 `asyncio.Queue`~~ → 已修正：改为 DB-poll Worker。
- 遗留 `frontend/src/features/ai/DirectorPanel.tsx`（锁定版）已确认移除，目录仅剩 `useOperationPolling.ts`；现用 `features/director/AIDirectorPanel.tsx`。
- 回归防线：`backend/tests/test_docs_factsource.py` 锁定上述入口文案，漂移即红。

在 Phase 1 应建立“代码、契约、操作手册、里程碑状态”同步规则；以后不能再以单一状态段落代替可执行验证。
