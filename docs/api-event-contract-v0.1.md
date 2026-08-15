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

  "created_at": "...",
  "updated_at": "..."
}
```

---

# 26. Agent Run 状态

统一：

```text
created

understanding

loading_context

planning

waiting_approval

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

当：

```text
status = waiting_approval
```

调用：

```http
POST /api/v1/agent/runs/{run_id}/resume
```

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

---

# 29. Resume Request

```json
{
  "approval_id": "approval_001",
  "decision": "approve"
}
```

也可以：

```json
{
  "decision": "cancel"
}
```

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

Agent 完成修改后：

```text
change_set_id
```

例如：

```http
GET /api/v1/change-sets/{change_set_id}
```

---

# 33. ChangeSet Response

```json
{
  "id": "changeset_101",

  "project_id": "project_001",

  "source": "agent",

  "run_id": "agent_run_101",

  "changes": [
    {
      "operation": "update",

      "entity_type": "shot",

      "entity_id": "shot_005",

      "before": {
        "shot_type": "medium"
      },

      "after": {
        "shot_type": "close_up"
      }
    }
  ],

  "created_at": "..."
}
```

---

# 34. Undo ChangeSet

```http
POST /api/v1/change-sets/{id}/undo
```

Response：

```json
{
  "undo_change_set_id": "changeset_102",
  "status": "completed"
}
```

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
  "parameters": {}
}
```

> workflow_id **可选**（P4-T007）：省略时由 WorkflowResolver 按优先级链解析并写入
> `generation.workflow_id` —— **request override → project default → system default**
> （project default 取 `project_settings.default_image_workflow_id` / `default_video_workflow_id`，
> 按 `type` 选择；system default = `default_image_api`）。显式传入保持原有 422 前检；
> 未知的解析结果一律 422（绝不静默回退）。
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

最近生成（底部队列历史）：

```http
GET /api/v1/generations/recent
```

返回 `Generation[]`（按 created_at 倒序，最多 20 条）。
静态路由 `/generations/recent` 必须先于 `/generations/{generation_id}`
注册，避免被参数路由吞掉（P1-E4-T01 路由冲突回归）。

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

  "error": null
}
```

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

# 49. WebSocket 连接

建议：

```text
ws://localhost:{port}/api/v1/events
```

---

# 50. WebSocket Authentication

桌面 MVP 本地环境可采用 Session Token。

例如：

```text
?token=...
```

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

agent.tool.started

agent.tool.completed

agent.review.started

agent.review.completed

agent.change_set.created

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
