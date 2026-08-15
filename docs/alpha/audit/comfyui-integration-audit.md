# ComfyUI / Provider / Agent 接入审查报告（P0-T006）

# AI 漫剧 Studio Phase 0 审查报告（P0-T006 + Agent 现状补充）

**审查范围**：Provider / ComfyUI / Generation / Worker / 状态机 / Asset / Version / Agent / LLM / Operation / Event / Config 全部指定文件，对照两份 incoming 设计文档（`backend-api-service-design-v0.1.md`、`ai-director-agent-design-v0.2.md`）与 `AGENTS.md` 红线。工作目录 `D:\Develop\AI_Manga_Drama_Studio`，全程只读。

---

## 一、ComfyUI 接入审查（对应 P0-T006）

### 1. workflow 如何存储与加载？

- **存储**：静态 JSON 模板文件 `<repo>/workflows/default_image_api.json`，由 `WORKFLOW_CATALOG` 映射 `workflow_id → 文件名`，路径根在 `settings.workflows_dir`（`backend/app/core/config.py:73`，默认 `REPO_ROOT/workflows`，可用 `STUDIO_WORKFLOWS_DIR` 覆盖）。
- **定位与校验**：`WorkflowMapper.resolve_workflow_path()`（`workflow_mapper.py:42-56`）把 `workflow_id` 映射为路径，未知 id 抛 `ValidationError`（→422），**绝不静默回落**。`load_template()`（:67-81）读 JSON 并 `_preflight()` 校验。
- **preflight**（`workflow_mapper.py:91-120`）：必须（a）合法 JSON；（b）**恰好一个** `SaveImage` 输出节点；（c）包含全部必备占位符 `$PROMPT/$SEED/$WIDTH/$HEIGHT`。缺失即 `ComfyUIError`，生成前失败。
- **加载实现**：`ComfyUIProvider.generate()`（`image/comfyui.py:44`）用 `WorkflowMapper(workflow_id=request.workflow_id)` 解析模板再 `mapper.build(...)`。

### 2. node id 是否硬编码？在哪些层出现？

- **硬编码 node id 只出现在**：
  - `workflows/default_image_api.json`：数字键 `"3"/"6"/"7"/"5"/"12"/"13"/"14"` 即 node id（如 `"14"` 是 `SaveImage`，`"6"` 承接 `$PROMPT`）。
  - `workflow_mapper.py`：`OUTPUT_NODE_CLASS="SaveImage"`、`output_node_id` 只是**从模板动态探测**出来的 `_output_node_id`（:103），非固定写死。
- **业务层完全不感知 node_id**：`image/comfyui.py` 只把 `prompt`/`seed`/`width` 等 Studio 逻辑参数交给 mapper；`client.py` 的 WS monitor 注释明确“executed / execution_error 事件 carry final state”，**不解析具体 node**（`client.py:140-141`）。`AGENTS.md` 红线“业务层不能见 ComfyUI node_id”**符合**。
- **残留对照**：设计文档 §64-65 提到 `ComfyUIWorkflowAdapter` 允许在 adapter 内做 `node["87"].inputs.text` 式映射，且仅 adapter 知道 node id——现状把 node 逻辑收敛在 `workflow_mapper.py`（等价 adapter），方向正确。

### 3. 逻辑参数如何注入（input schema / 占位符替换）？

- **注入机制**：`WorkflowMapper.build()`（`workflow_mapper.py:122-153`）将 `values` 字典（`$PROMPT`/`$NEGATIVE_PROMPT`/`$SEED`/`$WIDTH`/`$HEIGHT`/`$REFERENCE_IMAGE`）对模板做**深拷贝后逐 inputs 值替换**（`if isinstance(value, str) and value in values: inputs[key] = values[value]`）。
- **没有 input schema**：注入对象就是 `ImageRequest` dataclass（`image/base.py:13-24`），参数来自 `generation.parameters` JSON（`worker.py:224`）。默认值在 `build` 内硬给（`width or 512`、`height or 912`）。
- `$REFERENCE_IMAGE` 目前仅取 `refs[0]`，upload 是调用方职责（注释），真实 ControlNet/IPAdapter 链路未接。

### 4. 输出文件如何获取（outputs / history / WS）？

- **链路**（`image/comfyui.py:69-86` + `client.py`）：
  1. `queue_prompt()` 提交，拿 `prompt_id`；
  2. `client.monitor()` 走 **WebSocket** 等 `executing(node=None)` 判定完成（`:137-139`）；
  3. monitor 结束后 `client.get_outputs(prompt_id)` 从 **history** 解析 `outputs`（`client.py:65-75`，筛选 `type=="output"`）；
  4. `download_output()` 走 `GET /view` 把图下载到本地 `comfyui_output/comfy_xxx.png`（`:77-92`）。
- **回落**：WS 连接丢失时 `get_outputs` 判定为空 → `_poll_history_fallback()` 轮询 history 20 次（`client.py:156-165`）；monitor 返回但无 done 信号也回落 history 检查（`image/comfyui.py:73-77`）。
- 故：**WS 为主、history 兜底、outputs 只管下载对账**。

### 5. 是否支持进度上报？

- **支持**。`ImageProvider.generate(request, on_progress)` 约定 `on_progress(percent, stage)`（`base.py:45`）。
- ComfyUI 端：WS `progress` 事件 → `_progress()` 把 `value/max` 映射到 5-99%（`image/comfyui.py:59-61`）；`executed` → `on_progress(100,"saving")`。
- Worker 端：`_on_progress`（`worker.py:239-249`）既写 DB（`progress/stage/lease` 心跳）又发 `generation.progress` WS 事件。

### 6. 是否支持 cancel？

- **支持（best-effort + 两层）**：
  - Provider 层：`ComfyUIProvider.cancel(provider_ref)` → `client.cancel()`（`client.py:109-115`），发 `/interrupt` + `/queue delete`，失败仅 warning 不抛错。
  - Worker 层：`cancel_running()` 把 generation id 加进 `_cancelled` 集合，worker 在 `result.success` 后、`_persist_output` 前检查（`worker.py:261-263`），已产出则走 `_handle_cancelled` 状态机 ->`cancelled`（`worker.py:393-411`）。
- 注：生成中的 ComfyUI 任务本身靠 provider 的 `/interrupt`，DB 状态由 worker 收口。

### 7. 错误处理如何？

- 统一的 Studio 错误封装：`ProviderUnavailableError`（连接/传输）、`ComfyUIError`（工作流被拒/无输出/执行错误），见 `image/comfyui.py:71-81`；绝不向业务泄露原始 ComfyUI 协议。
- Worker 侧 `try/except StudioError` 与通用 `Exception`（`worker.py:251-259`）进 `_handle_failure`；DB update 失败 / lease 过期走 crash recovery。
- `client.monitor` 超时（900s）与 WS 异常均有兜底（`client.py:151-165`）。

### 8. ComfyUI 客户端是否可配置 URL？

- **是**。`settings.comfyui_url`（`config.py:56`，默认 `http://127.0.0.1:8188`），`ComfyUIClient(base_url)` 可传参覆盖（`client.py:24`），Provider 用 `settings.comfyui_url`（`image/comfyui.py:27`）。

> **P0-T006 小结**：ComfyUI 接入在“占位符模板 + mapper 探测 output node + WS/history 混合取输出 + 进度/cancel/错误封装 + URL 可配”上均已落地，且 node_id 不透出业务层，符合红线。剩余：`$REFERENCE_IMAGE` 仅取首元素未接 upload、无 WorkflowTemplate/Version 版本化（见二）。

---

## 二、Provider 抽象审查

### 现状接口形状

- **`ImageProvider` Protocol**（`image/base.py:40-51`）：`name: str` + `async generate(request, on_progress) -> ImageResult` + `async cancel(provider_ref)`。DTO：`ImageRequest`（prompt/negative_prompt/seed/width/height/reference_images/workflow_id/metadata）、`ImageResult`（success/output_path/provider_ref/width/height/error/extra）。
- **两个实现**：
  - `MockImageProvider`（`image/mock.py:20-60`）：`name="mock"`，确定性 9:16 图，`md5(prompt|seed)` 定色，模拟采样步进并回调进度，无副作用。
  - `ComfyUIProvider`（`image/comfyui.py:21-97`）：`name="comfyui"`，额外 `health_check()`。
- **registry**（`providers/registry.py`）：`get_image_provider(provider_id=None)` 按 `settings.image_provider`（`mock|comfyui`）解析并缓存；未知 id `ValidationError`(422)；`get_comfyui_provider()` 单例；`provider_status()` 输出状态 DTO；`reset_providers()` 仅测试用。
- **选择机制**：`GenerationService.create_generation()`（`generation_service.py:60-63`）在入队前即用 `get_image_provider(provider)` 校验、`resolve_workflow_path` 校验 → fail-fast；worker 再按**持久化在 generation.provider 的 id** 解析实例（`worker.py:228`）。`max_attempts` 在 domain 层 ge=1 le=5。

### 与目标差距

对照 `backend-api-service-design-v0.1.md` §61-67：

| 目标 | 现状 | 差距 |
|---|---|---|
| ProviderAdapter（`execute/cancel/queryStatus/healthCheck`）统一接口 | 有 `ImageProvider`（generate/cancel+on_progress），但**无状态查询 `queryStatus`** | 缺状态查询能力 |
| **Adapter 分类**（Llm/Image/Video/Voice/Workflow 五类）| 只有 `ImageProvider` 一类 | Video/Voice/Llm/Workflow adapter 均未建 |
| ComfyUI 属 `WorkflowProviderAdapter`（submitWorkflow/getExecutionStatus/cancelExecution/downloadOutputs/healthCheck）| 拆在 `ComfyUIClient`（queue/get_outputs/cancel/download/health） | 无独立 Workflow adapter 命名；能力齐全 |
| **ProviderRegistry** 多 providerType 注册（MINIMAX/OPENAI/COMFTUI_LOCAL/KLING…）| 只有 hash 表 `IMAGE_PROVIDERS=("mock","comfyui")` | 未按 providerType/名称注册，无扩展表 |
| **ProviderHealthService**（GET /providers/{id}/health → {status,latencyMs}| 仅 `ComfyUIProvider.health_check()` + `provider_status()` 静态 DTO（comfyui_local 默认 "unknown"） | 无独立 health service、无 periodic 探活、latency 未持久化 |
| **WorkflowTemplate / Workflow Version 抽象**（§64 WorkflowVersion + Logical Input→JSON→Node Mapping）| `WorkflowMapper` 读固定 catalog `default_image_api.json`，单模板无版本 | **无 workflow version 概念**，无模板版本管理 |

> 红线检查：`AGENTS.md` 5「Provider 不能知道 Episode/Scene/Shot 业务语义」——`ImageRequest` 仅收 prompt/seed/size 等，**符合**。

---

## 三、Generation / Worker / 状态机审查

### generations 表作为队列（DB-poll worker）

- **队列即表**：`Generation` 模型（`models/generation.py`）status 含 `queued/retrying` 即队内；worker 周期性 `select ... where status in (queued,retrying) and next_attempt_at<=now`（`worker.py:178-189`），`POLL_INTERVAL=0.5s`。
- **原子 claim**：`claim_generation()` 用单条**条件 UPDATE**（status+backoff+lease 全条件 → running + 新 claim_token + lease_expires），`rowcount==1` 判胜（`worker.py:93-127`），并发安全。
- **lease 崩溃恢复**：`recover_expired_leases()`（`worker.py:130-163`）把 lease 过期的 running 行 re-queue 或（超 budget）failed，`attempts+1`。**磁盘即队列 → 崩溃恢复免费**。
- **asyncio.Queue 弃用原因**：注释明示 sync 路由跑在 threadpool，asyncio.Queue 跨线程不安全（`worker.py:47-50`）。
- 仅 `concurrency=1`（config validator 强制，`config.py:63-69`）。

### 状态流转（state.py）

- `ALLOWED_TRANSITIONS`（`state.py:25-34`）：`created→queued`；`queued→running|cancelled`；`running→completed|failed|cancelled|retrying|queued(lease recovery)`；`retrying→running|cancelled|failed`；三者终态。
- 一切变更走 `validate_transition()`，非法转移抛 `ConflictError`（409）。
- 契约的中间态 `waiting_provider/processing_output` 存在 status 枚举但**不落行**（`state.py:13-14` 注释）。

### retry / cancel / 失败

- **retry**：`retry_generation()`（`generation_service.py:149-175`）运行中禁止，**新建记录**并回填 `retry_of=old`——满足“Retry 新记录、Generation 不覆盖历史”红线。
- **cancel**：`cancel_generation()` 走状态机直接置 `cancelled`；worker 侧另用 `_cancelled` 集合协作取消（见一.6）。
- **失败+重试**：`_handle_failure()`（`worker.py:349-390`）：attempts+1，未达上限 → `retrying` + 释放 claim + `next_attempt_at=now+backoff`（指数退避 base*2^(n-1)，上限 60s，`worker.py:68-71`）；达上限 → `failed`。均发对应事件。

### Asset 注册流程（temp→validate→commit）

`_persist_output()`（`worker.py:283-346`）→ `AssetService.register_asset()`（`asset_service.py:37-100`）：
1. 校验源文件存在（`NotFoundError`）；
2. `dest_dir = data_dir/projects/{pid}/images/EP01_SC03_SH005_IMG/`（`_shot_relative_dir` :142-152），`dest.write_bytes(source.read_bytes())` 拷贝（无临时区，直接落项目树）；
3. 读图尺寸、生成缩略图（`create_thumbnail` :102-112，240px）；
4. 写 DB `Asset`（存**相对路径**）+ `asset.created` 事件。
- 注：审查文件给的是“temp→validate→commit”目标描述，现状是逐条 commit（asset 一次 commit），无批量事务包裹 asset+version+generation（三者分三次 commit）。`AssetService._safe_path` 有项目根逃逸校验（:131-140）。

### 版本分配与 Active 切换

- `VersionService.create_media_version()`（`version_service.py:24-67`）：`version_number = max+1`（immutable，唯一索引 `uq_media_versions_shot_number`）；`make_active=True` 时先 `_clear_active`（:108-121，用 ORM 保 identity map 同步）再插新行并 `setattr(shot, active_<type>_version_id, version.id)`；部分唯一索引 `uq_media_versions_active` 保证每 shot 单 active。
- `set_active_version()`（:69-90）：同样先清后置，翻 `is_active` + `shot.active_*_version_id` → 触发 `shot.active_version.changed`。
- **版本不可变**（只翻 active）**符合**目标。

### 与目标差距

| 目标能力 | 现状 | 缺口 |
|---|---|---|
| **Generation immutable** | 输出历史不覆盖（V1/V2 共存、retry 新记录）| 但 `progress/stage/lease/status/error_message` 原地更新，Generation 非广义 immutable；无 immutable 审计快照 |
| **Retry 新记录** | ✅ `retry_of` 新行 | 已达成 |
| **Task / Job 分离**（Job API §46-50，JobService.createJob/addTask/pause/resume/cancel/retryFailedTasks + TaskExecutorRegistry 分类 CPU/LLM/Image/Video/ComfyUI）| **无 Job/Task 概念**；grep `class Job` 0 命中；只有 Generation + OperationStore（内存，`operations/store.py`，非 DB）| **最大结构性缺口**：多镜头批量生成、暂停/恢复、依赖编排（image→video）无法表达；Operation 与 Generation 两套 202 机制并存 |
| 队列持久化 | generations 表即队列 ✅ | 已达成 |
| Job 级 pause/resume/retry-failed | 无 | 缺 |

> **结论**：目前**只有 Generation，没有 Job/Task**。`operations/store.py` 提供的是内存 202 短任务（analyze/shot-plan），与 Generation 持久队列是两套机制且不互通。

---

## 四、Agent 层审查

### 现有 Director Graph 结构

- **节点/边**（`director/graph.py:293-306`）：`START→understand→load_context→plan→execute→review→END` 六节点（五业务 + START/END）。
- **State**：`DirectorState` TypedDict（`graph.py:41-59`）：run_id/project_id/selection/user_message + intent/context/plan/tool_results/status/final_result；`current_stage` 通过 `runner.set_run_stage` 实时回写内存。
- **执行模式**：Structured Planner + Deterministic Executor。understand 用 `llm.structured(ProductionIntent,...)`；plan 在 intent.operations 非空时直接引用、否则再 `llm.structured(DirectorPlan)`；execute 串行 `ToolExecutor.execute`。
- **协作取消**：`_cancelled(state)` 检查 `runner.is_cancel_requested`，节点 + tool 边界均查（`graph.py:69-73, 205`）。

### 工具集（tools.py）

- `ToolExecutor`（`tools.py:66-135`）：`_require_shot/_require_scene` 二次校验（存活性 + project ownership，`P1-E3-T01` 防御）；`execute(op)` 反射调用 handler，`StudioError` → `ToolResult(success=False,error,code)`。
- 四个 schema：`GetShotArgs/GetSceneShotsArgs/UpdateShotArgs/GenerateImageArgs`，全部严格 Pydantic（`tools.py:21-43`）。
- 三个实现 + `_get_scene_shots`（可选项已实现）：全部经 Service（ShotService/GenerationService/ContextService），**不碰 SQL/ComfyUI**，符合红线。`_update_shot` 统计**实际 diff** 字段 + 事件带 `source=agent, run_id`（:153-177）。

### FakeLLM 规则解析

- `parse_director_plan()`（`fake_planner.py:38-106`）：关键词表（近景/特写/中景/全景/远景/大远景；紧张/平静/兴奋/悲伤/愤怒/温柔）+ `第N镜` 正则 + duration `N秒`；组合意图（update+generate）。无具体改法→要求澄清；无 target→要求选中。满足 Scenario A/B/C。
- `FakeLLMGateway.structured()` 对 `DirectorPlan/ProductionIntent` 分发到这些解析函数（`llm/fake.py:55-58`），从 prompt 正则提 selection（`selection_from_prompt` :25-33）。

### Agent Run 存储与 API

- **内存存储**：`_runs: dict[str,dict]`（`runner.py:31`）+ `_cancel_requested: set`。字段含 `approval/change_set_id/current_stage/plan/result`（`runner.py:54-67`）。
- **API**：`POST /api/v1/agent/director/runs`(202) → `create_run` + `start_run`（`asyncio.create_task(_run_graph)`）；`GET runs/{id}`；`cancel_run`（协作式，status→cancelling）；`resume_run` 仅占位（须 `waiting_approval` 否则 409，MVP 永不满足，`runner.py:184-194`）。
- **事件**：run.started/plan.created/tool.started/tool.completed/run.completed/failed/cancelled（bus.py 全定义，graph/runner 发布）。

### 与目标差距

对照 `ai-director-agent-design-v0.2.md`：

| 目标能力 | 现状 | 缺口 |
|---|---|---|
| **AgentRun 独立**（比 Generation 多 LLM Call/node/tool/Human Review）| **内存 dict 独有**，未 DB 持久化 | AgentRun 表/CRUD 持久化缺失（重启丢失）；后续 LLM 重放/审计无支撑 |
| **AgentRun 字段**（agentType/threadId/model/targetType/targetId/proposalId/inputContextHash/tokenUsage/cost/finishedAt）| domain `AgentRunRead` 只有 id/project/status/stage/plan/approval/change_set/result/timestamps | agentType/model/target 信息/token/cost 字段缺失 |
| **AgentGateway 抽象**（planEpisode/planScene/planShots/buildPrompt/reviewContinuity/resumeAgentRun）| 无；graph 内 `create_gateway()` 直连 LLMGateway | 缺统一 AgentGateway 层，业务无法以接口调 Agent |
| **Proposal 机制**（AgentProposal + ProposalStatus DRAFT..APPLIED + ProposalTool，tool 输出 Proposal 而非直接写 DB）| `approval`/`change_set_id` 字段存在但**永不填充**；execute 直接经 ToolExecutor 写 Service | **无 Proposal/proposal tool/Human Review**；写库无 proposal 前置 |
| **Human Review / interrupt**（Graph Interrupt + resumeAgentRun + WAITING_HUMAN）| 无 interrupt；resume 占位 | 缺 |
| **ContextResolver** | 现有 `ContextService`（`context_service.py`）实现 Selection-aware 最小上下文 + 所有权/歧义解析（P1-E3-T01，get_shot_context/resolve_shot_reference）| 功能已具备，仅命名/泛化需对齐目标 |
| **Token 记录**（每个 node input/output/cached + totalCost + tokenBudget + maxToolCalls/maxRevisionLoops 预算）| 无 token/cost 采集；无 budget 限制 | 缺 |

---

## 五、LLM 抽象审查

### 分工

- **`LLMGateway` Protocol**（`llm/gateway.py:16-29`）：`invoke / structured / structured_list`，业务（ScriptService/Agent graph）只见此接口。
- **`factory.create_gateway()`**（`llm/factory.py:22-32`）：按 `settings.llm_mode` 选择：
  - `fake`（默认）→ `FakeLLMGateway`；
  - `openai` → `LangChainOpenAIGateway`。
  缓存全局实例 + `reset_gateway()` 测试钩子。
- **`LangChainOpenAIGateway`**（`llm/langchain_gateway.py`）：`ChatOpenAI(model, base_url, api_key)`,结构化走 `with_structured_output(schema, method=settings.llm_structured_method)`（`json_schema`|`function_calling`）；`structured_list` 用 `create_model` 包容器；错误统一 `ProviderUnavailableError`。
- **`FakeLLMGateway`**（`llm/fake.py`）：对 `ScenePlan/ShotPlan` 提供确定性启发式；对 `DirectorPlan/ProductionIntent` 分发到 `fake_planner`。`invoke` 返回 `FAKE:...` 前缀。
- **`STUDIO_LLM_MODE` 切换**：config `llm_mode`（`config.py:46`，`fake|openai`），factory 依此实例化；相关 `llm_base_url/llm_api_key/llm_model/llm_structured_method`。真实模型需 `STUDIO_LLM_BASE_URL/API_KEY`，否则 `ProviderUnavailableError`。

### 综合评价

分工清晰、红线（业务不依赖具体 SDK，ScriptService 只依赖 `LLMGateway`）符合。**缺口**：无 token usage / cost 记录（`LangChainOpenAIGateway` 未读取 usage 元数据），无 budget；`FakeLLMGateway.invoke` 过于占位（仅 echo），真实 director 对话/总结无 fake 路径但 MVP 场景可接受。

---

## 六、差距汇总表

| # | 目标能力 | 现状 | 缺口 | 建议动作 |
|---|---|---|---|---|
| 1 | Provider 分类（Llm/Image/Video/Voice/Workflow adapter）| 仅 `ImageProvider` | 缺 Video/Llm/Voice/Workflow adapter | 先建命名清晰的 `WorkflowProviderAdapter`（包住 ComfyUIClient）与 `ImageProviderAdapter` 基类 |
| 2 | ProviderRegistry 多 providerType 注册 | `IMAGE_PROVIDERS=("mock","comfyui")` hash | 无 providerType/扩展表 | registry 按 `(type,id)` 注册，能力清单进 `capabilities` |
| 3 | ProviderHealthService + periodic 探活 | 仅 `health_check()` + 静态 `provider_status()` | 无独立服务、无周期性 | 加 `ProviderHealthService`，`GET /providers/{id}/health` 返回 `{status,latencyMs}` |
| 4 | WorkflowTemplate / Workflow Version | `WorkflowMapper` 读固定 catalog JSON，单模板无版本 | **无版本概念** | 建 workflow_template 表（template 内容 + 版本），mapper 按版本取 |
| 5 | ProviderAdapter 含 queryStatus | 仅 generate/cancel | 缺 status 查询 | provider 接口加 `query_status(executionId)` |
| 6 | Task / Job 分离 + Job API | **无 Job/Task**，仅 Generation + 内存 OperationStore | 最大结构性缺口 | 引入 Job/Task 持久模型 + JobService（pause/resume/cancel/retry-failed），Generation 作为 Task 载体 |
| 7 | Generation immutable | 输出历史不覆盖 ✅ | progress/lease/status 原地改，缺审计快照 | 保持现状即可，如需审计可加 immutable snapshot 表 |
| 8 | AgentRun DB 持久化 | 内存 dict | 重启丢失、无审计 | AgentRun 落库 + `GET/POST` 基于表 |
| 9 | AgentRun 字段（agentType/model/target/tokenUsage/cost）| 字段缺失 | 缺 | domain/表扩展字段 |
| 10 | AgentGateway 抽象 | graph 直连 LLMGateway | 缺统一层 | 包一层 AgentGateway（planEpisode/planShots/reviewContinuity/resume）|
| 11 | Proposal + Human Review/interrupt | approval/change_set 字段空；resume 占位 | 缺 | 接 LangGraph interrupt，产 Proposal（DRAFT→REVIEW→APPROVED→APPLIED），`WAITING_HUMAN` 状态 |
| 12 | ContextResolver | `ContextService` 已具备（P1-E3-T01）| 命名/泛化 | 对齐目标命名（可选） |
| 13 | Token Tracking / Budget | 无 token/cost | 缺 | LangChain 读 usage → LLMCall/AgentRun 记录 + budget 限制 |
| 14 | `$REFERENCE_IMAGE` 真实链路 | 仅取 refs[0]，未接 upload | 缺 | 在 mapper/provider 接 `upload_image` 走 ControlNet/IPAdapter |

---

### 附：关键文件清单（本次审查读取）

Provider：`backend/app/providers/image/base.py`、`mock.py`、`comfyui.py`；`providers/comfyui/client.py`、`workflow_mapper.py`；`providers/registry.py`；`workflows/default_image_api.json`。
Generation：`backend/app/generations/worker.py`、`state.py`；`services/generation_service.py`、`asset_service.py`、`version_service.py`；`db/models/generation.py`、`media_version.py`。
Agent：`backend/app/agents/fake_planner.py`、`tools.py`、`director/graph.py`、`director/runner.py`；`domain/agent.py`。
LLM：`backend/app/llm/gateway.py`、`factory.py`、`fake.py`、`langchain_gateway.py`。
其余：`services/context_service.py`、`script_service.py`；`operations/store.py`；`events/bus.py`、`ws.py`；`core/config.py`；`domain/generation.py`。

**总体判断**：MVP 全链路（Stage A–D + P1）代码落地完整、红线合规度高（node_id 不透业务、Agent 不碰 DB/ComfyUI、版本不可变、retry 新记录、commit-then-publish、202+Event）。主要结构性欠账集中在：**① Job/Task 分离缺失**（与 Operation/Generation 两套机制并存）、**② AgentRun 未持久化**、**③ Proposal/Human Review 未实现**（字段已是占位壳）、**④ Provider/Workflow 版本抽象与健康服务未建**、**⑤ Token/Cost 记录缺失**——均为 Phase 2 目标项，不影响当前 MVP 验收。
