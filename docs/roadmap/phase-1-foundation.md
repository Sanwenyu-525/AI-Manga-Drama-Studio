# Phase 1 — Foundation & Stabilization

## Goal

把“happy path 能运行”提升为“Project State 不会被静默写错，核心长任务可恢复，错误可诊断，后续开发有可靠门禁”。本阶段禁止顺带开发 Timeline、多 Agent、云端或新 Provider。

## Exit Criteria

- P0 数据映射、跨项目边界、并发 revision、reorder 与路由冲突均有回归测试。
- Generation 有合法状态机、原子 claim、崩溃恢复与幂等完成策略。
- Agent cancel 后不再执行写工具，Selection/Reference 不能越过 project。
- ComfyUI 默认 workflow 可加载，持久 provider 与真实执行一致。
- 422/404/409/500 使用统一错误 Envelope；关键链路可按 ID 关联日志。
- 最小 CI 覆盖后端、迁移、前端构建/测试与 Tauri 检查。

---

## Epic 1.1 — 核心数据正确性

### P1-E1-T01 — 修复 AI 计划映射与批量写入事务

**背景**：小说分析结果进入数据库后即成为唯一 Project State，不能依赖 Pydantic 静默忽略字段。

**当前问题**：`backend/app/domain/analysis.py::ScenePlan` 使用 `title/location/time`，`backend/app/domain/scene.py::SceneCreate` 使用 `name/time_of_day`；`backend/app/services/script_service.py` 直接 `SceneCreate(**plan.model_dump())`，会丢标题、地点和时间。Scene/Shot 循环调用会自行 commit 的 Service，中途失败留下部分数据；重复执行会继续追加。现有 `test_script_planning.py` 只验证数量和编号。

**目标**：显式、可测试地把已确认的 Plan 映射为 Domain Create；一次确认全成或全败，并定义重复提交策略。

**修改范围**：backend、database（仅事务使用，是否迁移按设计决定）、docs、tests。

**实现建议**：建立单一显式 Mapper；由 ScriptService 持有 transaction/Unit of Work，底层批量写方法不自行 commit；为同一 analysis snapshot 使用幂等键或明确 replace/append policy。不要创建通用映射框架。

**Acceptance Criteria**：

- [ ] Scene title/name、location、time/time_of_day 映射测试通过且不再静默丢字段。
- [ ] ShotPlan 所有受支持字段有同样的显式映射测试。
- [ ] 任意第 N 条写入失败时，前 N-1 条不留在数据库。
- [ ] 重复提交同一确认请求不会静默追加重复 Scene/Shot。
- [ ] API/Event 契约与相关事实源文档同步。
- [ ] 现有 31 项后端测试无回归。

**Design Decision（P1-E1-T01，2026-08）**：

- 映射：新建 `app/services/plan_mapper.py` 单一显式 Mapper（ScenePlan↔SceneCreate、ShotPlan↔ShotCreate + ORM 行↔Plan 回放），禁止 `SceneCreate(**plan.model_dump())`。
- 事务：ScriptService 持有 Unit of Work；SceneService/ShotService 的批量写方法（create_scenes/create_shots/soft_delete_*）不自行 commit，事件在 commit 后由 ScriptService 发布。任一步失败整体 rollback。
- 幂等/替换：`episodes.analysis_key`（源文本 hash）与 `scenes.storyboard_key`（场景上下文 hash）作为幂等键；同一 key 重复确认 = no-op（返回已落库行，不重复调用 LLM）；key 变化 = replace（软删除旧 AI 场景/镜头后重建）。手动行（analysis_key IS NULL）始终保留；遗留无 key 数据按手动行处理，历史重复检测与约束化留给 P1-E1-T02。迁移：`e1f2a3b4c5d6`（4 列 nullable Text）。
- API 变化：Scene DTO 新增 `location_id`（create/update/read）；analyze 与 generate-shots 新增幂等/替换语义（见 api-event-contract §14/§18）。

**Priority**：P0  
**Complexity**：M  
**Dependencies**：无  
**Risk**：事务边界调整可能暴露 Service 内隐式 commit；需先以失败注入测试锁定行为。

### P1-E1-T02 — 建立数据库不变量、原子 revision 与安全重排

**背景**：Service 校验不足以抵抗并发和旁路写入，关键业务不变量应由 Service 与数据库共同保护。

**当前问题**：Scene/Shot/Version 使用 `MAX + 1`；缺 `(episode_id, scene_number)`、`(scene_id, shot_number/order)`、`(shot_id, character_id)`、版本号/单 active 等约束。`ShotService.reorder_shots` 接受部分或重复 ID，可能制造重复编号。Shot/Character revision 是“先读后写”，不是真正条件更新；Scene 无 revision。

**目标**：并发更新只有一个成功，编号/关联/active version 永不重复，reorder 要么完整成功要么失败。

**修改范围**：backend、database、docs、tests。

**实现建议**：先写不变量表和现存数据预检；新增可升级/可回滚 Alembic 迁移；revision 用 `UPDATE ... WHERE revision = expected`；reorder 校验完整、唯一集合并在事务内使用两阶段临时编号避免唯一约束冲突。

**Acceptance Criteria**：

- [ ] 两个并发相同 revision 更新恰有一个成功，另一个返回 409。
- [ ] 部分、重复、跨 Scene reorder 均被拒绝且数据不变。
- [ ] 关键唯一约束、必要 CHECK/FK 与 worker 查询索引有迁移和说明。
- [ ] 当前三版数据库可升级到 head；空库迁移与 downgrade/rollback smoke 通过。
- [ ] Scene revision 是否纳入本阶段有明确契约决定并落实。
- [ ] 软删除父实体后，子实体的可读写/恢复规则有测试。

**Design Decision（P1-E1-T02，2026-08）**：

- 不变量（Alembic `b1e2f3a4c5d6`，部分唯一索引排除软删除行）：scenes(episode_id, scene_number)、shots(scene_id, shot_number)、(scene_id, shot_order)、shot_characters(shot_id, character_id)、media_versions(shot_id, media_type, version_number) + (shot_id) WHERE is_active=1；generations(status, created_at) worker 索引。模型 `__table_args__` 同步声明（create_all 与迁移一致）。
- 原子 revision：Shot/Character 更新改为 `UPDATE ... WHERE id=? AND revision=?` 条件更新（rowcount=0 → 409），杜绝旧快照丢失更新；脏数据写入前先 flush 删除旧 character 链接（唯一对索引）。
- 安全重排：reorder 校验完整+无重复集合（部分/重复/跨场景 → 422，数据不变）；两阶段编号（shot_number 与 shot_order 一起整体移开再赋终值）单事务内完成。
- 父删子隐：软删除场景后其镜头读/写/删一律 404（行保留，恢复场景即可见）。
- Scene revision 决策：本阶段不纳入（Scene 编辑低频、Shot 才是原子生产单元；Phase 2 随 ChangeSet/Undo 引入），契约文档已注明。
- 历史重复：迁移先检测后失败（不静默丢弃）；dev DB 中 episode dbc57a32 的重复 scene_number 已无损重编号为 7。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E1-T01 的事务边界决策  
**Risk**：SQLite 添加约束需要重建表；必须先检测并处理历史重复数据，禁止静默丢弃。

---

## Epic 1.2 — Generation Runtime 稳定化

### P1-E2-T01 — 修复真实 ComfyUI workflow 与 Provider 选择

**背景**：MVP 声称已经支持真实 ComfyUI，但代码存在不经真实环境即可确认的默认路径错误。

**当前问题**：`workflow_mapper.py` 的 `parents[3]/workflows` 指向 `backend/workflows`，真实模板在仓库根目录。Generation 可记录任意 provider 或 `default`，Worker 却忽略该字段只用全局 Registry。`workflow_id` 不决定模板；video 请求仍走 ImageProvider；默认模板硬编码 checkpoint，输出 node 固定为 `14`。

**目标**：每个 Generation 的实际 Adapter、capability、workflow 与历史 provenance 一致；默认 ComfyUI 在正确配置后能通过 preflight。

**修改范围**：backend、workflows、config、docs、tests。

**实现建议**：让 Provider Runtime 解析并持久化规范 provider ID；对 media type/capability fail fast；workflow 由受校验配置/definition 选择并显式声明输出；增加不需要 GPU 的 fixture contract test 和可选真实 smoke profile。

**Acceptance Criteria**：

- [ ] 默认 workflow 在源码、测试和打包资源布局下均可定位。
- [ ] 未知 provider/type/workflow 返回结构化 4xx，不会静默回落。
- [ ] generation.provider 与实际执行 Implementation 一致。
- [ ] workflow_id 确实决定模板，模板缺 placeholder/output 时 preflight 失败。
- [ ] `httpx`、`websockets` 等运行依赖显式声明。
- [ ] 配置正确的 ComfyUI 可完成 test connection 与最小生成 smoke。

**Design Decision（P1-E2-T01，2026-08）**：

- 规范 provider id：`mock|comfyui`；GenerationService 创建时解析（缺省 = settings.image_provider）并校验，未知 provider/type/workflow → 422（fail fast，不静默回落）；落库的 generation.provider 即 Worker 实际执行的实现（get_image_provider(provider_id) 按 id 解析）。
- workflow catalog：`WORKFLOW_CATALOG`（MVP：default_image_api → default_image_api.json）；模板目录 = `settings.workflows_dir`（默认仓库根 workflows/，STUDIO_WORKFLOWS_DIR 可覆盖打包布局），修复原 parents[3] 指向 backend/workflows 的错误默认路径。
- preflight：合法 JSON + 恰好一个 SaveImage 输出节点 + 必需 placeholder（`$PROMPT/$SEED/$WIDTH/$HEIGHT`）；缺失时 ComfyUIError；test connection 同时报告 preflight。WS monitor 移除硬编码 node 14。
- 依赖：httpx、websockets 声明为显式运行依赖。
- 测试：`test_provider_contract.py` 10 项（无需 GPU）：模板定位/preflight 失败注入/workflow_id 决定模板/未知 provider/workflow/video 422/worker 按存储 provider 解析/test 端点 preflight。

**Priority**：P0  
**Complexity**：M  
**Dependencies**：无  
**Risk**：用户自定义 workflow 形态不同；先定义最小 contract，不在本任务制作通用节点编辑器。

### P1-E2-T02 — 实现 Generation 状态机、原子认领与崩溃恢复

**背景**：数据库作为队列适合单机桌面，但必须有明确 lease 与恢复语义。

**当前问题**：`generations/worker.py` 先查询再标记 running，不是原子 claim；只扫描 queued/retrying，进程崩溃后的 running 永久滞留。配置的 concurrency 未真正并行，重试无退避，状态转换没有集中校验。

**目标**：单 Worker 与受控多 Worker 下任务只执行一次；崩溃后可按 lease 恢复；非法状态转换被拒绝。

**修改范围**：backend、database、config、docs、tests。

**实现建议**：定义状态转换表、claim token/lease_expires_at/heartbeat 或单实例锁；SQLite 条件更新完成认领；启动 recovery 扫描过期 lease；指数退避带上限；若仍只支持单 Worker，就校验 concurrency=1，不暴露虚假能力。

**Acceptance Criteria**：

- [ ] 两个执行器竞争同一 Generation 时只有一个获得 claim。
- [ ] 在 running 状态模拟进程退出后，任务可恢复或明确进入 failed/retryable。
- [ ] 非法状态迁移返回 Domain Error，不能直接写入。
- [ ] retry 使用配置的最大次数与退避，并记录 attempt/error。
- [ ] worker 活性进入 health 检查。
- [ ] 故障注入与真实轮询 loop 测试通过。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E1-T02 的 schema/并发策略  
**Risk**：SQLite 锁竞争；需以短事务和明确单机容量目标控制复杂度。

### P1-E2-T03 — 原子化生成完成、真实取消与资产补偿

**背景**：生成成功只有在 Generation、Asset、Version 和 Shot active 指针一致时才算完成。

**当前问题**：Worker 依次调用多个自行 commit 的 Service；崩溃会留下半完成状态。provider_ref 未落库，running cancel 不调用 Provider；临时取消集合不清理。Asset 整文件读写、非原子覆盖，DB 失败留下孤儿，`meta_json=str(dict)` 不是 JSON；Version 事件 project_id 为 None。

**目标**：完成链幂等且可恢复；queued/running cancel 都符合用户看到的语义；文件与数据库失败有补偿。

**修改范围**：backend、database、filesystem storage、docs、tests。

**实现建议**：加深 Generation Completion Module：Provider 结果先落受控临时文件，数据库业务更新在一个 Unit of Work，commit 后原子 rename/或采用可重放 finalization；持久化 provider_ref/provenance；取消走 Provider Interface；清理临时输出与孤儿文件。

**Acceptance Criteria**：

- [ ] 在 save/asset/version/activate/complete 每个断点注入失败，重试后只有一个有效版本。
- [ ] queued cancel 不会被 claim；running cancel 调用正确 Provider 且之后不写版本。
- [ ] Generation、Asset、Version、Shot active 指针最终一致。
- [ ] `meta_json` 为有效 JSON，MIME/size/checksum 来自真实文件。
- [ ] 大文件使用流式/临时文件路径，不整文件载入内存。
- [ ] 临时文件、provider output 和取消状态不会无限泄漏。

**Priority**：P0  
**Complexity**：XL  
**Dependencies**：P1-E2-T01、P1-E2-T02  
**Risk**：文件系统与 SQLite 无分布式事务；必须采用幂等 finalizer/补偿，不伪装成绝对原子。

---

## Epic 1.3 — Agent 执行边界

### P1-E3-T01 — 强制 Agent Project Ownership 与 Run-local Context

**背景**：Agent 是高权限执行入口，selection 和自然语言 reference 必须先解析为项目内确定实体。

**当前问题**：`ContextService.resolve_shot_reference` 对原始 Shot ID/selection 未完整验证 project 与 deleted；`shot_number:N` 在全项目重号时取首个。FakeLLM 使用模块级 `_FAKE_SELECTION`，并发 Run 可能串镜头。

**目标**：Run 只能访问声明 project 内、未删除、无歧义的实体，所有上下文均为 run-local。

**修改范围**：backend、docs、tests。

**实现建议**：建立有深度的 Project Ownership Module；reference 解析使用 selected scene/shot 上下文，歧义时返回 clarification；把 Fake/real selection 放入 Graph State/调用参数，移除进程全局。

**Acceptance Criteria**：

- [ ] 跨项目 Shot ID、已删除 Shot、伪造 selection 均在工具执行前失败。
- [ ] 同号 Shot 有歧义时要求澄清，不静默选首个。
- [ ] 两个并发 Fake Run 不会交叉 selection。
- [ ] ToolExecutor 再做一次 ownership 防御，不能只信 Planner。
- [ ] Scenario A/B/C 保持通过，并新增跨项目/并发场景。

**Design Decision（P1-E3-T01，2026-08）**：

- ContextService.resolve_shot_reference 返回结构化 ' + bt + 'ShotResolution' + bt + '（resolved|ambiguous|not_found|rejected|none）：raw Shot ID / selection 校验存在（含软删除）与 project ownership；' + bt + 'shot_number:N' + bt + ' 先按 selection.scene_id 定域，项目内重号 → ambiguous（澄清），不再取首个。
- Graph：load_context 记录 resolution status/message；execute 在无 resolved 目标且有计划步骤时以 ' + bt + 'result.clarification' + bt + ' 完成（review 节点透传标准结果形状），工具绝不执行。
- ToolExecutor 第二道防线：' + bt + '_require_shot/_require_scene' + bt + ' 在每次工具执行前校验 live + project ownership（不信任 Planner）。
- FakeLLM 移除进程全局 ' + bt + '_FAKE_SELECTION' + bt + '：selection 经 Graph State → prompt（run-local）传递，并发 Run 不交叉；runner 不再 set/reset 全局。
- 测试：跨项目/已删除/伪造 selection 拒绝、同号歧义澄清、选中场景定域、并发双 Run 不交叉（test_agent.py 新增 5 项）、ToolExecutor 防御（test_agent_ownership.py 3 项）。Scenario A/B/C 保持通过。
- P1-E3-T02 依赖的边界：取消检查在节点与工具边界（见 P1-E3-T02）。

**Priority**：P0  
**Complexity**：M  
**Dependencies**：无  
**Risk**：旧指令依赖宽松“第 N 镜”解析；需要兼容有明确 selected scene 的常见路径。

### P1-E3-T02 — 实现协作式 Agent Cancel 与真实执行报告

**背景**：取消是用户信任边界；UI 显示 cancelled 后不能继续写 Project State。

**当前问题**：`runner.py::cancel_run` 立即改内存状态，但 Graph 继续到结束后才检查；可能仍 update Shot/创建 Generation。`current_stage` 不随节点更新；ToolResult 可能报告请求字段而不是实际变化，Service event source 固定为 user。

**目标**：每个节点和写工具前都有取消检查；取消后没有新副作用；状态、source 与 ToolResult 可审计。

**修改范围**：backend、events、frontend（仅必要状态）、docs、tests。

**实现建议**：取消令牌进入 Graph State/Run Context；Executor 在每步前后检查；为不可中断的外部调用定义 cancelling→cancelled；Mutation Context 传递 source/run_id；只记录实际 changed fields。

**Acceptance Criteria**：

- [ ] 在每个节点与工具边界取消都有自动测试。
- [ ] cancelled 后 revision、Generation 数量和 active version 不再变化。
- [ ] API/Event 不会重复发出互相矛盾的终态。
- [ ] GET run 能看到实时 current_stage 与 cancelling 状态。
- [ ] shot.updated 能区分 user/agent 并关联 run_id。

**Design Decision（P1-E3-T02，2026-08）**：

- 协作式取消：`POST /agent/runs/{id}/cancel` 立即置 `cancelling`（写入取消令牌 `_cancel_requested`）；Graph 每个节点入口与每个工具执行前检查令牌（`_cancelled(state)`），观察到即停止产生副作用；Runner 在 Graph 真正停止后发布唯一一次 `agent.run.cancelled` 终态事件（API/Event 无矛盾终态，无重复发布）。取消前已提交的单步更新不回滚（Undo 属 Phase 2）。
- 实时报告：`set_run_stage` 由各节点在入口写入 `current_stage`（understand/load_context/plan/execute/review），GET run 实时可见。
- 真实执行报告：ToolExecutor 的 update_shot 按 before/after 对比上报 `changed_fields`（实际变化，而非请求字段）；`shot.updated` 事件 payload 携带 `source`（user|agent）与 `run_id`。
- 测试：cancel 前后置 + 工具边界注入（首工具提交后取消 → 后续工具不执行）、单次终态事件断言、慢网关下轮询 current_stage、事件 source/run_id 断言（test_agent.py 新增 5 项）。

**Priority**：P0  
**Complexity**：M  
**Dependencies**：P1-E3-T01  
**Risk**：已提交的单步更新不能凭空撤销；本阶段保证停止后续步骤，完整 Undo 在 Phase 2。

---

## Epic 1.4 — API、Event 与可诊断性

### P1-E4-T01 — 修复路由冲突并统一错误/请求契约

**背景**：调用者必须能稳定区分验证、找不到、冲突和系统错误，并用 request_id 定位问题。

**当前问题**：`/generations/{generation_id}` 注册在 `/generations/recent` 前，静态路由被当作 ID；`main.py` 只处理 StudioError，422/500 不符合统一 Envelope。Router 仍有直接 SQL/ORM；前端 ApiError 丢 request_id 且缺 timeout/cancel。

**目标**：REST 路由无歧义，所有失败符合契约，Router 仅做协议适配，前端能展示安全且可追踪的错误。

**修改范围**：backend、frontend、docs、tests。

**实现建议**：调整静态路由/改为项目作用域端点；统一 validation/unhandled exception handler；用 contextvar 贯穿 request_id；recent/assets 查询移入现有 Service/Repository；客户端支持 AbortSignal 与 timeout。

**Acceptance Criteria**：

- [ ] `/generations/recent` 返回列表而非 `generation_id=recent` 的 404，并有路由回归测试。
- [ ] 422/404/409/500 均为统一 Envelope 且包含 request_id。
- [ ] 500 不暴露栈、绝对路径、API key 或原始 Provider 响应。
- [ ] Router 不再直接执行业务 SQL/`db.get`。
- [ ] 前端错误状态可显示 message 与可复制 request_id。
- [ ] OpenAPI/API Event 契约同步。

**Design Decision（P1-E4-T01，2026-08）**：

- 路由：`/generations/recent` 先于 `/generations/{generation_id}` 注册（FastAPI 按注册顺序匹配）；recent/assets 查询移入 GenerationService/AssetService，Router 不再直接执行业务 SQL/db.get。
- 错误：main.py 注册 4 个 handler —— StudioError、RequestValidationError（422，详情仅 loc/type/msg 不回显请求体）、StarletteHTTPException（404/405 等）、Exception（500 通用 INTERNAL_ERROR，完整异常仅服务端日志）。request_id 由 HTTP 中间件生成并回传响应头。
- 注意：新版 Starlette 的 ServerErrorMiddleware 发送 500 响应后仍会 re-raise，TestClient 需 raise_server_exceptions=False 才能观察 500 Envelope（见 test_errors.py）。
- 前端：ApiError 携带 requestId；request() 支持 timeoutMs 与 AbortSignal；新增 ApiErrorPanel（message + 可复制 request_id），接入 EpisodePanel/StoryboardView/AIDirectorPanel。
- P1-E4-T02 依赖的 request/project context 基线：request_id 已贯穿错误响应；日志关联字段由 P1-E4-T03 落实。

**Priority**：P0  
**Complexity**：M  
**Dependencies**：无  
**Risk**：错误响应变化影响所有调用点；需要契约测试而非逐页面手工修补。

### P1-E4-T02 — 修复 Event Gateway 线程、生命周期与恢复语义

**背景**：WS 是提示通道，断线或丢事件不能让客户端状态永久错误。

**当前问题**：同步 Service 可能从 threadpool 直接调用 `asyncio.Queue.put_nowait`；Queue 无界，慢客户端串行发送；startup 重复 subscribe，shutdown 不 unsubscribe/cancel。sequence 仅内存，前端发现 gap 后不 reconcile，socket 生命周期脱离页面。

**目标**：事件跨线程安全、有界、按项目传递；断线/重启后客户端以 REST/bootstrap 重建事实状态。

**修改范围**：backend、frontend、events、docs、tests。

**实现建议**：通过目标 event loop 的 thread-safe 调度发布；每连接独立有界队列/超限策略；显式订阅句柄和 shutdown；客户端 gap 时 invalidate scoped keys + bootstrap hydrate。持久 outbox 留到确有审计/云端需求时。

**Acceptance Criteria**：

- [ ] threadpool publish 能可靠唤醒 WS loop。
- [ ] 慢/断开的一个客户端不阻塞其他客户端且内存有上限。
- [ ] 多次 app lifespan 不产生重复事件或悬挂 task。
- [ ] 事件按 project 过滤；前端重连/gap 后执行可观察的 reconcile。
- [ ] malformed/unknown-version event 被记录并安全忽略。
- [ ] WS 与恢复路径有自动化测试。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E4-T01 的 request/project context  
**Risk**：线程与异步时序难复现；测试需控制 loop 和慢客户端，避免只测 happy path。

### P1-E4-T03 — 建立关联日志与深度健康检查

**背景**：桌面产品也需要回答“哪个项目、哪次请求、哪个 Run/Generation 在哪里失败”。

**当前问题**：Formatter 虽含 correlation_id，但没有注入，日志常显示 `[-]`；health 只检查 DB，Worker/Event/Provider 失效仍报 healthy。

**目标**：核心链路可按 request_id/project_id/run_id/generation_id 关联；health 区分 ready/degraded/unhealthy。

**修改范围**：backend、config、docs、tests。

**实现建议**：contextvar + logging Filter/Adapter；结构化输出与开发文本格式可切换；敏感字段 redaction；健康检查返回组件级摘要，不在每次请求做昂贵外部调用。

**Acceptance Criteria**：

- [ ] 请求、Agent、Generation 日志具备约定的关联字段。
- [ ] 日志不记录 secrets、完整 source_text 或不必要 Prompt。
- [ ] health 分别报告 DB、Worker、Event Gateway、当前 Provider。
- [ ] Worker 停止或生产 Provider 配置无效时 readiness 不为 healthy。
- [ ] 日志格式和诊断字段有测试/示例文档。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P1-E4-T01、P1-E2-T02  
**Risk**：过量进度日志影响 SQLite/磁盘；需定义级别和采样。

---

## Epic 1.5 — 本地安全与配置

### P1-E5-T01 — 生产配置 Fail-closed 与依赖/环境契约

**背景**：开发默认 Fake/Mock 合理，但生产不能因为缺少配置而生成假结果并让用户误以为成功。

**当前问题**：LLM 默认 fake、Image Provider 默认 mock，production 没有启动校验；无 `.env.example`/配置矩阵；秘密仅依赖环境变量；运行时依赖声明不完整。

**目标**：development/test 可显式使用 Fake/Mock，production 缺真实配置时拒绝启动或明确 degraded。

**修改范围**：backend、desktop、config、docs、tests。

**实现建议**：按 environment 建立配置 schema 与 startup preflight；枚举值严格校验；列出所有变量、默认值、secret 属性和重启影响；Phase 5 再接 OS secure store。

**Acceptance Criteria**：

- [ ] production 无法静默启用 FakeLLM/MockImageProvider。
- [ ] 无效 provider/URL/path/model 在启动或保存配置时明确失败。
- [ ] 运行依赖为直接依赖，锁文件可复现。
- [ ] `.env.example`/配置文档不包含真实 secret。
- [ ] development/test 默认行为保持方便且可见。

**Priority**：P0  
**Complexity**：M  
**Dependencies**：P1-E2-T01  
**Risk**：过早严格化会影响开发脚本；用 profile 分离而非移除 Mock。

### P1-E5-T02 — 建立本地 Session、WS Origin 与 Tauri CSP

**背景**：localhost 不是认证边界，本机其他进程和恶意网页仍可访问固定端口。

**当前问题**：REST/WS 无认证；WS accept 后广播所有项目；Tauri `csp: null`；端口监听不能证明是本应用后端。

**目标**：只有当前 Tauri 会话可调用本地控制面；浏览器跨站与错误后端进程被拒绝。

**修改范围**：backend、frontend、desktop、config、docs、tests。

**实现建议**：Tauri 启动时生成高熵短期 token，经受控启动握手传给前端/后端；REST header 与 WS query/subprotocol 同一校验；限制 Origin/Host；收紧 CSP；保留开发模式显式开关。

**Acceptance Criteria**：

- [ ] 无 token/错误 token 的 REST 与 WS 请求被拒绝。
- [ ] 非允许 Origin 不能建立 WS。
- [ ] token 不写日志、URL 历史、项目数据库或源码配置。
- [ ] Tauri CSP 不再为 null，并允许必要的本地连接与媒体显示。
- [ ] 后端握手能区分“端口被占用”和“已运行的本应用实例”。
- [ ] 安全回归测试和桌面开发流程通过。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E4-T01、P1-E4-T02  
**Risk**：开发浏览器与 Tauri 两种入口不同；必须提供明确 dev bootstrap，不得用全局关闭认证解决。

---

## Epic 1.6 — 质量基线与事实治理

### P1-E6-T01 — 建立风险驱动测试基线与最小 CI

**背景**：现有测试绕过 Alembic、真实 Worker/WS，前端没有测试；后续修复没有自动门禁会快速回归。

**当前问题**：`backend/tests/conftest.py` 使用 `Base.metadata.create_all()`；Generation 测试直接调用执行函数；无前端测试/E2E、lint/type/coverage、安全扫描或 GitHub Actions。

**目标**：PR 能自动证明迁移、核心状态机、前端契约和构建未回归。

**修改范围**：backend、frontend、desktop、infra、docs、tests。

**实现建议**：先建立快速必过层：Alembic-from-zero/current-upgrade、pytest、Ruff/类型检查、前端 typecheck+组件 smoke、Cargo check、secret/dependency scan；真实 GPU/LLM 作为可选 nightly/manual，不阻塞普通 PR。

**Acceptance Criteria**：

- [ ] CI 在干净环境安装锁定依赖并执行统一命令。
- [ ] 测试数据库由 Alembic 建立，另保留快速 Service fixture 时注明用途。
- [ ] Worker loop、WS、路由、并发/取消/ownership 风险有自动测试。
- [ ] 前端至少覆盖 API error、Character conflict、Event reconcile 和关键状态 Store。
- [ ] 失败门禁阻断合并，文档列出本地等价命令。
- [ ] 不要求普通 PR 连接 GPU、真实 LLM 或用户 ComfyUI。

**Design Decision（P1-E6-T01，2026-08）**：

- 测试库：`tests/test_migrations.py` 用 Alembic 从零 upgrade → head（含 P1 列断言）与 downgrade round trip；`alembic/env.py` 尊重显式注入的 sqlalchemy.url（测试临时库），只有占位符才回退 settings。conftest 的 create_all fixture 保留但注明"仅单元速度用途"。
- Worker loop：`tests/test_worker_loop.py` 驱动真实 DB-poll 循环完成一次生成（非直接调用执行函数）。
- Lint：引入 ruff（select E/F/W/B/S/UP/ASYNC，忽略 E501/B008/S101/S311/S324），存量问题一次性修复，`uv run ruff check app tests` 为门禁。
- 前端测试：vitest + jsdom + testing-library；覆盖 API 错误契约（含 CONFLICT=Character conflict）、Event reconcile 门（从 socket.ts 提取纯函数 shouldRouteEvent/isWellFormedEvent）、selectionStore、ApiErrorPanel。
- CI：.github/workflows/ci.yml（backend pytest+ruff+secret scan / frontend build+test / windows cargo check）；scripts/scan-secrets.py 扫描 git-tracked 文件，SECRET-SCAN 标记允许测试夹具。本地等价命令见 `docs/testing.md`。
- 真实 LLM/ComfyUI 属 nightly/manual，不进普通 PR 门禁。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：可先搭框架；具体回归用例随本 Sprint P0 Task 同步落入  
**Risk**：一次引入过多工具会拖慢反馈；以稳定、快速和高风险覆盖优先。

### P1-E6-T02 — 修正文档事实源与移除误导性遗留入口

**背景**：README/QA/代码文案冲突会让协作者错误判断阶段和可用能力。

**当前问题**：README 仍是 Stage A；`design-qa.md` 称 Stage D 未接；AGENTS 技术栈仍写 asyncio.Queue；`frontend/src/features/ai/DirectorPanel.tsx` 是未使用的锁定版，与真实 Director 并存。

**目标**：入口文档、状态清单和 UI 只声明可验证能力；遗留代码不再形成第二实现。

**修改范围**：docs、frontend（仅删除确认未引用的遗留入口）、tests。

**实现建议**：以自动验证结果和 capability matrix 更新 README；明确“实现存在/Mock 验证/真实 Adapter 验证/生产可用”四种状态；用 import scan 确认遗留文件后删除，不顺带重构。

**Acceptance Criteria**：

- [ ] README、AGENTS、design-qa 与代码当前状态一致。
- [ ] 每项外部能力标明默认模式与真实验证状态。
- [ ] 未使用的 Stage D 锁定 DirectorPanel 无引用后移除。
- [ ] 技术栈描述与 DB-poll Worker 一致。
- [ ] 后续 Task 完成状态按 Roadmap 规则维护。

**Priority**：P1  
**Complexity**：S  
**Dependencies**：P1-E6-T01 提供验证命令；其余可并行  
**Risk**：文档更新不能提前宣称尚未通过真实 smoke 的能力。
