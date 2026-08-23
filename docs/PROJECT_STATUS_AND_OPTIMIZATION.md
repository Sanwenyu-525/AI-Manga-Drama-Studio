# 项目现状全面分析与优化方向报告

> 报告日期：2026-08-23 ｜ 分析对象：`main`（HEAD `d36e91e`）+ 工作区未提交改动
> 分析方法：全仓库代码扫描（后端 / 前端 / 桌面壳 / 文档 / CI / 脚本）+ 分层红线核查 + 实际执行测试套件验证
> 实测基线：后端 pytest **314 passed / 1 skipped**（4:46）；前端 vitest **26 文件 / 157 项全部通过**（2:09）
> 性质：只读分析报告，未修改任何业务代码

---

## 一、项目阶段判断

**结论：处于「MVP+ / Alpha 功能闭环」阶段 —— 核心生产闭环已完成且测试覆盖良好，但真实 AI 链路未经实测验证、成片只有无声视频、无发行工程，距 Beta / 可生产使用还有明确的一段路。**

判断依据（均为代码与提交证据）：

- MVP 四阶段（Stage A–D）全部完成并有验收记录（`AGENTS.md` §5）；
- Post-MVP 又推进了 P1（收尾）、P2–P6（角色/地点/服装版本库、read model、provenance、prompt 版本、工作流注册表、Job DAG）、P7（Agent 落库 + Proposal 审批）、P8（连续性引擎）、P9（时间线 + 整集渲染），见 git log `4f80177`→`501b422` 共 145 个提交；
- `docs/audits/post-mvp-audit.md` 自评"功能闭环 Alpha"；`docs/alpha/design/codex-phase-roadmap-v0.1.md` 头部状态 P0–P9 全部 DONE；
- 但：LLM/图片生成默认走 fake/mock（`backend/app/core/config.py:46,55`），openai/comfyui 真实链路无测试覆盖；成片渲染只有视频轨（无混音）；Tauri 壳为开发级（128 行 Rust，CSP null，无 sidecar/安装器）。

```text
当前完成度：65%   （对「Alpha 可用桌面产品」目标；若按 PRD 完整愿景衡量约 45%）
工程成熟度：60%   （分层纪律与测试优秀；但前端无 lint、无 E2E、无发行流水线）
产品完成度：45%   （小说→分镜→生成→时间线→渲染闭环可用；音频/字幕/批量生产缺失）
架构成熟度：75%   （红线基本落实、Provider 抽象干净；存在 3 处破口与进程内有状态）
测试成熟度：70%   （471 项测试、迁移回环、阶段 gate；但 openai 真路径与 E2E 为零）
可维护性：  70%   （事实源文档体系是巨大优点；但已出现双轨计划与状态漂移）
```

---

## 二、能力清单（按代码实际实现，非 README 声明）

### 已完成（真正实现且可用，有测试佐证）

| 能力 | 证据 |
|---|---|
| Core Studio：Project/Episode/Scene/Shot CRUD、软删除、revision 乐观并发 | `backend/app/services/{project,episode,scene,shot}_service.py`；`test_revision_*` |
| 小说导入 → AI 分析 → Scene/Shot 生成（202 + Operation 轮询） | `script_service.py`、`operations/store.py`、前端 `useOperationPolling.ts` |
| 图片生成全链路：DB 即队列 + 租约 + 指数退避 + 崩溃恢复 | `generations/worker.py`（907 行，头部文档自述设计） |
| 不可变版本系统 V1/V2 共存 + Set Active + 版本溯源 | `version_service.py`、`provenance_service.py`、ADR-001/002 |
| 角色/地点/服装：身份表 + 版本库 + MASTER | `character_version_service.py`、`location_service.py`、`costume_service.py`（P2 提交 `eefea46`、`1eefd8b`） |
| AI Director：LangGraph 编排 + SQLite Checkpointer + Proposal 审批流 + WAITING_HUMAN + resume | `agents/director/`、`agents/checkpointer/sqlite_saver.py`、`proposal_service.py`（418 行） |
| 连续性引擎：规则 + 状态机 + 重算 + Agent check/fix + UI 警示 | `continuity_service.py`（1180 行）、`agents/continuity/runner.py`、前端 `features/continuity/` |
| 时间线：四轨模型、clip 拖拽/裁剪、版本替换、排片、非渲染预览 | `timeline_service.py`、前端 `TimelineView.tsx` + `timelineMath.ts` |
| 整集渲染：mock MJPEG AVI（真实可播）/ ffmpeg H.264 MP4，产物注册 FINAL_VIDEO 不可变版本 | `providers/render/{mock,ffmpeg}.py`、`render_service.py` |
| Job/JobTask/DAG 调度（P5 正式化） | `jobs/scheduler.py`（313 行）、`job_service.py` |
| WS 事件网关：envelope + sequence 去重 + 前端 EventRouter | `events/{bus,ws}.py`、前端 `events/socket.ts` |
| ComfyUI 客户端：prompt 提交、WS 进度、历史轮询、断线 fallback、取消 | `providers/comfyui/client.py`（169 行，完成度高） |
| CI：backend（uv+ruff+pytest+密钥扫描）/ frontend（build+vitest）/ desktop（cargo check） | `.github/workflows/ci.yml` |

### 基本完成（主体存在，有明确缺口）

- **真实 LLM 模式**：`llm/factory.py:26-28` 真接 `ChatOpenAI` + `with_structured_output`，`script_service.py:162,200` 与 `director/graph.py:104,170` 均走 `llm.structured()` —— 管线已通，但**openai 路径零测试、prompt 质量未经真实迭代**，默认仍是 fake。
- **ComfyUI 集成**：client 完整，但默认 workflow 模板 `workflows/default_image_api.json` 是占位符，未在真实 ComfyUI + 真实模型上验证过出图回填。
- **Tauri 桌面壳**：能跑（`studio.ps1` 一键起全栈），但 128 行 Rust、`csp: null`、依赖源码布局与外部 uv，`docs/architecture/current-state.md` 自评"开发级"。
- **前端工作流页**：`WorkflowsPage.tsx` 只读目录 + preflight 元数据，编辑明确标注"MVP 范围外"。
- **前端基线恢复**：`2cfcb3d`（恢复样式）+ `2a6f143`（Episode-aware 路由）已落地 R0/R1 主体，但仍有 6 个前端文件未提交（R0/R1 收尾中）。

### 开发中（有代码，未完全打通）

- **R0–R4 前端重构计划**（`docs/frontend-refactor-plan-v0.1.md`）：R0/R1 基本落地，R2（响应式布局）、R3（query key 统一 + socket 拆分）、R4（一致性收尾）未做。
- **Episode 渲染的完整成片**：视频轨可渲，VOICE/MUSIC/SUBTITLE 三轨只是数据结构，渲染器不混音。

### 仅设计（文档/接口存在，无实现）

- **视频生成 Provider**：`providers/video/` 只有 `base.py` + `unavailable.py`（一律 raise ProviderUnavailableError）—— 存根。
- **TTS / 配音 / BGM / 音效**：PRD §150 与 §311 明确要求；`providers/` 下**无任何音频 provider**，连存根都没有。
- **批量生产 / Production Run**（backlog P4-E2）、**ChangeSet/Undo**、**Continuity 跨集**、**多 Agent**、**云端**：仅文档规划。
- **字幕渲染**：SUBTITLE 轨有数据模型，无烧录/导出实现。

### 尚未开始（产品明显需要但不存在）

- 桌面发行工程：安装器、后端 sidecar 打包、签名、自动更新、用户数据备份/迁移回滚（backlog P5-E2 全部 XL 项未动）。
- E2E 测试（无 playwright/cypress）。
- 前端 ESLint / Prettier / 代码分割 / OpenAPI 类型生成。
- 鉴权与多用户隔离（当前完全无 auth，本地单机假设 —— 桌面 MVP 可接受）。

---

## 三、当前架构还原

### 3.1 总体形态

**分层模块化单体 + Provider 端口适配器 + 顶层 Agent 编排**的混合体：

```text
React SPA (五区布局, URL 为视图事实源)
  → REST (202+Operation/轮询) + WS (EventBus→envelope+sequence)
    → API Router (21 个, 无业务逻辑✅)
      → Services (26 个, 业务核心)
        → Domain (20 文件) / Repositories → SQLAlchemy 同步 + SQLite WAL
      → Provider 抽象: image / comfyui / llm / render / video / workflow (注册表+preflight)
    → Generations Worker (DB-poll 单并发) + Jobs Scheduler (DAG)
    → AI Director (LangGraph 五节点) ── 只允许调 Service ──→ AgentRun 落库 + 独立 Checkpointer DB
```

与 `backend-architecture-v0.1.md` 的设计**高度一致**，红线 11 条落实 8.5 条（见 §五）。这是本项目最大的工程优点：**文档先行 + 按文档施工 + 提交历史与任务编号一一对应**。

### 3.2 前端架构（事实）

- 路由：`src/app/router.tsx` 唯一路由表，Episode-aware canonical 路由 + 3 条 legacy 重定向；URL 拥有工作区，Editor Tabs 只是镜像（`WorkspaceHost.tsx:1-2` 注释明示契约）。
- 状态分层纪律好：服务端数据只在 TanStack Query；6 个 Zustand store 全部是 UI/瞬态（`selectionStore.ts` 25 行、`workspaceStore.ts` 面板尺寸、`agentStore.ts` run 镜像、`generationStore.ts` progress 高频直写）——**无 store 滥用、无 props drilling**。
- API client：`api/client.ts` 统一 fetch 封装（超时/AbortSignal/ApiError 带 request_id/FormData），质量高；但 `api/types.ts` **912 行手写 DTO**，无 OpenAPI codegen。
- WS：`events/socket.ts` 单例 + 指数退避重连 + sequence 去重 + envelope 校验。
- 样式：`:root` 17 个 CSS 变量的深色 design token 系统（`styles.css:1-19`），风格统一；但 1450 行单文件无分层。

**存在的问题**：

1. 【问题】巨型多职责组件：`TimelineView.tsx` 715 行（拖拽引擎+轨道 UI+3 侧栏 tab+渲染导出）、`ProjectExplorer.tsx` 596 行（树+CRUD+弹窗+版本库）、`ShotInspector.tsx` 449 行（双 variant+表单+冲突+版本+连续性）。
2. 【问题】**Query Key 双轨制**：`api/queryKeys.ts` 工厂存在，但约 48 处原始数组 key + 39 处原始 invalidation 散落在组件与 `socket.ts:130-131,202-203,292-297`；`providers/workflows/versions/generations` 甚至不在工厂内。WS 失效靠字符串约定，无编译期保障 —— 全项目最脆的数据一致性环节。
3. 【问题】无 ESLint/Prettier、无 React.lazy 代码分割、无 E2E。
4. 【推测】WS 重连成功后未做断线期间的补偿 refetch（`socket.ts:52-54` 仅重置退避），断线中的事件会漏 invalidate。

### 3.3 后端架构（事实）

- 分层干净：api 层 grep `db.query` 零命中，全部走 `Service(Session)` 注入；统一错误 envelope 四 handler（`main.py:98-158`）+ `core/errors.py` 错误码；X-Request-ID 中间件 + correlation 日志。
- 队列设计务实：generations 表即队列（原子条件 UPDATE claim + lease 心跳 + 崩溃恢复），Job/JobTask/Dependency DAG 只编排不执行，与 worker 分工明确。
- Agent 层：LangGraph 只编排不碰 DB（改动经 Service），AgentRun 在业务库、LangGraph 状态在独立 checkpointer 库 —— "Checkpoint ≠ Project DB" 红线落实。
- Provider 层：registry + preflight + base 抽象，**零业务依赖**（grep 证实），换 ComfyUI/新增 TTS 不动业务层。

**架构适配性判断（未来 6–12 个月）**：

> 【现状】单进程桌面应用 + 单机 SQLite + 单 GPU 生成。
> 【推测】6 个月内（继续单机桌面产品路线）：当前架构完全够用，不需要大改。
> 【推测】若走向「批量生产整季 / 多端 / 云端」，三个硬顶会出现：① EventBus/operations store/WS 连接全内存（重启丢事件与 operation 状态）；② 同步 SQLAlchemy + worker 单并发（config 强制 generation_concurrency=1）；③ 无鉴权多用户模型。这些都是**已知且被注释自认的设计边界**，不是事故。

---

## 四、模块依赖与耦合分析

```text
UI → API Router → Services → Repositories → SQLite   （方向正确✅）
AI Director(LangGraph) → Services                    （正确✅，但有破口⚠）
GenerationService → Provider Registry → ComfyUI/Render/LLM （正确✅，零反依赖）
EventBus ← Services(commit 后 publish)  → WS → 前端 Query invalidate
```

高耦合/越界点（全部有证据）：

| # | 问题 | 位置 | 程度 |
|---|---|---|---|
| 1 | agents 层直接持 SQLAlchemy Session / import `app.db.session`（红线"Agent 只走 Service"破口） | `agents/tools.py:12`、`agents/context_resolver.py:14`、`agents/director/runner.py:22`、`agents/continuity/runner.py:21` | 轻（变更仍经 Service，但 Session 生命周期管理越层） |
| 2 | API 层裸 SQL + 业务函数 | `api/continuity.py:88`（`db.execute(text(...))` 合并 shadow warnings）、`api/prompts.py:62` 函数内 import Repository | 轻，但"例外会繁殖"的起点 |
| 3 | Services import `app.llm.gateway.LLMGateway` | `script_service.py:34`、`continuity_service.py:78` | 设计选择（LLMGateway 即业务抽象协议），可接受 |
| 4 | revision 冲突检查在 5 个 service 重复实现 | character:156 / costume:135 / episode:107 / location:147 / project:182 | 无基类/mixin，每加实体抄一遍 |
| 5 | 前端 shot 选中双源（URL route.shotId 与 selectionStore/workspaceStore） | `ShotInspector.tsx:21-22` 二者取或 | R1 已大幅收敛，残余在收尾中 |

**未来最容易成为技术债核心的位置**：`services/` 目录（26 个 service、最大 1180 行、无公共基类）——目前靠纪律维持，实体再涨 5–8 个（声音、字幕、成片模板、批量 Run）时会失控。

---

## 五、代码质量分析

### P0（可能造成数据丢失 / 严重 Bug / 无法扩展）

- **无。** 未发现路径穿越（`asset_service.py:390-399` `_safe_path` resolve 校验 + 50MB 上限）、未发现版本覆盖（版本不可变由 service 强制）、事务边界正确（77 处 commit 均先于 publish）。
- 唯一半 P0：**`api/continuity.py:88` 裸 SQL** 属于红线破口，若成为惯例会侵蚀架构 —— 归入 P1 首项处理。

### P1（明显影响可维护性/可扩展性/稳定性）

1. **事实源与仓库状态漂移**：README 停在"MVP Stage A"（落后 4 个大阶段）；`docs/roadmap/`（Phase 1–6，08-15）与 `docs/alpha/design/codex-phase-roadmap`（P0–P9 DONE）双轨并行、状态互不反映；工作区 26 项未提交改动混杂合法重构产物与杂物。对 **AI Agent 驱动开发的仓库**，过期事实源 = 高频返工来源（AGENTS.md §2 自己声明"文档是事实源"）。
2. **杂物与个人脚本进入 git**：已提交 1.4MB 截图 `c8368514-*.png`、`design-qa.md`、`vinput-asr-dummy.js`；已暂存 `.plib-debug/`、`frontend/.r0-smoke/`、**`scripts/Disable-Startup.ps1` / `Enable-Startup-Restore.ps1`（操作 Docker/QQ/微信/WPS 开机自启的个人系统脚本，与项目无关，疑似误入）**。无 pre-commit 拦截。
3. **前端 Query Key 双轨制**（见 §3.2）。
4. **真实链路零验证**：`STUDIO_LLM_MODE=openai` / `STUDIO_IMAGE_PROVIDER=comfyui` 无任何测试或实测记录；`fake_planner.py` 仅覆盖 shot 域关键词规则 —— "demo 可用"与"产品可用"之间的差距未被覆盖。
5. **revision/分页/软删除五重复制**，无 mixin。

### P2（应逐步改善）

1. 巨型文件：`continuity_service.py` 1180 行（规则+语义+状态+transition+ack/fix）、`generations/worker.py` 907 行（claim+lease+retry+render+cancel）、前端 `TimelineView.tsx` 715 行等。
2. `api/types.ts` 912 行手写 DTO 与 Pydantic 双份漂移风险。
3. 前端无 ESLint/Prettier/代码分割；`styles.css` 1450 行单文件。
4. operations store 内存态重启即失（`operations/store.py:31-33`，注释已自认）。
5. readmodel 无专测文件（覆盖弱）。

### P3（体验与洁净度）

- WS 重连后无补偿 refetch；全局 `/assets` 与项目 `/assets` 命名混淆；Storyboard Tab 标题用 UUID 尾部而非 scene_number；New Project 四种启动方式实际只有两种行为（refactor-plan P2-2）。

---

## 六、Technical Debt Map

| 类别 | 问题 | 位置 | 影响 | 严重度 | 修复成本 | 现在处理? |
|---|---|---|---|---:|---:|---|
| Architecture | agents 持 Session 越层 | `agents/tools.py:12` 等 4 处 | 红线腐化起点 | 中 | 低（改注入 Service） | ✅ 是 |
| Architecture | 进程内有状态（EventBus/operations/WS） | `events/bus.py:124`、`operations/store.py:31` | 重启丢状态 | 低（单机） | 高 | ❌ 暂不 |
| Code | revision/分页/软删 ×5 复制 | 5 个 `*_service.py` | 新实体成本线性涨 | 中 | 中 | ⚠️ 下一个实体出现时抽 mixin |
| Code | 巨型文件（1180/907/715） | 见 §五 P2 | 改动/定位成本高 | 中 | 中 | ⚠️ 按触发条件拆（refactor-plan R3 原则） |
| UI | styles.css 1450 行单文件 | `frontend/src/styles.css` | 合并冲突面大 | 低 | 低 | ⚠️ 随 R2/R3 顺手拆 |
| API | Query Key 双轨 | `socket.ts` + 组件 48 处 | WS 失效静默失败 | 高 | 中 | ✅ 是（R3 首项） |
| API | 手写 types.ts 912 行 | `frontend/src/api/types.ts` | DTO 漂移 | 中 | 中（codegen 一次） | ⚠️ Phase 1 决策 |
| Database | 19 迁移无回滚脚本（仅 head） | `alembic/versions/` | 升级风险 | 低 | 中 | ❌ 发行前 |
| Agent | fake_planner 仅 shot 域 | `agents/fake_planner.py`（122 行） | 真实意图覆盖窄 | 中 | 中 | ✅ Phase 2 随真 LLM |
| Workflow | 默认模板占位 | `workflows/default_image_api.json` | ComfyUI 真链路不可用 | 高（产品） | 中 | ✅ Phase 2 |
| Testing | openai 路径 / E2E / readmodel 零覆盖 | — | 回归不可见 | 中 | 中 | ✅ Phase 1–2 |
| DevOps | 无 pre-commit / 无发行流水线 / 无备份 | `.github/`、`apps/desktop` | 协作与交付 | 中 | 高（发行）/ 低（pre-commit） | pre-commit ✅ 现在做；发行 Phase 4 |
| Docs | README 过期 + 双轨 roadmap | `README.md`、`docs/roadmap/` | Agent/新人误导 | 高 | 低 | ✅ 立即 |
| Performance | 单 worker + 0.5s DB 轮询 + 同步 ORM | `worker.py:56`、`config.py:67-73` | 批量生产吞吐顶 | 低（当前） | 高 | ❌ 规模化后 |
| Security | 无 auth、CSP null、allow_credentials | `main.py:73-79`、`tauri.conf.json` | 本地桌面可接受 | 低（当前） | — | ❌ 产品化前评估 |

---

## 七、重复建设识别

| 重复项 | 位置 | 处置 |
|---|---|---|
| revision 冲突检查 ×5 | character/costume/episode/location/project service | **抽象**为 mixin/base（第 6 个实体出现时） |
| 分页 offset/limit 各自实现 | 各 service（如 `asset_service.py:334-374`） | 同上，随 mixin 顺带 |
| 软删除过滤模式 | 各 repository | 同上 |
| 前端裸 Query Key vs queryKeys 工厂 | 组件 vs `api/queryKeys.ts` | **合并**到工厂（R3 首项，非新抽象） |
| 全局 Assets vs 项目 Assets 两套语义 | `/assets`（Recent Generations）vs `/projects/:id/assets`（Asset Library） | **保留但改名**（refactor-plan R4：全局页改"跨项目素材"） |
| 事件→缓存失效映射散落 | `socket.ts` switch | **保留** switch，但 key 走工厂；不需要事件总线类抽象 |

未发现重复 Service、重复 DTO、重复 Provider 能力 —— 后端命名空间纪律良好，**不建议**为进一步统一而引入更多抽象层。

---

## 八、Hidden Incomplete Features（看起来完成，实则未完成）

| 模块 | 表面 | 实际 | 证据 |
|---|---|---|---|
| 时间线四轨 | UI 有 VOICE/MUSIC/SUBTITLE 轨 | **纯数据结构，渲染不混音不烧字幕**，成片只有视频 | `providers/render/ffmpeg.py`（仅视频拼接）、`providers/video/` 存根 |
| 视频生成 | providers 目录有 video/ | `unavailable.py` 一律 raise | `providers/video/unavailable.py:20-30` |
| AI Director"智能" | 面板可用、Scenario A/B/C 过 | 默认 fake_planner 是**关键词规则引擎**（6 景别+6 情绪），非 LLM | `agents/fake_planner.py:19-26` |
| ComfyUI 集成 | 设置页可测连接、可生成 | client 完整但**默认 workflow 是占位模板**，未真实出图验证 | `workflows/default_image_api.json` |
| TTS/配音/BGM | PRD 要求、时间线有轨 | **后端无任何音频 provider，连存根都没有** | `providers/` 目录清单 |
| Operation 恢复 | 202+轮询体验完整 | 重启即失（内存 dict），前端会永远轮询失败 | `operations/store.py:31-33` |
| 「导演画布」按钮 | 顶部导航存在 | 只是切换右侧 AI Director 面板，非文档定义的 Director Canvas | refactor-plan P2-1 |
| 新建项目向导 | 四种启动方式 | 实际只有"建 Project(+Episode)"两种行为，Stepper 只实现第一步 | refactor-plan P2-2 |

---

## 九、工程化能力清单

| 能力 | 状态 | 证据 |
|---|---|---|
| 单元/集成测试 | ✅ 已有 | pytest 314+1skip、vitest 157（本日实测） |
| lint（后端） | ✅ 已有 | ruff E/F/W/B/S/UP/ASYNC，`pyproject.toml` |
| lint/format（前端） | ❌ 缺失 | 无 .eslintrc*/.prettierrc* |
| type check | ✅ 部分 | tsc strict 随 build；无独立 typecheck script |
| CI | ✅ 已有 | `.github/workflows/ci.yml` 三 job |
| CD / 发行流水线 | ❌ 缺失 | 无 release/bundle workflow |
| E2E | ❌ 缺失 | 无 playwright/cypress |
| pre-commit | ❌ 缺失 | 杂物已实际进入暂存区（反证） |
| Docker | ❌ 缺失（**暂时不需要**，桌面产品） | — |
| 环境隔离 | ✅ 部分 | STUDIO_* env + fake/mock 模式；无 staging/prod 概念（桌面不需要） |
| Migration | ✅ 已有 | alembic 19 版；`studio.ps1 start` 自动迁移 |
| 日志 | ✅ 已有 | stdlib logging + correlation_id + X-Request-ID |
| Metrics/Tracing/Crash Report | ❌ 缺失 | 桌面单机阶段**暂不需要** |
| Backup | ❌ 缺失 | 发行前必须（用户项目数据） |

---

## 十、性能分析

**当前真实存在的问题**：

- 后端 pytest 全程 4:46：生成类测试走真实 Pillow 编码/写盘，属可接受但 CI 会随用例增长变慢（推测：可给 render mock 加 fast 模式）。
- 前端无代码分割：715 行 TimelineView 进首屏 bundle；Tauri 桌面加载本地资源，影响小（推测：浏览器构建才可感）。
- Agent TokenBudget（4096 字符头尾截断）+ Selection-aware 最小上下文 —— context 设计已节制，无浪费。

**当前不存在、规模化后才会出现的**（明确不提前优化）：

- 同步 SQLAlchemy + 单 worker：GPU 生成本来就串行，单并发是**合理约束**而非缺陷；批量生产整季时才需要队列并发化。
- SQLite WAL 单写者：单机桌面完全够。
- WS 无广播扇出压力（单客户端）。
- 前端虚拟化已做（`VirtualizedShotGrid` + `useVirtualizedGrid`）。

---

## 十一、产品层面分析（用户流程走查）

目标主路径（PRD §5）：**新建项目 → 导入小说 → AI 分析出 Scene/Shot → 分镜板编辑 → 生成图片（版本/审批/连续性）→ 时间线排片 → 渲染导出成片**。

| 环节 | 状态 | 断点/负担 |
|---|---|---|
| 进入/创建项目 | ✅ 通 | New Project 四入口语义重复（认知负担）；Stepper 只有第一步 |
| 导入+AI 分析 | ✅ 通 | 默认 fake 模式分析质量是规则级的（用户若不知 env 切换会困惑） |
| 分镜编辑 | ✅ 通 | URL 直达已修复（R1）；Tab 标题用 UUID 尾部不友好 |
| 生成+版本 | ✅ 通 | mock 出图非真实风格，真 ComfyUI 需用户自备 workflow 模板 |
| AI Director 修改 | ✅ 通 | 审批流完整；但 fake planner 只懂景别/情绪关键词 |
| 时间线排片 | ✅ 通 | 1440×900 布局预算失衡（R2 未做） |
| **渲染导出** | ⚠️ 半通 | **导出的"漫剧"没有声音、没有字幕烧录 —— 对一款"剧"类产品，这是当前最大的产品断点** |
| 再修改/重渲 | ✅ 通 | 版本不可变 + replace-asset 语义正确 |

新用户上手负担中等（五区布局清晰），但「为什么生成的图是色块」「为什么片子没声音」两个问题会在第一次真实使用时立刻出现 —— 都指向同一个根因：**真实生成链路未接通/未验证**。

---

## 十二、当前最核心的问题（提炼为 4 个）

### 核心问题 1：事实源漂移 + 仓库状态混杂（AI 协作仓库的特有高风险）

- **现象**：README 停在 Stage A；roadmap 双轨（Phase 1–6 vs P0–P9）状态互不反映；26 项未提交改动里混着调试产物、冒烟截图与个人系统脚本；无 pre-commit。
- **根因**：项目以 AI Agent 为主要施工者，但"文档↔代码↔git 状态"的同步纪律只靠人工，且没有工具拦截。
- **影响**：任何后续 Agent/协作者读到过期事实源都会做错决策；个人脚本（含 `WpsUpdateLogonTask_ASUS` 这类机器专属名）一旦推上 GitHub 属于隐私泄漏。
- **为什么现在解决**：成本极低（半天），且直接决定后续所有开发的质量。
- **方案**：清理暂存区（移除个人脚本与调试产物，进 .gitignore）；提交 R0/R1 收尾；README/roadmap 合并为单一状态源；加 pre-commit（禁止 .png/.log/调试目录 + ruff + tsc）。

### 核心问题 2：「AI 原生」核心卖点未在真实条件下验证

- **现象**：LLM 默认 fake、图片默认 mock、ComfyUI 模板占位；openai/comfyui 真实路径零测试、零实测记录。
- **根因**：MVP 三原则先做 Studio 再接 AI 是**正确的顺序**，但 Stage B 之后真链路验证一直被后续功能（P2–P9）挤占。
- **影响**：产品的差异化价值（AI 原生生产）实际处于"未验证"状态；fake→real 切换时大概率暴露 prompt/结构化输出/workflow 映射的真实缺陷。
- **方案**：一次"真链路冲刺"——`STUDIO_LLM_MODE=openai` 跑通小说分析三案例、真实 ComfyUI workflow 模板出图回填、Director 真实意图理解；补 openai 路径契约测试（mock HTTP 层）；fake 保留为 CI/开发模式。

### 核心问题 3：成片无声 —— "漫剧"产品的最大产品缺口

- **现象**：四轨里三轨（VOICE/MUSIC/SUBTITLE）是数据壳；无 TTS provider；渲染不混音。
- **根因**：P9 优先打通了视频时间线与渲染管线（合理），音频链路从未立项。
- **影响**：用户拿到手的成片不构成"剧"；时间线 UI 承诺了 UI 未兑现的能力（Hidden Incomplete）。
- **方案**：Phase 3 立项音频链路：TTS Provider（接口对齐现有 registry 模式）→ 配音生成任务 → ffmpeg 混流（`-filter_complex amix`）→ 字幕烧录。渲染器已具备 ffmpeg 基建，边际成本可控。

### 核心问题 4：前端数据层一致性防线缺失

- **现象**：Query Key 双轨（48 处裸数组）、912 行手写 DTO、WS 重连无补偿、无 lint。
- **根因**：功能高速迭代期未建立前端工程门禁。
- **影响**：某处 key 拼写变化即静默失效（UI 不刷新且无报错）；DTO 漂移靠人肉发现。
- **方案**：执行 refactor-plan R3 前两项（key 统一 + socket 拆分）+ ESLint/Prettier + 评估 openapi-typescript codegen（后端 FastAPI 免费提供 OpenAPI schema，接上即消灭手写 types.ts）。

---

## 十三、架构风险预测

| 时间 | 预测瓶颈 | 依据 |
|---|---|---|
| 3 个月 | services 目录继续膨胀（每阶段 +2~4 个 service、无 mixin），agents 层 Session 破口被新代码模仿；前端大组件再长 200 行 | P2–P9 每阶段都以新增 service/组件交付；当前无 lint/mixin 拦截 |
| 6 个月 | 真实链路接入后暴露 prompt 质量与结构化输出健壮性问题；音频引入后 render worker 907 行进一步复合；时间线 UI 承诺与渲染能力差距成为用户投诉点 | fake_planner 122 行规则 vs 真实自然语言意图空间；worker 已含 render 分支 |
| 12 个月 | 若走向批量生产/云端：内存 EventBus、单 worker、无 auth 三硬顶集中爆发，需要一次"去进程内状态"改造（DB 事件表/多 worker/会话层） | `events/bus.py`、`operations/store.py`、`config.py:67-73` 的设计注释均已自认边界 |

---

## 十四、优化方向（按时机分档）

**必须立即处理（影响后续开发的基础）**
1. 仓库清账：暂存区去杂物 + .gitignore 补漏 + pre-commit；提交 R0/R1 收尾（6 个前端文件）。
2. 事实源同步：README 重写为当前真实状态；roadmap 双轨合一（以 codex P0–P9 为历史归档、`docs/roadmap` 为唯一前瞻）。
3. refactor-plan R3 首项：Query Key 全量收编进工厂。
4. ESLint + Prettier 接入 CI（前端质量门禁从零到一）。

**MVP 后应该处理（很快成瓶颈）**
5. 真链路冲刺（LLM openai 实测 + prompt 迭代 + ComfyUI 真实模板 + 契约测试）。
6. 音频链路立项（TTS provider + 混音渲染 + 字幕烧录）。
7. OpenAPI codegen 决策（消灭 912 行手写 types.ts）。
8. service mixin（revision/分页/软删三合一基类），agents 层 Session 注入改造。

**产品化之前处理**
9. E2E 冒烟（Playwright：主路径一条，fake/mock 模式跑）。
10. Tauri 发行：后端 sidecar 打包、CSP、安装器、数据备份与迁移回滚。
11. alembic downgrade 路径、错误上报（本地日志收集即可）。

**规模化之后处理（现在明确不做）**
12. Redis/Celery/消息队列、async SQLAlchemy、多 worker、Docker 化、微服务拆分、多 Agent 框架、云端多租户、插件系统。

---

## 十五、优先级矩阵

| 优化项 | 用户价值 | 工程价值 | 风险 | 成本 | 优先级 |
|---|---:|---:|---:|---:|---|
| 仓库清账 + pre-commit | 低 | 高 | 低 | 低 | **P0** |
| 事实源同步（README/roadmap 合一） | 低 | 高 | 低 | 低 | **P0** |
| Query Key 统一（R3 首项） | 中 | 高 | 低 | 中 | **P0** |
| ESLint/Prettier + CI | 低 | 高 | 低 | 低 | **P0** |
| 真链路冲刺（openai+comfyui 实测） | **高** | 高 | 中 | 中 | **P1** |
| 音频链路（TTS+混音+字幕） | **高** | 中 | 中 | 高 | **P1** |
| OpenAPI codegen | 低 | 中 | 低 | 中 | P1 |
| service mixin + agents Session 改造 | 低 | 中 | 低 | 中 | P1 |
| refactor-plan R2（响应式布局） | 中 | 低 | 低 | 低 | P2 |
| 巨型文件拆分（按触发条件） | 低 | 中 | 中 | 中 | P2 |
| E2E 冒烟 | 中 | 中 | 低 | 中 | P2 |
| Tauri 发行工程 | 高（交付前提） | 中 | 高 | 高 | P2（产品化前） |
| 队列并发化 / 去内存态 / auth | — | — | — | — | P3（规模化后） |

---

## 十六、下一阶段开发路线

### Phase 1 — 稳定基础与治理（约 1 周）

- **目标**：仓库回到"干净、可信、有门禁"状态，前端数据层一致性收口。
- **任务**：清账四件套（§十四 1–2）+ Query Key 统一 + ESLint/Prettier + 提交 R0/R1 收尾并更新 refactor-plan 状态。
- **涉及模块**：git/.gitignore/pre-commit、`docs/`、`frontend/src/api/queryKeys.ts` + `events/socket.ts` + 各 feature 组件、CI yml。
- **完成标准**：`git status` 干净；README/roadmap 与代码一致；grep 裸 Query Key 归零（或仅工厂导出）；CI 增 lint job 且绿；pytest 314+ / vitest 157+ 不回退。

### Phase 2 — 真实 AI 链路验证（约 2–3 周）

- **目标**：核心卖点从"fake 可跑"变为"real 可用"。
- **任务**：openai 模式三案例实测与 prompt 迭代；真实 ComfyUI workflow 模板（出图→回填→版本全链路）；Director 真实 LLM 意图理解 + fake 降级策略；openai 路径契约测试（HTTP mock）；fake_planner 扩展或标记为 dev-only。
- **涉及模块**：`app/llm/`、`services/script_service.py`、`agents/director/`、`providers/comfyui/`、`workflows/`、tests。
- **完成标准**：真实模式下「小说→分析→分镜→出图→Director 改近景→重生成」全链路人工验收通过并留档；CI 新增 openai 契约测试。

### Phase 3 — 成片补全：音频与字幕（约 4–6 周）

- **目标**：导出的成片是"有声音、有字幕的漫剧"。
- **任务**：TTS Provider（base + 至少一个实现，接口对齐 registry/preflight 模式）；配音生成任务类型（复用 generations 队列）；时间线音频轨拾取/对位；渲染器 ffmpeg 混音 + 字幕烧录；前端音轨 UI 从"数据壳"变真功能。
- **涉及模块**：`providers/`（新增 audio/）、`generations/worker.py`（render 分支）、`services/{generation,render,timeline}_service.py`、前端 `TimelineView`。
- **完成标准**：渲染产物含视频+配音+BGM+烧录字幕（ffmpeg 模式），mock 模式有确定性音频轨占位；pytest/vitest 新增覆盖。

### Phase 4 — 产品化与发行（约 3–4 周，可与 Phase 3 并行启动设计）

- **目标**：可交付安装包。
- **任务**：Tauri sidecar 打包后端 + PyInstaller/嵌入 Python；CSP 与启动安全；安装器与自动更新；用户数据备份/迁移回滚；alembic downgrade；最小 E2E 冒烟。
- **完成标准**：全新 Windows 机器安装→建项目→出片全流程无需开发者环境。

---

## 十七、Recommended Backlog

```markdown
## P0
- [ ] TASK-001 清理暂存区：移除 .plib-debug/、frontend/.r0-smoke/、scripts/*-Startup*.ps1、
      vinput-asr-dummy.*，补 .gitignore（.plib-debug/、.r0-smoke/、*.png 根目录、.design-qa-ui-check/）
- [ ] TASK-002 提交 R0/R1 收尾的 6 个前端文件，更新 docs/frontend-refactor-plan-v0.1.md 状态为 R0/R1 Done
- [ ] TASK-003 重写 README.md「当前阶段」与能力清单至 P9 后真实状态
- [ ] TASK-004 合并双轨 roadmap：codex-phase-roadmap 归档为历史，docs/roadmap/README 声明唯一前瞻并
      反映 P2–P9 已落地
- [ ] TASK-005 新增 pre-commit（ruff + tsc + 禁止调试产物模式），CI 增加 frontend lint job
- [ ] TASK-006 前端 ESLint + Prettier 配置与全量修复（独立提交，不改行为）
- [ ] TASK-007 Query Key 全量收编 queryKeys.ts 工厂（补 providers/workflows/versions/generations
      工厂），socket.ts 与组件零裸数组 key

## P1
- [ ] TASK-008 STUDIO_LLM_MODE=openai 实测：3 个真实小说段落 → ScenePlan/ShotPlan 质量评估与 prompt 迭代
- [ ] TASK-009 openai 路径契约测试：HTTP 层 mock OpenAI API，覆盖 structured 输出解析与失败分支
- [ ] TASK-010 制作真实 ComfyUI workflow 模板替换 default_image_api.json 占位符，真机出图→回填→V2 验证
- [ ] TASK-011 Director 接真实 LLM 意图理解；fake_planner 标记 dev-only 并文档化降级策略
- [ ] TASK-012 TTS Provider 立项：base 接口 + registry/preflight 接入 + 首个实现选型（含成本评估）
- [ ] TASK-013 渲染器音频混流：ffmpeg amix 合成 VOICE/MUSIC 轨 + SUBTITLE 烧录，mock 渲染确定性占位音轨
- [ ] TASK-014 OpenAPI codegen 评估：openapi-typescript 生成 types，制定 types.ts 迁移计划
- [ ] TASK-015 抽取 service 基类/mixin：revision 冲突 + 分页 + 软删除三合一，先迁 character 验证再推广
- [ ] TASK-016 agents 层去 Session：tools.py/context_resolver.py/runner.py 改为经 Service 边界注入，
      api/continuity.py:88 裸 SQL 下沉 service
- [ ] TASK-017 WS 重连补偿：socket 连接恢复后触发一次活跃 query refetch

## P2
- [ ] TASK-018 refactor-plan R2：1440×900 布局预算、响应式三档、移除 episode-panel min-width:920px
- [ ] TASK-019 Playwright E2E 冒烟：主路径一条（建项目→分析→生成→排片→渲染），fake/mock 模式
- [ ] TASK-020 TimelineView 拆分（满足 R3 触发条件时：TimelinePage/Canvas/ClipInspector/useTimelineEditor）
- [ ] TASK-021 continuity_service.py 拆分：规则引擎/语义检查/生命周期三模块
- [ ] TASK-022 readmodel_service 专项测试
- [ ] TASK-023 New Project 四入口收敛为两种真实行为；全局 /assets 改名「跨项目素材」
- [ ] TASK-024 Tauri 发行工程启动：sidecar 打包 PoC（PyInstaller 后端嵌入）

## P3
- [ ] TASK-025 generations worker 并发化（config 放开 concurrency 上限 + per-provider 并发策略）
- [ ] TASK-026 EventBus/operations store 持久化（DB 事件表），服务重启可恢复
- [ ] TASK-027 alembic downgrade 脚本补齐关键迁移
- [ ] TASK-028 styles.css 按 tokens/base/shell/features 拆分
- [ ] TASK-029 批量 Production Run（整季排期）设计文档
```

---

## 十八、暂时不要动的模块（修改收益 < 成本）

| 模块 | 现状 | 为什么不动 |
|---|---|---|
| 内存 EventBus / operations store / WS 连接管理 | 进程内有状态 | 单机桌面假设成立，注释已自认边界；持久化改造收益出现在多进程/云端需求时 |
| 同步 SQLAlchemy | 非 async | 全部 service/repository 按 sync 写成且测试齐全；迁 async 是全量重写级改动，当前零收益 |
| DB-poll 生成 worker（单并发） | config 强制 concurrency=1 | GPU 生成本来串行；"免费崩溃恢复"的设计优势远大于轮询开销 |
| 自研时间线 DOM 拖拽（无第三方库） | TimelineView + timelineMath 纯函数 | 有测试、够用、无依赖；换库是负收益 |
| 自研 LangGraph SQLite Checkpointer | stdlib sqlite3 实现 | 语义正确且有迁移回环测试；换官方包反而引入依赖 |
| revision/分页五处重复 | 无 mixin | 第 6 个实体出现前抽基类是过度设计（TASK-015 已排 P1，时机=新实体立项） |
| 五区布局与深色 design token | 刚恢复基线（2cfcb3d） | 视觉重做零收益，refactor-plan §11 已明确非目标 |
| Tauri → Electron 迁移念头 | Tauri 2 壳能跑 | 架构文档已决策（architecture §27–28），重写壳无收益 |
| 手写 types.ts | 912 行 | 在 codegen 决策（TASK-014）落地前不要手工大改；一旦 codegen 全部作废 |

---

## 十九、总体评价

| 维度 | 评分 | 评价 |
|---|---:|---|
| 产品完整度 | 6/10 | 核心生产闭环完整且好用；音频/字幕/批量三块大缺口，成片还不是"剧" |
| 架构 | 8/10 | 文档先行 + 红线纪律 + Provider 抽象是同类项目少见的；扣分在 3 处越层破口与进程内状态 |
| 代码质量 | 7/10 | 零 TODO 残留、错误/日志规范统一；扣分在巨型文件、五重复制、前端无 lint |
| UI/UX | 7/10 | 五区布局清晰、design token 统一、暗色主题完整；扣分在布局预算失衡与若干命名混淆 |
| 可维护性 | 7/10 | 事实源文档体系 + 提交对应任务编号是巨大优点；扣分在双轨计划与 README 漂移 |
| 可扩展性 | 7/10 | Provider/registry/事件模式为接新引擎留好了口；扣分在 service 层无基类与单进程假设 |
| 测试 | 8/10 | 471 项测试 + 迁移回环 + 阶段 gate + Scenario A/B/C，密度高；扣分在真链路与 E2E 零覆盖 |
| 稳定性 | 7/10 | 版本不可变、租约恢复、乐观并发保障数据安全；扣分在 operation 重启丢失与 WS 断线漏失效 |
| 工程化 | 6/10 | CI 三 job 齐全；缺 pre-commit、前端 lint、E2E、发行流水线 |
| 产品化程度 | 4/10 | 无安装器/签名/更新/备份；CSP null；当前只有开发者能"用上"它 |

### 如果我是这个项目的 Tech Lead，现在最先做三件事

1. **清账与锁基线（半天～1 天）**：把 26 项未提交状态处理干净（杂物出暂存区、个人脚本删除、R0/R1 收尾提交），加 pre-commit，README/roadmap 合一。这是成本最低、对后续所有开发杠杆最高的一步 —— 尤其对一个靠 AI Agent 施工的仓库，过期的事实源就是持续产生错误决策的源头。
2. **真链路冲刺（1–2 周）**：用真实 LLM + 真实 ComfyUI 把「小说→分镜→出图→AI Director 修改→重生成」跑通并修到稳定，同时补 openai 契约测试。产品的全部差异化押在"AI 原生"上，而它目前只被 fake 验证过 —— 这个风险必须最先消除，再谈新功能。
3. **给音频链路立项（设计先行）**：TTS Provider 接口 + 渲染混音方案。渲染器 ffmpeg 基建已经就绪，这是把"无声分镜视频"变成"漫剧"的最短路径，也是 Phase 3 唯一能改变产品性质的工作。

---

## 附：与既有文档的关系

- 本报告与 `docs/frontend-refactor-plan-v0.1.md`（前端专项，R0–R4）**互补不冲突**：本报告采纳其全部结论，R0/R1 已落地状态依提交 `2cfcb3d`/`2a6f143` 判定，R2/R3 任务已编入本报告 Backlog（TASK-007/018/020）。
- `docs/audits/post-mvp-audit.md`（08-15）与 `docs/alpha/audit/*` 的结论本报告已吸收并更新至 P9 后现状。
- 建议本报告作为下一次 roadmap 修订的输入；TASK-004 完成后本报告 §一/§二 的"现状"部分即应由合并后的事实源承接。
