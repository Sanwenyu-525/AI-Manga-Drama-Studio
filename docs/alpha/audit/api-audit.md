# API 审查报告（P0-T004）

> Phase 0 审查 · AI 漫剧 Studio · 只读分析（未修改任何代码）
> 审查对象：MVP 0.1（Stage A–D + P1 收尾）现状 vs Alpha 目标 API/Service
> 目标文档：`docs/incoming/backend-api-service-design-v0.1.md`
> 现状事实源：`docs/api-event-contract-v0.1.md`、`backend/app/api/*`

---

## 1. 现有全部路由清单（`backend/app/api/*` + `router.py`）

前缀统一 `/api/v1`（`router.py` 挂载，`main.py:157`）。WS 网关 `/api/v1/events`（`events/ws.py`）。

| 方法 | 路径 | 同步/异步 | 文件 | 简述 |
|---|---|---|---|---|
| POST | `/projects` | sync | projects.py | 建项目（201） |
| GET | `/projects` | sync | projects.py | 项目列表 |
| GET | `/projects/{id}` | sync | projects.py | 单项目 |
| PATCH | `/projects/{id}` | sync | projects.py | 更新项目 |
| GET | `/projects/{id}/bootstrap` | sync | projects.py | Workspace 摘要（契约 §103-104） |
| POST | `/projects/{id}/cover` | **async** | projects.py | 上传封面（multipart） |
| GET | `/projects/{id}/cover` | sync | projects.py | 取封面（FileResponse） |
| DELETE | `/projects/{id}` | sync | projects.py | 软删项目树 |
| POST | `/projects/{id}/episodes` | sync | episodes.py | 建集（201） |
| GET | `/projects/{id}/episodes` | sync | episodes.py | 集列表 |
| GET | `/episodes/{id}` | sync | episodes.py | 单集 |
| PATCH | `/episodes/{id}` | sync | episodes.py | 更新集 |
| DELETE | `/episodes/{id}` | sync | episodes.py | 软删集树 |
| POST | `/episodes/{id}/analyze/preview` | **async** | episodes.py | AI 分析预览（不落库） |
| POST | `/episodes/{id}/analyze` | **async 202** | episodes.py | AI 分析（operation_id） |
| GET | `/episodes/{id}/scenes` | sync | scenes.py | 场列表 |
| POST | `/episodes/{id}/scenes` | sync | scenes.py | 建场（201） |
| GET | `/scenes/{id}` | sync | scenes.py | 单场 |
| PATCH | `/scenes/{id}` | sync | scenes.py | 更新场 |
| DELETE | `/scenes/{id}` | sync | scenes.py | 软删场 |
| GET | `/scenes/{id}/storyboard` | sync | scenes.py | **聚合端点**（scene + shot 摘要） |
| POST | `/scenes/{id}/generate-shots` | **async 202** | scenes.py | AI 分镜（operation_id） |
| GET | `/scenes/{id}/shots` | sync | shots.py | 镜头列表 |
| POST | `/scenes/{id}/shots` | sync | shots.py | 建镜头（201，可带 character_ids） |
| GET | `/shots/{id}` | sync | shots.py | 单镜头 |
| PATCH | `/shots/{id}` | sync | shots.py | 更新（revision 乐观锁 409） |
| DELETE | `/shots/{id}` | sync | shots.py | 软删镜头 |
| PATCH | `/scenes/{id}/shots/reorder` | sync | shots.py | 镜头重排（校验全量/无重复） |
| POST | `/shots/{id}/generations` | sync **202** | generations.py | 创建图像 generation |
| GET | `/generations/recent` | sync | generations.py | 底部 Dock 历史（静态路由优先） |
| GET | `/generations/{id}` | sync | generations.py | 单 generation |
| GET | `/shots/{id}/generations` | sync | generations.py | 镜头下 generations |
| POST | `/generations/{id}/retry` | sync 202 | generations.py | 重试（新行 retry_of） |
| POST | `/generations/{id}/cancel` | **async** | generations.py | 取消（状态机校验 + worker） |
| GET | `/shots/{id}/versions` | sync | generations.py | 镜头版本列表 |
| POST | `/media-versions/{id}/activate` | sync | generations.py | 设 Active 版本 |
| GET | `/operations/{id}` | sync | operations.py | 轮询后台 AI operation |
| GET | `/assets/{id}/content` | sync | assets.py | 资产内容流 |
| GET | `/assets/{id}/thumbnail` | sync | assets.py | 缩略图 |
| GET | `/providers` | sync | providers.py | Provider 状态 |
| POST | `/providers/comfyui/test` | **async** | providers.py | ComfyUI 连接+模板 preflight |
| POST | `/agent/director/runs` | **async 202** | agents.py | 建 Director Run |
| GET | `/agent/runs/{id}` | sync | agents.py | Run 状态 |
| POST | `/agent/runs/{id}/resume` | sync | agents.py | 恢复（占位） |
| POST | `/agent/runs/{id}/cancel` | sync | agents.py | 取消 Run（不取消 generation） |
| GET | `/workflows` | sync | workflows.py | 只读目录元数据 |
| GET | `/health` | sync | health.py | 组件健康（db+worker） |
| GET | `/system/info` | sync | health.py | 版本信息 |
| WS | `/events` | **async WS** | ws.py | 事件网关（sequence 去重） |

（`router.py` 汇总了上述全部路由 + WS 网关。）

---

## 2. 与 Alpha 目标 API 的差距

### 已有（KEEP，后续对齐命名/聚合）
- Project CRUD（目标 §14 的 POST/GET/PATCH 已覆盖；缺 `open/archive/restore/tree`）。
- Episode / Scene / Shot CRUD。
- `POST /shots/{id}/generations`（对应目标 `generate-image`）。
- `GET /generations/{id}` + retry / cancel。
- `GET /providers` + `POST /providers/comfyui/test`。
- `/operations/{id}`。
- Agent runs 系列（`/agent/director/runs`、`runs/{id}`、resume、cancel）。
- `GET /health`。
- `/scenes/{id}/storyboard`（≈目标 `scenes/{id}/editor` 的雏形，但返回字段更少）。

### 缺失或需迁移（BUILD / MIGRATE）
- **Job API 全缺**：`/projects/{id}/jobs`、`/jobs/{id}/tasks`、pause / resume / cancel / retry-failed（目标 §46）。
- **Generation 业务化端点缺**：`POST /shots/{id}/generate-image`、`/generate-video`、`POST /scenes/{id}/generate`（批量 Job）、`/generations`（通用）→ 现状只有 `/shots/{id}/generations`（单一 image）。
- **Character 版本 API 全缺**：`/characters/{id}/versions`、`versions/{versionId}/set-master`、`generate-reference`（目标 §26）。
- **Location / Costume / Prop API 全缺**（目标 §29 等，与 Domain 缺失一致）。
- **Prompt API 全缺**：`/shots/{id}/prompts`、`/prompts/{id}/versions`、`activate`、`generate`（目标 §34）。
- **Asset API 强烈受限**：仅有 `content/thumbnail`；缺 `import`、`archive/restore`、`set-active`、`provenance`、`version-groups`（目标 §30-31）。无来源导入。
- **Continuity API 全缺**：`/scenes/{id}/continuity`、`/shots/{id}/continuity`、`review`、`warnings`（目标 §80）。
- **Timeline API 全缺**：`/episodes/{id}/timeline`、tracks / clips、`/render`（目标 §84-85）。
- **Workflow API 只读**：只有 `GET /workflows`；缺 `POST /workflows`、`versions`、`activate`、`validate`、`import-comfyui`（目标 §58）。
- **Source Document API 全缺**：`/projects/{id}/documents`、`import`（目标 §17）。
- **Project**：缺 `tree`、`settings`、`open/archive/restore`（目标 §14）。
- **命名/机制差异**：MVP `POST /episodes/{id}/analyze` / `POST /scenes/{id}/generate-shots` 用 `/operations/{id}` 内存轮询；Alpha 改为 `POST /episodes/{id}/plan` / `POST /scenes/{id}/plan-shots`（Job + Agent Task，持久队列）。需要 **MIGRATE**。

---

## 3. 错误格式检查（core/errors.py + main.py）

- **统一 error envelope 已实现**：`main.py:_error_response`（`:20-42`）返回 `{"error": {"code","message","details","request_id"}}`；`StudioError` 基类统一 code + status_code（`errors.py:12-22`），含 `NotFoundError/ConflictError/ValidationError/AgentError/GenerationError/ProviderError/ProviderUnavailableError/ComfyUIError`（404/409/422/500/502/503 齐全）。
- **request_id 已包含**：request-logging 中间件（`main.py:78-93`）生成/透传 `X-Request-ID` 并写 `request.state.request_id`，`_error_response` 回填。✅ 达成 Alpha §9 目标（注意：当前字段名用 `request_id`，Alpha §9 写的是 `requestId`，仅命名差异）。
- **422 / 500 也统一 envelope**（validation handler `:112`、unhandled `:145`，500 不泄 stack / 绝对路径）。
- 结论：**错误基础设施达标（KEEP）**。需补：按模块的细分错误码（当前 `ConflictError` 统一为 `CONFLICT`；Alpha §10 期望更细 `MODULE_ERROR` 命名，如 `SHOT_REVISION_CONFLICT`）。

---

## 4. 分层检查（Router → Service → Repository）

- **api 层有无直接 `db.query`？—— 无**。grep `backend/app/api` 无 `db.query(` / `.query(` 命中。Routers 全部经 `ProjectService(db)/EpisodeService(db)/...` 调用（验证于各 router 文件）；`generations.py` 的 `_to_read` 只是 DTO 序列化（不查库）。
- 注意点：routers 的 **DTO 序列化逻辑放在 router 层**（如 `generations.py:13-32` `_to_read`、`assets.py` 直接调 `AssetService`），这是可接受的「轻 presentational 序列化」，不算业务逻辑；但更贴近目标是放 Service 返回 READ DTO（`generation_service.py:list_recent` 已在 Service 内做查询，符合 P1-E4-T01）。
- Repository 层：`repositories/base.py` 通用 `SQLAlchemyRepository`（get / list / next_sequence / soft-delete），Service 通过 `ShotRepository(session)` 等注入。
- **物流：Router ↔ Service ↔ Repository 已遵守红线 6（`api 层无 db.query`）✅**。

---

## 5. 事件契约核对（events/bus.py + events/ws.py vs api-event-contract）

### 现有 Event 类型（`bus.py:23-67`）
- CRUD：`shot.created/updated/deleted/active_version.changed`，`character.created/updated/deleted`，`scene.created/updated/deleted`，`episode.created/updated/deleted`，`project.created/updated/deleted`。
- 生成：`generation.created/queued/started/progress/completed/failed/cancelled/retrying`。
- Provider：`provider.connected/disconnected`。
- Asset：`asset.created`。
- Agent：`agent.run.started/resumed/completed/failed/cancelled`，`agent.intent.resolved/context.loaded/plan.created/approval.required/tool.started/tool.completed/review.started/review.completed/change_set.created`。

### vs 契约 §143 必备事件
`shot.updated` ✅ · `agent.run.started` ✅ · `agent.plan.created` ✅ · `agent.approval.required` ✅ · `agent.tool.started` ✅ · `agent.tool.completed` ✅ · `agent.run.completed/failed` ✅ · `generation.queued/started/progress/completed/failed` ✅ · `asset.created` ✅ · `provider.connected/disconnected` ✅。**MVP 必需事件全部覆盖。**

### 差距（Alpha 目标 §73/§82 扩展）
- 缺领域语义事件：`CharacterMasterChanged`（含 old/new versionId）、`AssetMarkedStale`、`GenerationSucceeded`（含 outputAssetIds）、`JobCompleted`。
- `events/ws.py` envelope 字段（`event_id/event_type/event_version/project_id/entity_type/entity_id/timestamp/sequence/payload`）与契约 §Envelope 完全一致，且 WS 支持 sequence 去重、`system.connected` 重放。✅
- 「commit 后 publish」红线在 service 中遵守（如 `shot_service.py` commit / refresh 后才 publish）✅。

---

## 6. 差距汇总表

| 目标能力 | 现状 | 缺口 | 建议动作 |
|---|---|---|---|
| Project 聚合 | MVP 版可用 | 缺 project_type / active_episode_id / last_opened_at；生成策略未拆 | **REFACTOR**（拆 ProjectSetting），**MIGRATE** `deleted_at→archived_at` |
| ProjectSetting | 无 | 全部缺失 | **BUILD** |
| SourceDocument | 无（source_text 内联） | 文档 / 导入 | **BUILD**（§17/§16） |
| Episode | 可用 | 缺 order_index / source_document_id / target_duration；无 revision | **REFACTOR** |
| Scene | 可用 | location_id 空挂；缺 narrative_purpose / continuity_state_id；无 revision | **REFACTOR** |
| Shot | 可用 | Prompt 内联；缺 visual_spec_id / continuity_state_id；无 order_index 类型对齐 | **REFACTOR + MIGRATE** |
| ShotVisualSpec | 无（字段内联） | 独立表 | **BUILD**（§25） |
| Character | 可用（身份） | 无版本 / 无 MASTER | **BUILD** CharacterVersion / MASTER |
| CharacterVersion | 无 | 全部缺失（Alpha 关键） | **BUILD**（§29-32） |
| Location / LocationVersion | 无 | 全部缺失 | **BUILD**（§33-36） |
| Costume / Prop | 无（弱引用） | 全部缺失 | **BUILD**（§32 / §33-36） |
| Asset（版本化） | 单 Asset | 缺 version_group_id/version_number/source_type/checksum/parent_asset_id/status | **REFACTOR**（§40-43） |
| media_versions | 存在且不可变 | 与 Asset 自版本化冲突 | **MIGRATE**（合并进 Asset 版本） |
| Prompt / PromptVersion | 无 | 全部缺失（Shot != Prompt 规则） | **BUILD**（§44-48） |
| Generation（immutable） | 不覆盖历史，但多余可写字段 | 缺 parent_generation_id / target_type / prompt_version_id / workflow_version_id | **REFACTOR + MIGRATE**（parent_generation_id） |
| GenerationInput / Output | 无（JSON / 弱引用） | 多对多关系表（provenance） | **BUILD**（§50-52，含 Asset provenance API） |
| Job / JobTask / 依赖 | 无（generations 当队列） | Job ≠ Generation | **BUILD + MIGRATE**（§56-60，队列迁到 job_tasks） |
| WorkflowTemplate / Version | 无（内置 JSON 目录） | 抽象 + 版本 | **BUILD**（§53-55 / §78-80） |
| ResourceDependency | 无 | Stale 传播根基 | **BUILD**（§61-63） |
| ContinuityState | 无（字段预留） | 结构化状态链 | **BUILD**（§64-69） |
| Timeline / Track / Clip | 无 | 全部缺失 | **BUILD**（§70-73） |
| revision 乐观锁 | 仅 Shot / Character | Scene / Episode / Project / Workflow | **REFACTOR**（红线 10） |
| 软删除命名 | deleted_at（8 表） | archived_at | **MIGRATE** |
| Error envelope | ✅ 统一含 request_id | 细分 MODULE_ERROR 码 | **REFACTOR**（KEEP 基础设施） |
| Router → Service → Repo | ✅ 无 db.query | — | **KEEP** |
| 事件总线 | ✅ MVP 事件全覆盖 + WS envelope | 缺领域事件 / 持久化 | **BUILD**（domain_events / audit_logs） |
| API 异步 202 | ✅ analyze / generate-shots / generations / agent | operation 内存轮询 → Job 持久 | **MIGRATE** |
| 批量生成（Job） | 无 | /scenes/{id}/generate | **BUILD** |

---

## 7. 关键结论（API）

- **MVP 的基础设施达标可复用（KEEP）**：统一 error envelope + request_id、Router → Service → Repository 分层无违规、WS 事件网关含 sequence 去重、202 异步思想贯穿 analyze / generate-shots / generations / agent。
- **API 缺口与 Domain 缺口一一对应**：Job / Continuity / Timeline / Prompt / CharacterVersion(MASTER) / GenerationIO / Asset 版本化 的目标端点几乎全缺，属于 BUILD。
- **命名与机制迁移集中在三条线**：① `media_versions` → Asset 自版本化（影响 `/shots/{id}/versions`、`/media-versions/{id}/activate`）；② prompt 内联 → `Prompt/PromptVersion`（影响 generation 业务端点）；③ operation 内存轮询 → Job 持久队列（影响 analyze / generate-shots 的返回与轮询）。
