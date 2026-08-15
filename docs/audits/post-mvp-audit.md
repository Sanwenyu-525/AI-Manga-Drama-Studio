# MVP 后全局审计

> 审计日期：2026-08-15  
> 范围：README、事实源文档、前后端、数据库与迁移、API、Service/Repository、Agent、Provider、状态管理、UI、Tauri、配置、测试和交付工程。  
> 限制：本轮只读代码并创建规划文档，没有修改业务代码、API 或数据库。

## 1. 执行摘要

AI Manga Drama Studio 已经具备真实的 MVP 闭环，而不是只有界面原型：用户可以建立 Project State、导入文本、生成 Scene/Shot 计划、编辑分镜、生成图片、保留不可变版本，并通过 AI Director 执行“修改镜头再生成”。后端 31 项测试、前端生产构建和 Tauri `cargo check` 均通过。

但“功能存在”与“生产可用”之间仍有明显距离。当前最危险的缺口集中在运行语义：Generation 崩溃后不能恢复 running 任务，完成回填跨多次事务；Agent 取消后仍可能继续执行，且跨项目 ownership 校验不足；真实 ComfyUI 默认工作流路径与仓库布局不一致；API 错误与日志上下文不统一；前端断线/刷新后不能可靠对账。

因此下一阶段应进入 **Phase 1 — Foundation & Stabilization**，暂不扩展 Timeline、多 Agent、云端或插件体系。

## 2. 审计方法与验证

### 阅读与静态检查

- 阅读项目入口、PRD、架构、后端架构、Agent、前端 UX、API/Event 契约、数据库、MVP 技术规格和设计规范。
- 逐层检查 Router → Service → Repository、SQLAlchemy Model/Alembic、异步 Store/Worker、Provider Adapter、React Query/Zustand/Event Router、Tauri 启动器和环境配置。
- 扫描 `TODO/FIXME/HACK/临时/placeholder/mock/deprecated/未实现`，只保留影响产品或维护成本的条目。
- 检查 CI、Docker、GitHub Actions、前后端测试与发布配置是否真实存在。

### 可执行基线

| 检查 | 结果 |
|---|---|
| `uv run pytest tests -q` | 31 passed，10.70s |
| `npm run build` | TypeScript + Vite 构建通过；JS 约 406 kB / gzip 118 kB |
| `cargo check` | 通过 |
| 前端测试 / E2E | 不存在 |
| CI/CD / GitHub Actions | 不存在 |
| Docker / Compose | 不存在；当前不是桌面发布的前置条件 |

这些结果证明当前 happy path 有可重复基线，但没有覆盖重启、并发、断线、真实 Adapter、迁移升级和桌面安装包。

## 3. 能力盘点

| 能力 | 真正完成的部分 | 仍为 MVP 级的部分 | 判断 |
|---|---|---|---|
| Project State | 真实 SQLite 模型、迁移、Service、REST | 生命周期不完整、部分 revision/约束缺失 | 可开发，不宜宣称生产级 |
| 小说分析 | Fake 与 OpenAI-compatible Gateway、结构化输出、Preview/Confirm | 默认 Fake；Operation 内存；确认可能重跑计划 | 开发闭环完成 |
| Storyboard | Scene/Shot 编辑、聚合读取、角色关联 | reorder 数据约束弱、无批量/筛选/多选 | 核心编辑可用 |
| Generation | DB 队列、状态、重试/取消 API、Mock 生成 | recovery/lease/原子完成不足；取消不终止 Provider | happy path 完成 |
| ComfyUI | Client、Mapper、WS progress、测试连接 API | 默认路径疑似错误，workflow/capability/cancel 未验证 | 代码存在，不具备生产可用性 |
| Asset/Version | 项目相对存储、缩略图、不可变版本、Set Active | 缺资产库、元数据规范、并发版本约束、比较体验 | 基础完成 |
| AI Director | Graph 与三工具、Selection-aware happy path | Run 内存、无 checkpoint/审批/ChangeSet；取消和 ownership 风险 | Demo/MVP 可用 |
| Character | CRUD、关联、revision、软删除 | 缺搜索/批量/恢复与生成一致性 | 基础完成 |
| Event | Envelope、sequence、WS 推送、Query invalidate | 进程内、无回放/项目订阅/认证/gap 恢复 | 实时提示可用 |
| Desktop | Tauri 壳、开发态后端启动 | 依赖源码与系统 uv，无安装/升级/迁移/签名 | 开发壳 |

## 4. 分级发现

### P0 — 立即阻断后续开发的风险

#### A-00 AI 计划正在静默丢失字段并可能部分写入

- **证据**：`backend/app/domain/analysis.py::ScenePlan` 使用 `title/location/time`，`backend/app/domain/scene.py::SceneCreate` 使用 `name/time_of_day`；`backend/app/services/script_service.py` 直接 `SceneCreate(**plan.model_dump())`，Pydantic 默认忽略多余字段，导致名称、地点和时间丢失。
- Scene/Shot 批量创建逐项 commit；中途失败留下部分数据，重复 analyze 会继续追加。现有测试只验证数量和 scene_number。
- **影响**：小说分析看似成功，但唯一 Project State 已经与 LLM 输出和用户预期不一致。
- **处置**：作为第一个开发任务，显式映射字段、建立批量事务和重复提交策略，并增加失败注入测试。

#### A-01 Generation 不具备可靠的崩溃恢复与原子完成

- **证据**：`backend/app/generations/worker.py` 只轮询 `queued/retrying`；任务进入 `running` 后进程崩溃会永久滞留。
- Asset、MediaVersion、active version 与 Generation completed 分别 commit；中途失败会形成半完成 Project State。
- concurrency 配置存在但循环串行；多 Worker 又没有 lease/claim token。
- **影响**：重复生成、历史不一致、任务永远进行中，直接破坏唯一事实源。
- **处置**：Phase 1 建立状态机、lease/recovery、幂等 finalizer 和故障注入测试。

#### A-02 Agent 取消与项目边界不可信

- **证据**：`backend/app/agents/director/runner.py::cancel_run` 只修改内存状态；Graph 可能继续执行 update/generate。
- `backend/app/agents/context_service.py` 对显式 Shot ID 的 project ownership 校验不足；`shot_number:N` 在整个项目内取首个匹配，跨 Scene 重号时静默选错。
- `backend/app/llm/fake.py::_FAKE_SELECTION` 是进程级可变全局，并发 Run 可互相污染。
- **影响**：用户取消后仍修改数据，或 Run 操作错误项目/镜头。
- **处置**：Phase 1 先补回归测试，再实现 ownership guard、协作式取消与 run-local context。

#### A-03 真实 ComfyUI 主路径未被真实验证

- **证据**：`backend/app/providers/comfyui/workflow_mapper.py` 使用 `parents[3] / workflows`，从该文件推导到 `backend/workflows`，实际模板在仓库根 `workflows/`。
- `client.py` 固定读取输出 node `14`；provider_ref 未写入 Generation，取消无法调用真实 Provider；`websockets` 依赖依靠传递依赖。
- **影响**：切换 `STUDIO_IMAGE_PROVIDER=comfyui` 后可能立即找不到模板，或在不同 workflow 上无法取结果/取消。
- **处置**：Phase 1 建立 preflight、可配置且受校验的 workflow contract、Adapter smoke test 与 provenance。

#### A-04 数据库与写操作的不变量不足

- **证据**：Scene/Shot/Version 使用 `MAX + 1`，缺少相应唯一约束；`ShotService.reorder_shots` 可对部分集合重排，造成重复 order/shot_number。
- `Scene` 缺 architecture redline 指定的 revision；部分弱引用没有 FK/校验。
- `ShotService.update_shot` 对 no-op 仍可能增加 revision，nullable 字段无法用标准 PATCH 清空，event source 固定为 `user`。
- **影响**：并发或批量操作下产生不可修复的序号、版本与审计错误。
- **处置**：Phase 1 先定义不变量和迁移策略，再以 Service+DB 双层保护。

#### A-05 本地 API/WS 没有安全边界

- **证据**：REST 和 `/api/v1/events` 无本地 session token；WS 不校验 Origin、不按 project 订阅并广播全部事件；Tauri CSP 为 `null`。
- **影响**：同机其他进程或恶意网页可探测本地端口、读取项目事件或调用写接口。
- **处置**：Phase 1 实现桌面启动时生成的短期 session secret、REST/WS 同一认证、Origin/CSP 收紧；不提前引入 RBAC。

### P1 — 核心产品与稳定性缺口

#### A-06 API 错误契约和日志上下文不完整

- `backend/app/api/generations.py` 先注册 `/{generation_id}`，后注册 `/recent`；实际 `/generations/recent` 被解释为 ID 并返回 404，Bottom Dock 的 recent 查询不可用。
- `backend/app/main.py` 只处理 `StudioError`；Pydantic 422 与未捕获 500 不保证统一 `{error:{...}}`。
- request_id 没有贯穿 Service/Event/日志；异常路径可能没有 access log。
- `frontend/src/api/client.ts` 丢失 request_id，缺 timeout、AbortSignal 与统一错误呈现。

#### A-07 Event Client 无断线恢复

- `frontend/src/events/socket.ts` 仅记录 sequence；发现 gap 不执行 bootstrap/REST 对账。
- socket 为模块单例，页面卸载后仍重连；无项目订阅、认证或 schema validation。
- Queue/Agent store 没有从持久状态水合，刷新或丢事件后会卡住。

#### A-08 Operation 与 Agent Run 仅内存

- `backend/app/operations/store.py`、Director runner 使用进程内字典，无 TTL/清理；重启丢状态，长期运行会增长。
- `resume` 是明确占位；无法形成审批、恢复或历史。

#### A-09 Preview 与 Confirm 不是同一份已审阅事实

- `frontend/src/features/script/EpisodePanel.tsx` 先调用 preview，确认时又发起 analyze；后端可能重新运行 LLM。
- 用户审阅的 ScenePlan 与最终写入内容可能漂移。
- UI 还承诺“自动创建角色”，现有分析流程没有这一行为；“替换原文”按钮无 handler（已修复：2026-08-15 接入本地 .txt/.md 文件导入，见 EpisodePanel）。

#### A-10 Router 分层红线存在局部违例

- `backend/app/api/generations.py` 的 recent 查询直接执行 SQL。
- `backend/app/api/assets.py` 直接 `db.get` 并处理资源业务判断。
- 应移动到 Service/Repository，不需要为每个单查询制造新框架。

#### A-11 Generation provenance、retry、cancel 语义不完整

- `GenerationService.create_generation` 在未指定 provider 时记录 `default`，Worker 实际使用 Registry 当前 Implementation，历史不可追溯。
- `retry_generation` 创建并发布任务后才写 `retry_of`，Worker 可能先认领。
- settings 中最大重试次数没有真正成为默认状态机规则。
- API 接受 video 类型，Worker 固定构造 ImageRequest，应拒绝未支持能力。

#### A-12 Asset/Version 数据质量不足

- `AssetService` 以 `str(dict)` 写 `meta_json`，不是标准 JSON。
- 先复制文件再提交 DB，失败会留下孤儿；对大文件使用整文件读写。
- `VersionService._project_id` 固定返回 `None`，版本事件缺 project_id；`MAX + 1` 有竞争。

#### A-13 前端核心错误与冲突反馈不完整

- 多个 Query/Mutation 失败无可见反馈，只有 ShotInspector 部分处理 409。
- `ProjectExplorer` 的 Character 编辑器在请求完成前清空表单，`conflict` 状态没有从错误设置。
- `useOperationPolling` 每 500ms 无限重试网络错误，无退避、超时、暂停或取消。
- Storyboard `active_generation` 后端总为 `None`，实时生成覆盖层不可靠。

#### A-14 前端契约与状态重复

- `frontend/src/api/types.ts` 手写复制后端 DTO；事件 payload 多为断言而非运行时校验。
- `selectionStore` 与 `workspaceStore.activeShotId` 是两个 UI 事实源。
- Query key 有中央工厂又有大量裸数组与宽泛 invalidate，局部更新成本随功能增长上升。

#### A-15 桌面发布仍是开发态

- `apps/desktop/src-tauri/src/backend.rs` 假设源码目录和系统 `uv`，没有 bundled runtime/sidecar。
- 无自动迁移、数据备份、升级回滚、签名或 installer smoke。
- `studio.ps1` 与 `studio.bat` 形成重复启动路径，后者还存在终端编码可读性问题。

### P2 — UX、性能与维护性

#### A-16 UI 中存在惰性或误导控件

- Storyboard grid/list toggle 无行为；顶部“素材/工作流/设置”是不可操作文本。
- 遗留 `frontend/src/features/ai/DirectorPanel.tsx` 仍显示“Stage D 接入后”，实际功能在 `features/director/AIDirectorPanel.tsx`。
- NewProject 的多个起始模式最终执行同一创建逻辑，默认项目名是示例内容，Provider 切换文案没有设置入口。

#### A-17 缺统一体验基础件

- 没有全局 Error Boundary、Toast、Skeleton、Modal/Confirm、离线提示和任务恢复提示。
- icon-only 按钮、焦点顺序、reduced-motion 与键盘导航不完整。
- 当前 dark-first 符合设计系统；Light Mode 不是现阶段阻塞项。

#### A-18 查询与事件存在无效负载

- ShotInspector、VersionReview、GenerationQueue 同时使用频繁 polling 与 WS。
- recent generations 未按 project 过滤/分页；Event Gateway 向所有连接广播所有项目。
- 缺 worker 与列表查询的复合索引；是否增加索引应先通过真实数据基准确认。

#### A-19 Module 边界深浅不均

- Project ownership 查询链在多个 Service 重复；序列化/DTO 映射也分散。
- Generation completion 涉及多个浅 Service 的公开步骤，调用者需要知道执行顺序，Locality 差。
- 另一方面，当前没有证据支持拆微服务或创建通用 Repository 框架；应只加深高杠杆 Seam。

#### A-20 文档事实漂移

- README 仍停留 Stage A；`design-qa.md` 称 Stage D 未接入；AGENTS 技术栈段落仍提 `asyncio.Queue`。
- 文档不能作为事实源时，会直接误导后续 Agent 和人类协作者。

## 5. 测试缺口

当前 31 项后端测试对 MVP happy path 有价值，但以下失败模式没有被覆盖：

- Worker 在 claim 后、asset 后、version 后、complete 前崩溃。
- 两个 Worker/两个更新请求争用编号、revision、retry。
- Agent 取消发生在每个节点/工具之前与之后；跨项目 Shot ID。
- Event sequence gap、服务重启、WS 断线重连与 REST reconcile。
- 真实 OpenAI-compatible structured output、真实 ComfyUI workflow/preflight/cancel。
- Alembic 从空库到 head、旧版本升级、失败回滚与备份恢复。
- 前端表单冲突、loading/error/empty、断线恢复与关键用户 E2E。
- Tauri 安装包启动、内置后端、迁移、升级与卸载后数据保留。

## 6. 安全审计

### 现在必须处理

- 本地 REST/WS session boundary、Origin 校验、CSP。
- 文件路径继续保持 project root containment，并为资产注册增加 ownership/类型校验。
- 日志与错误禁止返回 API key、绝对路径、原始异常栈和不必要的 Prompt。
- 生产 profile 禁止 FakeLLM/MockImageProvider 静默启用。

### 暂不处理

- 用户账号、OAuth、RBAC、多租户、团队权限：当前是本地单用户桌面产品，提前实现成本大于价值。
- 公网 WAF、复杂 Rate Limit：在云端/API 暴露前不需要；Phase 5 只做本地防滥用与资源配额。

## 7. 性能风险

- SQLite 每次 generation progress commit 会造成写放大，应节流并通过基准确定频率。
- 列表缺分页，recent generation 跨项目读取；未来 Asset/Version 量增长后首屏变慢。
- 整文件 `read_bytes/write_bytes` 不适合视频资产。
- 单 bundle 目前可接受，不应为 406 kB 提前重构；在功能增加后通过 route-level lazy loading 和 profiler 决定。
- 缺少目标数据量（约 500 Scene/10,000 Shot）的查询与启动基准。

## 8. 真正的技术债清单

纳入 Roadmap：

- Agent `resume` 占位与内存 Run Store。
- 默认 Mock/Fake 的生产配置风险。
- ComfyUI workflow placeholder/capability/cancel 不完整。
- 遗留锁定版 DirectorPanel。
- 重复的 ownership 查询、手写 DTO/Event 类型和启动脚本。
- 文档阶段状态漂移。

不单独立项：

- 测试中的 Fake/Mock 文案是必要测试设施，不是债务。
- CSS placeholder class、合法的 UI placeholder 属性不是债务。
- 为单次使用的小函数做“纯洁性重构”没有产品价值。

## 9. 应延后的需求

| 延后项 | 原因 | 最早进入 |
|---|---|---|
| 多 Agent 协作 | 单 Agent 的取消、审批、持久化尚未可信 | Phase 6 或独立验证后 |
| 云端/多租户/RBAC | 产品仍是本地桌面，未证明协作需求 | Phase 6 触发式 |
| 微服务/Redis/Celery/Kafka | 当前规模下增加部署与故障面 | Phase 6 性能触发后 |
| 通用 Plugin SDK | 还没有两个稳定第三方扩展案例 | Phase 6 |
| 完整 NLE 时间线 | 图片生产链和版本 UX 尚未完善 | Phase 4 后段 |
| 复杂视频特效/音频混合 | 非 MVP 核心差异化，成本高 | Timeline 验证后 |
| Light Mode | dark-first 已满足桌面生产工具定位 | P3/Nice-to-have |
| 搜索引擎 | SQLite 查询尚未到瓶颈 | Phase 6 数据触发后 |

## 10. 最大五个问题

1. **异步任务不可靠**：Generation/Agent 的恢复、取消、幂等与原子完成不足。
2. **数据映射、边界与不变量不足**：AI 计划会静默丢字段；跨项目 ownership、编号唯一性、reorder/revision/provenance 存在正确性风险。
3. **真实 Adapter 尚未形成可验证产品路径**：ComfyUI 与真实 LLM 代码存在，但默认配置、workflow 和测试仍偏开发态。
4. **错误、事件和客户端恢复体系不完整**：服务端无法统一诊断，客户端断线/刷新后不能可靠重建状态。
5. **没有生产交付系统**：前端测试、E2E、CI/CD、桌面打包、迁移/备份/回滚和安全边界均未闭环。

## 11. 审计建议

- 当前进入 Phase 1，不并行开发高级功能。
- 第一个任务执行 `P1-E1-T01 修复 AI 计划映射与批量写入事务`；它范围可控，却直接影响小说导入后写入唯一事实源的正确性。
- Sprint 01 应围绕“保护 Project State 与核心异步链路”，而不是围绕页面或技术模块平均分配工作。
- Phase 5 的测试、安全、发布不是最后才开始：其基础工作从 Phase 1 纳入门禁，Phase 5 负责完成真实发布验收。
