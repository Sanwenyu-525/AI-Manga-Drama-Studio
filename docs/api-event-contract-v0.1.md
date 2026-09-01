# AI 漫剧 Studio 前后端 API + Event Contract v0.1

> 文档类型：**Frontend / Backend Integration Specification**
> 状态：**draft**（主创定稿，前后端数据契约的事实源）
> 目标阶段：MVP → V1
> 适用范围：Desktop Studio、FastAPI Backend、AI Director、Generation Runtime
> 通信方式：REST + WebSocket
> 核心目标：明确定义前端、后端、Agent、Generation Engine 之间的数据契约
> 关联文档：[PRD v0.1](./prd-v0.1.md) · [系统架构设计 v0.1](./architecture-v0.1.md) · [数据库与 ER 模型设计 v0.1](./database-v0.1.md) · [后端 API 与 Service 架构 v0.1](./backend-architecture-v0.1.md) · [AI Director Agent 详细设计 v0.1](./agent-director-v0.1.md) · [前端 UX / 信息架构设计 v0.1](./frontend-ux-v0.1.md)

---

# 1. 设计目标

这份文档负责解决一个核心问题：

> **前端到底如何稳定地驱动后端，并实时感知 Agent 和生成任务的状态变化。**

系统存在四类主要参与方：

```text
Frontend Studio

Backend Application API

AI Director Runtime

Production Runtime
```

它们之间不能依靠：

```text
"大家约定一下大概这么传"
```

而必须建立明确：

```text
REST Contract

Event Contract

DTO Contract

Error Contract

State Contract
```

---

# 2. 总体通信模型

建议采用：

```text
REST
+
WebSocket
```

其中：

```text
REST
=
Command + Query
```

用于：

- Project CRUD
- Scene CRUD
- Shot CRUD
- Asset 查询
- 发起 Agent Run
- 创建 Generation
- Approve Agent
- Cancel Task

WebSocket：

```text
Event Stream
```

用于：

- Agent 状态
- Generation 进度
- Workflow 进度
- Shot 更新
- Asset 创建
- Provider 状态
- Error 通知

---

# 3. 核心通信原则

## 原则一

Frontend 不直接访问：

```text
Database

ComfyUI

LLM Provider
```

---

## 原则二

所有用户操作先经过：

```text
Application API
```

---

## 原则三

所有后台异步变化通过：

```text
Event Stream
```

通知前端。

---

## 原则四

REST 返回：

```text
Current State
```

Event 返回：

```text
State Change
```

---

# 4. API Base URL

建议：

```text
/api/v1
```

例如：

```text
/api/v1/projects

/api/v1/shots/{id}
```

以后升级：

```text
/api/v2
```

不会破坏旧客户端。

---

# 5. REST Response 基础格式

推荐普通资源 API 直接返回 DTO。

例如：

```json
{
  "id": "shot_001",
  "shot_number": 1,
  "status": "image_ready"
}
```

不要所有接口都套：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

除非未来需要兼容多语言网关。

---

# 6. Error Response

统一采用：

```json
{
  "error": {
    "code": "SHOT_NOT_FOUND",
    "message": "Shot does not exist.",
    "details": {},
    "request_id": "req_xxx"
  }
}
```

覆盖范围（P1-E4-T01）：所有失败路径使用同一 Envelope —— 领域错误
（404/409/422 StudioError）、请求校验失败（422）、未知路由（404）、
方法不允许（405）、未捕获异常（500）。Envelope 必须包含 request_id。

request_id 规则（P1-E4-T01）：

- 客户端可传 `X-Request-ID` 请求头；后端缺失时自动生成。
- 响应头 `X-Request-ID` 始终回传同一值（成功与失败一致）。
- `request_id` 出现在所有错误 Envelope 中；前端应展示并支持复制，
  便于按日志关联排查。
- 500 响应不包含堆栈、绝对路径、API key 或原始 Provider 响应；
  完整异常仅写入服务端日志。

---

# 7. Error Code 分类

建议：

```text
PROJECT_*

EPISODE_*

SCENE_*

SHOT_*

ASSET_*

AGENT_*

GENERATION_*

WORKFLOW_*

PROVIDER_*

COMFYUI_*

VALIDATION_*

SYSTEM_*

NOT_FOUND（未知路由）

METHOD_NOT_ALLOWED

BAD_REQUEST

INTERNAL_ERROR（未捕获异常 500）

TIMEOUT（前端本地超时）
```

---

# 8. HTTP Status 使用

建议：

```text
200 OK

201 Created

202 Accepted

204 No Content

400 Bad Request

404 Not Found

409 Conflict

422 Validation Error

429 Too Many Requests

500 Internal Error

502 Provider Error

503 Provider Unavailable
```

长任务创建应优先使用：

```text
202 Accepted
```

---

# 9. Project API

## 创建 Project

```http
POST /api/v1/projects
```

Request：

```json
{
  "name": "最后一种打法",
  "description": "篮球题材漫剧",
  "aspect_ratio": "9:16",
  "fps": 24
}
```

Response：

```json
{
  "id": "project_001",
  "name": "最后一种打法",
  "status": "draft",
  "aspect_ratio": "9:16",
  "fps": 24,
  "cover_url": null,
  "created_at": "..."
}
```

---

# 10. Project 列表

```http
GET /api/v1/projects
```

支持：

```text
?status=active

?limit=50

?cursor=...
```

---

# 11. 获取 Project

```http
GET /api/v1/projects/{project_id}
```

---

# 12. 更新 Project

```http
PATCH /api/v1/projects/{project_id}
```

乐观并发（P1 已落地）：提交 `{revision, patch}`，revision 为读取时返回的当前版本号（缺失 → 422）；
patch 只发送修改字段：

```json
{
  "revision": 3,
  "patch": { "name": "新的项目名" }
}
```

数据库级条件更新（`WHERE id = ? AND revision = ?`）失败 → **409 Conflict**（payload 携带
expected/current revision），与 Shot 的 P1-E1-T02 语义一致。

---

# 12.1 上传 / 读取 Project 封面

```http
POST /api/v1/projects/{project_id}/cover
```

multipart/form-data，字段 `file`（.png / .jpg / .jpeg / .webp / .gif，≤10 MB）。
覆盖式存储：DB 只存相对路径（`cover<ext>`），文件落在项目目录
`data/projects/{project_id}/cover.<ext>`。成功返回 ProjectRead（`cover_url` 更新）。

```http
GET /api/v1/projects/{project_id}/cover
```

返回封面图片文件；未上传时 404。

# 12.2 删除 Project（软删除项目树）

```http
DELETE /api/v1/projects/{project_id}
```

软删除（`deleted_at`，database-v0.1 §41）并级联其 Episode / Scene / Shot / Character；
删除后列表与各子资源不可见。返回：

```json
{ "id": "project_001", "deleted": true }
```

---

# 13. Episode API

创建：

```http
POST /api/v1/projects/{project_id}/episodes
```

Request：

```json
{
  "title": "第一集",
  "source_text": "..."
}
```

更新（乐观并发，同 §12 语义：`{revision, patch}`，冲突 409）：

```http
PATCH /api/v1/episodes/{episode_id}
```

```json
{
  "revision": 2,
  "patch": { "title": "第一集（修订）" }
}
```

---

# 14. Episode Analyze

```http
POST /api/v1/episodes/{episode_id}/analyze
```

该操作可能调用 LLM。

推荐返回：

```http
202 Accepted
```

幂等与替换语义（P1-E1-T01）：

- 同一原文（analysis key = 实际送入 LLM 的原文截断文本的 hash）重复提交为幂等 no-op：
  返回已落库场景，不重复创建、不再次调用 LLM。
- 原文变化后再次提交执行 replace：软删除该剧集旧的 AI 场景及其镜头后重建；
  手动创建的场景（无 analysis_key）始终保留。
- 任一场景写入失败：整批回滚，不留下部分场景（all-or-nothing）。

Response：

```json
{
  "operation_id": "op_001",
  "status": "queued"
}
```

## 14.1 Analysis Snapshot（P2-E1-T01，preview → confirm 的不可变快照）

Preview 落库不可变快照；Confirm 只提交快照 id，写入的**正是用户预览看到的计划**
（零二次 LLM 调用——真实模型非确定性不再影响确认语义）。

```http
POST /api/v1/episodes/{episode_id}/analyze/preview
```

Response（原为裸 ScenePlan[]，现为信封）：

```json
{
  "snapshot_id": "b630637c-2138-459f-8591-a306a095d4b4",
  "episode_id": "...",
  "source_hash": "9f86d081884c7d65",
  "plans": [ { "scene_number": 1, "title": "...", "location": "...", "time": "...", "description": "...", "mood": "..." } ],
  "model": "deepseek-chat",
  "status": "pending"
}
```

```http
GET /api/v1/episodes/{episode_id}/analysis-snapshots/latest
```

返回该剧集最近一条快照（任意状态；从未预览过 → `null`）。字段：`id/status/plans/
episode_revision/source_hash/model/prompt_version/schema_version/created_scene_ids/created_at`。
前端刷新后用它水合 pending 预览（AC：刷新后可读取 preview 状态）。

Confirm（`POST /episodes/{id}/analyze` 请求体新增可选字段）：

```json
{ "snapshot_id": "b630637c-..." }
```

- **带 snapshot_id**：operation 内写入快照计划，零 LLM 调用。幂等（已确认的快照重放
  `created_scene_ids`，不重复创建）；快照过期（预览后原文或 episode revision 变化）
  → operation failed，`error` 提示重新预览，快照状态置 `expired`。
- **不带 snapshot_id**：遗留路径（analyze 自行调用 LLM），语义同上节，向后兼容。
- 快照跨剧集提交 / 不存在 → operation failed（422 语义在异步任务内呈现）。
- Provenance：快照记录 `model` / `prompt_version` / `schema_version` / `source_hash`。

---

# 15. Analysis Result

查询：

```http
GET /api/v1/operations/{operation_id}
```

Response：

```json
{
  "id": "op_001",
  "type": "episode_analysis",
  "status": "completed",
  "result": {
    "scene_plans": [],
    "created_scene_ids": []
  }
}
```

---

# 15.1 Pipeline API（C2 一键成片，2026-08 落地）

Episode 级流水线：`analyze(预览) → 人工确认 → shots → images → 排片 → 渲染`。长 LLM 阶段走 Operation（202 + operation_id）；`finalize` 同步（本地快操作）。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/episodes/{episode_id}/pipeline/run` | 202：分析预览 → `waiting_confirm`（result 含 pipeline + plans + snapshot_id） |
| POST | `/episodes/{episode_id}/pipeline/{pipeline_id}/confirm` | 202：确认快照 → scenes → 逐 scene 分镜 → 入队缺图 shot 的 image generation（跳过已有图）→ `running/images`（result 含 pending_shot_ids） |
| POST | `/episodes/{episode_id}/pipeline/{pipeline_id}/finalize` | 同步：建/排 timeline（sequence-from-shots）→ 入队 render → `completed` |
| POST | `/episodes/{episode_id}/pipeline/{pipeline_id}/resume` | 202：从第一个未完成阶段继续（断点续跑） |
| GET | `/episodes/{episode_id}/pipeline/latest` | 最新 pipeline 状态（无则 null） |

Pipeline 状态：`running / waiting_confirm / completed / failed`；`stages` 每阶段 `done|pending`（`analyze/shots/images/timeline/render`）。落库为真相——崩溃后 `resume` 从断点继续（confirm_snapshot 幂等可重放）。

Read（PipelineRead）：

```json
{
  "id": "p_001", "episode_id": "ep_01", "project_id": "p_01",
  "status": "waiting_confirm", "current_stage": null,
  "stages": { "analyze": "done", "shots": "pending", "images": "pending", "timeline": "pending", "render": "pending" },
  "snapshot_id": "snap_01", "error_message": null,
  "created_at": "...", "updated_at": "..."
}
```

事件：`pipeline.updated`（payload: episode_id/status/current_stage/stages）。

---

# 16. Scene API

列表：

```http
GET /api/v1/episodes/{episode_id}/scenes
```

创建：

```http
POST /api/v1/episodes/{episode_id}/scenes
```

更新：

```http
PATCH /api/v1/scenes/{scene_id}
```

乐观并发（P1 已落地）：`{revision, patch}`（缺失 revision → 422，冲突 → 409），同 §12。

删除：

```http
DELETE /api/v1/scenes/{scene_id}
```

---

# 17. Scene DTO

```json
{
  "id": "scene_003",
  "episode_id": "episode_001",
  "scene_number": 3,
  "name": "体育馆",
  "location_id": "学校体育馆",
  "time_of_day": "night",
  "mood": "tense",
  "shot_count": 8,
  "status": "active"
}
```

---

# 18. Generate Shots

```http
POST /api/v1/scenes/{scene_id}/generate-shots
```

Request：

```json
{
  "mode": "ai",
  "target_count": 8
}
```

Response：

```json
{
  "operation_id": "op_generate_shots_001",
  "status": "queued"
}
```

幂等与替换语义（P1-E1-T01）：

- 同一场景上下文（storyboard key = 场景字段 + 剧集原文摘录的 hash）重复提交为
  幂等 no-op：返回已落库镜头，不重复创建、不再次调用 LLM。
- 场景上下文变化后再次提交执行 replace：软删除该场景旧的 AI 镜头后重建；
  手动创建的镜头（无 analysis_key）始终保留。
- 任一镜头写入失败：整批回滚，不留下部分镜头（all-or-nothing）。

---

# 19. Shot API

乐观并发（P1-E1-T02）：`PATCH /api/v1/shots/{shot_id}` 的 revision 校验在数据库层
执行（条件更新）——两个基于同一旧 revision 的并发写入只有一个成功，另一个 409，
不存在先读后写丢失更新。Character 更新（§88）同理。

重排（P1-E1-T02）：`PATCH /api/v1/scenes/{scene_id}/shots/reorder` 必须提交该场景
完整且无重复的镜头 ID 集合；部分/重复/跨场景集合返回 422，数据保持不变。

批量操作（自主迭代 02，additive）：

```http
POST /api/v1/scenes/{scene_id}/shots/batch-update   # {shot_ids, patch} → ShotBatchResult
POST /api/v1/scenes/{scene_id}/shots/batch-delete   # {shot_ids}          → ShotBatchResult
```

- **批量覆盖语义**：batch-update 不携带 per-shot revision——批量意图是「把所选
  镜头改成一致状态」，服务端取每个镜头当前 revision 应用（逐镜头走 update_shot，
  revision+1 / dirty_state / PromptVersion / `shot.updated` 事件 / continuity 重算
  与单镜头编辑完全一致）。
- **逐项结果**：返回 `{scene_id, requested, succeeded, failed, results:[{shot_id,
  status: updated|deleted|failed, error_code?, message?}]}`——部分失败仍 200
  （对齐 ChangeSet undo 逐项结果模式）；重复 id / 空 patch → 422，场景不存在 →
  404；跨场景或未知 id 计入该项 failed。
- batch-delete 逐镜头软删除并发 `shot.deleted` 事件。

Scene 乐观并发：本阶段**不纳入**（决策见 roadmap P1-E1-T02 Design Decision）；
Scene 编辑保持无条件更新，Phase 2 随 ChangeSet/Undo 一并引入。

列表：

```http
GET /api/v1/scenes/{scene_id}/shots
```

获取：

```http
GET /api/v1/shots/{shot_id}
```

创建：

```http
POST /api/v1/scenes/{scene_id}/shots
```

修改：

```http
PATCH /api/v1/shots/{shot_id}
```

---

# 20. Shot Response

建议：

```json
{
  "id": "shot_005",
  "scene_id": "scene_003",

  "shot_number": 5,
  "shot_order": 5,

  "shot_type": "close_up",
  "camera_angle": "low_angle",
  "camera_movement": "static",

  "duration": 3.2,

  "action": "主角急停",
  "emotion": "tense",

  "image_prompt": "...",
  "video_prompt": "...",

  "status": "image_ready",

  "dirty_state": "clean",

  "active_image_version": {
    "id": "media_v003",
    "asset_id": "asset_089",
    "thumbnail_url": "/api/v1/assets/asset_089/thumbnail"
  },

  "characters": [
    {
      "id": "character_001",
      "name": "沈亦"
    }
  ],

  "updated_at": "..."
}
```

---

# 20.1 设定文档 API（SourceDocument，2026-08 落地）

项目级源内容归档：人物设定 / 世界观 / 大纲 / 小说原稿等自由文本设定文档。Agent 分析按预算注入设定摘要（见 database §32.6）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/projects/{project_id}/documents?doc_type=` | 项目设定文档列表（可按 doc_type 过滤） |
| POST | `/projects/{project_id}/documents` | 新建设定文档（201） |
| GET | `/documents/{document_id}` | 单个设定文档 |
| PATCH | `/documents/{document_id}` | 更新（`{revision, patch}`，409 conflict，§21/§88） |
| DELETE | `/documents/{document_id}` | 软删除（§89） |

Create body：

```json
{
  "doc_type": "character_setting",
  "title": "人物设定·沈亦",
  "content": "……设定原文……",
  "character_id": "character_001",
  "location_id": null,
  "costume_id": null
}
```

Read（DocumentRead）：

```json
{
  "id": "document_001",
  "project_id": "project_001",
  "doc_type": "character_setting",
  "title": "人物设定·沈亦",
  "content": "……设定原文……",
  "character_id": "character_001",
  "location_id": null,
  "costume_id": null,
  "source_hash": "a1b2c3…",
  "status": "active",
  "revision": 1,
  "created_at": "...",
  "updated_at": "..."
}
```

---

# 21. Optimistic Concurrency

建议资源增加：

```text
revision
```

例如：

```json
{
  "id": "shot_005",
  "revision": 12
}
```

更新时：

```json
{
  "revision": 12,
  "patch": {
    "duration": 2.8
  }
}
```

如果服务器已经：

```text
revision = 13
```

则返回：

```http
409 Conflict
```

防止：

```text
AI Director
+
用户
```

同时编辑造成覆盖。

---

# 22. Shot Selection 不需要后端保存

当前选中：

```text
Shot 05
```

属于：

```text
Frontend UI State
```

通常不保存到数据库。

但是调用 Agent 时要附带。

---

# 23. AI Director Run API

```http
POST /api/v1/agent/director/runs
```

Request：

```json
{
  "project_id": "project_001",

  "message": "把这个镜头改成近景，然后重新生成。",

  "selection": {
    "workspace": "storyboard",

    "episode_id": "episode_001",

    "scene_id": "scene_003",

    "shot_ids": [
      "shot_005"
    ],

    "asset_ids": []
  }
}
```

---

# 24. Agent Run Response

立即返回：

```http
202 Accepted
```

```json
{
  "run_id": "agent_run_101",
  "status": "running",
  "created_at": "..."
}
```

不要让 HTTP Request 一直挂到 Agent 执行完成。

---

# 25. 查询 Agent Run

```http
GET /api/v1/agent/runs/{run_id}
```

Response：

```json
{
  "id": "agent_run_101",

  "project_id": "project_001",

  "status": "executing",

  "current_stage": "execute",

  "plan": {
    "objective": "修改 Shot 05 并重新生成",
    "steps": []
  },

  "approval": null,

  "change_set_id": null,

  "messages": [
    { "role": "user", "content": "把 Shot05 改成近景再重新生成" },
    { "role": "assistant", "content": "已修改 Shot05 并提交生成。" }
  ],

  "created_at": "...",
  "updated_at": "..."
}
```

> **messages（自主迭代 05 刷新恢复）**：会话消息转录 `[{role, content}]`，由已持久化的
> input（用户指令）+ result（assistant 摘要/澄清）+ status（waiting_human 审批提示 /
> failed 错误）**确定性计算**，零新增写入。前端刷新/重开后据此水合对话流。

## 25.1. 列出项目最近 Agent Run（自主迭代 05）

```http
GET /api/v1/agent/runs?project_id={id}&limit={1..50}
```

返回该项目最近 director 会话（created_at 倒序，默认 10 条），每条含 messages 转录。
前端在导演面板挂载时取 `limit=1` 水合「上一次会话」，实现刷新恢复。

---

# 26. Agent Run 状态

统一：

```text
created

understanding

loading_context

planning

waiting_approval

waiting_human

executing

reviewing

completed

failed

cancelled
```

Frontend 不自行推断。

完全依据服务器状态。

Ownership 与歧义（P1-E3-T01）：

- Run 只能访问声明 project 内、未删除、无歧义的实体；跨项目 Shot ID、
  已删除 Shot、伪造 selection 在工具执行前被拒绝。
- 目标歧义（如项目内多个"第 1 镜"且未选中场景）时 Run 以
  `result.clarification` 完成（tool_count=0），不静默选首个。
- `shot_number:N` 优先在 selection.scene_id 场景内解析。
- 工具执行层（ToolExecutor）对每个目标再做一次 ownership 校验，
  不信任 Planner 输出。

---

# 27. Agent Approval API

当（P7 + P2-E3-T02）：

```text
status = waiting_human（或等待审批时的 waiting_approval）
```

P2-E3-T02 风险分级后只有需要审批的工具会进入此状态：

- **R0**（get_shot / get_scene_shots / check_workflow / inspect_comfy）：只读，自动执行。
- **R1**（update_shot / update_scene）：可逆编辑，**自动执行**并记录 ChangeSet（可撤销），
  不再为每次近景修改打断用户。update_scene 修改场景环境（时段/光照/天气/氛围/描述），
  走 SceneService（触发 P8-T017 连续性重算 + 活跃资产 stale 标记），scene_id 由
  selection.scene_id 解析（自主迭代 07）。
- **R2**（generate_image）：昂贵操作，**审批前不创建任何 Generation**，
  产生 pending AgentProposal（含 risk_level/reason/estimated_tasks/
  estimated_cost/irreversible/expires_at），run 进入 WAITING_HUMAN 并发出
  `agent.approval.required`。
- **R3**（破坏性，MVP 暂无工具映射）：必须审批，分类器对未知工具一律按 R3 处理。

approve 语义：R2 proposal 的 approve 才创建 Generation（base_revision 冲突则 conflict，
不创建）；R1 审批版（如 continuity_fix）approve 经 ShotService 应用并记录 ChangeSet。

proposal 具有有效期（`expires_at`，默认 24h，`STUDIO_AGENT_PROPOSAL_TTL_HOURS`）：
过期后 approve/reject 返回 409（status=expired，终态、不可再决策），
全部过期后 waiting run 置为 failed（不永久悬挂）。读路径（GET run / proposals list /
resume）做懒过期扫描。

人工可通过两条路径决策：

- 恢复整个 run（继续 graph，如批准后运行后续 generate 步骤）：

```http
POST /api/v1/agent/runs/{run_id}/resume
```

- 或按 proposal 决策：

```http
POST /api/v1/agent/proposals/{proposal_id}/approve
POST /api/v1/agent/proposals/{proposal_id}/reject
```

---

# 27.1 ChangeSet / Undo API（P2-E3-T03）

每次 Agent mutation（update_shot 自动应用 / proposal approve 应用 /
worker 完成后的 active-version 切换）产生一条可读 ChangeSet：最小 before/after
patch + revision_before/after + run/tool/source。Undo 是**新的补偿变更**
（revision+1、产生新 ChangeSet、原记录仅翻 undone 标记），历史永不改写；
媒体版本只切换 active 指针、不删除。

```http
GET  /api/v1/agent/change-sets?project_id=&run_id=&entity_id=&undone=
POST /api/v1/agent/change-sets/{change_set_id}/undo      body {force?: bool}
POST /api/v1/agent/runs/{run_id}/change-sets/undo         body {force?: bool}
```

- 单条 undo：409 冲突（后续编辑覆盖了同字段）时 details 携带
  `fields: {field: {expected, current, before}}` 与 `recovery`（恢复路径=原值），
  `force=true` 强制恢复原值（仍走 ShotService、revision+1）。
- 批量 undo（按 run，逆序）：返回逐项结果
  `[{id, status: undone|conflict|skipped, reason?, compensating_change_set_id?}]`，
  绝不半静默。
- undo 幂等终态：对已撤销的 change set 再次 undo → 409。

---

# 28. Approval Request

Frontend 从 Event / Run API 获得：

```json
{
  "approval_id": "approval_001",

  "title": "重新生成整个场景",

  "description": "将重新生成 8 张图片。",

  "risk_level": "R2",

  "affected_entities": [
    "shot_012",
    "shot_013"
  ],

  "estimated_tasks": 8,

  "options": [
    {
      "id": "approve",
      "label": "确认"
    },
    {
      "id": "cancel",
      "label": "取消"
    }
  ]
}
```

P2-E3-T02：AgentProposalRead 现已携带同构字段（risk_level / reason /
estimated_tasks / estimated_cost / irreversible / expires_at），本地 provider
无价格时 estimated_cost 为 null（诚实显示「未知」，不伪造）。

---

# 29. Resume Request

P7 语义（向后兼容：无 body / 空 body = approve-all-pending）：

```json
{
  "decision": "approve",
  "proposal_ids": ["proposal_001"]
}
```

- `decision = "approve"`：批准（指定或全部）pending proposal，经 ShotService 应用
  （base_revision 一致 → applied；不一致 → conflict，不覆盖用户编辑），然后继续被
  中断的 graph（运行后续步骤，如 generate）。
- `decision = "reject"`：拒绝 proposal（不应用），继续 graph。

proposal_ids 省略时对 run 的所有 pending proposal 决策。

---

# 30. 修改计划后 Resume

未来支持：

```json
{
  "decision": "modify",
  "feedback": "不要删除 Shot 14，只调整时长。"
}
```

Graph 恢复后重新规划。

---

# 31. Agent Cancel

```http
POST /api/v1/agent/runs/{run_id}/cancel
```

注意：

取消 Agent Run：

```text
≠
```

取消已经提交的 Generation。

---

# 32. ChangeSet API

Agent 完成修改后（P2-E3-T03 已实现，端点挂在 agent 前缀下）：

```text
change_set_id
```

例如：

```http
GET /api/v1/agent/change-sets?run_id={run_id}
```

---

# 33. ChangeSet Response

```json
{
  "id": "changeset_101",

  "project_id": "project_001",

  "source": "agent",

  "run_id": "agent_run_101",

  "tool": "update_shot",

  "entity_type": "shot",

  "entity_id": "shot_005",

  "revision_before": 1,

  "revision_after": 2,

  "before": {
    "shot_type": "medium"
  },

  "after": {
    "shot_type": "close_up"
  },

  "undone": false,

  "created_at": "..."
}
```

---

# 34. Undo ChangeSet

```http
POST /api/v1/agent/change-sets/{id}/undo
```

Response（返回补偿 ChangeSet 本体）：

```json
{
  "undo_change_set_id": "changeset_102",
  "status": "completed"
}
```

同字段结构与 §33（source="undo"，tool 为 `undo:{原tool}`）。
批量撤销 `POST /api/v1/agent/runs/{run_id}/change-sets/undo` 返回逐项结果数组，
见 §27.1。

Undo 本身也形成新的 ChangeSet。

---

# 35. Generation API

创建图片：

```http
POST /api/v1/shots/{shot_id}/generations
```

Request：

```json
{
  "type": "image",
  "provider": "comfyui",
  "workflow_id": "wf_image_001",
  "parameters": {},
  "reference_asset_ids": null
}
```

> workflow_id **可选**（P4-T007）：省略时由 WorkflowResolver 按优先级链解析并写入
> `generation.workflow_id` —— **request override → project default → system default**
> （project default 取 `project_settings.default_image_workflow_id` / `default_video_workflow_id`，
> 按 `type` 选择；system default = `default_image_api`）。显式传入保持原有 422 前检；
> 未知的解析结果一律 422（绝不静默回退）。
>
> **reference_asset_ids（M1 参考图显式覆盖，P3 一致性预研 §5.1；自主迭代 03 扩展场景地点）**：
> `null`（缺省）= 自动解析：① 角色（ShotCharacter → 角色 MASTER CharacterVersion → 代表资产，
> 每角色一张）+ ② **场景地点**（Scene.location_id → Location MASTER LocationVersion → 代表资产，
> 一张，`role=location_reference`，排在角色之后）。非空数组 = **替代**全部自动解析（资产须存在
> 404 / 同项目 422 / 图片类型 422，顺序即注入槽位顺序，worker 侧截断至 3 张 = Z-Image Omni 上限，
> 角色优先、地点兜底）；空数组 = 显式不注入任何参考图。溯源写入 `generation_inputs`
> （角色 `role=character_reference` / 地点 `role=location_reference`，metadata 带
> asset_id/character_id|location_id/source），由 `GET /generations/{id}` 明细读回（§39）。
> provider 无 `reference_image` 能力（§47）时 worker 诚实降级为不注入（debug 日志），不报错。
>
> **逻辑参数 schema（P4-T005）**：每个 workflow 的占位符注入由声明式逻辑参数表驱动
> （`providers/comfyui/workflow_schema.py`，逻辑参数名 → `$PLACEHOLDER` token）：
>
> ```text
> prompt            str    必填（$PROMPT）
> negative_prompt   str    可选（$NEGATIVE_PROMPT，默认 ""）
> seed              int    可选（$SEED，0..2^31-1；缺省随机）
> width / height    int    可选（$WIDTH/$HEIGHT，64..4096，默认 512x912）
> reference_images  list[str] 可选（$REFERENCE_IMAGE，取首项；上传由 provider 负责）
> duration / resolution        视频预留字段（$DURATION/$RESOLUTION，MVP image 不实例化）
> ```
>
> template 校验：模板中出现的占位符必须都在 schema 内（未知 token → preflight 失败）；
> schema 必需占位符（`$PROMPT/$SEED/$WIDTH/$HEIGHT`）必须出现在模板。请求参数类型/范围错误
> （如 width/height 超出 64..4096、seed 非法）→ ValidationError 422。前端只见逻辑参数，
> 永不暴露 node_id（见 §112-113）。

---

# 36. Generation Response

```http
202 Accepted
```

```json
{
  "id": "gen_001",

  "shot_id": "shot_005",

  "type": "image",

  "provider": "comfyui",

  "status": "queued",

  "created_at": "..."
}
```

---

# 37. Generation 状态

统一：

```text
created

queued

running

waiting_provider

processing_output

completed

failed

cancelled

retrying
```

---

# 38. Generation 查询

```http
GET /api/v1/generations/{generation_id}
```

单条明细**独有** `references` 字段（参考图溯源，见 §39）；列表端点
（recent / per-shot）不填充该字段（`null`，避免 N+1）。

最近生成（底部队列历史）：

```http
GET /api/v1/generations/recent
```

返回 `Generation[]`（按 created_at 倒序，最多 20 条）。
静态路由 `/generations/recent` 必须先于 `/generations/{generation_id}`
注册，避免被参数路由吞掉（P1-E4-T01 路由冲突回归）。

镜头自动参考图预览（M1 前端闭环——生成前可见）：

```http
GET /api/v1/shots/{shot_id}/reference-images
```

返回 `ShotReference[]`（与 `POST .../generations` 缺省自动解析完全同源）：

```json
[
  {
    "character_id": "char_001",
    "character_name": "沈亦",
    "version_id": "cver_003",
    "asset_id": "asset_0102"
  }
]
```

无出场角色 / 角色无 MASTER 版本 → `[]`；镜头不存在 → 404。返回**全部**
解析结果（>3 张时前端提示「仅前 3 张会被注入」）；`asset_id` 直接用于
`/assets/{id}/thumbnail` 缩略图展示。

---

# 39. Generation Response

```json
{
  "id": "gen_001",

  "shot_id": "shot_005",

  "status": "running",

  "progress": 0.68,

  "provider": "comfyui",

  "model": "flux",

  "queue_position": 1,

  "started_at": "...",

  "output_asset_id": null,

  "error": null,

  "references": [
    {
      "character_id": "char_001",
      "character_name": "沈亦",
      "version_id": "cver_003",
      "asset_id": "asset_0102",
      "source": "auto"
    }
  ]
}
```

`references` 仅单条明细端点填充：生成时实际记录的参考图溯源
（`source`：`auto` = 角色 MASTER 自动解析 / `explicit` = 调用方显式指定；
无参考图 → `[]`；列表端点 → `null`）。

---

# 40. Generation Cancel

```http
POST /api/v1/generations/{id}/cancel
```

---

# 41. Generation Retry

```http
POST /api/v1/generations/{id}/retry
```

返回：

```json
{
  "generation_id": "gen_002",
  "retry_of": "gen_001"
}
```

推荐创建新的 Generation Record。

不要覆盖旧记录。

---

# 42. Batch Generation

```http
POST /api/v1/generations/batch
```

Request：

```json
{
  "shot_ids": [
    "shot_001",
    "shot_002",
    "shot_003"
  ],

  "type": "image",

  "provider": "comfyui"
}
```

Response：

```json
{
  "workflow_run_id": "workflow_run_001",

  "generation_ids": [
    "gen_101",
    "gen_102",
    "gen_103"
  ]
}
```

---

# 43. Workflow Run API

查询：

```http
GET /api/v1/workflow-runs/{id}
```

Response：

```json
{
  "id": "workflow_run_001",

  "type": "batch_image_generation",

  "status": "running",

  "progress": 0.33,

  "tasks": {
    "total": 12,
    "completed": 4,
    "failed": 0
  }
}
```

---

# 44. Asset API

列表：

```http
GET /api/v1/projects/{project_id}/assets
```

过滤：

```text
?type=image

?character_id=...

?shot_id=...
```

---

# 45. Asset DTO

```json
{
  "id": "asset_001",

  "type": "image",

  "name": "EP01_SC03_SH005_IMG_V003.png",

  "thumbnail_url": "/api/v1/assets/asset_001/thumbnail",

  "width": 1024,

  "height": 1792,

  "metadata": {},

  "created_at": "..."
}
```

---

# 46. Asset File

本地 Desktop 可以选择：

```text
Custom Asset Protocol
```

或者：

```http
GET /api/v1/assets/{id}/content
```

第一版推荐后者，方便前端统一加载。

---

# 47. Provider API

```http
GET /api/v1/providers
```

```json
[
  {
    "id": "comfyui_local",
    "name": "Local ComfyUI",
    "type": "image",
    "status": "active",
    "capabilities": {
      "image_generation": true,
      "reference_image": true
    },
    "base_url": "http://127.0.0.1:8188",
    "health": {
      "status": "available",
      "last_checked_at": "...",
      "latency_ms": 12
    }
  }
]
```

> P4-T003：每个 provider 附带 `health` 块（向后兼容——保留 id/name/type/status/
> capabilities/base_url 旧字段）。`health.status` ∈ available | unavailable | degraded；
> Mock 恒 available；ComfyUI 为最近一次探测缓存（未探测时为 unavailable）。
>
> P4-T002：`GET /providers` 已泛化为多类型（image / video / workflow / llm），每个
> 条目带完整 `capabilities`（新增字段，不破坏旧字段；前端按 capabilities 判定按钮，
> 见 §130）。新增条目 id 与 image 区分：`video_mock`（video，MVP 恒 `status:"unavailable"`）、
> `workflow_comfyui`、`llm_fake`、`llm_openai`。
>
> P4-T001：视频生成在 MVP 明确拒绝，见 §41 —— `POST /shots/{id}/generations` 传
> `type=video` 返回 422（code `VALIDATION_ERROR`，supported=["image"]），不会静默
> 排队后再到 provider 才失败；VideoProvider 协议/注册已存在但为 unavailable 占位。

---

# 47.1 LLM Runtime Config API

让设置页在运行时改 LLM 连接（无需改环境变量/重启）。P-LLM-Profiles 起连接层分为两半：

- **引导层**：环境变量（`STUDIO_LLM_MODE` / `STUDIO_LLM_BASE_URL` / `STUDIO_LLM_API_KEY` /
  `STUDIO_LLM_MODEL`）+ 可选 `{data_dir}/llm.json` 覆盖层 —— 仅用于首次播种「默认连接」。
  **api_key 安全策略：env（`STUDIO_LLM_API_KEY`）优先于任何磁盘明文**（llm.json /
  llm_profiles.json）。配置 env 后，磁盘残留明文永不生效；读取掩码（api_key_hint）
  反映的也是生效 key。
- **权威层**：`{data_dir}/llm_profiles.json`（§47.4 连接 Profile Registry）——
  多条命名连接 + 激活切换 + 任务绑定。本节两个端点读写**当前激活连接**。

更新任意连接/绑定后重置缓存 gateway，下次 AI 调用即用新配置。

```http
GET /api/v1/llm/config        → 激活连接生效配置（api_key 只回掩码）
PUT /api/v1/llm/config        → 局部更新激活连接（省略字段保持原值）
```

GET Response（api_key 永不明文回传，只给掩码提示；`profile_*`/`capabilities` 为增量字段）：

```json
{
  "mode": "fake",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "api_key_set": true,
  "api_key_hint": "••••1234",
  "profile_id": "prof_a1b2c3d4e5",
  "profile_name": "DeepSeek 云端",
  "capabilities": { "tools": true, "vision": false, "reasoning": false, "source": "heuristic" }
}
```

PUT Request（`mode` 限定 fake | openai；`api_key` 未改动时省略即保持）：

```json
{ "mode": "openai", "base_url": "https://api.deepseek.com", "model": "deepseek-chat" }
```

> 校验：`mode=openai` 必须同时提供非空 `base_url`，否则 422（`VALIDATION_ERROR`）。
> 更新成功即 `reset_gateway()`，`llm/factory.create_gateway()` 下次按新配置重建。

## 47.2 LLM 连接测试与模型列表

业界标配（对齐 LiteLLM / one-api 等高星网关的连接管理体验）：保存前连通性测试、
`GET {base_url}/models` 拉取模型列表填充下拉。探测走 httpx 直连 OpenAI 兼容端点。

```http
POST /api/v1/llm/test    → 连通性测试（body 可选：profile_id 指定连接 / 未保存的 base_url/api_key/model 覆盖）
GET /api/v1/llm/models   → 端点模型 id 列表（?profile_id= 指定连接；缺省用激活连接）
```

POST /llm/test Request（全部可选；`profile_id` 先切换基准连接（测试某条已存连接），
显式 base_url/api_key/model 覆盖再叠加 —— test-before-save。api_key 仅在用户输入新值时携带）：

```json
{ "profile_id": "prof_a1b2c3d4e5", "base_url": "https://api.deepseek.com", "api_key": "sk-...", "model": "deepseek-chat" }
```

POST /llm/test Response（**永不抛错**，对齐 `/providers/comfyui/test` 形态）：

```json
{
  "connected": true,
  "mode": "openai",
  "latency_ms": 380,
  "models_count": 2,
  "sample_models": ["deepseek-chat", "deepseek-reasoner"],
  "detail": "GET /models 探测通过"
}
```

- fake 模式（且无 base_url 覆盖参数）→ `connected=true, mode="fake"`。
- 探测链：`GET {base}/models`（鉴权/连通）→ 404/405/网络失败时降级最小
  `POST {base}/chat/completions`（`max_tokens=1`）；401/403 → `connected=false` 且
  error 提示鉴权失败。网络失败 `latency_ms=null`。

GET /llm/models Response：

```json
{ "models": ["deepseek-chat", "deepseek-reasoner"] }
```

- fake 模式 → `["fake-chat"]`；openai 拉取失败 → 503（`PROVIDER_UNAVAILABLE`），
  前端回退手动输入模型名。

---

# 47.3 LLM 本地服务检测（P-LocalModels）

探测本机常见 OpenAI 兼容服务（Ollama / LM Studio / vLLM / llama.cpp / Jan / KoboldCpp）
的默认端口：并发 `GET {base}/models`（每端点 1s 超时、`trust_env=False` 直连不走系统代理），
仅报告 200 的端点。设置页「AI 服务 → 检测本地服务」消费，一键把 base_url/模型名填入表单。

```http
POST /api/v1/llm/detect-local
```

Response（**永不抛错**，200 + servers 形态）：

```json
{
  "servers": [
    {
      "kind": "ollama",
      "label": "Ollama",
      "base_url": "http://127.0.0.1:11434/v1",
      "models_count": 2,
      "sample_models": ["qwen2.5:7b", "llama3:8b"]
    }
  ],
  "latency_ms": 45
}
```

- `servers=[]` 表示未发现运行中的本地服务（不是错误）。
- 探测目标是约定俗成的默认端口常量表（`_LOCAL_LLM_CANDIDATES`），非动态扫描进程。

---

# 47.4 LLM 连接 Profile Registry（P-LLM-Profiles）

模型无关的**多连接命名注册表**：Provider（fake/openai 端点）与 Model 分离存储，
任意多条连接共存、命名切换；三个 AI 任务（AI 导演 / 剧本分析 / 连续性检查）可分别
绑定到不同连接（例如本地模型跑导演意图解析、云端强模型跑剧本分析），未绑定的任务
跟随**激活连接**。首次读取时把 env + llm.json 生效配置播种成「默认连接」（不落盘），
此后 `llm_profiles.json` 是唯一事实源。api_key 只回掩码，永不明文回传。
**api_key 生效顺序：`STUDIO_LLM_API_KEY` env → profile 磁盘值**（env 优先，见 §47.1）。

```http
GET    /api/v1/llm/profiles                → 列表 + 激活 id + 任务绑定
POST   /api/v1/llm/profiles                → 新建连接
PATCH  /api/v1/llm/profiles/{id}           → 局部更新（省略字段保持原值）
DELETE /api/v1/llm/profiles/{id}           → 删除（激活连接禁删 → 422）
POST   /api/v1/llm/profiles/{id}/activate  → 切换激活连接
PUT    /api/v1/llm/task-bindings           → 任务 → 连接绑定
```

GET /llm/profiles Response：

```json
{
  "profiles": [
    {
      "id": "prof_a1b2c3d4e5",
      "name": "本地 Qwen",
      "mode": "openai",
      "base_url": "http://127.0.0.1:11434/v1",
      "model": "qwen3",
      "api_key_set": false,
      "api_key_hint": null,
      "created_at": "2026-08-30T10:00:00+00:00",
      "updated_at": "2026-08-30T10:00:00+00:00",
      "is_active": true,
      "bound_tasks": ["director"],
      "capabilities": { "tools": true, "vision": false, "reasoning": false, "source": "heuristic" }
    }
  ],
  "active_profile_id": "prof_a1b2c3d4e5",
  "task_bindings": {
    "director": { "profile_id": "prof_a1b2c3d4e5", "profile_name": "本地 Qwen" },
    "script": null,
    "continuity": null
  },
  "tasks": [
    { "id": "director", "label": "AI 导演" },
    { "id": "script", "label": "剧本分析 / 分镜" },
    { "id": "continuity", "label": "连续性检查" }
  ]
}
```

- **capabilities**（advisory，非硬门槛）：按模型名启发式给出 tools / vision /
  reasoning 标记（`source="heuristic"`）；profile 上显式声明 `capabilities` 时
  覆盖启发式（`source="override"`）。fake 连接三项全 false。
- POST / PATCH Request 字段：`name` / `mode`（fake|openai）/ `base_url` / `api_key`
  （空串=清除）/ `model` / `capabilities`（`{tools?, vision?, reasoning?}` 覆写）。
  `mode=openai` 无 `base_url` → 422。PATCH/DELETE 未知 id → 404（`ENTITY_NOT_FOUND`）。
- PUT /llm/task-bindings Request：`{ "bindings": { "director": "prof_…" | null } }`
  （null = 解绑跟随激活连接；未知任务/连接 → 422）。`default` 任务即激活连接，不可绑定。
- 任务 → 连接解析在 `llm/factory.create_gateway(task)` 内完成：绑定连接优先，否则激活
  连接；gateway 按「mode+base_url+api_key+model」四元组缓存共享。任何连接/绑定变更
  → `reset_gateway()`，下次 AI 调用即用新配置（无需重启）。gateway 不做静默降级
  （模型失败以 `PROVIDER_UNAVAILABLE` 上报）。

## 47.4.1 任务降级链（P-LLM-Fallback，不静默掩盖模型故障）

在任务绑定之上提供**显式配置**的有序降级链：主连接（绑定连接；未绑定任务用激活连接）
失败时按序尝试后备连接。四条硬约束（与「静默 fallback」的本质区别）：

1. **链是显式的**：只有 `task_fallbacks` 里配置过的连接才参与降级；已绑定任务的激活
   连接不隐式入链。默认空链 = 行为与纯 fail-fast 完全一致。
2. **降级必宣告**：每次真实降级 publish `llm.fallback.used` 事件（§70）+ WARNING 日志；
   主连接直接成功不发事件。
3. **结果可归因**：gateway 的 ChatResponse 标注 `served_by_profile(_name)`
   （主连接直接服务也标注，便于观测）。
4. **失败不吞**：全链耗尽抛 `PROVIDER_UNAVAILABLE`，details.attempted 携带每条候选的
   错误明细。流式仅在首个分片产出前降级，出流后中途失败原样上抛。

```http
PUT /api/v1/llm/task-fallbacks   → 任务 → 有序降级连接列表
```

PUT /llm/task-fallbacks Request（空列表 = 清除 = 回到 fail-fast；未知任务/连接 → 422；
列表去重保序；`default` 任务不参与降级配置）：

```json
{ "fallbacks": { "director": ["prof_local_qwen", "prof_deepseek"] } }
```

Response 与 `GET /llm/profiles` 同形（`task_fallbacks` 为
`{task: [{profile_id, profile_name}, …]}`）。删除连接时自动从所有降级链剥离。

---

# 48. Test ComfyUI

P1-E2-T01：连接成功时同时报告默认 workflow 的 preflight 状态（模板缺失 /
非法 JSON / 缺少 SaveImage 输出节点 / 缺少必需 placeholder 都会在 workflow.error
中返回，不需要 GPU 即可验证配置）。

```http
POST /api/v1/providers/comfyui/test
```

Request：

```json
{
  "base_url": "http://127.0.0.1:8188"
}
```

Response：

```json
{
  "connected": true,
  "latency_ms": 12,
  "health": {
    "status": "available",
    "last_checked_at": "...",
    "latency_ms": 12
  },
  "workflow": { "id": "default_image_api", "status": "ok", "output_node": "14" }
}
```

> P4-T003：该端点探测 ComfyUI 并同时刷新健康缓存，GET /providers 的 health 块随之更新。
> P-LocalModels：Request body 的 `base_url` 为可选覆盖 —— 传入时直接探测该未保存地址
> （不触碰缓存单例与已存配置），响应附带回显 `base_url`；省略时行为不变。

---

# 48.0 Agnes 连接测试

Agnes Cloud Image（真实云文生图，TASK-010）的连通性探测：用已配置的
`STUDIO_AGNES_API_KEY` 调 `GET {agnes_base_url}/models` 鉴权探测 —— **不消耗生图额度**。
Key 只存后端环境变量（不入库、不回传前端明文）。

```http
POST /api/v1/providers/agnes/test
```

Request（可选；允许对未保存的 base_url 先行探测，对齐 §47.2）：

```json
{ "base_url": "https://apihub.agnes-ai.com/v1" }
```

Response（**永不抛错**，200 + `connected` 形态）：

```json
{
  "connected": true,
  "key_set": true,
  "latency_ms": 420,
  "models_count": 6,
  "sample_models": ["agnes-2.0-flash", "agnes-image-2.1-flash"],
  "image_model_available": true
}
```

- 未配置 Key → `connected=false, key_set=false`，error 提示配置 `backend/.env`。
- 401/403/网络失败 → `connected=false, key_set=true` + error（含状态码或原因）。
- `image_model_available=true` 仅当模型列表包含 `agnes-image-2.1-flash`。

---

# 48.1 Workflow Catalog API（只读，P4-T004）

工作流模板以 API 格式 JSON 入库（workflows/*.json）。P4-T004 起，目录内容被幂等扫描
为只读注册表 workflow_templates + workflow_versions（SHA-256 哈希快照，见 database §24），
GET /workflows 返回的是已注册模板的目录（保持原有字段，兼容旧调用方）。
前端只读展示目录与预检元数据，不做编辑（YAGNI）。

```http
GET /api/v1/workflows
```

Response：

```json
[
  {
    "id": "default_image_api",
    "file": "default_image_api.json",
    "is_default": true,
    "workflow_type": "image",
    "template_id": "XXXX",
    "active_version_number": 1,
    "file_hash": "<sha256>",
    "output_node_class": "SaveImage",
    "required_placeholders": ["$PROMPT", "$SEED", "$WIDTH", "$HEIGHT"],
    "exists": true,
    "valid_json": true,
    "node_count": 7,
    "node_types": ["CLIPTextEncode", "KSampler", "SaveImage", "VAEDecode"],
    "placeholder_tokens": ["$HEIGHT", "$NEGATIVE_PROMPT", "$PROMPT", "$SEED", "$WIDTH"]
  }
]
```

字段：

- `id` / `file`：workflow_id 与模板文件名（WORKFLOW_CATALOG 约束）
- `is_default`：默认生成使用的模板
- `workflow_type`：image | video（按文件名/约定推断，默认 image）
- `template_id` / `active_version_number` / `file_hash`：P4-T004 注册表元数据
- `output_node_class`：preflight 要求恰好一个输出节点（SaveImage）
- `required_placeholders`：preflight 必需的占位符；缺失时生成前失败
- `node_types` / `placeholder_tokens`：模板结构清单（只读展示用）

版本快照（不可变哈希历史）：

```http
GET /api/v1/workflows/{workflow_id}/versions
```

```json
[
  {
    "id": "XXXX",
    "template_id": "XXXX",
    "workflow_id": "default_image_api",
    "version_number": 1,
    "file_hash": "<sha256>",
    "file_path": "default_image_api.json",
    "status": "active",
    "created_at": "..."
  }
]
```

未知 workflow_id → 422（VALIDATION_ERROR）；已注册但无版本 → 404。

---

# 48.2 ComfyUI 模型列表（P-LocalModels）

从 ComfyUI 服务端拉取可用 checkpoint 文件名（`GET /object_info/CheckpointLoaderSimple`
宽容解析）。设置页「图像服务 → ComfyUI 本地引擎」的消费端：列表填入生成模型
（checkpoint）选择建议。**永不抛错**（对齐 §47.2/§48.0 形态）。

```http
GET /api/v1/providers/comfyui/models?base_url={可选覆盖}
```

Response：

```json
{
  "connected": true,
  "base_url": "http://127.0.0.1:8188",
  "models": ["sd_xl_base_1.0.safetensors", "flux1-dev.safetensors"],
  "catalog": {
    "checkpoints": ["sd_xl_base_1.0.safetensors"],
    "unets": ["z_image_turbo_int8_convrot.safetensors"],
    "clips": ["qwen_3_4b_fp4_mixed.safetensors"],
    "vaes": ["ae.safetensors"]
  }
}
```

- `base_url` 查询参数省略时读运行时 image.json 的 `comfyui_url`（env 兜底）；
  传入时探测该未保存地址（probe-before-save）。
- `connected=false`（服务不可达）→ `models=[]`、`catalog={}`；`connected=true` 但响应
  形态异常 → 对应槽位 `[]`（旧版 ComfyUI 兼容）。
- **`catalog`（Sprint 05 · P2-1）**：按加载器架构分组（`checkpoints` ←
  CheckpointLoaderSimple / `unets` ← UNETLoader / `clips` ← CLIPLoader+DualCLIPLoader /
  `vaes` ← VAELoader），并行 `GET /object_info/{node}` 宽容解析。非 SD 架构（DiT unet
  如 Z-Image）此前在该端点不可见，现由 `unets` 暴露。`models` 字段保留为
  `checkpoints` 的向后兼容平铺。

---

# 48.2b Workflow live 诊断（P2-E4-T02 检查通道）

双通道架构的"理解/诊断层"：静态 preflight + 对当前连接的 ComfyUI 做逐节点
live 校验（缺节点 / 缺模型枚举越界 / 断链）。introspection 实现由
`STUDIO_COMFY_INTROSPECTION` 选择（`native` 直连 `/object_info` 或 `mcp`
经用户自装 comfy-mcp；MCP 失败自动回落 native）。**只读通道**——永不下发
queue/interrupt；生产执行通道（GenerationService → ImageProvider）不受影响。

```http
GET /api/v1/providers/comfyui/workflows
```

Response（自动发现的模板清单，文件名 stem 即 id）：

```json
{ "workflows": [ { "id": "default_image_api", "filename": "default_image_api.json", "is_default": true } ] }
```

```http
POST /api/v1/providers/comfyui/workflows/{workflow_id}/validate
```

Request（可选）：`{ "base_url": "http://127.0.0.1:8189" }`（probe-before-save 覆盖）。

Response（**永 200**——诊断降级不报错；未知 workflow_id 才 422）：

```json
{
  "workflow_id": "zimage_turbo_ref",
  "status": "invalid",
  "source": "native",
  "ok": false,
  "nodes": [
    { "node_id": "1", "class_type": "UNETLoader", "status": "missing_model",
      "detail": "Input unet_name: 'z_image_turbo_int8.safetensors' is not available on the server.",
      "missing_choices": ["z_image_turbo_int8.safetensors"] },
    { "node_id": "7", "class_type": "WanVideoSampler", "status": "missing_node", "detail": "...", "missing_choices": [] }
  ],
  "missing_nodes": ["WanVideoSampler"],
  "missing_models": ["z_image_turbo_int8.safetensors (UNETLoader.unet_name)"],
  "broken_links": [],
  "static_error": null,
  "error": null
}
```

- `status`：`ok`（静态+live 全过）/ `invalid`（发现确定性问题，可安全 fail-fast）/
  `unreachable`（无法完成 live 校验，**不阻断排队**，worker 运行时诚实失败）/
  `static_error`（模板静态缺陷：JSON 损坏 / 缺 SaveImage / 占位符契约违约）。
- **排队前 fail-fast**：image 生成且 provider=comfyui 时，`invalid` 诊断 →
  `POST /shots/{id}/generations` 直接 422（details 含 missing_nodes/missing_models/
  broken_links）；unreachable → 照常 202。
- `$PROMPT` 等 schema 占位符（含 LoadImage 参考图槽位）不参与 live 校验（build 时注入）。
- object_info 快照按 base_url 做 60s TTL 缓存（`WorkflowDiagnosticsService.invalidate()` 清空）。
- Agent 侧：R0 工具 `check_workflow`（workflow_id 可省略=默认模板）与
  `inspect_comfy`（可达性/节点数/模板清单/检查通道模式）经
  `WorkflowDiagnosticsService` 走同一检查通道（红线：Agent 不直调 ComfyUI/MCP）。
- **许可说明**：mcp 模式依赖用户自装的官方 comfy-mcp（AGPL-3.0-or-later OR
  Comfy commercial license 双许可，beta）。Studio 不打包不分发该组件；
  mcp 缺失/能力不足时自动回落 native，无硬依赖。

---

# 48.3 本地模型扫描（P-LocalModels）

两种互斥形态：`path` 给定 → 递归扫描该目录收集模型文件（限深 4 层、上限 500 个、
按父目录名分类 checkpoint/lora/vae/controlnet/…，体积降序）；`path` 省略 → 自动检索
本机常见默认位置（Ollama 模型目录含 `OLLAMA_MODELS` env、LM Studio、ComfyUI Desktop、
HuggingFace 缓存）。只读，不移动文件。

```http
POST /api/v1/providers/models/scan
```

Request：

```json
{ "path": "D:\\Models" }
```

Response（path 形态）：

```json
{
  "mode": "path",
  "path": "D:/Models",
  "total": 2,
  "truncated": false,
  "files": [
    { "name": "flux1-dev.safetensors", "path": "D:/Models/checkpoints/flux1-dev.safetensors",
      "dir": "checkpoints", "kind": "checkpoint", "size_bytes": 23800000000 }
  ]
}
```

Response（autodetect 形态，`locations=[]` 表示什么都没找到，不是错误）：

```json
{
  "mode": "autodetect",
  "locations": [
    { "kind": "ollama", "label": "Ollama 模型", "path": "C:/Users/me/.ollama/models",
      "model_count": 2, "sample_models": ["qwen2.5:7b", "llama3:8b"] }
  ]
}
```

- `path` 不存在/不是目录 → 422（VALIDATION_ERROR）——这是客户端错误而非连通性探测。
- 认得的扩展名：`.safetensors .ckpt .pt .pth .gguf .onnx`。

---

# 48.4 本地模型导入（P-LocalModels）

把一个本地模型文件放入 ComfyUI models 目录（按 kind 映射子目录：
checkpoint→checkpoints、lora→loras、vae→vae、controlnet→controlnet、
diffusion→diffusion_models、text_encoder→text_encoders、upscale→upscale_models）。
同盘优先 `os.link` 硬链接（GB 级文件瞬时完成），失败回落 `shutil.copy2` 复制；
源文件永不删除。GB 级大文件属长任务 → **202 + Operation**（契约 §81-82，
`GET /operations/{id}` 轮询 queued/running/completed/failed；Operation 为内存态，
进程重启丢失进行中的导入）。

```http
POST /api/v1/providers/models/import
```

Request：

```json
{
  "source": "D:/Models/checkpoints/flux1-dev.safetensors",
  "kind": "checkpoint",
  "models_root": "D:/ComfyUI_windows_portable/ComfyUI/models",
  "overwrite": false
}
```

- `models_root` 省略时读运行时 image.json 的 `comfyui_models_root`（未配置 → 422）。
- 校验（source 存在/kind 合法/根目录存在/目标同名冲突）在返回 202 **之前**同步完成，
  坏请求直接 422 / 409（CONFLICT），不产生 Operation。

Response（202）：

```json
{ "operation_id": "op_xxxxxxxx", "status": "queued" }
```

Operation completed 后 `result`：

```json
{
  "source": "D:/Models/checkpoints/flux1-dev.safetensors",
  "target": "D:/ComfyUI/models/checkpoints/flux1-dev.safetensors",
  "strategy": "hardlink",
  "size_bytes": 23800000000
}
```

---

# 48.5 图像运行时配置（补录，P-LocalModels 扩展）

`GET/PUT /api/v1/image/config` 与 `POST /api/v1/image/test`（此前实现未入册，随本次
扩展一并补录）。镜像 §47.1：`{data_dir}/image.json` 覆盖层，**api_key 生效顺序：
`STUDIO_AGNES_API_KEY` env → image.json 明文**（env 优先；PUT 不会把 env key
固化回磁盘，显式传空 api_key 可清除覆盖回落 env），保存后重置
Provider 缓存即时生效。

```http
GET  /api/v1/image/config
PUT  /api/v1/image/config
POST /api/v1/image/test
```

GET Response：

```json
{
  "provider": "comfyui",
  "agnes_base_url": "https://api.agnes-ai.cn/v1",
  "api_key_set": false,
  "api_key_hint": null,
  "video_provider": "mock",
  "video_model": "agnes-video-2.5-flash",
  "comfyui_url": "http://127.0.0.1:8188",
  "checkpoint": "sd_xl_base_1.0.safetensors",
  "comfyui_models_root": null
}
```

PUT Request（全字段可选，局部更新）：

```json
{
  "provider": "comfyui",
  "comfyui_url": "http://127.0.0.1:8188",
  "checkpoint": "flux1-dev.safetensors",
  "comfyui_models_root": "D:/ComfyUI_windows_portable/ComfyUI/models"
}
```

- `checkpoint`：生成时注入默认工作流的 `$CHECKPOINT` 占位符（§48.1 预检声明见
  workflow_schema；业务层 Service 永不感知具体模型名 —— 红线 #5）。
- `comfyui_url`：ComfyUI 服务地址（env `STUDIO_COMFYUI_URL` 兜底），修改后
  ComfyUI Provider 单例随 `reset_image_providers` 重建。
- `comfyui_models_root`：§48.4 导入的默认目标根目录（可被请求参数覆盖）。
- 覆盖语义：`video_provider/video_model/comfyui_url/checkpoint/comfyui_models_root`
  省略 = 不动；显式 `""` = 清除覆盖回落 env/默认值。
- `POST /image/test`：agnes → GET {base}/models 鉴权探测；mock → 恒 connected；
  comfyui → 指引改用 §48 端点（`connected=null`）。

### 48.5.1 视频模型目录（GET /api/v1/image/video-models）

「视频服务」模型下拉的唯一事实源（前端不再硬编码模型清单）。返回静态目录
（`verified` = 后端是否实测出片）+ best-effort 实测可用性：已配置 Agnes Key 时
探测 `GET {base}/models`（不消耗额度），把每个模型的 `available` 标为
`true/false`；未配置 key 或探测失败永不报错（`available=null` + `probe_error`）。

```json
{
  "models": [
    { "id": "agnes-video-2.5-flash", "label": "快 · 当前免费", "verified": true, "available": true },
    { "id": "agnes-video-v2.0", "label": "当前免费 · 返回结构已适配", "verified": false, "available": false },
    { "id": "agnes-video-2.5", "label": null, "verified": false, "available": null }
  ],
  "probed": true,
  "probe_error": null
}
```

- `PUT /image/config` 的 `video_model` 只接受目录内 `id`，目录外值 →
  `422 VALIDATION_ERROR`（`details.allowed` 列出合法 id）。
- 目录新增/下线模型只改后端 `VIDEO_MODELS`（image_settings_service），前端零改动。

---

# 48.6 本地目录浏览（文件浏览器，设置页路径选择，P-LocalModels）

设置页「扫描模型目录路径 / ComfyUI 模型目录」输入框旁「浏览」按钮的后端。只读列目录：
`path` 省略/为空 → 列根（Windows 盘符含挂载点 / POSIX `/`）；给定 → 列该目录下的子目录
与文件（目录在前，组内按名称排序，文件带 `size_bytes`；单次上限 500 条，超出
`truncated=true`）。不读文件内容、不写任何路径；`$RECYCLE.BIN` 等无导航意义的系统目录
跳过，隐藏目录照常列出（HuggingFace 缓存等合法目标以 `.` 开头）。

```http
GET /api/v1/providers/fs/list?path=D:\Models
```

Response（根视图，`path` 省略或为空）：

```json
{
  "path": "",
  "parent": null,
  "entries": [
    { "name": "C:\\", "path": "C:\\", "type": "dir" },
    { "name": "D:\\", "path": "D:\\", "type": "dir" }
  ],
  "truncated": false
}
```

Response（目录视图）：

```json
{
  "path": "D:/Models",
  "parent": "D:/",
  "entries": [
    { "name": "checkpoints", "path": "D:/Models/checkpoints", "type": "dir" },
    { "name": "readme.txt", "path": "D:/Models/readme.txt", "type": "file", "size_bytes": 12 }
  ],
  "truncated": false
}
```

- `path` 不存在/不是目录 → `422 VALIDATION_ERROR`（同 §48.3 约定：客户端错误）。
- 目录无权限/读取失败 → `200` + `entries: []` + `error` 注记（浏览永不 500，UI 内联呈现）。
- `parent: null` 表示已在根（盘符或 `/`），UI 据此禁用「上一级」。
- Web 页面拿不到原生选目录对话框的绝对路径，故由本地 Studio Service 列目录——浏览器
  与 Tauri 壳共用同一弹窗。

---

# 49. WebSocket 连接

建议：

```text
ws://localhost:{port}/api/v1/events
```

## 49.1 握手与控制帧（P1-E4-T02，2026-08）

连接成功后服务端立即下发握手帧（**sequence=0**）：

```json
{ "event_type": "system.connected", "sequence": 0, "payload": {} }
```

连接后可发送**控制帧**（JSON 文本）：

```json
{ "type": "subscribe", "project_id": "proj_001" }
{ "type": "unsubscribe" }
```

- `subscribe`：此后该连接只接收 `project_id` 匹配的事件（按项目过滤）。
- `unsubscribe`：清空过滤，恢复接收全部事件。
- 畸形 / 非 JSON / 非对象 / 未知 `type` / 缺 `project_id` 的控制帧一律记录后安全忽略（§137），不中断连接。

## 49.2 每连接有界队列与每连接 sequence（P1-E4-T02）

- **有界队列 + drop-oldest**：每个连接有独立发送缓冲（上限 256 条）。客户端消费不及（慢 / 半死连接）时丢弃**最旧**未发送事件并继续接纳最新——该客户端只影响自己，**不阻塞其他客户端、内存有上限**；每次丢弃以 `ws client queue overflow` 日志告警，客户端观察到 sequence 空洞后必须 reconcile。
- **每连接独立 sequence**：sequence 从 1 起逐事件递增，只统计该连接**实际收到**的投递。因此**出现空洞（incoming > last + 1）必然意味着真实丢事件**（溢出 / 服务重启 / 断线），客户端必须走 reconcile（§52 / §77）；绝不使用全局序号——那会给被过滤投递制造假空洞。

---


# 50. 本地会话与 WS Origin（P1-E5-T02）

**本地控制面认证**：Tauri 壳每次启动生成高熵会话 token（`STUDIO_SESSION_TOKEN`）注入后端，并经由 `get_session_token` 命令交给前端。**设置了 token 后**：

- REST：请求头 `X-Session-Token: <token>`；缺失/错误 → 401 统一 Envelope。
- 媒体标签（`<img>`/`<video>`/`<audio>`/`<a download>`）无法携带自定义请求头，允许以 `?token=` query 参数提交同一 token（与 WS 同模式，2026-08-31 前端审计 P0 修复引入）；Header 优先。
- WS：连接 URL `?token=<token>`（浏览器 WebSocket 无法携带自定义 header，故走 query）；缺失/错误 → 连接被拒绝（close 1008）。
- 豁免：`/api/v1/health`、`/api/v1/system/info`——壳需在持有 token 前握手识别后端（§140 身份 marker）。
- **未设置 token**（开发浏览器 / 开发壳直连后端）= 本地控制面开放（auth 关闭），保持开发便捷。

token 绝不写日志、不入 URL 历史（REST 走 header）、不落项目数据库、不入源码配置。

**WS Origin**：`/api/v1/events` 在 accept 前校验 `Origin`——非白名单 Origin（`settings.cors_origins`）直接拒绝（close 1008）；无 Origin（非浏览器客户端）放行。

未来云端改：

```text
Bearer / Cookie
```

---

# 51. Event Envelope

所有 Event 使用统一包装：

```json
{
  "event_id": "evt_001",

  "event_type": "generation.progress",

  "event_version": 1,

  "project_id": "project_001",

  "entity_type": "generation",

  "entity_id": "gen_001",

  "timestamp": "...",

  "sequence": 1045,

  "payload": {}
}
```

---

# 52. 为什么需要 sequence

用于处理：

```text
WebSocket 重连

事件乱序

重复事件
```

Frontend 保存：

```text
last_sequence
```

如果：

```text
sequence <= last_sequence
```

可以忽略重复事件。

**P1-E4-T02 判定（2026-08）**：前端按每连接 sequence 三分类——`dupe`（`incoming <= last`，丢弃）、`route`（`incoming == last + 1`，正常路由）、`gap`（`incoming > last + 1`，**真实丢失**）。`gap` 出现在断线 / 队列溢出（drop-oldest）/ 服务重启后，前端**必须**触发 reconcile：invalidated 全部活跃查询并从 REST/bootstrap 重建事实状态，而非静默继续（WS 只是提示通道，不是事实来源）。

---

# 53. Event Version

必须增加：

```text
event_version
```

因为以后：

```text
generation.completed v1
```

可能升级字段。

避免客户端被破坏。

---

# 54. Event 分类

建议：

```text
project.*

episode.*

scene.*

shot.*

asset.*

agent.*

generation.*

workflow.*

provider.*

system.*
```

---

# 55. Project Events

```text
project.created

project.updated

project.deleted
```

---

# 56. Scene Events

```text
scene.created

scene.updated

scene.deleted

scene.reordered
```

---

# 57. Shot Events

```text
shot.created

shot.updated

shot.deleted

shot.reordered

shot.version.created   （兼容保留：语义同 Asset 版本创建，payload 指向 asset_id）

shot.active_version.changed   （ADR-001：payload = {media_type, asset_id, version_number}，active 指针指向 Asset）

shot.dirty_state.changed

prompt.version.created / prompt.active_version.changed   （预留：Alpha P3 尚未发布 prompt 事件，前端以 REST 为准）
```

---

# 58. shot.updated Event

```json
{
  "event_type": "shot.updated",

  "entity_id": "shot_005",

  "payload": {
    "revision": 13,

    "changed_fields": [
      "shot_type",
      "image_prompt"
    ],

    "source": "agent",

    "run_id": "agent_run_101",

    "change_set_id": "changeset_101"
  }
}
```

`source`：`user`（API 直接编辑，默认）或 `agent`（Director 工具修改）；
`run_id` 在 agent 修改时关联来源 Run（P1-E3-T02）。`changed_fields`
只包含实际发生变化的字段。

Frontend收到后：

```text
invalidate shot_005

invalidate scene shots
```

---

# 59. Agent Events

```text
agent.run.started

agent.intent.resolved

agent.context.loaded

agent.plan.created

agent.approval.required

agent.resumed

agent.run.awaiting_approval

agent.tool.started

agent.tool.completed

agent.review.started

agent.review.completed

agent.change_set.created

agent.proposal.created

agent.proposal.approved

agent.proposal.rejected

agent.proposal.conflict

agent.run.completed

agent.run.failed

agent.run.cancelled
```

---

# 60. agent.plan.created

```json
{
  "event_type": "agent.plan.created",

  "entity_id": "agent_run_101",

  "payload": {
    "objective": "修改第五镜并重新生成",

    "steps": [
      {
        "step_id": "step_1",
        "title": "修改镜头类型",
        "status": "pending"
      },
      {
        "step_id": "step_2",
        "title": "提交图片生成",
        "status": "pending"
      }
    ]
  }
}
```

前端：

```text
显示 Agent Plan Card
```

---

# 61. agent.tool.started

```json
{
  "event_type": "agent.tool.started",

  "payload": {
    "tool_call_id": "tool_001",

    "tool": "update_shot",

    "target": {
      "type": "shot",
      "id": "shot_005"
    }
  }
}
```

---

# 62. agent.tool.completed

```json
{
  "event_type": "agent.tool.completed",

  "payload": {
    "tool_call_id": "tool_001",

    "tool": "update_shot",

    "success": true,

    "changed_fields": [
      "shot_type"
    ]
  }
}
```

---

# 63. agent.approval.required

```json
{
  "event_type": "agent.approval.required",

  "payload": {
    "approval_id": "approval_001",

    "title": "重新生成 12 个镜头",

    "risk_level": "R2",

    "estimated_tasks": 12,

    "options": [
      {
        "id": "approve",
        "label": "确认"
      },
      {
        "id": "cancel",
        "label": "取消"
      }
    ]
  }
}
```

P2-E3-T02 实际 payload（proposal 维度）：

```json
{
  "proposal_id": "…",
  "tool": "generate_image",
  "target_type": "shot",
  "target_id": "…",
  "changes": {},
  "risk_level": "R2",
  "reason": "昂贵操作：将创建图片生成任务，占用生成资源。",
  "estimated_tasks": 1,
  "estimated_cost": null,
  "irreversible": false,
  "expires_at": "2026-08-31T12:00:00+00:00"
}
```

配套事件：`agent.proposal.created / approved / rejected / conflict / expired`、
`agent.change_set.created / undone`（P2-E3-T03：agent mutation 记录与撤销补偿）。

Frontend：

```text
打开 Approval Card
```

而不是弹系统 Modal。

---

# 64. Generation Events

```text
generation.created

generation.queued

generation.started

generation.progress

generation.completed

generation.failed

generation.cancelled

generation.retrying

generation.interrupted  (P5-T016 异常任务检测：系统中断，终态)
```

---

# 65. generation.progress

```json
{
  "event_type": "generation.progress",

  "entity_id": "gen_001",

  "payload": {
    "progress": 0.68,

    "queue_position": 0,

    "stage": "sampling"
  }
}
```

---

# 66. generation.completed

```json
{
  "event_type": "generation.completed",

  "entity_id": "gen_001",

  "payload": {
    "shot_id": "shot_005",

    "asset_id": "asset_089",

    "media_version_id": "media_v003"
  }
}
```

前端：

```text
invalidate generation

invalidate shot

invalidate asset list
```

---

# 67. generation.failed

```json
{
  "event_type": "generation.failed",

  "payload": {
    "error": {
      "code": "COMFYUI_EXECUTION_FAILED",

      "message": "Node execution failed.",

      "details": {
        "node_id": "32"
      }
    }
  }
}
```

---

# 68. Workflow Events

```text
workflow.run.created

workflow.run.started

workflow.task.started

workflow.task.completed

workflow.task.failed

workflow.run.progress

workflow.run.completed

workflow.run.failed
```

---

# 69. workflow.run.progress

```json
{
  "event_type": "workflow.run.progress",

  "entity_id": "workflow_run_001",

  "payload": {
    "progress": 0.42,

    "tasks": {
      "total": 12,
      "completed": 5,
      "running": 2,
      "failed": 0
    }
  }
}
```

---

# 70. Provider Events

```text
provider.connected

provider.disconnected

provider.degraded

provider.error

llm.fallback.used   （P-LLM-Fallback：LLM 任务降级宣告 —— payload: task/served_by_profile_id/
                     served_by_profile_name/failed[{profile_id, profile_name?, error}]；
                     主连接直接成功不发此事件；entity_type=llm_profile, entity_id=实际服务方）
```

---

# 71. ComfyUI 掉线

Event：

```json
{
  "event_type": "provider.disconnected",

  "entity_id": "comfyui_local",

  "payload": {
    "reason": "connection_lost"
  }
}
```

Frontend：

```text
TopBar

ComfyUI ●
→
ComfyUI ○
```

---

# 72. Event 与 REST 的职责

非常重要：

WebSocket Event：

```text
不是数据库。
```

如果收到：

```text
shot.updated
```

Frontend不一定直接依赖 Event Payload 完整更新所有 Shot 数据。

推荐：

```text
Event
 ↓
TanStack Query invalidate
 ↓
GET latest resource
```

---

# 73. 高频 Event 特殊处理

但是：

```text
generation.progress
```

这种高频实时数据可以直接：

```text
generationStore
```

更新。

因为没必要每 100ms 请求服务器。

---

# 74. Frontend Event Router

建议：

```text
EventSocket
    ↓
EventRouter
    │
    ├── ProjectHandler
    ├── ShotHandler
    ├── AgentHandler
    ├── GenerationHandler
    └── ProviderHandler
```

不要在 WebSocket `onmessage` 中写几百行 if。

---

# 75. Event Handler 示例

```text
shot.updated
 ↓
invalidate Shot
invalidate SceneShots

generation.progress
 ↓
update GenerationStore

agent.plan.created
 ↓
update AgentStore

agent.approval.required
 ↓
set Approval

provider.disconnected
 ↓
update ProviderState
```

---

# 76. WebSocket 重连

必须支持：

```text
Reconnect
```

策略：

```text
1s

2s

4s

8s

max 30s
```

---

# 77. 重连后的状态恢复

重连后不要假设漏掉的 Event 不重要。

Frontend：

```text
Reconnect
 ↓
GET Current Project
 ↓
GET Active Agent Runs
 ↓
GET Running Generations
 ↓
GET Running Workflow Runs
```

恢复真实状态。

---

# 78. Selection Contract

Frontend 发送：

```json
{
  "workspace": "storyboard",

  "project_id": "project_001",

  "episode_id": "episode_001",

  "scene_id": "scene_003",

  "shot_ids": [
    "shot_005"
  ],

  "asset_ids": []
}
```

---

# 79. Selection 只代表 UI Context

Agent不能把 Selection 当做：

```text
绝对事实
```

例如用户说：

> "修改第八镜。"

即使当前 Selection 是 Shot 05：

```text
显式语言 > Selection
```

---

# 80. Entity Resolution Priority

建议：

```text
Explicit ID / Number

↓

Explicit Name

↓

Selection Context

↓

Conversation Reference

↓

Semantic Resolution
```

---

# 81. Operation API

一些短时间 AI 操作可以统一：

```text
Operation
```

例如：

```text
episode analysis

scene planning

prompt generation
```

Operation 状态：

```text
queued

running

completed

failed
```

---

# 82. Operation 与 Generation 区别

Operation：

```text
普通后台任务
```

Generation：

```text
模型媒体生成任务
```

不要全部叫 Task。

否则 UI 后期很难区分。

---

# 83. Command / Query 分离

概念上：

```text
GET
=
Query
```

```text
POST / generate
PATCH
DELETE
=
Command
```

未来如果架构复杂，可以进一步正式采用 CQRS。

MVP 不需要。

---

# 84. Idempotency

重要创建操作支持：

```text
Idempotency-Key
```

例如：

```http
POST /generations
```

Header：

```text
Idempotency-Key: uuid
```

避免前端网络重试导致：

```text
同一个 Shot 生成两次。
```

---

# 85. Request ID

每个 Request：

```text
X-Request-ID
```

如果前端不提供，Backend生成。

日志全部记录：

```text
request_id
```

---

# 86. Correlation ID

Agent → Tool → Generation：

建议统一：

```text
correlation_id
```

例如：

```text
agent_run_101
```

触发：

```text
generation_202
```

日志可以追踪：

```text
User
↓
Agent
↓
Tool
↓
Generation
↓
ComfyUI
```

---

# 87. Source 字段

任何修改建议记录：

```text
source
```

值：

```text
user

agent

workflow

system
```

Frontend可以显示：

```text
AI Director 修改
```

而不是不知道谁改的。

---

# 88. Entity Revision

核心对象建议拥有：

```text
revision
```

包括：

```text
Scene

Shot

Character

Workflow
```

每次 Mutation：

```text
revision + 1
```

---

# 89. 删除 API

默认：

```text
Soft Delete
```

Response：

```json
{
  "id": "shot_005",
  "deleted": true
}
```

---

# 90. Restore API

未来：

```http
POST /api/v1/shots/{id}/restore
```

---

# 91. Batch Update

Storyboard 多选时：

```http
PATCH /api/v1/shots/batch
```

Request：

```json
{
  "shot_ids": [
    "shot_01",
    "shot_02"
  ],

  "patch": {
    "duration": 3
  }
}
```

---

# 92. Batch Operation Response

```json
{
  "updated": [
    "shot_01",
    "shot_02"
  ],

  "failed": []
}
```

---

# 93. Timeline API（Phase 9 落地，2026-08）

一集一条时间线；轨道 + 素材块编排。所有普通 CRUD 走 REST；渲染走
202 + generation 队列事件（沿用 `generation.*` 事件，宿主即 Job Queue）。

## 93.1 端点

```text
GET    /episodes/{episode_id}/timeline             一集的时间线（含 tracks + clips + asset 摘要）
POST   /episodes/{episode_id}/timeline             创建时间线（自动建默认四轨 VIDEO/VOICE/MUSIC/SUBTITLE）
PATCH  /timelines/{timeline_id}                    更新 duration/fps/width/height/status
POST   /timelines/{timeline_id}/tracks             新增轨道
PATCH  /timelines/{timeline_id}/tracks/{track_id}  改 mute/lock/name/order_index
DELETE /timelines/{timeline_id}/tracks/{track_id}  删除轨道（级联删 clip）
POST   /timelines/{timeline_id}/clips              新增 TimelineClip（text 可选：字幕/配音文案；transition 可选：cut/fade/dissolve）
PATCH  /timeline-clips/{clip_id}                   编辑（移动 start_time/end_time、微调 source_in/source_out、
                                                   换轨 track_id、order_index、enabled、text、transition）——即拖拽/裁剪/文案的落库接口；
                                                   P4-E3-T02：携带 revision 时走乐观并发（不匹配 → 409，绝不静默覆盖）
DELETE /timeline-clips/{clip_id}                   删除 clip
POST   /timeline-clips/{clip_id}/replace-asset     替换为另一个 Asset（版本替换）
POST   /timeline-clips/{clip_id}/generate-voiceover 202 → 入队 type=audio 的配音 Generation（TASK-012，
                                                    仅 VOICE 轨 clip；text 取请求或 clip.text）
POST   /timelines/{timeline_id}/generate-voiceovers 202 → C1 整轨批量配音：为所有「有台词且未绑定音频」
                                                    （enabled）的 VOICE 轨 clip 各入队一条 type=audio Generation；
                                                    返回 { timeline_id, submitted:[{clip_id,generation_id,text_head}],
                                                    skipped_no_text:[clip_id], already_bound:[clip_id] }
POST   /timelines/{timeline_id}/sequence-from-shots 一键排片：按 scene+shot 顺序建成 VIDEO 轨
                                                    （绑定 shot.active_video_asset_id，缺失则回退 active_image_asset_id）
                                                    + 按 dialogue 建 SUBTITLE 轨，片段首尾相接
POST   /timelines/{timeline_id}/preview             生成帧条预览图（JPEG，PIL；不依赖渲染后端）
POST   /timelines/{timeline_id}/render              202 → 入队 type=render 的 Generation
GET    /episodes/{episode_id}/final-video           该集最近一次渲染产物 FINAL_VIDEO Asset（无则 404）
```

## 93.2 Timeline DTO

```json
{
  "id": "tl_01", "project_id": "p_01", "episode_id": "ep_01",
  "duration": 24.0, "width": 720, "height": 1280, "fps": 24.0,
  "status": "DRAFT", "revision": 1, "created_at": "...", "updated_at": "...",
  "tracks": [ { "id": "tr_01", "timeline_id": "tl_01", "track_type": "VIDEO",
                "name": null, "order_index": 0.0, "locked": 0, "muted": 0 } ],
  "clips": [ { "id": "cl_01", "timeline_id": "tl_01", "track_id": "tr_01",
               "asset_id": "as_01", "shot_id": "sh_01",
               "start_time": 0.0, "end_time": 3.0, "source_in": 0.0, "source_out": null,
               "transition": "cut", "revision": 1,
               "order_index": 0.0, "enabled": 1,
               "asset": { "id": "as_01", "type": "image", "name": "...",
                          "thumbnail_url": "/api/v1/assets/as_01/thumbnail" } } ]
}
```

## 93.2a TimelineClip 转场 / revision / undo（P4-E3-T02 AC-2，2026-08-31）

- `transition`（`cut` 默认 | `fade` | `dissolve`）：片段头部的转场。非法值 422。
  渲染时对 fade/dissolve 做交叉淡化（ffmpeg `xfade` 链 / mock PIL 逐帧 blend），
  `cut` 硬切；渲染计划（generation.parameters.clips[].transition）完整透传可追溯。
- `revision`（乐观并发）：新建 = 1，每次成功编辑 +1。`PATCH /timeline-clips/{id}`
  的 patch 携带 `revision` 时，服务端执行原子条件更新
  `UPDATE … WHERE id=? AND revision=?`；不匹配 → 409
  `{ "current_revision": N }`（绝不静默覆盖）。不带 revision 保持 last-write-wins
  兼容（仍会 +1）。
- Timeline 编辑自动记录 ChangeSet（`source="timeline"`、`entity_type="timeline_clip"`、
  tool=`timeline.edit` / `timeline.replace_asset`），复用既有
  `GET /agent/change-sets?entity_id={clip_id}` 与
  `POST /agent/change-sets/{id}/undo`（undo 为补偿变更，clip revision +1）。
- 事件：`timeline.clip.updated` 保持不变；ChangeSet 事件沿用
  `agent.change_set.created` / `agent.change_set.undone`。

## 93.3 渲染 DTO/事件

```text
POST /timelines/{id}/render → 202 { "generation_id", "job_status": "queued", "timeline_id" }
```

渲染产物注册为 `vg:episode:{episode_id}:FINAL_VIDEO` 版本组下的 `type=video` Asset；
渲染完成发布 `timeline.rendered`（payload 含 output_asset_id / version_number / duration）。

渲染计划（TASK-013）除 VIDEO 轨外同时收集：未静音的 VOICE/MUSIC/SFX clip（混为
一路音频床）与有 text 的 SUBTITLE clip（ffmpeg 渲染经 subtitles 滤镜烧录、mock
渲染逐帧绘制）；两者均缺失时产物与 Phase 9 一致（无声视频）。

## 93.3a 配音（TASK-012，2026-08）

```text
POST /timeline-clips/{clip_id}/generate-voiceover → 202 GenerationRead
     body: { "text"?, "provider"?, "voice"?, "rate"? }   # text 缺省用 clip.text
```

- 仅接受 VOICE 轨 clip；text/rate/provider 校验失败 422，clip 不存在 404。
- 产物注册为 `vg:clip:{clip_id}:AUDIO` 版本组下的 `type=audio` Asset
  （V1/V2… 不可变），并把该 clip 重新绑定到最新版本（replace-asset 语义）。
- 事件复用 `generation.queued/started/progress/completed/failed`（payload 带
  `type: "audio"`、`timeline_clip_id`）+ `asset.created`（payload 带
  `role: "VOICEOVER"`）+ `timeline.clip.updated`（回绑后刷新前端缓存）。
- AudioProvider（registry type=audio）：`mock`（确定性 WAV，默认/CI）与
  `edge`（edge-tts 在线神经网络音色，`STUDIO_AUDIO_PROVIDER=edge`，
  dev/原型用途——依赖非公开微软端点，不作为产品默认）。

## 93.4 Timeline 事件

```text
timeline.created · timeline.updated · timeline.track.updated · timeline.clip.created
timeline.clip.updated · timeline.clip.deleted · timeline.rendered
```

全部统一 Envelope（§9）。前端据此 invalidate `timeline(episode_id)` 查询。

---

# 94. Continuity API

检查两个镜头：

```http
POST /api/v1/continuity/check-transition
```

Request：

```json
{
  "from_shot_id": "shot_008",
  "to_shot_id": "shot_009"
}
```

---

# 95. Continuity Response

```json
{
  "score": 0.76,

  "issues": [
    {
      "type": "prop_hand",

      "severity": "medium",

      "description": "篮球从右手变成左手。"
    }
  ],

  "suggestions": [
    "保持 Shot 09 右手持球。"
  ]
}
```

---

# 96. Review API

未来：

```http
POST /api/v1/generations/{id}/review
```

返回 Operation：

```json
{
  "operation_id": "review_op_001"
}
```

---

# 97. 前端 Query Key

建议 TanStack Query 使用：

```text
["projects"]

["project", projectId]

["episodes", projectId]

["scenes", episodeId]

["shots", sceneId]

["shot", shotId]

["assets", projectId, filters]

["generation", generationId]

["agentRun", runId]
```

---

# 98. Mutation 后刷新策略

例如：

```text
updateShot
```

成功：

```text
invalidate ["shot", shotId]

invalidate ["shots", sceneId]
```

而不是：

```text
invalidateEverything()
```

---

# 99. Optimistic Update

适合：

```text
Shot duration

Shot name

Reorder
```

不适合：

```text
AI generation

Agent batch modifications

Version restore
```

---

# 100. Shot Card 状态来源

Shot Card 不应该自己拼装多个来源。

Backend最好提供：

```text
ShotSummary DTO
```

例如：

```json
{
  "id": "shot_005",

  "shot_number": 5,

  "status": "image_ready",

  "dirty_state": "dirty_video",

  "image_stale": true,

  "thumbnail_url": "...",

  "duration": 3.2,

  "character_names": [
    "沈亦"
  ],

  "active_generation": null
}
```

---

# 101. Storyboard Endpoint

为了性能建议提供：

```http
GET /api/v1/scenes/{scene_id}/storyboard
```

一次返回：

```text
Scene Summary

Shot Summaries

Generation Summary
```

避免前端：

```text
1 Scene
+
50 Shot Requests
```

---

# 102. Storyboard Response

```json
{
  "scene": {
    "id": "scene_003",
    "name": "体育馆"
  },

  "shots": [
    {
      "id": "shot_005",
      "shot_number": 5,
      "thumbnail_url": "...",
      "status": "image_ready",
      "duration": 3.2
    }
  ]
}
```

---

# 103. Project Bootstrap API

打开 Project 时建议：

```http
GET /api/v1/projects/{id}/bootstrap
```

返回：

```text
Project

Episodes Summary
（每集：scene_count · has_timeline · has_final_video —— P2 管线阶段探针，
  取自真实 Project State：timelines 表 + vg:episode:{id}:FINAL_VIDEO 资产组；
  工作区首页用此判定「时间线 / 导出」阶段，替代逐集 404 探测）

Characters Summary

Provider Status

Active Agent Runs

Active Generations
```

用于快速启动工作区。

## 103.1. 生产就绪度（自主迭代 04）

```http
GET /api/v1/projects/{id}/readiness
```

确定性聚合（无 LLM、只读），回答「这部作品还差什么才能产出一致画面」——在工作区
「生产就绪度」面板展示，缺口可点击跳转补齐：

```text
characters:      { total, ready, missing }        # ready = 有 MASTER 参考图
scene_binding:   { scenes_total, bound, bound_with_master, unbound }
                                                  # bound_with_master = 绑定地点且有 MASTER（可注入地点参考）
continuity_open: int                               # status=open 的连续性警告数
```

语义：角色无 MASTER / 场景未绑定地点或地点无 MASTER → 生成无法注入一致性参考图；
开放连续性警告 → 已检测到跨镜头事实冲突。全部由真实 Project State 聚合，前端据此
在生成前提示补齐，避免对不一致资产浪费生成。

---

# 104. Bootstrap 不返回

不要返回：

```text
全部 Shot

全部 Prompt

全部 Assets
```

否则大型 Project 会非常重。

---

# 105. Pagination

Asset、Generation、Activity 必须分页。

优先：

```text
Cursor Pagination
```

而不是：

```text
offset=100000
```

---

# 106. Activity API

未来：

```http
GET /api/v1/projects/{id}/activities
```

可显示：

```text
用户修改

AI 修改

Generation

Version

Workflow
```

---

# 107. Activity DTO

```json
{
  "id": "activity_001",

  "type": "shot.updated",

  "source": "agent",

  "summary": "AI Director 修改了 Shot 05",

  "entity_id": "shot_005",

  "created_at": "..."
}
```

---

# 108. Event Persistence

不是所有 WebSocket Event 都要永久保存。

建议：

永久：

```text
重要业务 Activity

Agent ChangeSet

Generation
```

临时：

```text
Progress 31%

Progress 32%

Progress 33%
```

不需要永久数据库记录每个点。

---

# 109. Event Bus

Backend内部：

```text
Domain Event
       ↓
Internal Event Bus
       │
       ├── WebSocket Gateway
       ├── Logging
       ├── Workflow Listener
       └── Agent Listener
```

---

# 110. Domain Event 示例

ShotService：

```text
update()
 ↓
Commit DB
 ↓
ShotUpdated Event
```

而不是 API Router 手动：

```text
socket.send(...)
```

---

# 111. Transaction Boundary

重要操作：

```text
DB Mutation
+
Event Creation
```

必须保证一致性。

后期可以使用：

```text
Transactional Outbox
```

MVP 至少要做到：

```text
先 commit

再发布 Event
```

不能发布成功后数据库失败。

---

# 112. ComfyUI 与 Event

ComfyUI WebSocket：

```text
ComfyUI Event
```

不能直接透传到 Frontend。

需要：

```text
ComfyUI Protocol
       ↓
ComfyUI Adapter
       ↓
Studio Generation Event
       ↓
Frontend
```

---

# 113. 为什么不能透传 ComfyUI Event

否则前端会知道：

```text
node_id

prompt_id

execution_cached
```

这样 Studio 就和 ComfyUI 强耦合。

正确：

```text
generation.progress

generation.completed
```

---

# 114. Agent Tool Event

同理：

Frontend 不必知道：

```text
LangChain ToolMessage
```

只知道：

```text
agent.tool.started

agent.tool.completed
```

---

# 115. LangGraph Event Adapter

建议建立：

```text
LangGraphEventAdapter
```

负责：

```text
LangGraph Runtime Event
        ↓
Studio Agent Event
```

避免前端依赖 LangGraph 内部事件格式。

---

# 116. LangChain Message 不直接暴露

Backend内部可能：

```text
HumanMessage

AIMessage

ToolMessage
```

Frontend DTO 应转成：

```json
{
  "role": "assistant",
  "content": "...",
  "type": "message"
}
```

保持框架无关。

---

# 117. Agent Message API

历史：

```http
GET /api/v1/agent/sessions/{session_id}/messages
```

Response：

```json
[
  {
    "id": "msg_001",
    "role": "user",
    "content": "把第五镜改成近景"
  },
  {
    "id": "msg_002",
    "role": "assistant",
    "content": "已修改并提交生成。"
  }
]
```

---

# 118. Agent Message 与 Agent Run

一次 Message：

```text
可以触发一个 Run。
```

建议保存：

```text
message_id

run_id
```

关系。

---

# 119. UI 主链路：修改 Shot

完整流程：

```text
用户点击 Shot 05

↓

selectionStore
shot_005

↓

用户：
"这个改成近景"

↓

POST /agent/director/runs

↓

202 run_101

↓

WS:
agent.run.started

↓

WS:
agent.plan.created

↓

WS:
agent.tool.started

↓

ShotService.update

↓

WS:
shot.updated

↓

Frontend invalidate Shot

↓

Shot Card 更新

↓

WS:
agent.tool.completed

↓

WS:
agent.run.completed
```

---

# 120. UI 主链路：修改并生成

```text
User

↓

AI Director

↓

Agent Run

↓

Shot Update

↓

shot.updated

↓

GenerationService.create

↓

generation.created

↓

generation.queued

↓

Agent Run completed

↓

ComfyUI继续运行

↓

generation.progress

↓

generation.completed

↓

asset.created

↓

shot.active_version.changed

↓

Storyboard更新
```

这里体现：

> Agent 生命周期与 Generation 生命周期完全分离。

---

# 121. UI 主链路：审批

```text
User:
"重做第三场"

↓

Agent Plan

↓

Risk R2

↓

agent.approval.required

↓

Frontend ApprovalCard

↓

用户点击 Confirm

↓

POST /runs/{id}/resume

↓

agent.resumed

↓

agent.tool.started

↓

...
```

---

# 122. UI 主链路：失败重试

```text
generation.failed

↓

Frontend GenerationCard

↓

显示 Retry

↓

POST /generations/{id}/retry

↓

gen_002

↓

generation.queued
```

---

# 123. 前端 Connection State

需要：

```text
backendConnected

eventSocketConnected

comfyuiConnected

agentAvailable
```

不要只有一个：

```text
online
```

---

# 124. Offline State

如果 Backend 断开：

```text
Editing Disabled / Readonly
```

或者缓存部分 UI。

MVP可以直接显示：

```text
Backend disconnected
```

---

# 125. Local-first 特性

因为 Desktop + local backend：

正常情况下：

```text
Frontend
↔
127.0.0.1 Backend
```

因此可以获得：

```text
低延迟

不依赖远程网络
```

只有模型 Provider 可能联网。

---

# 126. Security

Local backend 不代表：

```text
完全不用安全。
```

至少：

```text
仅监听 localhost

随机 session token

禁止任意文件路径访问

文件 API 校验 project root
```

---

# 127. File Path 安全

API 不允许：

```json
{
  "path": "../../../Windows/System32"
}
```

AssetService 必须限制：

```text
Project Root
```

---

# 128. API Key

Frontend永远不读取真实 Key。

调用：

```text
credential_id
```

实际 Secret：

```text
OS Secure Storage
```

---

# 129. Provider Config DTO

例如：

```json
{
  "id": "openai_main",

  "provider": "openai",

  "configured": true,

  "credential_status": "available"
}
```

不返回：

```text
sk-xxxx
```

---

# 130. 前端生成按钮逻辑

Frontend不要根据 Provider 写：

```text
if comfyui ...
```

只读取：

```text
capabilities
```

例如：

```json
{
  "image_generation": true,

  "reference_image": true,

  "video_generation": false,

  "text_generation": true
}
```

> P4-T002：capabilities 由 ProviderRegistry 按 (type, id) 输出，覆盖 image_generation /
> reference_image / video_generation / text_generation；MVP 的 video_generation 恒为
> false（视频 provider 为 unavailable 占位，生成显式拒绝），前端据此禁用视频按钮。

---

# 131. Capability API

```http
GET /api/v1/providers/{id}/capabilities
```

---

# 132. Feature Flag

未来可：

```text
continuity_v2

timeline_beta

auto_router
```

Backend Bootstrap 返回：

```json
{
  "features": {
    "continuity": true,
    "timeline": false
  }
}
```

---

# 133. API Contract 测试

所有 API 使用：

```text
OpenAPI
```

FastAPI 自动生成。

Frontend 可根据：

```text
openapi.json
```

生成 TypeScript Client。

---

# 134. 推荐 TypeScript Client

不要手写几十个：

```text
fetch()
```

建议自动生成：

```text
API Types

API Client
```

以减少 Python Pydantic 与 TypeScript 类型漂移。

---

# 135. DTO 单一来源

原则：

```text
Backend OpenAPI
=
API Contract Source of Truth
```

Frontend 类型尽量由 API Schema 生成。

---

# 136. Event Schema

Event不能依赖 OpenAPI 自动解决。

建议单独维护：

```text
event_schema.json
```

或：

```text
shared Event Schema
```

---

# 137. Event Schema Validation

Backend发布前：

```text
Pydantic Event Model
```

验证。

Frontend开发阶段：

```text
Zod
```

验证。

避免异常 Event 直接破坏 UI。

---

# 138. Event 数据模型

可以：

```text
BaseEvent

AgentEvent

GenerationEvent

ShotEvent
```

而不是：

```text
dict[str, Any]
```

---

# 139. Contract Version

Studio 启动时：

```http
GET /api/v1/system/info
```

Response：

```json
{
  "backend_version": "0.1.0",

  "api_version": "1",

  "event_protocol_version": "1"
}
```

Frontend可以检测兼容性。

---

# 140. Health API

```http
GET /api/v1/health
```

Response：

```json
{
  "status": "healthy",

  "database": "healthy",

  "worker": "healthy",

  "event_bus": "healthy",

  "providers": {
    "comfyui": "connected"
  }
}
```

---

# 141. API Contract 核心规则

长期必须坚持：

### 1.

REST 管命令与查询。

### 2.

WebSocket 管状态变化。

### 3.

Event 不等于数据库。

### 4.

Frontend 不依赖 LangGraph 格式。

### 5.

Frontend 不依赖 LangChain Message 类型。

### 6.

Frontend 不依赖 ComfyUI Protocol。

### 7.

所有外部实现先转换成 Studio Domain Contract。

### 8.

Generation 与 Agent 生命周期分离。

### 9.

所有关键实体支持 revision。

### 10.

所有长任务返回 202，而不是长期阻塞 HTTP。

---

# 142. MVP 必须实现的 REST API

```text
/projects

/projects/{id}/bootstrap

/episodes

/episodes/{id}/analyze

/scenes

/scenes/{id}/storyboard

/shots

/shots/{id}

--- P2（CharacterVersion，P2-T007/T008）---

/characters/{id}/versions                  （视觉版本列表，按 version_number 升序）
/characters/{id}/versions                  （POST：{asset_id, name?, description?}，新建默认 stale，201）
/characters/{id}/versions/{versionId}/activate   （POST：置 active + master_version_id 指向它）

/characters/{id} 响应新增 master_version_id（MASTER 指针，可空）

--- P2（Location / LocationVersion，P2-T009）---

/projects/{id}/locations                            （GET：按 project 列出；POST：201 创建）
/locations/{id}                                    （GET / PATCH{revision,patch} / DELETE 软删）
/locations/{id}/versions                           （GET：按 version_number 升序；POST：{asset_id,name?,description?}，201，默认 stale）
/locations/{id}/versions/{versionId}/activate      （POST：置 active + master_version_id 指向它）

/locations/{id} 响应新增 master_version_id（MASTER 指针，可空）

--- P2（Costume，P2-T010）---

/projects/{id}/costumes                            （GET：按 project 列出；POST：201 创建）
/costumes/{id}                                     （GET / PATCH{revision,patch} / DELETE 软删）

--- P2（Shot costume 扩展）---

POST /scenes/{id}/shots   与 PATCH /shots/{id} 之 patch 可选 `characters: [{character_id, costume_id}]`
（向后兼容：缺省退化为 `character_ids` 列表；提供 `characters` 时覆盖 `character_ids`）

--- P2（Read Models，P2-T011/T012/T013）---

/projects/{id}/tree              （GET：Project + Episodes(scene_count) + Scenes(shot_count) + Shot 摘要：shot_number/shot_type/status/active 版本摘要，一次返回）
/scenes/{id}/editor              （GET：Scene + Shots（视觉 spec 摘要 + active_image/video 版本号 + characters 名））
/shots/{id}/inspector            （GET：Shot 完整详情 + visual spec + active 版本 + prompt 版本摘要 + 出场角色含 costume）

说明：这些 Read Model 与 bootstrap（§103 工作区启动摘要）和 storyboard（§101 单场景网格）互补——
bootstrap 只返回顶层摘要、不返回全部 shot（§104）；tree/editor/inspector 提供完整导航与明细形状。

--- P8（Continuity Engine，P8-T001~T017）---

GET  /api/v1/scenes/{id}/continuity              （Scene Continuity 视图：base_state + 每个 shot 的 start/end/delta/state_hash/warnings）
GET  /api/v1/shots/{id}/continuity-state         （单 shot：{shot_id, start_state, end_state, delta, state_hash, warnings}）
POST /api/v1/scenes/{id}/continuity/recompute    （手动触发 dirty-range 重算，返回 {scene_id, recomputed_shots, total_shots, state_hash}）

DTO：SceneContinuityRead{scene_id, base_state, base_state_hash, shots: ShotContinuityRead[]} ·
ShotContinuityRead{shot_id, shot_number, start_state, end_state, delta, state_hash, warnings: ContinuityWarning[]} ·
ContinuityRecomputeRead{scene_id, recomputed_from, recomputed_shots, total_shots, state_hash}
warnings 来源 = shot_continuity_states.warnings_json（source=RULE）；并行 continuity_warnings 表（P8-B)落地后，
场景聚合端点会合并该场景的 OPEN 条目（warnings_json 为准，兼容合并）。

--- P2 之后的核心线 ---

/agent/director/runs

/agent/runs/{id}

/agent/runs/{id}/resume

/generations

/generations/{id}

/generations/{id}/retry

/assets

--- P5（P5-T013/T014 队列级暂停）---

/generations/pause        （暂停调度新任务；运行中的继续跑完）

/generations/resume       （恢复调度新任务）

/generations/queue-status （队列状态：paused / pending / pending_total / running）

/providers

/providers/comfyui/test
/providers/agnes/test   （POST，Agnes 连通探测，§48.0）
/providers/comfyui/models （GET，ComfyUI checkpoint 列表，§48.2）
/providers/comfyui/workflows （GET，自动发现的 workflow 模板清单，§48.2b）
/providers/comfyui/workflows/{id}/validate （POST，workflow live 诊断，§48.2b）
/providers/models/scan  （POST，本地模型扫描/自动检索，§48.3）
/providers/models/import （POST 202 + Operation，导入模型到 ComfyUI models，§48.4）
/providers/fs/list       （GET，本地目录浏览（设置页文件浏览器），§48.6）

/llm/config            （GET / PUT，运行时激活 LLM 连接配置）
/llm/profiles          （GET / POST，连接 Profile Registry；PATCH/DELETE /llm/profiles/{id}、POST /llm/profiles/{id}/activate，§47.4）
/llm/task-bindings     （PUT，任务 → 连接绑定，§47.4）
/llm/task-fallbacks    （PUT，任务 → 有序降级链（显式配置 + 事件宣告），§47.4.1）
/llm/test              （POST，连通性测试，§47.2）
/llm/models            （GET，模型列表，§47.2）
/llm/detect-local      （POST，本机 LLM 服务探测，§47.3）

/image/config          （GET / PUT，图像运行时配置（含 ComfyUI 字段），§48.5）
/image/video-models    （GET，视频模型目录 + 实测可用性，§48.5.1）
/image/test            （POST，图像连接探测，§48.5）

/workflows

/health

--- P3（ADR-001/ADR-002）---

/shots/{id}/versions                （Asset 版本列表，image+video）

/media-versions/{assetId}/activate  （按 Asset 激活，旧路径兼容保留）

/shots/{id}/image-versions          /shots/{id}/video-versions

/shots/{id}/image-versions/{assetId}/activate

/shots/{id}/video-versions/{assetId}/activate

/shots/{id}/prompts                 （列表/创建，ADR-002）

/prompts/{id}/versions              （列表/创建 vN+1）

/prompts/{id}/versions/{versionId}/activate

/projects/{id}/prompts              （提示词库：项目级预设 target_type=PROJECT，GET/创建，复用 prompts 模型）

/prompts/{id}                       （DELETE，删除提示词或其预设及其全部版本）

--- P1（ProjectSetting）---

/projects/{id}/settings             （GET / PUT，P1：项目级生成/配置默认值）

--- P3（Provenance）---

/assets/{id}/provenance             （P3：asset + generation 块 + inputs + retry 链）

/generations/{id}/inputs            （P3：生成请求输入引用）

/generations/{id}/outputs           （P3：生成结果资产）

--- P3（Asset Import / Missing）---

/projects/{id}/assets/import         （P3-T003：multipart 导入外部文件 → 项目级 Asset，201 返回 AssetRead）

/projects/{id}/assets/check-missing  （P3-T005：扫描项目资产，ready→missing，返回 {checked, missing}）

--- P6-B（Asset Browser Read Models，P6-B-01/P6-B-02）---

GET /projects/{id}/assets            （P6-B-01：项目级资产列表 {total, items}；分页 offset/limit 默认 limit=50 上限 200 + 过滤 asset_type=image|video、status=ready|missing|...、include_deleted=false 默认；只含 live 资产，非删排除；按 created_at 倒序；非法 type/status → 422）
GET /assets/{id}                     （P6-B-02：单资产完整详情，供 Inspector；含 checksum/file_size + meta_json + generation_id + parent_asset_id + shot_id 引用摘要；404 不存在/已软删）

DTO：AssetListItemRead{id,type,status,version_group_id,version_number,checksum,file_size,width,height,_
created_at,file_path(项目相对路径),thumbnail_url} · AssetListRead{total,items[]} · AssetDetailRead{Id=AssetListItemRead 字段 + project_id + meta_json + generation_id + parent_asset_id + shot_id}

--- P5（Job / JobTask，P5-E1/E2/E3）---

POST /projects/{id}/jobs         （body {scene_id, name?} → 201 JobRead，含 tasks 摘要）
GET  /projects/{id}/jobs         （Job 列表摘要，不含 tasks）
GET  /jobs/{id}                  （JobRead + 完整 tasks 列表）
POST /jobs/{id}/pause            （→ paused；调度跳过该 job，运行中 generation 继续）
POST /jobs/{id}/resume           （→ queued）
POST /jobs/{id}/cancel           （未完成任务 → cancelled；运行中 generation 走现有取消路径）
POST /jobs/{id}/retry            （failed/dependency_failed/skipped 任务 → queued 并清 generation 引用；completed 保持）

DTO：JobCreate{scene_id,name?} · JobRead{id,project_id,name,job_type,scene_id,status,progress,error_summary,_
created_at,updated_at,task_count,task_status_counts,tasks[]} · JobTaskRead{id,job_id,task_type,target_type,_
target_id(=shot_id),status,priority,progress,generation_id,error_message,created_at,updated_at} · JobSummaryRead

（P5-T019 SSE：MVP 已有 WS 事件网关 /api/v1/events，SSE 需求由该 WS 网关满足，不重复实现。）
```

--- P8（Continuity Agent + Video Bridge 结构，api-event-contract §142 Continuity）---

POST /agent/continuity/check                 （body {scene_id} → 202 + run_id：跑连续性语义 check，规则 + LLM 语义警告落 continuity_warnings，事件 WS 推送；轮询用 GET /agent/runs/{run_id}）
GET  /agent/continuity/runs/{run_id}         （连续性 run 状态/结果 {run_id,status,result(error)warnings_created?,error}）
POST /agent/continuity/fix                   （body {warning_id, patch?} → 该 warning 发起 fix run，run 进入 waiting_human，含 pending proposal；approve/reject 复用 POST /agent/proposals/{id}/approve|reject）
GET  /scenes/{id}/continuity-warnings        （该场景 open 警告列表 {id,project_id,scene_id,shot_id?,run_id?,category,severity,message,evidence{},status,created_at,resolved_at?}）
POST /continuity-warnings/{id}/acknowledge   （标记已读 → status=acknowledged，避免重复骚扰）
GET  /scenes/{id}/transitions                （shot_transitions 结构列表 {id,scene_id,from_shot_id,to_shot_id?,mode,frame_from_asset_id?,frame_to_asset_id?,created_at}）

DTO：SemanticWarning{scope:scene|shot,shot_id?,category,message,severity:info|warning|error,evidence{}} ·
ContinuityWarningRead{id,project_id,scene_id,shot_id?,run_id?,category,severity,message,evidence{},status,created_at,resolved_at?} ·
continuity.fix proposal 经 P7 Proposal 表（tool=continuity_fix，target_type=shot 走 ShotService 应用；
target_type=continuity 仅置 warning fixed 不改域）。

（P8 说明：先 check 后对具体 warning 发起 fix run —— 采用「分开」设计而非 /continuity/runs{auto_fix}，便于前端在
Scene Warning / Shot Inspector 面板逐条处置。）

---

# 143. MVP 必须实现的 Events

```text
shot.updated

episode.created

episode.updated

episode.deleted

scene.deleted

agent.run.started

agent.plan.created

agent.approval.required

agent.tool.started

agent.tool.completed

agent.run.completed

agent.run.failed

generation.queued

generation.started

generation.progress

generation.completed

generation.failed

generation.interrupted

asset.created

character.created

character.updated

character.deleted

character.version.created      （新建角色视觉版本，payload: character_id/version_id/version_number/asset_id）

character.version.activated    （激活为 MASTER，payload: character_id/version_id/version_number/asset_id）

location.created

location.updated

location.deleted

location.version.created      （新建地点视觉版本，payload: location_id/version_id/version_number/asset_id）

location.version.activated    （激活为 MASTER，payload: location_id/version_id/version_number/asset_id）

costume.created

costume.updated

costume.deleted

document.created

document.updated

document.deleted

provider.connected

provider.disconnected

llm.fallback.used   （LLM 任务降级宣告，P-LLM-Fallback；payload: task/served_by_profile_id/served_by_profile_name/failed）

--- P5（Job / JobTask，P5-E2）---

job.created        （payload: job_type/scene_id/task_count）
job.updated        （payload: status/progress/reopened_tasks?）
job.completed      （payload: status/progress/failed_count/error_summary?）
job.failed         （保留；partial failure 依赖 job.completed+error_summary 表达）
job.cancelled      （payload: cancelled_tasks）
job.paused         （payload: previous_status）
job.resumed
job.task.updated   （payload: task_id/task_type/shot_id/status/generation_id）
```

--- P8（Continuity Agent，api-event-contract §143）---

continuity.warning.created       （payload: scene_id/shot_id?/category/severity/message/run_id?）
continuity.warning.acknowledged  （payload: scene_id/shot_id?/category）
continuity.warning.fixed         （payload: scene_id/shot_id?/category；fix 经 P7 proposal 批准应用后发出）
---

# 144. MVP Integration Milestone 1

必须跑通：

```text
Frontend ShotCard

↓

PATCH Shot

↓

ShotService

↓

Database

↓

shot.updated

↓

Frontend Refresh
```

---

# 145. MVP Integration Milestone 2

必须跑通：

```text
Frontend

↓

Generate Shot

↓

POST Generation

↓

202

↓

Generation Queue

↓

WebSocket Progress

↓

ComfyUI

↓

Asset

↓

Shot Update

↓

Frontend Storyboard
```

---

# 146. MVP Integration Milestone 3

必须跑通：

```text
Frontend Selection

↓

AI Director Message

↓

Agent Run

↓

LangGraph

↓

Tool

↓

ShotService

↓

shot.updated

↓

Agent Completed

↓

Frontend
```

---

# 147. MVP Integration Milestone 4

必须跑通：

```text
AI Director

↓

Risk Operation

↓

Approval Event

↓

ApprovalCard

↓

Resume API

↓

Agent Continue

↓

ChangeSet
```

做到这里：

> AI Director 与 Studio UX 真正融合。

---

# 148. 最终通信架构

```text
                           Frontend
                              │
                ┌─────────────┴─────────────┐
                │                           │
              REST                      WebSocket
                │                           ▲
                ▼                           │
          Application API             Event Gateway
                │                           ▲
       ┌────────┼──────────┐                │
       ▼        ▼          ▼                │
    Domain     Agent    Generation          │
   Services   Runtime     Runtime            │
       │        │          │                │
       │        │          │                │
       └────────┴────┬─────┘                │
                    │                      │
                 Event Bus ────────────────┘
                    │
                    ▼
              Project State
```

---

# 149. 最终设计结论

AI 漫剧 Studio 的前后端通信不能只是：

```text
Frontend
↓
REST API
↓
Database
```

而必须形成：

```text
Command
+
Query
+
Event
+
Long-running Task
+
Agent Run
+
Production Run
```

六种完整交互语义。

这样才能同时支撑：

```text
普通手动编辑

AI Director 操作

ComfyUI 长任务

批量生成

审批

实时进度

版本与撤销
```

最终用户看到的是一个连续、实时、可靠的 Studio。

而不是多个后台系统拼接出来的感觉。
