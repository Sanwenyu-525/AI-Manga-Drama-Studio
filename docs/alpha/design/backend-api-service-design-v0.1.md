# AI 漫剧 Studio Alpha Backend API & Service 详细设计 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**上游文档：**

* 《AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1》
* 《AI 漫剧 Studio 核心领域模型详细设计 v0.1》
* 《AI 漫剧 Studio 数据库 Schema 与数据关系设计 v0.1》

**目标：** 将已经确定的领域模型和数据库 Schema 转换为可直接实施的 Backend API、Application Service、Domain Service、Repository、Agent Runtime、Job Queue、Workflow Adapter 和 Provider Adapter 架构。

---

# 1. Alpha 后端的核心职责

Alpha Backend 不应该只是：

```text
Controller
 ↓
CRUD Service
 ↓
Database
```

真正职责应包含：

```text
Project State
+
Domain Rules
+
AI Orchestration
+
Generation Scheduling
+
Asset Management
+
Version Management
+
Workflow Execution
+
Continuity
+
Progress Events
```

最终形成：

```text
Studio UI
   ↓
Backend Application Layer
   ↓
Domain Layer
   ↓
Generation / Agent Orchestration
   ↓
Provider Adapter
   ↓
ComfyUI / LLM / Image / Video / Voice
```

---

# 2. 推荐技术架构

结合当前 AI 漫剧 Studio 的特点，推荐采用：

```text
Desktop Studio
      │
      │ HTTP / SSE / WebSocket
      ▼
┌───────────────────────────┐
│ Studio Core Backend       │
│                           │
│ Project                   │
│ Episode / Scene / Shot    │
│ Asset                     │
│ Generation                │
│ Version                   │
│ Job                       │
│ Timeline                  │
│ Continuity                │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ AI Orchestration Layer    │
│                           │
│ Director                  │
│ Script                    │
│ Visual                    │
│ Prompt                    │
│ Continuity                │
│ LangChain / LangGraph     │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Provider Layer            │
│                           │
│ ComfyUI                    │
│ LLM                       │
│ Image                     │
│ Video                     │
│ Voice                     │
└───────────────────────────┘
```

---

# 3. 关于 Java 与 LangChain 的建议

考虑 Studio 后端业务复杂度和 AI Agent 特性，推荐采用：

```text
Core Backend
=
Java + Spring Boot
```

负责：

```text
Project
Asset
Generation
Version
Job
Workflow
Timeline
Database
Business Rules
```

AI Runtime 推荐：

```text
Python
+
LangChain
+
LangGraph
```

负责：

```text
Director Agent
Script Agent
Visual Agent
Continuity Agent
LLM Tool Calling
Agent Graph
```

架构：

```text
Spring Boot
      │
      │ Internal API
      ▼
Python Agent Runtime
      │
      ▼
LangGraph
      │
      ▼
LLM
```

但 Alpha 不要求立即拆成两个独立服务。

---

# 4. Alpha 推荐渐进实现

## Alpha A

如果 MVP 当前是单体：

```text
Studio Backend
```

先按模块分层。

不要立即微服务化。

---

## Alpha B

当 Agent 复杂起来后：

```text
Studio Core
    +
Agent Runtime
```

再拆。

因此代码层必须从一开始就定义：

```text
AgentGateway
```

而不是业务层直接：

```text
LangChain.invoke(...)
```

---

# 5. 最终 Backend 逻辑架构

```text
┌────────────────────────────────────┐
│ API Layer                          │
│                                    │
│ REST                               │
│ SSE / WebSocket                    │
└──────────────────┬─────────────────┘
                   ↓
┌────────────────────────────────────┐
│ Application Layer                  │
│                                    │
│ Command Services                   │
│ Query Services                     │
│ Transaction                        │
│ DTO Mapping                        │
└──────────────────┬─────────────────┘
                   ↓
┌────────────────────────────────────┐
│ Domain Layer                       │
│                                    │
│ Aggregate                          │
│ Domain Service                     │
│ Domain Event                       │
│ Repository Interface               │
└──────────────────┬─────────────────┘
                   ↓
┌────────────────────────────────────┐
│ Orchestration Layer                │
│                                    │
│ Generation Planner                 │
│ Job Scheduler                      │
│ Agent Orchestrator                 │
│ Workflow Resolver                  │
└──────────────────┬─────────────────┘
                   ↓
┌────────────────────────────────────┐
│ Infrastructure                     │
│                                    │
│ SQLite                             │
│ File Storage                       │
│ ComfyUI                            │
│ LangChain / LangGraph              │
│ AI Provider APIs                   │
└────────────────────────────────────┘
```

---

# 6. 后端模块划分

推荐按业务模块，而不是全局：

```text
controller/
service/
repository/
entity/
```

建议：

```text
studio
├── project
├── source
├── episode
├── scene
├── shot
├── character
├── location
├── asset
├── prompt
├── generation
├── job
├── workflow
├── agent
├── continuity
├── timeline
├── provider
├── storage
└── common
```

---

# 7. 单模块内部结构

例如：

```text
shot
├── api
│   ├── ShotController
│   ├── request
│   └── response
│
├── application
│   ├── ShotApplicationService
│   ├── ShotQueryService
│   ├── command
│   └── dto
│
├── domain
│   ├── Shot
│   ├── ShotVisualSpec
│   ├── ShotStatus
│   ├── ShotRepository
│   ├── ShotDomainService
│   └── event
│
└── infrastructure
    ├── ShotRepositoryImpl
    └── persistence
```

---

# 8. API 基础规范

统一：

```text
/api/v1
```

例如：

```text
/api/v1/projects
/api/v1/projects/{projectId}/episodes
/api/v1/shots/{shotId}
```

---

# 9. API 返回格式

成功时不强制再包：

```json
{
  "code": 200,
  "data": {}
}
```

建议直接返回资源：

```json
{
  "id": "01K...",
  "name": "Episode 01",
  "status": "DRAFT"
}
```

错误统一：

```json
{
  "error": {
    "code": "SHOT_NOT_FOUND",
    "message": "Shot does not exist.",
    "details": {
      "shotId": "01K..."
    },
    "requestId": "req_01K..."
  }
}
```

---

# 10. Error Code 分类

统一格式：

```text
MODULE_ERROR
```

例如：

```text
PROJECT_NOT_FOUND

PROJECT_ARCHIVED

SHOT_NOT_FOUND

SHOT_REVISION_CONFLICT

ASSET_NOT_FOUND

ASSET_FILE_MISSING

GENERATION_FAILED

GENERATION_ALREADY_RUNNING

JOB_NOT_RESUMABLE

WORKFLOW_NOT_FOUND

WORKFLOW_INPUT_INVALID

PROVIDER_UNAVAILABLE

COMFYUI_CONNECTION_FAILED

AGENT_OUTPUT_INVALID

CONTINUITY_CONFLICT
```

---

# 11. HTTP 状态码

建议：

```text
200 OK

201 Created

202 Accepted

204 No Content

400 Bad Request

404 Not Found

409 Conflict

422 Unprocessable Entity

500 Internal Server Error

502 Provider Error

503 Provider Unavailable
```

其中：

```text
202 Accepted
```

非常重要。

所有异步 AI 任务应该：

```text
POST Generate
```

立即返回：

```text
202
```

而不是阻塞 HTTP 请求数分钟。

---

# 12. 异步任务统一返回

例如：

```http
POST /api/v1/shots/{shotId}/generate-video
```

返回：

```json
{
  "jobId": "job_01K...",
  "taskId": "task_01K...",
  "generationId": "gen_01K...",
  "status": "QUEUED"
}
```

---

# 13. Project API

## 创建 Project

```http
POST /api/v1/projects
```

Request：

```json
{
  "name": "最后一种打法",
  "projectType": "MANGA_DRAMA",
  "aspectRatio": "9:16",
  "resolution": {
    "width": 1080,
    "height": 1920
  },
  "fps": 24
}
```

---

# 14. Project API 列表

```text
POST   /projects

GET    /projects

GET    /projects/{projectId}

PATCH  /projects/{projectId}

POST   /projects/{projectId}/open

POST   /projects/{projectId}/archive

POST   /projects/{projectId}/restore

GET    /projects/{projectId}/tree

GET    /projects/{projectId}/settings

PUT    /projects/{projectId}/settings
```

---

# 15. ProjectApplicationService

```text
ProjectApplicationService
```

负责：

```text
createProject()

openProject()

updateProject()

archiveProject()

restoreProject()

updateProjectSettings()
```

不负责：

```text
生成视频
Agent 分镜
Asset Storage
```

---

# 16. ProjectTree Query

前端最常用接口之一：

```http
GET /projects/{projectId}/tree
```

返回：

```json
{
  "project": {},
  "episodes": [],
  "scenes": [],
  "shots": []
}
```

前端自己 Normalize。

不要：

```text
Episode
 └ Scene
    └ Shot
       └ Assets
          └ Generation
```

返回无限深对象。

---

# 17. Source Document API

```text
POST   /projects/{projectId}/documents

GET    /projects/{projectId}/documents

GET    /documents/{documentId}

PATCH  /documents/{documentId}

POST   /documents/{documentId}/archive
```

文件导入：

```http
POST /projects/{projectId}/documents/import
```

支持：

```text
txt
md
docx
pdf
```

解析后形成：

```text
SourceDocument
```

原始文件同时作为：

```text
SOURCE_DOCUMENT Asset
```

保存。

---

# 18. Episode API

```text
POST   /projects/{projectId}/episodes

GET    /projects/{projectId}/episodes

GET    /episodes/{episodeId}

PATCH  /episodes/{episodeId}

POST   /episodes/{episodeId}/archive

POST   /episodes/{episodeId}/reorder

POST   /episodes/{episodeId}/plan
```

其中：

```text
/plan
```

用于 AI Director。

---

# 19. AI Episode Planning

例如：

```http
POST /episodes/{episodeId}/plan
```

Request：

```json
{
  "sourceDocumentId": "doc_xxx",
  "mode": "AUTO",
  "targetDuration": 180
}
```

返回：

```text
202 Accepted
```

创建：

```text
Job
→ Agent Task
```

而不是同步生成所有 Scene。

---

# 20. Scene API

```text
POST   /episodes/{episodeId}/scenes

GET    /episodes/{episodeId}/scenes

GET    /scenes/{sceneId}

PATCH  /scenes/{sceneId}

POST   /scenes/{sceneId}/archive

POST   /scenes/{sceneId}/reorder

POST   /scenes/{sceneId}/plan-shots

POST   /scenes/{sceneId}/generate

GET    /scenes/{sceneId}/editor
```

---

# 21. Scene Editor Query

```http
GET /scenes/{sceneId}/editor
```

返回：

```text
Scene

Shots

Shot Visual Specs

Shot Characters

Active Assets

Latest Generation Status

Continuity Warnings
```

这是 Read Model。

不要求严格对应某个 Aggregate。

---

# 22. Shot API

Shot API 是整个 Studio 最重要的一组接口。

```text
POST   /scenes/{sceneId}/shots

GET    /shots/{shotId}

PATCH  /shots/{shotId}

POST   /shots/{shotId}/duplicate

POST   /shots/{shotId}/move

POST   /shots/{shotId}/archive

PUT    /shots/{shotId}/visual-spec

PUT    /shots/{shotId}/characters

GET    /shots/{shotId}/inspector

GET    /shots/{shotId}/history
```

---

# 23. 更新 Shot

```http
PATCH /shots/{shotId}
```

Request：

```json
{
  "revision": 13,
  "duration": 4.5,
  "shotType": "CLOSE_UP",
  "cameraMovement": "PUSH_IN"
}
```

必须携带：

```text
revision
```

避免：

```text
用户修改
+
Agent 修改
```

互相覆盖。

---

# 24. Revision Conflict

如果数据库：

```text
revision = 14
```

客户端：

```text
revision = 13
```

返回：

```text
409 Conflict
```

```json
{
  "error": {
    "code": "SHOT_REVISION_CONFLICT",
    "message": "Shot has been modified.",
    "details": {
      "expectedRevision": 13,
      "currentRevision": 14
    }
  }
}
```

前端提示：

```text
Reload
Compare
Overwrite
```

Alpha 可以先只支持：

```text
Reload
```

---

# 25. Shot Inspector API

```http
GET /shots/{shotId}/inspector
```

返回：

```json
{
  "shot": {},
  "visualSpec": {},
  "characters": [],
  "activeAssets": {},
  "prompt": {},
  "generationSummary": {},
  "continuity": {},
  "staleWarnings": []
}
```

这是 Inspector 的核心 Query API。

---

# 26. Character API

```text
POST   /projects/{projectId}/characters

GET    /projects/{projectId}/characters

GET    /characters/{characterId}

PATCH  /characters/{characterId}

POST   /characters/{characterId}/archive

POST   /characters/{characterId}/versions

GET    /characters/{characterId}/versions

POST   /characters/{characterId}/versions/{versionId}/set-master

POST   /characters/{characterId}/generate-reference
```

---

# 27. Set Character MASTER

```http
POST /characters/{characterId}/versions/{versionId}/set-master
```

Application Service：

```text
Load Character

Load CharacterVersion

Validate Version belongs to Character

Set oldMaster = false

Set newMaster = true

Update character.masterVersionId

Publish CharacterMasterChanged
```

然后：

```text
DependencyService
```

处理：

```text
STALE
```

---

# 28. 不自动重新生成

`set-master` 绝对不能：

```text
直接重新生成所有 Shot
```

只能：

```text
CharacterMasterChanged
 ↓
DependencyService
 ↓
Affected Resource
 ↓
STALE
```

UI 再决定：

```text
Regenerate affected shots
```

---

# 29. Location API

结构与 Character 类似：

```text
POST   /projects/{projectId}/locations

GET    /projects/{projectId}/locations

GET    /locations/{locationId}

PATCH  /locations/{locationId}

POST   /locations/{locationId}/versions

GET    /locations/{locationId}/versions

POST   /locations/{locationId}/versions/{versionId}/set-master

POST   /locations/{locationId}/generate-reference
```

---

# 30. Asset API

```text
POST   /projects/{projectId}/assets/import

GET    /projects/{projectId}/assets

GET    /assets/{assetId}

GET    /assets/{assetId}/preview

POST   /assets/{assetId}/archive

POST   /assets/{assetId}/restore

POST   /assets/{assetId}/set-active

GET    /assets/{assetId}/provenance

GET    /assets/version-groups/{groupId}
```

---

# 31. Asset Provenance

```http
GET /assets/{assetId}/provenance
```

返回：

```text
Asset

Generated By
→ Generation

Generation Inputs
→ Character Asset
→ Location Asset
→ Prompt Version
→ Workflow Version

Parent Generation
```

最终 UI 可以实现：

```text
How was this generated?
```

---

# 32. AssetService

核心职责：

```text
registerGeneratedAsset()

importAsset()

archiveAsset()

restoreAsset()

createVersion()

activateVersion()

validateFile()

markMissing()

markStale()
```

---

# 33. StorageService

AssetService 不应该：

```text
Files.copy()
```

直接操作文件。

单独：

```text
StorageService
```

接口：

```text
store()

move()

copy()

delete()

exists()

checksum()

resolvePath()

createTempFile()
```

实现：

```text
LocalFileStorage
```

未来可以增加：

```text
S3Storage
OSSStorage
CloudStorage
```

---

# 34. Prompt API

```text
GET    /shots/{shotId}/prompts

POST   /shots/{shotId}/prompts

POST   /prompts/{promptId}/versions

GET    /prompts/{promptId}/versions

POST   /prompts/{promptId}/versions/{versionId}/activate

POST   /shots/{shotId}/prompts/generate
```

---

# 35. Prompt 生成流程

用户：

```text
Generate Prompt
```

后端：

```text
Shot
+
ShotVisualSpec
+
Character
+
Location
+
Project Style
     ↓
PromptContextResolver
     ↓
Prompt Agent
     ↓
Structured Prompt
     ↓
PromptVersion
```

Prompt 不直接进入 Shot 字段。

---

# 36. Generation API

统一：

```text
POST   /generations

GET    /generations/{generationId}

GET    /projects/{projectId}/generations

GET    /generations/{generationId}/inputs

GET    /generations/{generationId}/outputs

POST   /generations/{generationId}/retry

POST   /generations/{generationId}/cancel
```

但前端正常不应该直接大量调用：

```text
POST /generations
```

更多使用：

```text
GenerateShotImage
GenerateShotVideo
GenerateScene
```

业务 API。

---

# 37. Shot Image Generation API

```http
POST /shots/{shotId}/generate-image
```

Request：

```json
{
  "promptVersionId": "prompt_v3",
  "workflowTemplateId": "wf_shot_image",
  "provider": null,
  "model": null,
  "activateOnSuccess": false
}
```

---

# 38. Shot Video Generation API

```http
POST /shots/{shotId}/generate-video
```

Request：

```json
{
  "sourceImageAssetId": "asset_img_v3",
  "promptVersionId": "prompt_video_v2",
  "duration": 5,
  "workflowTemplateId": "wf_video_standard"
}
```

---

# 39. 不让 UI 指定 ComfyUI Node

禁止：

```json
{
  "node87": "...",
  "node92": 5,
  "node112": true
}
```

UI 应只表达：

```json
{
  "duration": 5,
  "motionStrength": 0.6,
  "resolution": "1080x1920"
}
```

Workflow Adapter 转换。

---

# 40. GenerationApplicationService

核心接口：

```text
generateShotImage()

generateShotVideo()

generateCharacterReference()

generateLocationReference()

generateVoice()

retryGeneration()

cancelGeneration()
```

它本身不调用 Provider。

职责是：

```text
Validate
 ↓
Resolve Context
 ↓
Create Generation Plan
 ↓
Create Job / Task
 ↓
Queue
```

---

# 41. GenerationPlanner

这是非常核心的 Domain/Application Service。

```text
GenerationPlanner
```

负责回答：

> 要生成这个目标，需要哪些输入和步骤？

例如：

```text
generateShotVideo(shot23)
```

Planner：

```text
Shot exists?
 ↓
Video Prompt exists?
 ↓
Active Image exists?
 ↓
Workflow exists?
 ↓
Provider available?
 ↓
Create Generation Plan
```

---

# 42. GenerationPlan

推荐内部模型：

```text
GenerationPlan
{
    target

    generationType

    provider

    model

    workflowVersion

    promptVersion

    inputs[]

    parameters

    dependencies[]
}
```

---

# 43. Generation Planner 与执行分离

禁止：

```text
GenerationService
{
    plan()
    调模型
    写文件
    改数据库
    Retry
    Timeline
}
```

应拆成：

```text
GenerationPlanner
       ↓
GenerationExecutor
       ↓
ProviderAdapter
```

---

# 44. GenerationExecutor

职责：

```text
Load Generation

Mark RUNNING

Resolve Provider Adapter

Prepare Provider Request

Execute

Receive Result

Store File

Register Asset

Register GenerationOutput

Mark SUCCEEDED
```

异常：

```text
Mark FAILED

Publish GenerationFailed
```

---

# 45. Generation 执行完整流程

```text
UI
 ↓
POST generate-video
 ↓
GenerationApplicationService
 ↓
GenerationPlanner
 ↓
JobService
 ↓
JobTask
 ↓
TaskQueue
 ↓
GenerationExecutor
 ↓
WorkflowResolver
 ↓
ProviderAdapter
 ↓
ComfyUI
 ↓
Output File
 ↓
StorageService
 ↓
AssetService
 ↓
GenerationOutput
 ↓
GenerationSucceeded
 ↓
JobService
 ↓
Progress Event
 ↓
UI
```

---

# 46. Job API

```text
GET    /projects/{projectId}/jobs

GET    /jobs/{jobId}

GET    /jobs/{jobId}/tasks

POST   /jobs/{jobId}/pause

POST   /jobs/{jobId}/resume

POST   /jobs/{jobId}/cancel

POST   /jobs/{jobId}/retry-failed
```

---

# 47. Generate Scene API

```http
POST /scenes/{sceneId}/generate
```

Request：

```json
{
  "steps": [
    "IMAGE",
    "VIDEO"
  ],
  "skipApprovedShots": true,
  "regenerateStaleOnly": false
}
```

后端创建：

```text
Job
Generate Scene 05
```

---

# 48. Scene Job 示例

```text
Job #100

├── Shot01 Image
│
├── Shot01 Video
│     depends on Image
│
├── Shot02 Image
│
├── Shot02 Video
│     depends on Image
│
└── ...
```

不是：

```text
for shot:
    generateImage()
    generateVideo()
```

同步执行。

---

# 49. JobService

负责：

```text
createJob()

addTask()

startJob()

pauseJob()

resumeJob()

cancelJob()

retryFailedTasks()

recalculateProgress()
```

---

# 50. TaskQueue

Alpha 第一阶段不需要 Kafka。

推荐：

```text
Persistent DB Queue
+
In-process Worker Pool
```

即：

```text
job_tasks
```

本身就是持久任务队列。

Worker：

```text
SELECT READY TASK
 ↓
Lock
 ↓
RUNNING
 ↓
Execute
```

---

# 51. 为什么 Alpha 不需要 Redis Queue

当前：

```text
Desktop
Single Machine
Local-first
```

使用：

```text
Redis
RabbitMQ
Kafka
```

只会增加：

```text
安装复杂度
端口
进程
恢复复杂度
打包难度
```

数据库持久 Queue 已足够。

---

# 52. Worker Pool

需要区分：

```text
CPU Task

LLM Task

Image Task

Video Task

ComfyUI Task
```

避免一个视频任务堵死所有任务。

推荐：

```text
TaskExecutorRegistry
```

例如：

```text
LLM_WORKER

COMFYUI_WORKER

REMOTE_IMAGE_WORKER

REMOTE_VIDEO_WORKER

LOCAL_PROCESS_WORKER
```

---

# 53. ComfyUI 并发

本地单 GPU 初期默认：

```text
maxConcurrentComfyUiTasks = 1
```

即：

```text
Image
 ↓
Video
 ↓
Image
```

如果以后检测多个 GPU：

```text
Worker Slot
```

再扩展。

---

# 54. Retry 策略

Task：

```text
maxRetryCount = 3
```

但是必须区分错误。

## 可 Retry

```text
HTTP_TIMEOUT

PROVIDER_BUSY

NETWORK_ERROR

COMFYUI_TEMPORARY_ERROR

RATE_LIMIT
```

## 不自动 Retry

```text
INVALID_PROMPT

WORKFLOW_MAPPING_ERROR

MISSING_ASSET

MODEL_NOT_FOUND

INVALID_INPUT
```

---

# 55. RetryPolicy

统一：

```text
RetryPolicy
```

返回：

```text
RETRY

FAIL

WAIT
```

并支持：

```text
backoff
```

例如：

```text
2s
5s
15s
```

---

# 56. Job Resume

应用启动：

```text
RecoveryService
```

扫描：

```text
Job = RUNNING
Task = RUNNING
Generation = RUNNING
```

这些意味着：

> 上次应用可能异常退出。

处理：

```text
Task → INTERRUPTED
Generation → FAILED / INTERRUPTED
Job → PAUSED
```

UI：

```text
Interrupted job detected.

[Resume]
```

---

# 57. 建议增加 INTERRUPTED

数据库原来状态可以扩展：

```text
INTERRUPTED
```

对于：

```text
Generation
JobTask
Job
```

比直接：

```text
FAILED
```

语义更准确。

---

# 58. Workflow API

```text
GET    /workflows

POST   /workflows

GET    /workflows/{workflowId}

PATCH  /workflows/{workflowId}

GET    /workflows/{workflowId}/versions

POST   /workflows/{workflowId}/versions

POST   /workflows/{workflowId}/versions/{versionId}/activate

POST   /workflows/{workflowId}/validate

POST   /workflows/import-comfyui
```

---

# 59. WorkflowService

职责：

```text
createTemplate()

createVersion()

activateVersion()

resolveWorkflow()

validateSchema()

validateInputMapping()

validateOutputMapping()
```

---

# 60. WorkflowResolver

输入：

```text
GenerationType = SHOT_VIDEO

Project Setting

Requested Workflow

Provider
```

输出：

```text
WorkflowVersion
```

优先级：

```text
Request Override
 ↓
Project Default
 ↓
System Default
```

---

# 61. ProviderAdapter

统一接口概念：

```text
ProviderAdapter
```

例如：

```text
execute(request)

cancel(executionId)

queryStatus(executionId)

healthCheck()
```

---

# 62. Adapter 分类

不要所有 Provider 强行一个巨大接口。

建议：

```text
LlmProviderAdapter

ImageProviderAdapter

VideoProviderAdapter

VoiceProviderAdapter

WorkflowProviderAdapter
```

---

# 63. ComfyUI Adapter

ComfyUI 属于：

```text
WorkflowProviderAdapter
```

主要接口：

```text
submitWorkflow()

getExecutionStatus()

cancelExecution()

downloadOutputs()

healthCheck()
```

---

# 64. ComfyUIWorkflowAdapter

负责：

```text
WorkflowVersion
+
Logical Input
     ↓
ComfyUI Workflow JSON
     ↓
Node Mapping
     ↓
ComfyUI API
```

例如：

```text
Logical:

prompt
duration
referenceImage
```

转换：

```text
node["87"].inputs.text

node["92"].inputs.duration

node["42"].inputs.image
```

---

# 65. ComfyUI Node Mapping 不进入业务层

只有：

```text
ComfyUIWorkflowAdapter
```

允许知道：

```text
node 87
node 42
node 92
```

以下对象禁止知道：

```text
Shot
Generation
GenerationService
JobService
Director Agent
Frontend
```

---

# 66. Provider Registry

统一：

```text
ProviderRegistry
```

注册：

```text
MINIMAX

OPENAI

COMFYUI_LOCAL

KLING

SEEDANCE

CUSTOM
```

根据：

```text
providerType
```

找到：

```text
Adapter
```

---

# 67. Provider Health

API：

```text
GET /providers

GET /providers/{providerId}/health
```

返回：

```json
{
  "status": "AVAILABLE",
  "latencyMs": 42,
  "details": {}
}
```

Studio 可以显示：

```text
ComfyUI ● Connected

MiniMax ● Available

Voice API ○ Not configured
```

---

# 68. Agent 架构

Alpha Agent 第一版：

```text
Director Agent

Script Agent

Visual Agent

Continuity Agent
```

后续：

```text
Character Agent
Camera Agent
Voice Agent
QA Agent
```

再增加。

---

# 69. AgentGateway

Core Backend 不直接依赖 LangGraph。

定义：

```text
AgentGateway
```

接口概念：

```text
planEpisode()

planScene()

generateShotPlan()

generatePrompt()

reviewContinuity()
```

实现可以：

```text
LocalLangGraphAgentGateway
```

或者：

```text
RemoteAgentRuntimeGateway
```

---

# 70. Agent Runtime

如果拆成 Python Service：

```text
agent-runtime
├── director
├── script
├── visual
├── continuity
├── prompt
├── graph
├── tools
├── schemas
└── providers
```

HTTP 只作为内部协议。

---

# 71. Agent 不直接修改数据库

禁止：

```text
Agent
 ↓
Repository
```

正确：

```text
Agent
 ↓
Proposal
 ↓
Application Service
 ↓
Validation
 ↓
Domain
 ↓
Repository
```

---

# 72. Agent Proposal

例如 Script Agent 返回：

```json
{
  "proposalType": "SCENE_PLAN",
  "episodeId": "episode_01",
  "scenes": [
    {
      "title": "训练结束",
      "description": "...",
      "narrativePurpose": "...",
      "locationRef": "gym"
    }
  ]
}
```

Backend：

```text
Validate
 ↓
Map Existing Character / Location
 ↓
Create Scene
```

---

# 73. Agent Structured Output

所有 Agent 关键输出必须：

```text
JSON Schema
```

验证。

禁止把：

```text
下面是我的分镜建议：
第一镜头……
```

自然语言直接写入数据库。

---

# 74. Agent Output Validation

流程：

```text
LLM Output
 ↓
JSON Parse
 ↓
Schema Validation
 ↓
Business Validation
 ↓
Repair Attempt
 ↓
Reject
```

如果仍失败：

```text
AGENT_OUTPUT_INVALID
```

---

# 75. Director Agent API

不直接暴露：

```text
/chat
```

建议业务化：

```text
POST /episodes/{episodeId}/agent/plan

POST /scenes/{sceneId}/agent/plan-shots

POST /shots/{shotId}/agent/improve

POST /shots/{shotId}/agent/generate-prompt

POST /scenes/{sceneId}/agent/review-continuity
```

---

# 76. Agent Chat

Studio 后期可以增加：

```text
POST /agent/chat
```

但 Alpha 核心能力不能依赖聊天框。

Agent 应主要驱动：

```text
Project State
```

而不是：

```text
Conversation History
```

---

# 77. Context Resolver

这是 Agent 系统最重要的基础能力之一。

```text
ContextResolver
```

输入：

```text
shotId
```

输出：

```text
Project Style

Episode Context

Scene Context

Current Shot

Previous Shots

Relevant Characters

Relevant Locations

Continuity State

Approved Assets
```

---

# 78. Context 不加载整个 Project

错误：

```text
把 20 万字小说
+
全部 80 个角色
+
500 个 Shot
```

全部塞给 LLM。

正确：

```text
Task
 ↓
Context Resolver
 ↓
Relevant Context
```

---

# 79. ContextPolicy

建议定义：

```text
ContextPolicy
```

例如：

```text
SHOT_PLANNING
```

加载：

```text
Current Scene
Previous 2 Shots
Next Narrative Beat
Characters in Scene
Location
Style
```

而：

```text
CHARACTER_GENERATION
```

加载：

```text
Character Definition
Character Master
Costume
Project Style
```

---

# 80. Continuity API

```text
GET    /scenes/{sceneId}/continuity

GET    /shots/{shotId}/continuity

PUT    /shots/{shotId}/continuity

POST   /scenes/{sceneId}/continuity/review

GET    /scenes/{sceneId}/continuity/warnings

POST   /continuity/warnings/{warningId}/ignore
```

---

# 81. ContinuityService

职责：

```text
resolveState()

inheritState()

applyDelta()

detectConflict()

markAffectedShots()

buildAgentContext()
```

---

# 82. Continuity Engine 分层

```text
Structured Continuity
        ↓
Rule Engine
        ↓
Agent Review
```

不要全部依赖 LLM。

例如：

```text
Shot 20 costume = WHITE_7

Shot 21 costume = BLACK_TRAINING
```

结构化规则就可以发现。

无需 LLM。

---

# 83. Continuity Rule Engine

第一版检测：

```text
Character Version

Costume

Location

Time

Prop Holder
```

第二版：

```text
Position

Orientation

Physical State

Emotion

Action
```

第三版：

```text
Screen Direction

Camera Axis

Motion Transition
```

---

# 84. Timeline API

```text
GET    /episodes/{episodeId}/timeline

POST   /episodes/{episodeId}/timeline

POST   /timelines/{timelineId}/tracks

POST   /timelines/{timelineId}/clips

PATCH  /timeline-clips/{clipId}

DELETE /timeline-clips/{clipId}

POST   /timeline-clips/{clipId}/replace-asset

POST   /timelines/{timelineId}/render
```

---

# 85. Render Episode

```http
POST /timelines/{timelineId}/render
```

创建：

```text
Job
 ↓
Render Task
 ↓
Generation VIDEO_RENDER
```

最终输出：

```text
FINAL_VIDEO Asset
```

仍然纳入：

```text
Generation
Asset
Version
```

体系。

---

# 86. Progress 通信

普通 CRUD：

```text
REST
```

长任务：

```text
SSE
```

优先推荐 SSE，而不是第一版全部上 WebSocket。

原因：

```text
Server → Client
```

进度通知是主要需求。

---

# 87. SSE Endpoint

例如：

```http
GET /api/v1/events
```

或者：

```http
GET /api/v1/projects/{projectId}/events
```

事件：

```text
JOB_UPDATED

TASK_STARTED

TASK_PROGRESS

GENERATION_STARTED

GENERATION_SUCCEEDED

GENERATION_FAILED

ASSET_CREATED

SHOT_UPDATED

CONTINUITY_WARNING
```

---

# 88. SSE Event

```json
{
  "eventId": "evt_01K...",
  "type": "GENERATION_SUCCEEDED",
  "projectId": "project_01",
  "timestamp": "...",
  "payload": {
    "generationId": "gen_01",
    "assetIds": [
      "asset_01"
    ]
  }
}
```

---

# 89. UI Progress

不要让前端：

```text
每 500ms GET /jobs/{id}
```

轮询。

正常：

```text
SSE
```

更新。

如果 SSE 断线：

```text
GET /jobs/{id}
```

重新同步。

---

# 90. WebSocket 使用时机

等需要：

```text
Agent Streaming

Interactive Generation

双向 Agent Control

多人协作
```

再正式引入 WebSocket。

Alpha 不应该因为“实时”两个字就全部 WebSocket 化。

---

# 91. Event Bus

后端内部：

```text
DomainEventPublisher
```

事件：

```text
ShotUpdated

CharacterMasterChanged

GenerationSucceeded

GenerationFailed

AssetActivated

JobCompleted
```

消费者：

```text
DependencyService

JobService

TimelineService

SseEventPublisher

AuditService
```

---

# 92. 不等于 Event Sourcing

数据库状态仍是：

```text
Source of Truth
```

Event 只是：

```text
业务副作用传播
```

不要 Alpha 就做复杂 Event Sourcing。

---

# 93. Transaction Boundary

Application Service 是主要事务边界。

例如：

```text
setCharacterMaster()
```

一个事务：

```text
Update CharacterVersion

Update Character

Write Audit
```

提交后：

```text
Publish Event
```

---

# 94. Provider 调用绝不放数据库事务

禁止：

```text
@Transactional

generateVideo() {
   save...
   callComfyUI(); // 5 minutes
   save...
}
```

必须拆：

```text
TX1
Generation RUNNING

COMMIT

↓

Provider Execution

↓

TX2
Asset
GenerationOutput
Generation SUCCEEDED

COMMIT
```

---

# 95. Idempotency

以下操作建议支持：

```text
Idempotency-Key
```

尤其：

```text
Generate Scene

Generate Shot

Render Timeline

Create Job
```

例如前端重复点击：

```text
Generate
Generate
Generate
```

不能创建三个相同任务。

---

# 96. Idempotency API

Header：

```text
Idempotency-Key:
gen-shot23-video-xxx
```

Backend：

```text
Key exists?
 ↓ YES
Return existing Job
```

---

# 97. Generate Button 防重复

除了前端按钮 Disabled，

后端还要检查：

```text
是否已有相同 Target + Type 的 RUNNING Generation
```

如果有：

```text
409 GENERATION_ALREADY_RUNNING
```

或直接返回已有任务。

---

# 98. Command / Query 分离

不需要完整 CQRS Framework。

代码概念上区分：

```text
Command
```

例如：

```text
CreateShotCommand

UpdateShotCommand

GenerateShotImageCommand

SetCharacterMasterCommand
```

以及：

```text
Query
```

例如：

```text
GetShotInspectorQuery

GetSceneEditorQuery

GetProjectTreeQuery
```

---

# 99. 为什么 Command / Query 分离

因为：

```text
GET Scene Editor
```

可能跨：

```text
Scene
Shot
Asset
Generation
Character
```

不应该强迫通过：

```text
SceneRepository
```

构建。

QueryService 可以直接使用高效 SQL / Projection。

---

# 100. Repository 原则

Domain Repository：

```text
ShotRepository
```

只负责：

```text
findById()

save()

findBySceneId()
```

禁止：

```text
callComfyUI()

生成 Prompt

发送 SSE

处理 Agent
```

---

# 101. 推荐 Application Service

核心：

```text
ProjectApplicationService

SourceDocumentApplicationService

EpisodeApplicationService

SceneApplicationService

ShotApplicationService

CharacterApplicationService

LocationApplicationService

AssetApplicationService

PromptApplicationService

GenerationApplicationService

JobApplicationService

WorkflowApplicationService

ContinuityApplicationService

TimelineApplicationService
```

---

# 102. 推荐 Domain Service

```text
ProjectLifecycleService

ShotPlanningService

CharacterVersionService

AssetVersionService

DependencyService

GenerationPlanner

ContinuityService

TimelineCompositionService
```

---

# 103. 推荐 Infrastructure Service

```text
LocalStorageService

SQLiteRepository

ComfyUIClient

LLMClient

ImageProviderClient

VideoProviderClient

VoiceProviderClient

SsePublisher

ProcessManager
```

---

# 104. Dependency Direction

必须：

```text
Infrastructure
     ↓ implements
Domain Interface
```

而不是：

```text
Domain
 ↓
ComfyUIClient
```

领域层不能依赖 ComfyUI。

---

# 105. Backend Package 示例

如果使用 Spring Boot：

```text
com.ai.mangastudio
│
├── project
├── story
├── shot
├── character
├── asset
├── generation
├── job
├── workflow
├── continuity
├── timeline
├── agent
├── provider
│   ├── comfyui
│   ├── llm
│   ├── image
│   ├── video
│   └── voice
│
├── storage
├── event
└── common
```

---

# 106. 模块依赖建议

```text
project
↑
story
↑
shot
```

而：

```text
generation
```

依赖领域接口：

```text
shot
asset
prompt
workflow
```

`provider` 不能反向控制业务。

---

# 107. API DTO 与 Entity 分离

禁止 Controller：

```text
return ShotEntity
```

必须：

```text
ShotResponse
```

Entity：

```text
Persistence Model
```

Domain：

```text
Business Model
```

API：

```text
DTO
```

至少概念分离。

---

# 108. Request Validation

例如：

```text
duration
```

必须：

```text
> 0
```

`shotType`：

```text
合法 Enum
```

`characterVersionId`：

必须属于：

```text
characterId
```

但：

```text
Bean Validation
```

只能负责简单字段。

真正业务约束由：

```text
Application / Domain
```

验证。

---

# 109. Project Scope Validation

所有跨资源操作：

```text
Shot
Character
Asset
```

必须确认：

```text
project_id 相同
```

禁止：

```text
Project A Shot
使用
Project B Character Asset
```

除非未来明确支持：

```text
Shared Library
```

---

# 110. Local Desktop Security

Alpha 如果 Backend：

```text
127.0.0.1
```

本地运行，

可以不做完整用户登录系统。

但是必须：

```text
只绑定 localhost
```

不要默认：

```text
0.0.0.0
```

暴露局域网。

---

# 111. Local Session Token

仍建议 Desktop 启动 Backend 时产生：

```text
Local Session Token
```

前端请求：

```text
Authorization: Bearer ...
```

避免其他本机网页随便调用：

```text
localhost:xxxx
```

API。

---

# 112. Provider Credential

Backend 通过：

```text
CredentialService
```

读取：

```text
Windows Credential Manager
macOS Keychain
```

项目数据库永远不保存明文 API Key。

---

# 113. Logging

统一：

```text
requestId

projectId

jobId

taskId

generationId
```

写入日志。

例如：

```text
generationId=gen_123
provider=COMFYUI
status=FAILED
```

方便定位。

---

# 114. 不记录敏感数据

日志禁止默认完整记录：

```text
API Key

Authorization Header

完整用户小说内容

大段 Base64

图片二进制
```

Prompt 日志可以：

```text
generationId
promptVersionId
```

数据库已有完整 Prompt。

---

# 115. Agent Run 记录

建议以后增加：

```text
agent_runs
```

字段：

```text
id

project_id

agent_type

target_type

target_id

model

status

input_context_hash

proposal_json

token_usage

started_at

finished_at
```

Alpha v0.1 可以先将其纳入：

```text
Generation
```

其中：

```text
generation_type = STORY_ANALYSIS
```

等。

---

# 116. Token Usage

LLM Generation 建议记录：

```text
input_tokens

output_tokens

cached_tokens

estimated_cost
```

不要等后期才加。

因为未来 Studio 必须回答：

> 哪个 Agent 最烧 Token？

---

# 117. Generation Cost Metadata

建议 Generation 增加：

```text
usage_json
```

例如：

```json
{
  "inputTokens": 12300,
  "outputTokens": 1600,
  "cachedTokens": 8000,
  "estimatedCost": 0.12,
  "currency": "USD"
}
```

Image / Video 也可记录：

```text
credits
seconds
estimatedCost
```

---

# 118. CostService

Beta 后可以建立：

```text
CostService
```

Alpha 至少把数据保存下来。

未来 Studio 可以展示：

```text
Episode 01

LLM          ¥3.2
Image       ¥12.5
Video       ¥48.7
Voice        ¥2.1
----------------
Total       ¥66.5
```

这是制作 Studio 很重要的能力。

---

# 119. API Versioning

统一：

```text
/api/v1
```

在 Alpha 期间不要因为字段小改动就：

```text
/v2
```

只有出现：

```text
breaking API semantics
```

才进入 v2。

---

# 120. Backend Health

```text
GET /api/v1/system/health
```

返回：

```json
{
  "status": "OK",
  "database": "OK",
  "storage": "OK",
  "providers": {
    "comfyui": "AVAILABLE"
  }
}
```

---

# 121. Startup Recovery

Backend 启动：

```text
Boot
 ↓
Load Global Config
 ↓
Open Project
 ↓
Schema Migration
 ↓
Integrity Check
 ↓
Asset Quick Check
 ↓
Job Recovery
 ↓
Provider Health Check
 ↓
Start Event Stream
```

---

# 122. Shutdown

应用关闭：

```text
Stop accepting Jobs

Mark running tasks

Flush DB

Close SSE

Close SQLite

Stop Worker Pool
```

不要：

```text
直接 kill process
```

正常关闭。

---

# 123. Cancel Generation

如果 Provider 支持：

```text
cancel
```

则：

```text
Generation → CANCEL_REQUESTED
 ↓
Provider.cancel()
 ↓
CANCELLED
```

如果不支持：

```text
CANCEL_REQUESTED
```

但输出回来时：

```text
Discard / Archive Output
```

不能重新变：

```text
SUCCEEDED
```

---

# 124. 建议加入 CANCEL_REQUESTED

异步状态最好：

```text
CREATED
QUEUED
RUNNING
CANCEL_REQUESTED
SUCCEEDED
FAILED
CANCELLED
INTERRUPTED
```

而不是把 Cancel 当同步动作。

---

# 125. Shot Regenerate 核心流程

用户：

```text
Shot 23
镜头改 CLOSE_UP
```

↓

```text
UpdateShot
```

↓

```text
DependencyService
```

标记：

```text
Prompt STALE
Image STALE
Video STALE
```

↓

用户：

```text
Regenerate
```

↓

```text
POST /shots/23/generate-image
```

↓

创建：

```text
Prompt v4

Generation 1004

Asset Image v4
```

↓

用户预览：

```text
Use v4
```

↓

```text
active_image_asset_id = v4
```

↓

Video：

```text
仍然保持旧 v3
```

但：

```text
STALE
```

直到用户生成新 Video。

---

# 126. 不自动破坏 Timeline

如果 Shot Video：

```text
v2
```

当前 Timeline 正在使用。

新：

```text
v3
```

生成成功后：

```text
Timeline 仍用 v2
```

除非：

```text
autoUpdateTimeline = true
```

或者用户点击：

```text
Replace in Timeline
```

专业创作软件不能随便换用户成片。

---

# 127. Backend 对前端的关键 Read Models

Alpha 建议至少：

```text
ProjectTreeView

SceneEditorView

ShotInspectorView

AssetBrowserView

GenerationHistoryView

JobQueueView

TimelineView

CharacterLibraryView
```

这些 Read Model 可以为 UI 专门优化。

---

# 128. ProjectTreeView

```text
Project

Episode Summary

Scene Summary

Shot Summary
```

只包含：

```text
id
name
status
order
thumbnail
```

不要加载全部 Prompt。

---

# 129. ShotInspectorView

加载：

```text
Shot

VisualSpec

Characters

Prompt

Active Image

Active Video

Versions

Generation Status

Continuity Warning
```

Inspector 打开时再查询。

---

# 130. AssetBrowserView

支持：

```text
type

character

scene

shot

generated/imported

status

date
```

过滤。

不要一次加载整个 Asset Metadata JSON。

---

# 131. API Pagination

Asset / Generation：

必须分页。

例如：

```text
GET /projects/{id}/assets?limit=50&cursor=...
```

推荐：

```text
Cursor Pagination
```

而不是：

```text
page=382
```

Generation 历史特别适合 Cursor。

---

# 132. Search

Alpha 可以做基础：

```text
?query=沈亦
```

查询：

```text
Character
Scene
Asset
```

全局复杂搜索可以 V1 再增加。

---

# 133. Backend 第一期开发模块

为了让 Codex 实际开发，不要一次实现全文所有内容。

## Backend Phase B1

完成：

```text
Project

Episode

Scene

Shot

Character

Location

Asset

Prompt

Generation
```

---

# 134. B1 验收

必须完成：

```text
Create Project

Create Episode

Create Scene

Create Shot

Create Character MASTER

Bind Character

Generate Prompt

Generate Shot Image

Register Asset

Generate Shot Video

Switch Active Version
```

---

# 135. Backend Phase B2

增加：

```text
Workflow

ComfyUI Adapter

Job

Task Queue

Retry

Resume

SSE Progress
```

---

# 136. B2 验收

一个 Scene：

```text
20 Shots
```

批量执行：

```text
Image
+
Video
```

其中：

```text
3 tasks fail
```

系统：

```text
其他任务继续

失败任务可 Retry

应用重启可 Resume
```

---

# 137. Backend Phase B3

增加：

```text
Director Agent

Script Agent

Visual Agent

Context Resolver

Agent Proposal
```

---

# 138. B3 验收

输入：

```text
小说章节
```

自动：

```text
Episode
 ↓
Scenes
 ↓
Shots
 ↓
Visual Specs
```

并形成数据库正式对象。

不是：

```text
一个 JSON 文件
```

---

# 139. Backend Phase B4

增加：

```text
Dependency

STALE

Continuity

Timeline

Render
```

---

# 140. B4 验收

角色 MASTER 更新：

```text
v4 → v5
```

系统正确识别：

```text
Affected Shots
```

并：

```text
Mark Stale
```

不自动重生成。

---

# 141. Backend Phase B5

增加：

```text
Audit

Cost

Recovery

Project Backup

Project Repair
```

进入真正可长期使用的 Alpha。

---

# 142. Codex 开发时的任务拆分原则

每一个开发任务控制为：

```text
一个明确业务闭环
```

例如不要：

```text
实现 Asset 系统
```

过于宽泛。

应该拆：

```text
实现 Asset Entity + Repository

实现 LocalStorageService

实现 Import Asset API

实现 Generated Asset Registration

实现 Asset Preview

实现 Asset Version Group

实现 Asset Archive

实现 Asset Provenance Query
```

---

# 143. 推荐 Codex 第一批任务

```text
Task 01
建立 Backend module package 结构

Task 02
实现 Project Aggregate + Repository

Task 03
实现 Project API

Task 04
实现 Episode / Scene / Shot Core

Task 05
实现 ProjectTree Query

Task 06
实现 Character + CharacterVersion

Task 07
实现 Location + LocationVersion

Task 08
实现 Asset + LocalStorage

Task 09
实现 Prompt Version

Task 10
实现 Generation Core
```

---

# 144. 第二批 Codex 任务

```text
Task 11
GenerationInput / Output

Task 12
GenerationPlanner

Task 13
Provider Adapter Interfaces

Task 14
ComfyUI Client

Task 15
ComfyUI Workflow Adapter

Task 16
Shot Image Generation

Task 17
Shot Video Generation

Task 18
Generation History

Task 19
Version Activate

Task 20
Asset Provenance
```

---

# 145. 第三批 Codex 任务

```text
Task 21
Job Core

Task 22
JobTask

Task 23
Task Dependency

Task 24
Persistent Queue

Task 25
Worker Pool

Task 26
Retry Policy

Task 27
Cancel

Task 28
Resume / Recovery

Task 29
SSE Event Stream

Task 30
Scene Batch Generation
```

---

# 146. 第四批 Codex 任务

```text
Task 31
AgentGateway

Task 32
ContextResolver

Task 33
Director Agent

Task 34
Script Agent

Task 35
Visual Agent

Task 36
Structured Output Validation

Task 37
Agent Proposal

Task 38
Episode Plan

Task 39
Scene Shot Planning

Task 40
Prompt Agent
```

---

# 147. 第五批 Codex 任务

```text
Task 41
ResourceDependency

Task 42
Stale Propagation

Task 43
Continuity State

Task 44
Continuity Rule Engine

Task 45
Continuity Agent

Task 46
Timeline

Task 47
Timeline Clip Version

Task 48
Episode Render

Task 49
Audit

Task 50
Project Recovery
```

---

# 148. Alpha Backend 最核心的 10 个 Service

如果只看核心，优先保证：

```text
ProjectApplicationService

ShotApplicationService

AssetService

PromptService

GenerationApplicationService

GenerationPlanner

JobService

WorkflowService

AgentGateway

DependencyService
```

稳定。

---

# 149. 最关键的调用链一：单 Shot Image

```text
Studio
 ↓
POST Generate Shot Image
 ↓
ShotApplicationService
 ↓
GenerationPlanner
 ↓
PromptResolver
 ↓
WorkflowResolver
 ↓
Create Generation
 ↓
Create JobTask
 ↓
Queue
 ↓
GenerationExecutor
 ↓
Image / ComfyUI Adapter
 ↓
StorageService
 ↓
AssetService
 ↓
GenerationOutput
 ↓
GenerationSucceeded
 ↓
SSE
 ↓
Studio Preview
```

---

# 150. 最关键调用链二：完整 Scene

```text
Generate Scene
 ↓
SceneApplicationService
 ↓
GenerationPlanner
 ↓
Create Job
 ↓
Build Task DAG
 ↓
Persistent Queue
 ↓
Workers
 ↓
Shot Image
 ↓
Shot Video
 ↓
Progress
 ↓
Partial Failure
 ↓
Retry
 ↓
Scene Complete
```

---

# 151. 最关键调用链三：Director

```text
Novel
 ↓
SourceDocument
 ↓
Plan Episode
 ↓
AgentGateway
 ↓
ContextResolver
 ↓
Director Graph
 ↓
Structured Proposal
 ↓
Backend Validation
 ↓
EpisodeApplicationService
 ↓
Scene
 ↓
Shot
 ↓
VisualSpec
```

---

# 152. 最关键调用链四：MASTER 更新

```text
Set Character MASTER
 ↓
CharacterApplicationService
 ↓
CharacterVersionService
 ↓
Commit
 ↓
CharacterMasterChanged
 ↓
DependencyService
 ↓
Find affected Assets
 ↓
Mark STALE
 ↓
SSE Warning
 ↓
Studio
```

---

# 153. 后端禁止事项

## 禁止 1

Controller 直接操作 Repository。

---

## 禁止 2

Service 直接依赖 ComfyUI JSON。

---

## 禁止 3

Agent 直接操作数据库。

---

## 禁止 4

同步 HTTP 等待视频生成完成。

---

## 禁止 5

每种模型单独写一套业务 Service。

例如：

```text
MiniMaxShotService

KlingShotService

SeedanceShotService
```

错误。

应该：

```text
GenerationService
 ↓
ProviderAdapter
```

---

## 禁止 6

将：

```text
Shot
```

等价于：

```text
Prompt
```

---

## 禁止 7

重新生成覆盖旧 Asset。

---

## 禁止 8

Generation Retry 修改原 Generation。

---

## 禁止 9

Character MASTER 更新自动覆盖历史 Shot。

---

## 禁止 10

Job Queue 只存在内存。

应用重启后必须能够恢复。

---

# 154. Alpha Backend 完成定义

后端达到以下能力：

```text
Novel
 ↓
Director
 ↓
Episode
 ↓
Scene
 ↓
Shot
 ↓
Prompt
 ↓
Generation
 ↓
Job Queue
 ↓
ComfyUI / Provider
 ↓
Asset
 ↓
Version
 ↓
Timeline
```

并支持：

```text
Edit

Regenerate

Retry

Resume

Cancel

Version Switch

MASTER

STALE

Progress

History

Provenance
```

即可认为：

> AI 漫剧 Studio Alpha Backend Core 成立。

---

# 155. 下一份设计文档

后端 API 与 Service 架构完成以后，下一步不建议立刻继续画更多 API。

现在应该把整个后端最关键、也是最复杂的子系统单独拆出来：

# 《Asset / Generation / Version 系统详细设计 v0.1》

因为未来 AI 漫剧 Studio 几乎所有核心操作：

```text
生成角色

生成场景

生成分镜

生成图片

生成视频

生成语音

局部重生成

版本切换

MASTER

失败 Retry

依赖追踪

成本统计

历史恢复
```

本质都围绕：

```text
Asset
      ↕
Version
      ↕
Generation
```

运转。

这套系统一旦设计正确，后面的：

```text
ComfyUI
MiniMax
Seedance
Kling
Veo
本地模型
云模型
```

都只是 Provider。

下一份文档应该重点把：

```text
Asset 生命周期

Asset Version Group

MASTER / ACTIVE

Generation Immutable

Generation Input / Output

Provenance

Regenerate

Dependency

STALE

Cache

Asset Storage

Orphan Cleanup

Asset Repair

Preview

Thumbnail

Import

Export
```

全部定死。

这将是整个 AI 漫剧 Studio **生成基础设施的核心设计文档**。
