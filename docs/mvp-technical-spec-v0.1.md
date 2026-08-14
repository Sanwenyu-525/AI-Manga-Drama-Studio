# AI 漫剧 Studio MVP Technical Specification / 开发任务拆解 v0.1

> 文档类型：**MVP Technical Specification**
> 状态：**draft**（主创定稿，MVP 开发任务拆解的事实源）
> 目标阶段：MVP 0.1
> 开发目标：打通从小说导入 → AI 分析 → Scene → Shot → Storyboard → AI Director 修改 → ComfyUI 生成 → Asset / Version 回填的完整闭环
> 推荐技术栈：Tauri + React + TypeScript + FastAPI + SQLAlchemy + SQLite + LangChain + LangGraph + ComfyUI
> 关联文档：[PRD v0.1](./prd-v0.1.md) · [系统架构设计 v0.1](./architecture-v0.1.md) · [数据库与 ER 模型设计 v0.1](./database-v0.1.md) · [后端 API 与 Service 架构 v0.1](./backend-architecture-v0.1.md) · [AI Director Agent 详细设计 v0.1](./agent-director-v0.1.md) · [前端 UX / 信息架构设计 v0.1](./frontend-ux-v0.1.md) · [前后端 API + Event Contract v0.1](./api-event-contract-v0.1.md)

---

# 1. MVP 最终目标

MVP 不追求：

```text
完整 AI 漫剧生产平台
```

第一阶段只验证：

> **AI 是否能够可靠地操作一个结构化漫剧项目，并通过 ComfyUI 完成真实媒体生成。**

必须跑通：

```text
Create Project
      ↓
Import Novel
      ↓
AI Analyze
      ↓
Create Scenes
      ↓
Generate Shots
      ↓
Storyboard
      ↓
Select Shot
      ↓
AI Director Edit
      ↓
Generate Image
      ↓
ComfyUI
      ↓
Import Result
      ↓
Media Version
      ↓
Storyboard Update
```

---

# 2. MVP 核心成功标准

MVP 完成后，用户应该能够：

1. 创建一个漫剧 Project。
2. 导入一章小说。
3. 使用 AI 自动识别 Scene。
4. 自动将 Scene 拆成 Shot。
5. 在 Storyboard 查看 Shot。
6. 手动编辑 Shot。
7. 对 AI Director 说：

```text
"把这个镜头改成近景。"
```

8. Agent 自动识别当前选中的 Shot 并修改。
9. 用户点击生成图片。
10. Studio 调用本地 ComfyUI。
11. 显示实时生成状态。
12. 图片生成完成后自动进入对应 Shot。
13. 保留旧图片 Version。
14. 支持重新生成。
15. 支持查看 Generation 失败原因。

如果以上全部完成：

> MVP 成立。

---

# 3. MVP 暂不包含

以下全部延后：

```text
完整视频工作流

专业 Timeline Editor

音频工作站

自动配音

字幕编辑器

完整 Continuity Engine

完整 Director Canvas

多人协作

Cloud Sync

插件市场

多 Agent

自动 Provider Router

团队权限

完整 RAG

复杂 MCP

云端 GPU 调度
```

---

# 4. MVP 架构范围

MVP 包含三个 Runtime。

```text
Application Runtime
+
Agent Runtime
+
Generation Runtime
```

---

# 5. Application Runtime

负责：

```text
Project

Episode

Scene

Shot

Character

Asset

Generation

Version
```

技术：

```text
FastAPI

SQLAlchemy

SQLite
```

---

# 6. Agent Runtime

负责：

```text
Intent

Context

Plan

Tool

Review
```

技术：

```text
LangGraph

LangChain
```

MVP 只实现：

```text
One Director Agent

+

Studio Tools
```

---

# 7. Generation Runtime

负责：

```text
Generation Queue

ComfyUI

Progress

Result

Failure

Retry
```

MVP：

```text
asyncio Queue
+
Generation Worker
+
ComfyUI Provider
```

暂时不引入：

```text
Redis

Celery

Temporal
```

---

# 8. MVP 技术栈

## Desktop

```text
Tauri
```

## Frontend

```text
React

TypeScript

Vite

Zustand

TanStack Query
```

第一版 Storyboard 不一定需要 React Flow。

---

## Backend

```text
Python

FastAPI

Pydantic

SQLAlchemy

Alembic

SQLite

httpx

WebSocket

asyncio
```

---

## AI

```text
LangChain

LangGraph
```

---

## Image Generation

```text
ComfyUI
```

MVP 默认：

```text
External ComfyUI Server
```

用户自行启动。

---

# 9. 推荐 Monorepo

```text
ai-manga-studio/

├── apps/
│   └── desktop/
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── backend/
│   ├── app/
│   ├── tests/
│   └── pyproject.toml
│
├── docs/
│
├── workflows/
│
└── README.md
```

---

# 10. Backend 目录

```text
backend/app/

├── main.py

├── api/

├── domain/

├── db/

├── repositories/

├── services/

├── agents/

├── llm/

├── providers/

├── generations/

├── events/

└── core/
```

---

# 11. Frontend 目录

```text
frontend/src/

├── app/

├── components/

├── features/

│   ├── project/
│   ├── scenes/
│   ├── storyboard/
│   ├── shots/
│   ├── assets/
│   ├── generation/
│   └── director/

├── stores/

├── api/

├── events/

├── types/

└── routes/
```

---

# 12. 开发 Epic 总览

MVP 推荐拆成 10 个 Epic。

```text
Epic 01
Project Skeleton

Epic 02
Domain + Database

Epic 03
Core Application Services

Epic 04
REST API

Epic 05
Frontend Studio Shell

Epic 06
Storyboard

Epic 07
LLM Script / Shot Planning

Epic 08
ComfyUI Generation

Epic 09
AI Director

Epic 10
Integration + Stabilization
```

---

# 13. Epic 01 — Project Skeleton

目标：

> 所有工程能够启动并通信。

---

## Backend Tasks

```text
BE-001
初始化 Python 项目

BE-002
安装 FastAPI

BE-003
创建 app/main.py

BE-004
配置 CORS

BE-005
建立 Config System

BE-006
建立 Logging

BE-007
GET /api/v1/health
```

---

## Frontend Tasks

```text
FE-001
创建 React + TypeScript

FE-002
配置 Vite

FE-003
建立基础 Router

FE-004
建立 API Client

FE-005
建立 Studio Shell
```

---

## Desktop Tasks

```text
DT-001
创建 Tauri App

DT-002
嵌入 React Frontend

DT-003
开发环境启动 Backend

DT-004
配置 localhost 通信
```

---

# 14. Epic 01 验收

打开 Desktop：

```text
Studio UI
```

成功调用：

```text
GET /health
```

显示：

```text
Backend Connected
```

---

# 15. Epic 02 — Domain + Database

目标：

> 建立真实 Project State。

MVP 表：

```text
projects

episodes

scenes

shots

characters

shot_characters

assets

generations

media_versions
```

---

# 16. Backend Domain Tasks

```text
BE-101
Project Model

BE-102
Episode Model

BE-103
Scene Model

BE-104
Shot Model

BE-105
Character Model

BE-106
Asset Model

BE-107
Generation Model

BE-108
MediaVersion Model
```

---

# 17. 数据库基础

```text
BE-110
SQLAlchemy Base

BE-111
SQLite Config

BE-112
DB Session

BE-113
Alembic

BE-114
Initial Migration
```

---

# 18. Shot 最低字段

必须支持：

```text
id

scene_id

shot_number

shot_order

shot_type

camera_angle

camera_movement

duration

action

emotion

image_prompt

status

dirty_state

revision

created_at

updated_at
```

---

# 19. Asset 最低字段

```text
id

project_id

type

name

file_path

thumbnail_path

width

height

metadata

created_at
```

---

# 20. Generation 最低字段

```text
id

project_id

shot_id

type

provider

status

parameters

output_asset_id

error_message

created_at

started_at

completed_at
```

---

# 21. Epic 02 验收

能够通过 Python 测试：

```text
Create Project

↓

Create Episode

↓

Create Scene

↓

Create Shot

↓

Query Shot
```

数据库重启后数据仍存在。

---

# 22. Epic 03 — Application Services

目标：

> 所有业务逻辑通过 Service 操作。

---

# 23. ProjectService

Tasks：

```text
BE-201
create_project

BE-202
get_project

BE-203
list_projects

BE-204
update_project
```

---

# 24. EpisodeService

```text
BE-210
create_episode

BE-211
import_source_text

BE-212
get_episode
```

---

# 25. SceneService

```text
BE-220
create_scene

BE-221
list_scenes

BE-222
update_scene

BE-223
delete_scene
```

---

# 26. ShotService

```text
BE-230
create_shot

BE-231
list_shots

BE-232
get_shot

BE-233
update_shot

BE-234
delete_shot

BE-235
reorder_shots

BE-236
increment_revision
```

---

# 27. AssetService

```text
BE-240
register_asset

BE-241
copy_file_into_project

BE-242
get_asset

BE-243
list_assets

BE-244
create_thumbnail
```

---

# 28. VersionService

```text
BE-250
create_media_version

BE-251
set_active_version

BE-252
list_shot_versions
```

MVP 暂时只做：

```text
Media Version
```

不先做完整 Shot Snapshot。

---

# 29. Epic 03 红线

API Router 不能：

```text
db.query()
```

直接写业务。

必须：

```text
Router
↓
Service
↓
Repository
```

---

# 30. Epic 03 验收

Service Test：

```text
ShotService.update_shot()
```

必须：

```text
更新数据

revision + 1
```

并正确返回 DTO。

---

# 31. Epic 04 — REST API

目标：

> Frontend 可以操作 Project State。

---

# 32. MVP Project API

```text
POST /api/v1/projects

GET /api/v1/projects

GET /api/v1/projects/{id}

PATCH /api/v1/projects/{id}
```

---

# 33. Episode API

```text
POST /api/v1/projects/{id}/episodes

GET /api/v1/episodes/{id}
```

---

# 34. Scene API

```text
GET /api/v1/episodes/{id}/scenes

POST /api/v1/episodes/{id}/scenes

PATCH /api/v1/scenes/{id}
```

---

# 35. Shot API

```text
GET /api/v1/scenes/{id}/shots

GET /api/v1/shots/{id}

POST /api/v1/scenes/{id}/shots

PATCH /api/v1/shots/{id}
```

---

# 36. Storyboard API

增加：

```text
GET /api/v1/scenes/{scene_id}/storyboard
```

返回：

```text
Scene Summary

+

ShotSummary[]
```

---

# 37. Epic 04 验收

使用 API Client 能：

```text
Create Project
↓

Create Episode
↓

Create Scene
↓

Create Shot
↓

Modify Shot
```

全部通过 HTTP 完成。

---

# 38. Epic 05 — Studio Shell

目标：

> 建立真正的桌面 Studio 外壳。

---

# 39. 主布局

```text
Top Bar

Left Project Explorer

Main Workspace

Right Panel

Bottom Dock
```

---

# 40. Frontend Tasks

```text
FE-101
AppShell

FE-102
TopBar

FE-103
ProjectExplorer

FE-104
WorkspaceContainer

FE-105
RightPanel

FE-106
BottomDock
```

---

# 41. Zustand Stores

实现：

```text
selectionStore

workspaceStore

uiStore

agentStore

generationStore
```

---

# 42. TanStack Query

实现 Query：

```text
projects

project

episodes

scenes

storyboard

shot

assets
```

---

# 43. Project Explorer MVP

只显示：

```text
Project

Episode

Scene

Shot
```

暂时不显示：

```text
Workflow

Timeline

复杂 Asset Tree
```

---

# 44. Epic 05 验收

用户：

```text
打开 Project
↓

点击 Scene
↓

中央切换 Storyboard
```

并且选择状态保存到：

```text
selectionStore
```

---

# 45. Epic 06 — Storyboard

目标：

> 用户可以真正以 Shot 为中心工作。

---

# 46. ShotCard

必须显示：

```text
Shot Number

Image / Placeholder

Shot Type

Duration

Status
```

---

# 47. Shot Inspector

支持编辑：

```text
shot_type

camera_angle

camera_movement

duration

action

emotion

image_prompt
```

---

# 48. Shot Update

Inspector 修改：

```text
PATCH /shots/{id}
```

成功后：

```text
TanStack Query Refresh
```

---

# 49. Storyboard Tasks

```text
FE-201
StoryboardGrid

FE-202
ShotCard

FE-203
ShotInspector

FE-204
Selection Logic

FE-205
Shot Status Badge

FE-206
Empty State
```

---

# 50. Multi-select

MVP 可延后。

第一版只要求：

```text
Single Shot Selection
```

---

# 51. Epic 06 验收

用户可以：

```text
点击 Shot 05

↓

右边看到参数

↓

修改 medium → close_up

↓

保存

↓

ShotCard 更新
```

---

# 52. Epic 07 — LLM Script / Shot Planning

目标：

> 导入小说后自动产生结构化 Scene 和 Shot。

---

# 53. LangChain Integration

实现：

```text
LLMGateway
```

内部：

```text
LangChain Model
```

---

# 54. 第一版只需一个 LLM Provider

例如：

```text
OpenAI-compatible
```

抽象接口仍保留。

不要第一版同时接五家模型。

---

# 55. Structured Schemas

实现：

```text
ScenePlan

ShotPlan
```

---

# 56. ScenePlan

例如：

```text
scene_number

title

location

time

description

mood
```

---

# 57. ShotPlan

```text
shot_number

shot_type

camera_angle

camera_movement

duration

action

emotion

dialogue

image_prompt
```

---

# 58. ScriptService

实现：

```text
analyze_episode()

generate_scene_plans()

generate_shot_plans()
```

---

# 59. Analyze API

```text
POST /episodes/{id}/analyze
```

MVP 可先同步处理短文本。

但接口设计仍建议：

```text
202 Operation
```

---

# 60. Review Before Commit

AI分析结果先显示 Preview。

Frontend：

```text
AI Analysis Review
```

用户确认：

```text
Create Scenes
```

MVP 如果工期紧，也可以第一版自动创建。

---

# 61. Generate Shots

用户：

```text
Scene
↓
Generate Storyboard
```

后端：

```text
Scene Context
↓
LLM
↓
ShotPlan[]
↓
ShotService
```

---

# 62. Epic 07 验收

输入一段小说文本：

```text
1000–3000 字
```

系统能够生成：

```text
Scenes
+
Shots
```

并在 Storyboard 展示。

---

# 63. Epic 08 — ComfyUI Generation

目标：

> Shot 能真正生成图片。

这是 MVP 最大技术里程碑之一。

---

# 64. ComfyUIClient

实现：

```text
health_check

queue_prompt

get_history

upload_image

download_output

websocket_monitor
```

---

# 65. ComfyUIProvider

实现统一：

```text
submit_image_generation()
```

---

# 66. Workflow Template

第一版只支持：

```text
一个固定 Workflow
```

不要一开始做 Workflow Editor。

文件：

```text
workflows/default_image_api.json
```

---

# 67. Parameter Mapping

第一版只支持：

```text
prompt

negative_prompt

seed
```

需要时：

```text
width

height
```

---

# 68. GenerationService

实现：

```text
create_generation

queue_generation

retry_generation

cancel_generation

complete_generation

fail_generation
```

---

# 69. GenerationWorker

使用：

```text
asyncio.Queue
```

任务：

```text
Queue
↓
Worker
↓
Provider
↓
ComfyUI
```

---

# 70. Generation API

```text
POST /shots/{id}/generations
```

Request：

```text
type=image

provider=comfyui
```

---

# 71. Generation Result

完成后：

```text
ComfyUI Output
↓
AssetService
↓
Asset
↓
MediaVersion
↓
Shot Active Image
```

---

# 72. 文件命名

例如：

```text
EP01_SC03_SH005_IMG_V001.png
```

第二次：

```text
EP01_SC03_SH005_IMG_V002.png
```

永不覆盖 V1。

---

# 73. Generation Queue UI

Bottom Dock：

```text
Shot 05

Generating 64%
```

支持：

```text
Queued

Running

Completed

Failed
```

---

# 74. WebSocket Events

MVP 最少：

```text
generation.queued

generation.started

generation.progress

generation.completed

generation.failed
```

---

# 75. Epic 08 验收

用户：

```text
点击 Shot 05
↓

Generate Image
↓

Studio 显示 Running
↓

ComfyUI 生成
↓

图片出现
↓

ShotCard 自动刷新
```

再次 Generate：

```text
生成 V2
```

旧 V1 保留。

---

# 76. Epic 09 — AI Director

目标：

> AI 能真正操作 Studio。

---

# 77. Director MVP 能力

只支持：

```text
Get Shot

Update Shot

Generate Image
```

先不要做复杂全场重构。

---

# 78. DirectorState

第一版：

```text
project_id

user_message

selection

intent

context

plan

tool_results

status

final_result
```

---

# 79. MVP Graph

```text
START
 ↓
Understand
 ↓
Load Context
 ↓
Plan
 ↓
Execute
 ↓
Review
 ↓
END
```

第一版甚至可以没有：

```text
Complex Retry

Multi-Agent
```

---

# 80. Director Tools

只做三个：

```text
get_shot

update_shot

generate_image
```

第四个：

```text
get_scene_shots
```

可选。

---

# 81. Selection Context

Frontend 调 Agent：

```text
selected_shot_id
```

例如：

用户选 Shot 05：

```text
"这个改成近景。"
```

Agent必须解析到：

```text
shot_005
```

---

# 82. Agent API

```text
POST /agent/director/runs
```

输入：

```text
message

project_id

selection
```

---

# 83. AI Director Panel

MVP 只需要：

```text
Message List

Input Box

Current Status

Action List
```

---

# 84. Agent Event

最少：

```text
agent.run.started

agent.plan.created

agent.tool.started

agent.tool.completed

agent.run.completed

agent.run.failed
```

---

# 85. 第一条 Agent 测试

用户选择 Shot 05。

输入：

```text
把这个镜头改成近景。
```

预期：

```text
resolve shot_005

↓

update_shot

↓

Shot 更新

↓

UI 刷新
```

---

# 86. 第二条 Agent 测试

输入：

```text
把这个改成近景，然后重新生成。
```

预期：

```text
update_shot

↓

generate_image

↓

Agent completed

↓

Generation continues
```

---

# 87. Epic 09 验收

AI Director 能稳定完成：

```text
自然语言
↓
Project Operation
```

而不是只回答：

```text
"好的，我建议改成近景。"
```

---

# 88. Epic 10 — Integration & Stabilization

目标：

> 把 Demo 变成真正可使用的 MVP。

---

# 89. Integration Tasks

```text
INT-001
Project Create Flow

INT-002
Novel Import Flow

INT-003
Scene Generate Flow

INT-004
Storyboard Flow

INT-005
Shot Edit Flow

INT-006
Generation Flow

INT-007
AI Director Flow
```

---

# 90. Error Handling

必须覆盖：

```text
Backend disconnected

LLM API unavailable

Invalid structured output

ComfyUI unavailable

ComfyUI generation failure

File import failure

Database conflict

Generation cancelled
```

---

# 91. Provider Status

TopBar：

```text
ComfyUI ●
```

失败：

```text
ComfyUI ○
```

点击打开：

```text
Connection Details
```

---

# 92. Loading UX

所有 > 300ms 的操作必须有：

```text
Loading
```

长任务：

```text
Progress / Status
```

---

# 93. Empty UX

必须设计：

```text
No Projects

No Scenes

No Shots

No Image

No Generation
```

不要出现裸空白区域。

---

# 94. Testing Strategy

MVP 至少：

```text
Unit Test

API Integration Test

Agent Scenario Test

ComfyUI Integration Test

Frontend Smoke Test
```

---

# 95. Backend Unit Tests

重点：

```text
ShotService

GenerationService

VersionService

WorkflowMapper
```

---

# 96. API Integration Tests

测试：

```text
Project CRUD

Scene CRUD

Shot CRUD

Generation Create

Generation Retry
```

---

# 97. Agent Scenario Tests

必须固定测试：

## Scenario A

```text
Selection = Shot05

User:
"改成近景"
```

预期：

```text
Shot05.shot_type = close_up
```

---

## Scenario B

```text
User:
"改成近景再生成"
```

预期：

```text
Shot Update
+
Generation Created
```

---

## Scenario C

```text
没有 Selection

User:
"把这个改一下"
```

预期：

```text
Agent 不应猜
```

应要求明确目标。

---

# 98. ComfyUI Test

准备：

```text
Known Workflow

Known Prompt
```

CI 不一定执行真实 ComfyUI。

开发环境 Integration Test执行。

---

# 99. Mock Provider

强烈建议建立：

```text
MockImageProvider
```

返回固定测试图片。

这样前端开发不需要每次跑 GPU。

---

# 100. Mock LLM

建立：

```text
FakeLLMGateway
```

固定返回：

```text
ScenePlan

ShotPlan

Intent
```

方便测试 Agent。

---

# 101. 开发环境模式

支持：

```text
APP_ENV=development
```

配置：

```text
Mock LLM

Mock Image Provider

Local ComfyUI
```

自由切换。

---

# 102. MVP 开发优先级

建议使用：

```text
P0
必须

P1
重要

P2
以后
```

---

# 103. P0

```text
Project

Scene

Shot

Storyboard

LLM Shot Planning

ComfyUI Generation

Media Version

AI Director basic edit

Generation Progress
```

---

# 104. P1

```text
Character Management

Better Prompt Editing

Generation Retry

Provider Settings

Basic Version Browser

Project Bootstrap
```

---

# 105. P2

```text
Continuity

Timeline

Canvas

Video

Audio

Multi-Agent
```

---

# 106. 推荐开发顺序

严格建议：

```text
1 Project Skeleton

2 Database

3 Services

4 CRUD API

5 Frontend Shell

6 Storyboard

7 LLM Scene / Shot Planning

8 ComfyUI

9 Generation Queue

10 AI Director

11 Integration

12 Polish
```

---

# 107. 为什么 Agent 不先开发

因为 Agent必须操作：

```text
ShotService

GenerationService
```

如果这些不存在：

Agent就只能：

```text
说
```

而不能：

```text
做
```

---

# 108. Milestone 0

项目能启动。

```text
Frontend
↔
Backend
```

---

# 109. Milestone 1

**Project State**

```text
Project
↓
Scene
↓
Shot
```

完整 CRUD。

---

# 110. Milestone 2

**Storyboard**

用户真正能操作 Shot。

---

# 111. Milestone 3

**AI Planning**

```text
Novel
↓
AI
↓
Scenes
↓
Shots
```

---

# 112. Milestone 4

**Real Generation**

```text
Shot
↓
ComfyUI
↓
Image
```

这是第一个非常重要 Demo。

---

# 113. Milestone 5

**Agent**

```text
Natural Language
↓
ShotService
```

---

# 114. Milestone 6

**Complete MVP**

```text
Novel
↓
Storyboard
↓
AI Director
↓
ComfyUI
↓
Version
```

形成完整产品闭环。

---

# 115. MVP Demo Script

最终展示可以这样进行。

---

## Step 1

创建：

```text
《最后一种打法》
```

---

## Step 2

粘贴小说章节。

点击：

```text
AI Analyze
```

---

## Step 3

系统生成：

```text
Scene 01

Scene 02

Scene 03
```

---

## Step 4

打开 Scene 03。

点击：

```text
Generate Storyboard
```

生成：

```text
Shot 01–08
```

---

## Step 5

点击 Shot 05。

用户：

```text
"这个镜头太普通了，改成低机位近景。"
```

---

## Step 6

AI Director：

```text
Plan

✓ 修改 Shot 05 景别
✓ 修改 Camera Angle
✓ 更新 Prompt
```

Storyboard 自动刷新。

---

## Step 7

用户：

```text
"生成。"
```

或者点击：

```text
Generate Image
```

---

## Step 8

Bottom Dock：

```text
Shot 05
ComfyUI
Generating 73%
```

---

## Step 9

生成完成。

Shot Card 自动出现图片。

---

## Step 10

用户：

```text
"这个脸不太行，再生成一版。"
```

系统生成：

```text
V2
```

V1 仍保留。

这一套 Demo 已经足以非常明确地体现：

> **AI 漫剧 Studio ≠ 普通聊天 Agent。**

---

# 116. MVP 性能目标

第一版建议：

```text
Project 打开
< 2 秒

Storyboard 100 Shots
流畅滚动

Shot Update
< 300ms 本地响应

Agent Status
实时反馈

Generation Event
< 500ms UI 延迟
```

---

# 117. 数据规模目标

MVP 至少支持：

```text
10 Projects

20 Episodes / Project

100 Scenes / Project

1000 Shots / Project

5000 Assets
```

不要求极端优化。

但架构不能假设：

```text
一个 Project 只有20个 Shot。
```

---

# 118. 日志

必须记录：

```text
Backend

Agent

Generation

ComfyUI
```

包含：

```text
project_id

shot_id

run_id

generation_id

request_id
```

---

# 119. Developer Mode

建议增加：

```text
Developer Mode
```

显示：

```text
Agent Run

Tool Call

Generation ID

Workflow ID

ComfyUI Error
```

普通用户不显示。

---

# 120. MVP 代码质量要求

关键原则：

```text
No business logic in routers

No SQL in Agent Tools

No ComfyUI protocol in frontend

No LangGraph types in frontend

No provider-specific logic in ShotService
```

---

# 121. Definition of Done

一个 Feature 完成必须：

```text
功能实现

Error Handling

Loading State

Type Definition

API Contract

Basic Test

Logging
```

不能：

```text
"能跑一下就算完成。"
```

---

# 122. Git Branch 建议

如果个人开发：

```text
main

develop

feature/*
```

例如：

```text
feature/project-domain

feature/storyboard

feature/comfyui-provider

feature/director-agent
```

---

# 123. Commit 范围

尽量：

```text
一个 commit
=
一个明确行为变化
```

例如：

```text
feat: add shot update API

feat: add comfyui generation worker

fix: preserve previous media version
```

---

# 124. MVP 文档同步

代码开发过程中必须同步维护：

```text
API Contract

Database Schema

Agent Tools

Events
```

尤其：

```text
Agent Tool Schema
```

不能只存在 Prompt 里。

---

# 125. 推荐开发阶段划分

可以将实际开发拆成四阶段。

## Stage A — Core Studio

```text
Project
Scene
Shot
Storyboard
```

## Stage B — AI Planning

```text
Novel
↓
Scene
↓
Shot
```

## Stage C — Production

```text
ComfyUI
Generation
Version
```

## Stage D — Agent

```text
AI Director
```

---

# 126. Stage A 结束验收

无需任何 AI。

Studio 已经可以：

```text
创建项目

手动创建 Scene

手动创建 Shot

编辑 Storyboard
```

如果做不到：

不要开始 Agent。

---

# 127. Stage B 结束验收

AI能够：

```text
Novel
→
Structured Scene / Shot
```

但暂时不生成图片。

---

# 128. Stage C 结束验收

用户通过按钮：

```text
Generate
```

即可完成：

```text
Shot
→
ComfyUI
→
Image
```

---

# 129. Stage D 结束验收

用户通过自然语言：

```text
"把这个改近一点然后生成"
```

即可调用：

```text
ShotService
+
GenerationService
```

---

# 130. MVP 最核心技术闭环

最终只有这一条链路真正重要：

```text
User Intent
     │
     ▼
AI Director
     │
     ▼
Project State
     │
     ▼
Shot
     │
     ▼
GenerationService
     │
     ▼
ComfyUI
     │
     ▼
Asset
     │
     ▼
Version
     │
     ▼
Storyboard
```

---

# 131. MVP 产品壁垒验证

第一版不是验证：

```text
"AI能不能生成图片"
```

这件事 ComfyUI 已经可以。

也不是验证：

```text
"LLM能不能拆分镜"
```

这也不是核心壁垒。

真正验证：

> **AI 能否可靠地理解结构化漫剧项目，并对项目执行连续、可视化、可追踪的生产操作。**

---

# 132. MVP 最终交付物

开发结束至少应包含：

```text
Desktop Application

FastAPI Backend

SQLite Database

Storyboard UI

AI Scene / Shot Planning

AI Director

ComfyUI Integration

Generation Queue

Asset Management

Basic Version Management

Developer Logs

Automated Tests

README

Architecture Docs
```

---

# 133. 简历项目可以形成的技术描述

项目完成后，可以概括为：

> 设计并开发 AI 原生漫剧制作 Studio，采用 Tauri + React + FastAPI 构建桌面全栈系统，以 LangGraph/LangChain 构建有状态 AI Director Agent，通过结构化 Tool Calling 操作 Project / Scene / Shot 等领域对象，并设计独立 Generation Runtime 与 ComfyUI Adapter，实现长任务异步调度、实时 WebSocket 进度同步、媒体版本管理及模型提供方解耦。

这比：

> "做了一个调用大模型的 Agent。"

技术信息密度要高很多。

---

# 134. 第一批实际 Coding Task

如果现在正式开工，建议第一批只创建以下任务：

```text
01 初始化 Git Repository

02 创建 Tauri + React 项目

03 创建 FastAPI 项目

04 建立 /health

05 建立 SQLite

06 Project Model

07 Episode Model

08 Scene Model

09 Shot Model

10 Alembic Migration

11 ProjectService

12 SceneService

13 ShotService

14 Project API

15 Scene API

16 Shot API

17 AppShell

18 ProjectExplorer

19 StoryboardGrid

20 ShotCard
```

完成这 20 个任务后：

> **先得到一个"没有 AI 的漫剧 Studio"。**

然后再接 AI。

这是整个开发过程中最稳的切入点。

---

# 135. 开发总原则

整个 MVP 始终遵循：

### 第一阶段

**Make the Studio work.**

先让软件自己能工作。

### 第二阶段

**Make AI understand it.**

再让 AI 理解 Studio。

### 第三阶段

**Make AI operate it.**

最后让 Agent 操作 Studio。

而不是一开始：

```text
先做一个特别聪明的 Agent

然后再想它到底能操作什么。
```

---

# 136. MVP 最终定义

AI 漫剧 Studio MVP 不是：

```text
一个功能不完整的大型漫剧软件
```

而是：

> **一个只解决"结构化漫剧 + Agent 操作 + ComfyUI 生成"核心问题，但把这一条链路做完整的产品。**

如果这一条链路足够稳定：

后面的：

```text
Video

Continuity

Timeline

Multi-Agent

Voice

BGM

Cloud

Collaboration
```

全部只是在这个基础上继续增加能力。

这才是正确的 MVP。
