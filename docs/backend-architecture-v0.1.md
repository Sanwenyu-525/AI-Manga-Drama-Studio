# AI 漫剧 Studio 后端 API 与 Service 架构设计 v0.1

## —— LangChain / LangGraph 融合版

> 状态：**Architecture Draft**（主创定稿，作为后端主架构文档）
> 目标版本：MVP → V1
> 架构类型：Local-first AI Native Desktop Studio
> AI 架构：LangGraph + LangChain + Studio Domain Services
> 生成架构：Provider Gateway + ComfyUI Adapter + Production Workflow Engine
> 关联文档：[PRD v0.1](./prd-v0.1.md) · [系统架构设计 v0.1](./architecture-v0.1.md) · [数据库与 ER 模型设计 v0.1](./database-v0.1.md)

---

# 1. 系统定位

AI 漫剧 Studio 后端不是传统 CRUD Server，也不是单纯 Agent Server。

它应该被定义为：

> **AI Manga Drama Production Runtime**

负责同时管理：

1. 漫剧项目状态
2. Agent 推理与执行
3. 剧本/分镜结构
4. 角色、场景与资产
5. ComfyUI
6. 图片/视频模型
7. Workflow
8. 长时间 Generation Task
9. 版本管理
10. 连续性管理

整体关系：

```text
Studio UI
   │
   ├─────────────── 用户直接操作
   │
   ▼
Application API
   │
   ├────────────────────────────┐
   ▼                            ▼
Domain Services            AI Director
                                 │
                                 ▼
                             LangGraph
                                 │
                           LangChain Core
                                 │
                                 ▼
                            Agent Tools
                                 │
                                 ▼
                         Domain Services
                                 │
           ┌─────────────────────┼───────────────────┐
           ▼                     ▼                   ▼
     Project State          Asset System      Generation System
                                                   │
                                                   ▼
                                          Production Workflow
                                                   │
                                                   ▼
                                           Provider Gateway
                                     ┌─────────────┼─────────────┐
                                     ▼             ▼             ▼
                                  ComfyUI      GPT Image      Video API
```

---

# 2. 最重要的架构原则

整个项目必须遵循：

```text
AI 可以决定：

WHAT TO DO
做什么

但 Studio 决定：

HOW TO DO
怎么做
```

例如用户说：

> 把第三场改得紧张一点，然后把修改后的镜头重新生成。

AI Director 可以判断：

```text
Scene 03
↓
Shot 12–18
↓
需要调整镜头节奏
↓
需要更新 Prompt
↓
需要重新生成
```

但是实际修改必须通过：

```text
ShotService
```

生成必须通过：

```text
GenerationService
```

而不是让 Agent：

```text
直接 UPDATE SQL
直接调用 ComfyUI
直接修改文件
```

---

# 3. LangChain 在系统中的定位

LangChain不作为整个后端框架。

它只负责 AI 层基础能力：

```text
Model Integration

Tool Calling

Structured Output

Message Model

Agent Utilities

Middleware
```

LangChain当前提供统一 Agent、Tool、Model 和 Structured Output 抽象；Structured Output 可以直接返回 JSON、Pydantic Model 或 dataclass 等结构化对象，非常适合 Scene、Shot、Character、ContinuityReport 这种领域对象。([Docs by LangChain][1])

---

# 4. LangGraph 在系统中的定位

LangGraph负责：

```text
Agent State

Agent Workflow

Agent Loop

Conditional Routing

Checkpoint

Interrupt

Resume

Human In The Loop

Long-running Agent
```

LangGraph本身定位于底层 Agent orchestration，并重点提供 durable execution、streaming、human-in-the-loop 等能力。LangChain 的高级 Agent API目前也建立在 LangGraph之上。([Docs by LangChain][2])

因此：

```text
LangChain
=
AI Building Blocks

LangGraph
=
Agent Runtime

Studio Backend
=
Production Runtime
```

三者不能混为一层。

---

# 5. 两套 Workflow 必须严格分开

这是本架构最重要的概念之一。

## 5.1 Agent Workflow

负责"思考和操作项目"。

例如：

```text
用户请求
↓
理解意图
↓
加载 Context
↓
制定 Plan
↓
调用 Tool
↓
检查结果
↓
继续 / 修改 / 停止
```

这一套：

> 使用 LangGraph。

---

## 5.2 Production Workflow

负责真正的漫剧生产。

例如：

```text
Generate Storyboard
       ↓
Generate Image
       ↓
Image Review
       ↓
Generate Video
       ↓
Video Review
       ↓
Voice
       ↓
Compose
       ↓
Export
```

这里涉及：

```text
GPU
ComfyUI
任务队列
并发
重试
成本
网络 API
视频长任务
取消
恢复
```

这一套：

> 使用 Studio Workflow Engine。

不要完全交给 LangGraph。

---

# 6. 最终后端分层

建议：

```text
┌────────────────────────────┐
│         API Layer          │
├────────────────────────────┤
│     Application Layer      │
├────────────────────────────┤
│       Domain Layer         │
├────────────────────────────┤
│       Agent Layer          │
│ LangGraph + LangChain      │
├────────────────────────────┤
│      Workflow Layer        │
├────────────────────────────┤
│      Provider Layer        │
├────────────────────────────┤
│    Infrastructure Layer    │
└────────────────────────────┘
```

注意：

Agent Layer **调用 Application Layer**。

Application Layer 不反向依赖 Agent。

---

# 7. 依赖原则

必须保证：

```text
LangGraph
   ↓
Application Service
```

允许。

但：

```text
Application Service
   ↓
LangGraph
```

禁止。

同样：

```text
LangChain
   ↓
Studio Tool Adapter
   ↓
Service
```

允许。

但是：

```text
ShotService
   ↓
LangChain
```

禁止。

这样即使未来完全删除 LangChain/LangGraph：

```text
数据库
项目
ComfyUI
Generation
资产
版本
Timeline
```

都不会受到影响。

---

# 8. 推荐技术栈

## Desktop

```text
Tauri
```

## Frontend

```text
React
TypeScript
React Flow
Zustand
TanStack Query
```

## Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
SQLite
httpx
asyncio
WebSocket
```

## AI

```text
LangChain
LangGraph
Pydantic
```

## Generation

```text
Studio GenerationService

Studio WorkflowEngine

ProviderRegistry
```

## Render / Generation Provider

```text
ComfyUI
OpenAI Image
MiniMax
其他 Image API
其他 Video API
Local Model
```

---

# 9. 推荐项目目录

```text
backend/

app/

    main.py

    api/

        projects.py
        episodes.py
        scenes.py
        shots.py
        assets.py
        generations.py
        workflows.py
        providers.py
        agents.py
        events.py

    domain/

        project.py
        episode.py
        scene.py
        shot.py
        character.py
        asset.py
        generation.py
        workflow.py
        continuity.py

    services/

        project_service.py
        episode_service.py
        script_service.py
        scene_service.py
        shot_service.py
        character_service.py
        asset_service.py
        generation_service.py
        version_service.py
        continuity_service.py
        context_service.py

    repositories/

        project_repository.py
        scene_repository.py
        shot_repository.py
        asset_repository.py
        generation_repository.py

    agents/

        director/

            graph.py
            state.py
            nodes.py
            routes.py
            prompts.py

        context/

            builder.py
            selectors.py

        skills/

            script/
            storyboard/
            continuity/
            prompt/
            review/

        tools/

            project_tools.py
            scene_tools.py
            shot_tools.py
            asset_tools.py
            generation_tools.py

        schemas/

            plans.py
            storyboard.py
            continuity.py

    llm/

        gateway.py
        factory.py
        configuration.py

    workflows/

        engine.py
        definition.py
        run.py
        task.py
        scheduler.py
        executor.py

    providers/

        registry.py

        llm/

        image/

        video/

        vision/

        audio/

        comfyui/

            client.py
            provider.py
            workflow_mapper.py
            websocket.py

    events/

        bus.py
        types.py

    db/

        models/
        session.py
        migrations/

    core/

        config.py
        logging.py
        errors.py
        security.py

tests/
```

---

# 10. Studio Service Layer

核心 Service：

```text
ProjectService

EpisodeService

ScriptService

SceneService

ShotService

CharacterService

AssetService

GenerationService

VersionService

ContinuityService

ContextService

WorkflowService
```

这些 Service 是整个产品真正稳定的业务 API。

Agent 和 UI 都调用它们。

---

# 11. ProjectService

负责：

```text
create_project

update_project

open_project

archive_project

duplicate_project

export_project

delete_project
```

API：

```text
POST   /api/projects

GET    /api/projects

GET    /api/projects/{id}

PATCH  /api/projects/{id}

DELETE /api/projects/{id}
```

---

# 12. ScriptService

负责：

```text
import_source

analyze_script

extract_characters

extract_locations

extract_story_beats

split_scenes

rewrite_script
```

内部可调用：

```text
LLMGateway
```

但不要直接调用具体模型。

P1-E1-T01（修复 AI 计划映射与批量写入事务）：

- Plan → Domain Create 只经过单一显式 Mapper（app/services/plan_mapper.py），逐字段映射
  （ScenePlan.title→name、location→location_id、time→time_of_day），禁止
  `SceneCreate(**plan.model_dump())` 这类静默丢字段的写法。
- ScriptService 持有事务（Unit of Work）：SceneService/ShotService 提供不自行 commit 的
  批量方法（create_scenes / create_shots / soft_delete_*），由 ScriptService 一次性 commit
  并在 commit 后发布事件；任一步失败整体 rollback（all-or-nothing）。
- 幂等键：episodes.analysis_key / scenes.storyboard_key 对"实际送入 LLM 的输入"做 hash；
  同一 key 重复确认返回已落库行（不重复调用 LLM）；key 变化时执行显式 replace
  （软删除旧 AI 行后重建），手动行（analysis_key IS NULL）保留。
- 遗留无 key 数据按手动行处理；历史重复检测属 P1-E1-T02。

---

# 13. SceneService

负责：

```text
create_scene

update_scene

delete_scene

reorder_scene

generate_shot_plan

duplicate_scene
```

---

# 14. ShotService

系统最核心的 Service。

负责：

```text
create

update

delete

duplicate

split

merge

reorder

assign_character

assign_costume

assign_prop

change_camera

change_action

change_duration

approve

mark_dirty

restore_version
```

Agent 修改漫剧内容最终基本都会落到：

```text
ShotService
```

---

# 15. AssetService

负责：

```text
import_asset

register_asset

copy_asset

link_asset

unlink_asset

create_thumbnail

delete_asset

get_metadata
```

所有 AI 图片和视频最终统一转化为：

```text
Asset
```

---

# 16. GenerationService

负责：

```text
create_generation

submit

cancel

retry

status

complete

fail
```

它是：

```text
Studio
```

和：

```text
AI生成世界
```

之间的核心边界。

---

# 17. LLM Gateway

虽然采用 LangChain，但业务层仍然建立自己的：

```text
LLMGateway
```

例如：

```python
class LLMGateway:

    async def invoke(...):
        ...

    async def structured(...):
        ...

    async def stream(...):
        ...
```

内部再使用 LangChain Model。

因此：

```text
Agent

↓

LLMGateway

↓

LangChain

↓

OpenAI / Claude / Gemini / MiniMax / Local
```

LangChain当前提供多个主流模型提供商的统一集成入口，并支持 tool calling、structured output 和多模态等模型能力。([Docs by LangChain][3])

---

# 18. Structured Output

AI漫剧系统不应该大量依赖自然语言解析。

例如：

不要：

```text
"这一场可以拆成三个镜头，第一个镜头……"
```

应该返回：

```python
class ShotPlan(BaseModel):

    shot_type: str

    camera_angle: str

    camera_movement: str | None

    composition: str

    characters: list[str]

    action: str

    emotion: str

    dialogue: str | None

    duration: float
```

然后通过 LangChain Structured Output 获取：

```text
list[ShotPlan]
```

Structured Output是 LangChain 当前 Agent API 的一等能力，可将最终结果约束成应用可直接消费的结构化对象。([Docs by LangChain][1])

---

# 19. 核心 AI Schema

建议建立：

```text
StoryAnalysis

CharacterExtraction

LocationExtraction

ScenePlan

ShotPlan

PromptPlan

ContinuityReport

GenerationPlan

ReviewResult

ModificationPlan
```

其中：

```text
Pydantic Model
```

成为：

> LLM 与 Studio Domain 之间的数据契约。

---

# 20. Director Agent

第一版只需要一个主 Agent：

```text
DirectorAgent
```

而不是马上拆成：

```text
编剧Agent
导演Agent
摄影Agent
审核Agent
Prompt Agent
```

第一阶段：

```text
Director Agent
+
Skills
+
Tools
```

复杂以后再演化 Multi-Agent。

---

# 21. Director Agent State

建议：

```python
class DirectorState(TypedDict):

    project_id: str

    session_id: str

    user_request: str

    intent: dict

    context: dict

    plan: list

    current_step: int

    tool_results: list

    affected_entities: list

    pending_approval: dict | None

    errors: list

    final_response: str | None
```

LangGraph强调共享 State，并将复杂工作拆成离散节点，这种模式适合可检查、可恢复的 Agent 执行。([Docs by LangChain][4])

---

# 22. Director Graph

第一版：

```text
START
  │
  ▼
Understand Intent
  │
  ▼
Load Context
  │
  ▼
Create Plan
  │
  ▼
Risk Check
  │
  ├──── HIGH RISK ───→ Request Approval
  │                        │
  │                      Resume
  │                        │
  └────────────────────────┘
  │
  ▼
Execute Tool
  │
  ▼
Observe Result
  │
  ▼
Review
  │
  ├── Need More Work ───→ Execute Tool
  │
  └── Complete
           │
           ▼
         END
```

---

# 23. Human In The Loop

这是漫剧 Studio 很重要的能力。

例如：

用户：

```text
"把整集全部重新生成。"
```

Agent识别：

```text
影响 86 个 Shot
成本较高
```

Graph进入：

```text
interrupt
```

UI显示：

```text
AI准备重新生成86个镜头。

预计涉及：

86 Image Generation
64 Video Generation

[确认]
[取消]
```

用户确认后继续原来的 Agent Run。

LangGraph interrupt支持暂停 Graph、通过持久化保存状态，并在收到外部输入后继续运行，非常适合这种审批流程。([Docs by LangChain][5])

---

# 24. Checkpoint

Agent不能因为：

```text
软件关闭
网络断开
模型错误
```

就完全忘记正在执行什么。

因此：

```text
Director Graph
```

采用 Checkpointer。

开发阶段可使用：

```text
SQLite Checkpointer
```

未来云端：

```text
PostgreSQL Checkpointer
```

LangGraph官方提供独立的 SQLite 和 PostgreSQL checkpointer 实现。([Docs by LangChain][6])

但：

**LangGraph Checkpoint ≠ Project Database。**

两者必须严格分开。

---

# 25. Project State 与 Agent State

Project State：

```text
Scene
Shot
Character
Asset
Generation
Version
```

长期保存。

Agent State：

```text
当前任务
执行到哪一步
当前 Plan
Tool Results
Pending Approval
```

用于任务执行。

因此：

```text
Project State
=
业务真相

Agent State
=
AI工作记忆
```

---

# 26. ContextService

不要让 LangGraph直接随意查询整个数据库。

统一通过：

```text
ContextService
```

提供：

```text
get_project_context

get_scene_context

get_shot_context

get_character_context

get_generation_context
```

---

# 27. Context Builder

例如用户：

> 让第14镜接第13镜自然一点。

只加载：

```text
Project Style

Scene 03

Shot 13

Shot 14

Relevant Characters

Costumes

Relevant Assets

Continuity State
```

而不是：

```text
整个项目
整个小说
所有聊天记录
```

---

# 28. Agent Tool Layer

LangChain Tool 不能直接等于数据库操作。

例如 Tool：

```text
update_shot
```

内部：

```text
LangChain Tool
      ↓
ShotService.update()
      ↓
Repository
```

LangChain Tools本质上是具有明确定义输入输出的可调用函数，可由模型根据上下文选择调用。([Docs by LangChain][7])

---

# 29. 第一版 Tools

建议只开放：

```text
get_project

get_episode

get_scene

get_scene_shots

get_shot

create_scene

create_shot

update_scene

update_shot

create_character

update_character

generate_image

generate_video

check_continuity

list_assets

select_asset

create_version
```

---

# 30. Tool 风险等级

## Level 0

Read Only

```text
get_project

get_scene

get_shot
```

自动执行。

---

## Level 1

Normal Mutation

```text
update_shot

create_shot

change_prompt
```

自动创建 Version。

---

## Level 2

Expensive

```text
generate_image

generate_video

batch_generate
```

根据配置决定是否确认。

---

## Level 3

Destructive

```text
delete_scene

delete_asset

batch_delete
```

必须确认。

---

# 31. Skills 架构

Skill不是 Tool。

Skill代表：

```text
"如何完成某种专业任务"
```

第一版：

```text
ScriptAnalysisSkill

CharacterDesignSkill

ScenePlanningSkill

StoryboardSkill

PromptSkill

ContinuitySkill

ReviewSkill
```

例如：

```text
StoryboardSkill
```

内部可能：

```text
读取 Scene
↓
读取角色
↓
调用 LLM
↓
返回 ShotPlan[]
↓
调用 ShotService
```

---

# 32. Multi-Agent 暂缓

LangChain目前也支持多 Agent 架构，包括 subagents、handoffs、skills 等模式。([Docs by LangChain][8])

但 MVP 不建议直接设计：

```text
Director
├── Writer Agent
├── Camera Agent
├── Prompt Agent
├── Continuity Agent
└── Review Agent
```

优先：

```text
ONE Director

+

Many Skills
```

只有当某一个 Skill拥有：

```text
独立 Context
独立工具
独立循环
独立目标
```

再升级成 Sub-Agent。

---

# 33. Agent API

核心 API：

```text
POST /api/agents/director/runs
```

Request：

```json
{
    "project_id": "project_001",
    "message": "把第三场改得紧张一些"
}
```

Response：

```json
{
    "run_id": "agent_run_001",
    "status": "running"
}
```

---

# 34. Agent Streaming

前端需要实时看到：

```text
正在读取第三场

正在分析镜头

计划修改5个镜头

正在修改 Shot 12

正在修改 Shot 13
```

而不是等待最后一次性返回。

LangChain/LangGraph支持流式返回 Agent 与工具执行更新，可作为 Studio Agent 状态 UI 的基础。([Docs by LangChain][9])

建议：

```text
WS /api/agents/runs/{run_id}/events
```

或：

```text
SSE
```

---

# 35. Agent Event

统一事件：

```json
{
    "type": "agent.tool.started",

    "run_id": "xxx",

    "tool": "update_shot",

    "entity_id": "shot_013"
}
```

以及：

```text
agent.started

agent.plan.created

agent.tool.started

agent.tool.completed

agent.interrupted

agent.resumed

agent.completed

agent.failed
```

---

# 36. Generation 与 Agent 分离

非常重要。

Agent调用：

```text
generate_image
```

Tool内部只做：

```text
GenerationService.create()
```

然后立即得到：

```text
generation_id
```

Agent不应该坐在那里等 ComfyUI 跑完。

---

# 37. Generation 架构

```text
Agent / UI

↓

GenerationService

↓

Generation Record

↓

Task Queue

↓

Production Worker

↓

ProviderRegistry

↓

ImageProvider / VideoProvider

↓

ComfyUI / External API
```

---

# 37.1 Generation 状态机与 Worker 语义（P1-E2-T02）

- 状态表集中定义（app/generations/state.py）：created→queued→running→
  {completed|failed|cancelled|retrying→running}；running→queued 仅用于
  lease 过期恢复（进程崩溃）。非法迁移返回 409 Domain Error，禁止直接写状态。
- 原子认领：Worker 用条件 UPDATE 认领（status IN (queued,retrying) AND
  backoff 到期 AND (无 claim 或 lease 过期)），rowcount=1 才算获得；两个执行器
  竞争同一 Generation 只有一个成功。
- lease 与崩溃恢复：认领写入 claim_token/claimed_at/lease_expires_at，
  进度心跳续期；过期 lease 的行由恢复扫描重新排队（attempts+1），预算耗尽则
  failed（"lease expired"）。
- 重试退避：失败 → retrying + next_attempt_at = now + min(cap, base·2^(n-1))；
  认领查询跳过未到期的行。
- concurrency 校验：MVP 只支持单 Worker（settings.generation_concurrency=1，
  启动时校验，不暴露虚假并行）；Worker 心跳进入 /health 的 worker 字段。

---

# 38. ImageProvider

统一：

```python
class ImageProvider:

    async def submit(...):
        ...

    async def status(...):
        ...

    async def cancel(...):
        ...
```

实现：

```text
ComfyUIImageProvider

OpenAIImageProvider

MiniMaxImageProvider
```

---

# 39. VideoProvider

```text
ComfyUIVideoProvider

MiniMaxVideoProvider

OtherVideoProvider
```

业务层调用：

```text
VideoProvider
```

不知道最终使用哪个模型。

---

# 40. ComfyUI Adapter

ComfyUI模块：

```text
ComfyUIClient

ComfyUIProvider

WorkflowTemplate

WorkflowMapper

OutputResolver

WebSocketMonitor
```

---

# 41. ComfyUI 调用流程

Provider / Workflow 契约（P1-E2-T01）：

- 规范 provider id：`mock` | `comfyui`。Generation 创建时把请求中的 provider
  解析为规范 id（缺省 = `settings.image_provider`），未知 id 返回 422；
  落库的 `generation.provider` 就是 Worker 实际执行的实现（Registry 按 id 解析，
  不再忽略该字段）。media type 只支持 image，video 请求 fail fast 422。
- workflow catalog：`workflow_id` 决定模板文件（`workflow_mapper.py` 的
  WORKFLOW_CATALOG），未知 id 422；模板目录 = `settings.workflows_dir`
  （默认仓库根 `workflows/`，可用 `STUDIO_WORKFLOWS_DIR` 覆盖以适配打包布局）。
- preflight：模板必须是合法 JSON、声明恰好一个 `SaveImage` 输出节点、包含全部
  必需 placeholder（`$PROMPT/$SEED/$WIDTH/$HEIGHT`），否则 ComfyUIError 在生成前失败；
  `POST /providers/comfyui/test` 在连接成功后同时报告 workflow preflight 状态。
- WS monitor 不再硬编码输出 node id（"executed"/"execution_error" 事件承载终态）。

```text
GenerationRequest
       ↓
ComfyUIProvider
       ↓
Load Workflow Template (workflow_id → catalog → preflight)
       ↓
Inject Parameters
       ↓
Upload Reference
       ↓
Queue Prompt
       ↓
prompt_id
       ↓
WebSocket Monitor
       ↓
History
       ↓
Output
       ↓
AssetService
       ↓
MediaVersion
```

---

# 42. Workflow Parameter Mapping

Studio只理解：

```text
prompt

negative_prompt

seed

reference_image

width

height

character_reference
```

映射层负责：

```text
prompt
→ Node 12.text

seed
→ Node 31.seed
```

因此 Agent 永远不需要理解：

```text
KSampler

CLIP

VAE

ControlNet Node
```

---

# 43. Production Workflow Engine

第一版需要支持：

```text
Task

Dependency

Queue

Retry

Cancel

Resume

Progress

Parallel
```

Task State：

```text
PENDING

READY

QUEUED

RUNNING

WAITING

SUCCESS

FAILED

RETRYING

CANCELLED
```

---

# 44. Production Workflow 示例

```text
Scene 03

         ┌─ Shot12 Image ─ Review ─ Video ─ Review
         │
START ───┼─ Shot13 Image ─ Review ─ Video ─ Review
         │
         └─ Shot14 Image ─ Review ─ Video ─ Review

                          ↓

                     Scene Review

                          ↓

                         END
```

---

# 45. 不要用 LangGraph 替代 Production Engine

原因：

Agent Graph处理：

```text
认知
决策
Tool调用
审批
```

Production Engine处理：

```text
GPU任务
长时间视频任务
队列
并发
资源
成本
重试
```

它们生命周期不同。

---

# 46. ContinuityService

负责：

```text
analyze_shot

analyze_transition

check_scene

detect_issue

suggest_fix
```

输出：

```python
class ContinuityReport(BaseModel):

    score: float

    character_issues: list

    costume_issues: list

    action_issues: list

    spatial_issues: list

    lighting_issues: list

    suggestions: list
```

这里同样适合 LangChain Structured Output。

---

# 47. 多模态 Vision

VisionProvider 负责：

```text
analyze_image

compare_images

analyze_video

extract_visual_state
```

ContinuitySkill可以：

```text
Shot 13 Last Frame

+

Shot 14 First Frame

↓

Vision Model

↓

ContinuityReport
```

---

# 48. Agent Memory

分为：

## Thread Memory

LangGraph运行状态。

---

## Project Memory

SQLite：

```text
Project
Scene
Shot
Character
Asset
```

---

## Semantic Memory

用于：

```text
小说
世界观
人物设定
风格指南
参考资料
```

RAG检索。

LangGraph文档也明确区分短期 Agent state 与跨会话长期 memory，因此 Studio可以利用其运行态能力，但项目领域数据仍应由自己的持久化层掌握。([Docs by LangChain][10])

---

# 49. LangChain Middleware

后期可考虑使用：

```text
Model Retry

Tool Retry

Summarization

Tool Selection
```

LangChain目前提供包括 Tool Retry、Model Retry、Summarization、LLM Tool Selector 等预构建 middleware。([Docs by LangChain][11])

但 MVP 不要过度使用 Middleware。

第一版优先保持执行路径透明。

---

# 50. MCP 预留

未来可以考虑：

```text
Studio Tool
↔
MCP
```

例如外部插件：

```text
素材网站

项目管理

云盘

第三方生成平台
```

LangChain目前可以把 MCP Server 暴露的工具转换为 LangChain Agent可直接使用的 Tools。([Docs by LangChain][12])

但：

**MCP 不进入 MVP。**

只预留 Tool Registry。

---

# 51. 前端与后端通信

普通业务：

```text
REST
```

实时状态：

```text
WebSocket
```

例如：

```text
REST

Project
Scene
Shot
Asset
Settings
```

WebSocket：

```text
Agent Event

Generation Progress

Workflow Progress

ComfyUI Status
```

---

# 52. MVP API

## Project

```text
POST   /api/projects

GET    /api/projects

GET    /api/projects/{id}

PATCH  /api/projects/{id}
```

## Episode

```text
POST /api/projects/{id}/episodes

POST /api/episodes/{id}/analyze
```

## Scene

```text
GET  /api/episodes/{id}/scenes

POST /api/scenes/{id}/generate-shots
```

## Shot

```text
GET   /api/scenes/{id}/shots

GET   /api/shots/{id}

PATCH /api/shots/{id}
```

## Generation

```text
POST /api/shots/{id}/generate-image

GET  /api/generations/{id}

POST /api/generations/{id}/retry

POST /api/generations/{id}/cancel
```

## Agent

```text
POST /api/agents/director/runs

GET  /api/agents/runs/{id}

POST /api/agents/runs/{id}/resume
```

## Provider

```text
GET  /api/providers

POST /api/providers/comfyui/test
```

---

# 53. Agent Run 生命周期

```text
CREATED

RUNNING

WAITING_APPROVAL

WAITING_TOOL

COMPLETED

FAILED

CANCELLED
```

---

# 54. Agent 与 Generation 生命周期

例如：

用户：

> 把第三场改好并重新生成。

过程：

```text
Agent Run
    │
    ├─ Modify Shot12
    ├─ Modify Shot13
    ├─ Modify Shot14
    │
    └─ Create Workflow Run
              │
              ├─ Generation 01
              ├─ Generation 02
              └─ Generation 03
```

Agent任务可以已经：

```text
COMPLETED
```

而 Generation仍然：

```text
RUNNING
```

这是正确状态。

不要强行让 Agent等完整生产结束。

---

# 55. Agent Audit

每次 AI修改业务对象记录：

```text
AgentAction
```

例如：

```json
{
    "run_id": "run_001",

    "action": "update_shot",

    "entity": "shot_013",

    "before": {
        "shot_type": "wide"
    },

    "after": {
        "shot_type": "close_up"
    }
}
```

因此可以实现：

```text
Undo AI Changes
```

---

# 56. Agent 可观测性

建议每个 Agent Run 保存：

```text
run_id

session_id

project_id

model

tokens

latency

tool_calls

error

created_at
```

每个 Generation 保存：

```text
provider

model

cost

latency

success

retry_count
```

这样以后能够真正优化：

```text
哪个模型适合剧本

哪个模型适合分镜

哪个模型成本最低

哪个 Workflow 最稳定
```

---

# 57. Error Boundary

LangChain异常不能直接冒到 UI。

统一：

```text
StudioError

AgentError

ModelError

ToolError

GenerationError

ProviderError

WorkflowError

ComfyUIError
```

例如：

```text
OpenAI Timeout
```

转换成：

```text
ModelProviderUnavailable
```

错误响应契约（P1-E4-T01）：

- 所有失败（领域错误、422 校验、未知路由 404、405、未捕获异常 500）统一输出
  `{"error": {code, message, details, request_id}}` Envelope。
- `request_id` 由 HTTP 中间件生成（优先 `X-Request-ID` 请求头），回传响应头，
  并贯穿所有错误响应；前端 ApiError 携带 request_id 供复制排查。
- 校验错误详情只含 loc/type/msg，不回显请求体（防 secrets/整段原文泄露）。
- 未捕获异常只记录服务端日志（含堆栈），响应为通用 INTERNAL_ERROR。

---

# 58. 第一阶段开发顺序

## Phase 1

业务基础：

```text
FastAPI

SQLite

SQLAlchemy

Project

Episode

Scene

Shot

Asset
```

---

## Phase 2

Service：

```text
ProjectService

SceneService

ShotService

AssetService
```

---

## Phase 3

LangChain：

```text
LLMGateway

Model Factory

Structured Output
```

打通：

```text
小说
↓
ScenePlan
↓
ShotPlan
```

---

## Phase 4

ComfyUI：

```text
ComfyUIClient

ComfyUIProvider

WorkflowMapper

GenerationService
```

打通：

```text
Shot
↓
Image
↓
Asset
```

---

## Phase 5

LangGraph：

实现：

```text
DirectorState

Context Node

Planner Node

Tool Node

Review Node

Interrupt
```

---

## Phase 6

AI Director：

打通：

```text
"把第三镜改成近景"
↓
Director Graph
↓
update_shot Tool
↓
ShotService
↓
Database
↓
Frontend Update
```

---

## Phase 7

Production Workflow：

```text
Batch Generation

Queue

Retry

Parallel Generation
```

---

## Phase 8

Continuity：

```text
Vision

ContinuityState

ContinuityReport

Auto Fix
```

---

# 59. MVP 第一条完整 AI 链路

最终必须优先打通：

```text
用户导入小说

↓

ScriptService

↓

LangChain Structured Output

↓

ScenePlan

↓

SceneService

↓

ShotPlan

↓

ShotService

↓

Storyboard

↓

用户：
"生成第五镜"

↓

GenerationService

↓

ComfyUIProvider

↓

ComfyUI

↓

AssetService

↓

MediaVersion

↓

Storyboard Update
```

---

# 60. MVP 第一条完整 Agent 链路

```text
用户：

"第五镜人物太远了，改成近景再重新生成。"

↓

Director Agent

↓

LangGraph

↓

Understand Intent

↓

ContextService

↓

Shot005 Context

↓

ModificationPlan

↓

update_shot

↓

ShotService

↓

create_version

↓

generate_image

↓

GenerationService

↓

Workflow Engine

↓

ComfyUI
```

这条链路跑通以后：

**你的项目才真正拥有了 Agent。**

---

# 61. 系统最终职责边界

```text
LangChain
│
├── Models
├── Tools
├── Structured Output
└── AI Utilities


LangGraph
│
├── Agent State
├── Agent Loop
├── Routing
├── Interrupt
├── Checkpoint
└── Resume


Studio Services
│
├── Project
├── Scene
├── Shot
├── Character
├── Asset
├── Version
└── Continuity


Production Engine
│
├── Task
├── Queue
├── DAG
├── Retry
├── Parallel
└── Progress


Provider Gateway
│
├── LLM
├── Vision
├── Image
├── Video
└── Audio


Renderer
│
├── ComfyUI
├── OpenAI Image
├── MiniMax
└── Local Models
```

---

# 62. 架构红线

整个项目必须长期遵守以下规则。

### 红线一

LangChain不能直接操作数据库。

### 红线二

LangGraph不能成为 Project State。

### 红线三

Agent不能直接调用 ComfyUI。

### 红线四

前端不能直接调用 ComfyUI。

### 红线五

业务 Service不能依赖 LangGraph。

### 红线六

ShotService不能知道具体模型。

### 红线七

GenerationService不能知道剧情逻辑。

### 红线八

Provider不能知道 Episode / Scene / Shot 的业务语义。

---

# 63. 最终架构

```text
                         User
                           │
                           ▼
                    ┌─────────────┐
                    │ Studio UI   │
                    └──────┬──────┘
                           │
          ┌────────────────┴────────────────┐
          │                                 │
          ▼                                 ▼
     Direct Action                    AI Director
          │                                 │
          │                            LangGraph
          │                                 │
          │                            LangChain
          │                                 │
          │                            Agent Tools
          │                                 │
          └────────────────┬────────────────┘
                           ▼
                    Application Layer
                           │
           ┌───────────────┼────────────────┐
           ▼               ▼                ▼
      ProjectService   ShotService    AssetService
                           │
                           ▼
                  GenerationService
                           │
                           ▼
                  Production Engine
                           │
                           ▼
                    Provider Gateway
                    /      |       \
                   /       |        \
                  ▼        ▼         ▼
              ComfyUI   GPT Image   Video API
                  │
                  ▼
                Asset
                  │
                  ▼
                Shot
```

---

# 64. 最终技术定义

AI 漫剧 Studio 后端最终由三个 Runtime 组成：

## 第一层：Application Runtime

负责：

```text
项目
角色
场景
镜头
资产
版本
```

这是产品基础。

---

## 第二层：Agent Runtime

```text
LangGraph
+
LangChain
```

负责：

```text
理解
计划
决策
Tool Calling
Context
审批
循环
```

这是产品智能。

---

## 第三层：Production Runtime

负责：

```text
ComfyUI
图片
视频
Queue
Workflow
Retry
GPU Task
```

这是产品生产能力。

最终形成：

> **Application Runtime + Agent Runtime + Production Runtime**

这三层共同构成完整的 **AI Manga Drama Production System**。

其中真正需要长期保持稳定的是：

> **Domain Model + Project State + Service Layer + Production Graph。**

LangChain、LangGraph、ComfyUI、GPT Image、视频模型全部属于可替换能力层。

这能够保证底层 AI 技术快速变化时，AI 漫剧 Studio 的核心产品架构仍然保持稳定。

---

## 引用

本文档引用的 LangChain 官方文档：

- [1] LangChain Docs — Structured Output：https://python.langchain.com/docs/concepts/structured_outputs/
- [2] LangChain Docs — LangGraph / Agent orchestration：https://python.langchain.com/docs/concepts/agents/
- [3] LangChain Docs — Model integration / Chat Models：https://python.langchain.com/docs/concepts/chat_models/
- [4] LangChain Docs — LangGraph State：https://langchain-ai.github.io/langgraph/concepts/state/
- [5] LangChain Docs — Human in the Loop / Interrupt：https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/
- [6] LangChain Docs — Checkpointer（SQLite / PostgreSQL）：https://langchain-ai.github.io/langgraph/concepts/persistence/
- [7] LangChain Docs — Tools：https://python.langchain.com/docs/concepts/tools/
- [8] LangChain Docs — Multi-Agent（subagents / handoffs / skills）：https://python.langchain.com/docs/concepts/multi_agent/
- [9] LangChain Docs — Streaming：https://python.langchain.com/docs/concepts/streaming/
- [10] LangChain Docs — Memory：https://python.langchain.com/docs/concepts/memory/
- [11] LangChain Docs — Middleware：https://python.langchain.com/docs/concepts/middleware/
- [12] LangChain Docs — MCP：https://python.langchain.com/docs/concepts/mcp/

> 这版可以作为后端的**主架构文档**使用。LangGraph 的 durable execution、interrupt/checkpoint 适合 AI Director，而 LangChain 的 Tool 与 Structured Output 特别适合把自然语言转成 `ScenePlan / ShotPlan / ContinuityReport`；两者都不应取代 Studio 自己的领域层和生产任务引擎。
