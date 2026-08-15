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

只发送修改字段：

```json
{
  "name": "新的项目名"
}
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

Response：

```json
[
  {
    "id": "comfyui_local",

    "name": "Local ComfyUI",

    "type": "image",

    "status": "connected",

    "capabilities": {
      "image_generation": true,
      "reference_image": true
    }
  }
]
```

---

# 48. Test ComfyUI

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

  "latency_ms": 12
}
```

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

shot.version.created

shot.active_version.changed

shot.dirty_state.changed
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

    "change_set_id": "changeset_101"
  }
}
```

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

provider.error
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

# 93. Timeline API 预留

未来：

```text
GET /episodes/{id}/timeline

POST /timeline/items

PATCH /timeline/items/{id}
```

MVP 可暂不实现。

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

Characters Summary

Provider Status

Active Agent Runs

Active Generations
```

用于快速启动工作区。

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

  "image_edit": false,

  "reference_image": true
}
```

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

/characters

/characters/{id}

/agent/director/runs

/agent/runs/{id}

/agent/runs/{id}/resume

/generations

/generations/{id}

/generations/{id}/retry

/assets

/providers

/providers/comfyui/test

/health
```

---

# 143. MVP 必须实现的 Events

```text
shot.updated

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

asset.created

character.created

character.updated

character.deleted

provider.connected

provider.disconnected
```

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
