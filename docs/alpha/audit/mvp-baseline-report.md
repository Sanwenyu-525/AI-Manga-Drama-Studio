# MVP Baseline Report — AI 漫剧 Studio Alpha Phase 0

> 文档状态：Draft（Phase 0 Gate 评审稿）
> 审计日期：2026-08（本会话实测）
> 范围：backend/ frontend/ apps/desktop/ workflows/ docs/ 全部真实代码（只读分析，未修改业务代码）
> 依据：《AI 漫剧 Studio Alpha Codex 分阶段开发任务清单 v0.1》Phase 0（P0-T001 ~ P0-T006）

---

## 1. 可执行基线（本会话实测验证）

| 检查 | 结果 |
|---|---|
| 后端测试 `uv run pytest tests -q` | **105 passed**（38.42s，18 个 test_*.py + conftest） |
| 前端测试 `npm run test`（vitest） | **13 passed**（4 个测试文件） |
| 前端生产构建 `npm run build`（tsc -b && vite build） | 通过；JS 476.42 kB / gzip 136.47 kB |
| Tauri `cargo check` | 通过（dev profile，32.12s；exit 1 仅为 PowerShell stderr 误报） |
| CI | 存在 `.github/workflows/ci.yml`（backend pytest+ruff、frontend build+test、desktop cargo check、secret 扫描） |
| Git 状态 | 分支 `main`；**存在未提交改动**（episode/scene DELETE+rename 相关 7 个后端文件、11 个前端文件、新测试 `test_episode_scene_crud.py`、docs/incoming/、scripts/*.ps1） |

结论：项目已有可重复的绿色基线；未提交改动为进行中的 Episode/Scene 删除级联与前端 URL-driven 视图收尾，进入 Phase 1 前应先收尾提交或转入分支。

---

## 2. 现状总结（对照 Alpha 目标）

### 2.1 已达成且质量高（MVP Stage A~D + P1 全完成）

- **分层红线合规**：Router → Service → Repository，API 层无 `db.query`；统一错误 Envelope（`{error:{code,message,details,request_id}}`）覆盖 400/404/409/422/500/502/503。
- **事件体系**：内存 EventBus（commit-then-publish）+ WS 网关 `/api/v1/events`（Envelope + sequence 去重），MVP 必备事件全部覆盖。
- **Generation 运行时**：generations 表即持久队列（DB-poll worker）、原子认领（条件 UPDATE）、lease 心跳与崩溃恢复、状态机（非法迁移 409）、Retry 创建新记录（retry_of）、指数退避、协作式取消。
- **ComfyUI 接入**：占位符模板（$PROMPT/$SEED/$WIDTH/$HEIGHT）+ WorkflowMapper preflight（恰好一个 SaveImage、必备占位符）+ WS 进度 + history 兜底取输出 + /interrupt 取消 + URL 可配；**node_id 不渗入业务层**（仅 mapper 动态探测）。
- **Agent Director**：LangGraph 五节点 Graph + 三工具（get_shot/update_shot/generate_image）+ 严格 Pydantic 参数 + ToolExecutor 二次 ownership 防御 + 协作式取消 + 事件流；FakeLLM 规则解析覆盖 Scenario A/B/C。
- **Asset/Version**：项目相对存储、缩略图、路径安全校验、版本不可变（MediaVersion）、Active 显式切换 + 部分唯一索引。
- **前端**：TanStack Query（Server State）+ Zustand（UI/瞬时状态）+ 全局唯一 EventRouter（WS 不直达组件）+ Selection Store 单一事实源 + revision 409 处理 + 生成后不自动切换 Active（原则七正确）。
- **测试与工程**：后端 105 项（含状态机/lease/迁移 round-trip/worker 真实循环/错误契约）、前端 vitest 13 项、CI、ruff。

### 2.2 关键缺口（按 Phase 0 六项审计汇总）

| 领域 | 核心缺口 | 证据要点 |
|---|---|---|
| 领域模型 | CharacterVersion/MASTER、Location/LocationVersion、Costume、Prop、Prompt/PromptVersion、GenerationInput/Output、Job/JobTask、WorkflowTemplate/Version、ResourceDependency、ContinuityState、Timeline 全部缺失；Scene/Episode/Project 无 revision | domain-gap-analysis.md |
| 版本模型冲突 | MVP 用独立 `media_versions` 包装 Asset（Shot.active_*_version_id）；Alpha 要求 Asset 自版本化（version_group_id+version_number，Shot.active_*_asset_id）；Prompt 内联在 Shot 而非 PromptVersion 引用 | domain-gap-analysis.md |
| API | 缺 Job 全组、generate-image/video 业务化端点、Character 版本/Master、Location、Prompt、Asset import/provenance、Continuity、Timeline、Workflow 管理、SourceDocument、Project tree/settings；Operation 内存轮询 vs Job 持久队列需 MIGRATE | api-audit.md |
| 前端 | 无 Read Model 缓存与精确失效（事件只做宽泛 invalidate）、无 Editor Tabs、无工作区持久化、无虚拟列表、无 Error Boundary、ShotInspector 800ms/2s 高频轮询与 WS 双通道、assetStore/jobStore 缺位、selectionStore 与 workspaceStore.activeShotId 双源 | frontend-state-audit.md |
| Provider/Workflow | 仅 ImageProvider 一类（缺 Video/Voice/Llm/Workflow Adapter 分类）、无 WorkflowTemplate/Version、无 ProviderHealthService 周期探活、registry 未按 (type,id) 扩展、$REFERENCE_IMAGE 未接真实 upload | comfyui-integration-audit.md |
| Agent | AgentRun 内存存储（重启丢失）、无 AgentGateway 抽象、无 Proposal/Human Review（approval/change_set 字段空壳、resume 占位）、无 Token/Cost 记录与预算 | comfyui-integration-audit.md |
| 遗留 P0 | P1-E2-T03（Generation 完成链原子化：asset/version/generation 分多次 commit）、P1-E4-T02（Event Gateway 鉴权/项目订阅/回放） | current-sprint.md |
| 安全 | 本地 REST/WS 无 session token、WS 无 Origin 校验、Tauri CSP null | post-mvp-audit.md A-05 |
| 工程 | Tauri 壳依赖源码目录 + 系统 uv（无 sidecar/安装包/迁移/签名）；文档事实源漂移（README 仍 Stage A、AGENTS 仍写 asyncio.Queue、design-qa 称 Stage D 未接入） | repository-map.md |

---

## 3. 五类处置清单

### KEEP（保留复用，不重写）

1. 分层架构与红线合规（Router→Service→Repository；无 db.query；commit-then-publish）
2. 统一错误 Envelope + request_id 基础设施（仅需细分错误码）
3. Event Bus + WS 网关（Envelope/sequence/去重）
4. Generation DB-poll worker + 原子认领 + lease 崩溃恢复 + 状态机 + Retry 新记录 + 退避
5. ComfyUI WorkflowMapper 占位符/preflight + node_id 隔离 + WS/history 双通道取输出
6. ImageProvider 抽象 + MockImageProvider（测试基线）
7. LLMGateway 抽象 + FakeLLM（STUDIO_LLM_MODE=fake|openai）
8. Agent Director Graph + 三工具 + ownership 防御 + 协作式取消
9. 前端 TanStack Query + Zustand 分工、全局 EventRouter、Selection Store、409 处理
10. 版本不可变 + Active 显式切换语义（MediaVersion 基础上演进）
11. 202 + Operation 短任务机制（analyze/shot-plan 可保留，升级为持久化）
12. 105 项后端测试 + vitest + CI 作为回归基线

### REFACTOR（在现有实现上改造）

1. Scene/Episode/Project 补齐 revision 乐观锁（红线 10）
2. Asset 模型补字段：source_type/storage_provider/checksum/status/parent_asset_id/version_group_id
3. 前端 Read Model 缓存（data/loadedAt/stale）+ 分实体失效键 + EventDispatcher 分模块 Reducer
4. ShotInspector 等高频轮询改为 WS 驱动 + 断线降级轮询
5. 前端工作区持久化（workspace:{projectId}，localStorage）+ Editor Tabs/WorkspaceRegistry
6. selectionStore 与 workspaceStore.activeShotId 双状态源收敛
7. 前端手写 DTO 改由 OpenAPI 生成/校验（消除契约漂移）
8. Provider registry 按 (type, providerId) 注册并暴露能力清单
9. 错误码细分（SHOT_REVISION_CONFLICT 等 MODULE_ERROR 命名）
10. ContextService 泛化为目标 ContextResolver 命名（功能已具备）

### MIGRATE（需迁移/落库，建议逐项开 ADR）

1. `generations.retry_of` 文本 → `parent_generation_id` FK + 索引
2. 软删除字段 `deleted_at` → `archived_at`（8 表统一，Alpha 契约）
3. **版本模型合并**：media_versions 与 Asset 自版本化合并（version_group_id+version_number；Shot.active_*_asset_id）→ 需 ADR 决策兼容层
4. Shot 内联 Prompt → Prompt/PromptVersion 表 + active_prompt_version_id（需回填策略）
5. 编号体系对齐 order_index（当前 reorder 已保证 ID 不变，字段类型/间隔需对齐）
6. Operation 内存轮询 → Job 持久队列（202 语义保留）
7. 文档事实源同步（README/AGENTS.md/design-qa/api-event-contract）
8. Git 工作流：收尾 main 未提交改动，后续按 feature/ 分支开发（roadmap §7）

### REMOVE（清理/废弃）

1. 遗留 `features/ai/DirectorPanel.tsx`（Stage D 占位旧面板，功能已迁移到 features/director）
2. 无行为惰性控件（Storyboard grid/list toggle、顶部“素材/工作流/设置”文本按钮等）
3. AGENTS.md 中 `asyncio.Queue` 等过期技术描述（与代码不符）
4. 手写 DTO 与后端重复定义（替换为生成/校验后移除）
5. 重复启动路径冗余（studio.bat/studio.ps1 二选一或文档化分工）

### BUILD（Alpha 新增，独立 Epic）

**P1 校准后第一批（对齐 Phase 1~3 目标）：**
1. CharacterVersion + MASTER 机制 + Character 版本 API
2. Location / LocationVersion + Costume / Prop
3. Prompt / PromptVersion + 生成/历史/激活 API
4. GenerationInput / GenerationOutput 关系表 + Provenance 查询
5. Job / JobTask / TaskDependency + Job API + Scene 批量生成（POST /scenes/{id}/generate）
6. WorkflowTemplate / WorkflowVersion + Workflow 管理 API
7. ResourceDependency + STALE 传播（含 Master 变更联动）

**第二批（Phase 7~9 目标）：**
8. AgentRun 持久化 + AgentGateway + Proposal 机制 + Human Review/Interrupt/Resume + Token/Cost
9. Continuity Engine（Scene Base/Delta/Start/End State、规则引擎、Warning、Recompute、STALE 联动）
10. Timeline（Track/Clip/Render + FINAL_VIDEO Asset）

**基础设施（贯穿）：**
11. 本地安全边界：session token、WS Origin 校验、Tauri CSP
12. 前端 Asset Browser/Provenance、虚拟列表、Error Boundary、Command Palette
13. Tauri sidecar/打包与自动迁移
14. 遗留 P0 收尾：P1-E2-T03 完成链原子化、P1-E4-T02 Event Gateway

---

## 4. 对 Phase 1~10 Roadmap 的校准建议

1. **Phase 1（Project Domain & Persistence）大部分已 DONE**：Project Aggregate/API/软删已实现；需补 ProjectSetting 拆分、archived_at 迁移、revision。建议 Phase 1 重定义为“Project 契约对齐 + 版本模型迁移（ADR）”。
2. **Phase 3（Asset/Version/Generation）是核心迁移主战场**：media_versions 合并、Prompt 表、GenerationInput/Output、parent_generation_id —— 建议最先做，且先开 ADR 定版本模型。
3. **Phase 5（Job Queue）前置依赖小但影响大**：Job 表建立后，Operation 与 Scene 批量生成统一到 Job；Generation 保持为执行记录。
4. **Phase 6（前端）与后端 Job/Read Model 强耦合**：前端改造（Read Model 缓存、Editor Tabs、持久化）建议与后端契约同步推进（roadmap §92 纵向闭环）。
5. **Phase 7/8/9（Agent/Continuity/Timeline）为纯增量**，可独立 Epic，但依赖 Phase 1-3 的领域模型落地。
6. **遗留 P0 与安全边界建议插队**到 Phase 1（不作为新功能，属既有债务）。

---

## 5. Phase 0 Gate 结论

**判定：PASS（有条件）**

- 已完成六项审计并输出至 `docs/alpha/audit/`：
  - repository-map.md（P0-T001）
  - feature-inventory.md（P0-T002）
  - domain-gap-analysis.md（P0-T003）
  - api-audit.md（P0-T004）
  - frontend-state-audit.md（P0-T005）
  - comfyui-integration-audit.md（P0-T006）
- 前置条件（进入 Phase 1 前）：
  1. 收尾/提交 main 上的未提交改动（episode/scene CRUD 收尾），并切 feature 分支工作流；
  2. 对“版本模型合并（media_versions → Asset 自版本化）”与“Prompt 表迁移”先行产出 ADR；
  3. 遗留 P0（P1-E2-T03、P1-E4-T02）纳入 Phase 1 首批。

**下一步（用户确认后）**：按 roadmap §96 流程，将 Phase 1~3 任务按实际现状标记 TODO/PARTIAL/DONE，生成 `docs/alpha/roadmap/task-index.md` 与逐 Task 文件，然后从第一个 READY Task 开始开发。
