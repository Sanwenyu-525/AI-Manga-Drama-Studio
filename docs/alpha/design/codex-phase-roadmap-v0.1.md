# AI 漫剧 Studio Alpha Codex 分阶段开发任务清单 v0.1

**文档状态：** Draft
**用途：** Codex 主开发计划 / Alpha Roadmap
**执行对象：** Codex / 开发者
**阶段：** MVP → Alpha

**上游设计文档：**

1. 《AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1》
2. 《AI 漫剧 Studio 核心领域模型详细设计 v0.1》
3. 《AI 漫剧 Studio 数据库 Schema 与数据关系设计 v0.1》
4. 《AI 漫剧 Studio Alpha Backend API & Service 详细设计 v0.1》
5. 《Asset / Generation / Version 系统详细设计 v0.1》
6. 《Job Queue & Generation State Machine 详细设计 v0.1》
7. 《AI Director Agent Alpha 架构详细设计 v0.2》
8. 《Continuity Engine 详细设计 v0.1》
9. 《Alpha 前端 UX / 信息架构与交互设计 v0.1》
10. 《Alpha 前端 Component / Store / API Contract 详细设计 v0.1》

---

# 1. 本计划的目标

Codex 后续不能再采用：

```text
发现什么做什么
↓
临时设计
↓
直接修改
↓
继续堆功能
```

模式。

改为：

```text
Architecture
      ↓
Phase
      ↓
Epic
      ↓
Task
      ↓
Implementation
      ↓
Test
      ↓
Acceptance
      ↓
Phase Gate
```

每个阶段只有通过：

```text
Phase Gate
```

才能进入下一阶段。

---

# 2. Alpha 最终目标

Alpha 完成时必须支持完整用户链：

```text
Create Project
 ↓
Import Novel
 ↓
Episode
 ↓
Scene
 ↓
Shot
 ↓
Character / Location
 ↓
AI Director
 ↓
ShotVisualSpec
 ↓
Prompt
 ↓
Generation
 ↓
Asset Version
 ↓
Job Queue
 ↓
ComfyUI / Provider
 ↓
Continuity
 ↓
Timeline
 ↓
Render
```

同时具备：

```text
Edit
Regenerate
Version
MASTER
ACTIVE
STALE
Retry
Pause
Resume
Cancel
Recovery
Provenance
Human Review
```

---

# 3. Alpha 不做的内容

本计划明确排除：

```text
多人实时协作

云 GPU 集群调度

完整 Premiere 替代

完整 ComfyUI Node Editor

Workflow Marketplace

Agent Marketplace

复杂权限系统

大型云端 SaaS

移动端 Studio

专业调色

复杂合成

高级音频工作站
```

发现这些需求时：

```text
记录到 Beta Backlog
```

不要插入 Alpha 当前 Phase。

---

# 4. 开发阶段总览

```text
Phase 0  MVP Baseline & Architecture Audit

Phase 1  Project Domain & Persistence

Phase 2  Story / Scene / Shot Core

Phase 3  Asset / Version / Generation

Phase 4  Provider & ComfyUI Adapter

Phase 5  Persistent Job Queue

Phase 6  Studio Frontend Core

Phase 7  AI Director Agent

Phase 8  Continuity Engine

Phase 9  Timeline & Episode Render

Phase 10 Alpha Hardening
```

依赖关系：

```text
P0
 ↓
P1
 ↓
P2
 ↓
P3
 ↓
P4
 ↓
P5
 ↓
P6
 ↓
P7
 ↓
P8
 ↓
P9
 ↓
P10
```

部分工作可以交叉，但：

> **Phase Gate 不应跳过。**

---

# 5. 任务状态

统一使用：

```text
TODO

READY

IN_PROGRESS

BLOCKED

REVIEW

DONE

DEFERRED
```

不要使用含糊的：

```text
almost done
mostly finished
temporary done
```

---

# 6. 优先级

```text
P0 = 阻塞 Alpha 主链

P1 = Alpha 必须

P2 = 强烈建议

P3 = Beta / 优化
```

---

# 7. Git 分支规则

每一个明确功能任务：

```text
新建独立分支
```

推荐：

```text
feature/P1-project-core

feature/P2-shot-core

feature/P3-asset-version

feature/P4-comfyui-adapter

feature/P5-job-queue

feature/P6-studio-shell

feature/P7-director-agent

feature/P8-continuity

feature/P9-timeline

fix/xxx

refactor/xxx
```

禁止长期：

```text
直接在 main 上开发
```

---

# 8. Codex 每次执行的基本规则

Codex 开始 Task 前必须：

```text
1. 阅读当前 Task
2. 阅读相关设计文档
3. 检查现有代码
4. 判断已有能力是否可复用
5. 输出修改范围
6. 实现
7. 测试
8. 自审
9. 更新 Task 状态
```

禁止：

```text
未检查现有实现就重写

为了完成 Task 顺便大规模重构

修改 Task 范围外模块

静默修改既有业务规则
```

---

# Phase 0 — MVP Baseline & Architecture Audit

# 9. Phase 0 目标

不是开发新功能。

首先回答：

```text
当前 MVP 到底有什么？
```

输出：

```text
Current Architecture Map

Feature Inventory

Technical Debt

Reusable Modules

Gap Analysis

Migration Plan
```

---

# 10. Epic P0-E1 — Repository Audit

## P0-T001 项目结构扫描

**目标：**

输出当前 Repository：

```text
Frontend
Backend
Agent
ComfyUI
Storage
Database
Desktop Runtime
```

实际结构。

**交付物：**

```text
docs/alpha/audit/repository-map.md
```

包含：

```text
目录

模块

技术栈

启动入口

模块依赖

关键配置
```

---

## P0-T002 现有功能清单

整理当前已经实现：

```text
Novel Import

Scene

Shot

Prompt

Image

Video

ComfyUI

Agent

Timeline
```

分别达到什么状态。

输出：

```text
feature-inventory.md
```

状态：

```text
READY
PARTIAL
PROTOTYPE
MISSING
```

---

## P0-T003 数据模型审查

对照目标领域模型：

```text
Project
Episode
Scene
Shot
Character
Asset
Generation
Job
```

检查现有 Entity / Schema。

输出：

```text
domain-gap-analysis.md
```

---

## P0-T004 API 审查

记录：

```text
现有 Endpoint

实际 Request

Response

同步 / 异步

调用方
```

识别：

```text
需要保留
需要迁移
需要废弃
```

---

## P0-T005 前端状态管理审查

检查：

```text
Store

Global State

Component Local State

API 调用

SSE / WebSocket
```

输出重构建议。

---

## P0-T006 ComfyUI 接入审查

明确当前：

```text
Workflow 如何存储

Node ID 是否硬编码

Prompt 如何注入

Output 如何获取

是否有 Progress

是否支持 Cancel
```

---

# 11. Phase 0 Gate

必须得到：

```text
MVP Baseline Report
```

并明确：

```text
保留什么

删除什么

重构什么

迁移什么
```

**禁止在 Phase 0 一边审查一边大规模重写。**

---

# Phase 1 — Project Domain & Persistence

# 12. Phase 1 目标

正式建立：

```text
Project Database
+
Domain Foundation
+
Repository
+
Migration
```

这是后面所有系统基础。

---

# 13. Epic P1-E1 — Project Persistence

## P1-T001 Project Aggregate

实现：

```text
Project

ProjectStatus

ProjectType

ProjectSettings
```

验收：

```text
Create
Open
Update
Archive
Restore
```

全部有测试。

---

## P1-T002 Project Database

建立：

```text
project.db
```

并实现：

```text
SQLite

WAL

foreign_keys ON

Migration
```

---

## P1-T003 Global Project Registry

实现：

```text
app.db
```

只管理：

```text
Recent Project

Project Path

Last Opened
```

不得保存 Shot 等业务数据。

---

## P1-T004 Migration Framework

建立：

```text
V001...
```

Migration 机制。

必须支持：

```text
Detect Version

Backup

Migrate

Integrity Check
```

---

## P1-T005 Repository 基础

建立：

```text
ProjectRepository
```

及 Repository 基础约定。

---

## P1-T006 Project Application Service

实现：

```text
createProject()

openProject()

updateProject()

archiveProject()

restoreProject()
```

---

## P1-T007 Project API

实现：

```text
POST /projects

GET /projects

GET /projects/{id}

PATCH /projects/{id}

POST /projects/{id}/open
```

---

# 14. Epic P1-E2 — Storage Foundation

## P1-T008 Project Directory

正式建立：

```text
project/
├ project.db
├ assets/
├ workflows/
├ cache/
├ thumbnails/
├ exports/
└ logs/
```

---

## P1-T009 StorageService

实现：

```text
store

copy

move

exists

checksum

resolve

delete
```

禁止业务层直接大量操作文件系统。

---

## P1-T010 DesktopAdapter

前端桌面能力抽象：

```text
openFile

revealFile

selectFolder
```

不要绑定具体桌面框架到业务组件。

---

# 15. Phase 1 Gate

必须可以：

```text
Create Project
 ↓
Close Studio
 ↓
Reopen
 ↓
Project Complete
```

并且：

```text
Migration
Backup
Archive
```

正常。

---

# Phase 2 — Story / Scene / Shot Core

# 16. Phase 2 目标

建立真正的漫剧工程层级：

```text
Project
 ↓
Episode
 ↓
Scene
 ↓
Shot
```

---

# 17. Epic P2-E1 — Story Structure

## P2-T001 SourceDocument

实现：

```text
NOVEL
SCRIPT
OUTLINE
REFERENCE
```

支持：

```text
Import TXT / Markdown
```

复杂文档格式可以后续。

---

## P2-T002 Episode

实现：

```text
Create

Update

Order

Archive
```

---

## P2-T003 Scene

实现：

```text
Create

Update

Order

Archive
```

---

## P2-T004 Shot

实现：

```text
Create

Update

Move

Duplicate

Archive
```

---

## P2-T005 ShotVisualSpec

正式分离：

```text
Shot
```

与：

```text
ShotVisualSpec
```

---

## P2-T006 Shot Character Binding

实现：

```text
ShotCharacter
```

支持：

```text
Character

Version

Costume

Position

Action
```

---

# 18. Epic P2-E2 — Character & Location

## P2-T007 Character Core

实现：

```text
Character

CharacterVersion
```

---

## P2-T008 Character MASTER

实现：

```text
masterVersionId
```

但 Phase 2 暂不处理完整 STALE。

---

## P2-T009 Location

实现：

```text
Location

LocationVersion

Master
```

---

## P2-T010 Costume 基础

实现：

```text
Costume
```

先不做复杂版本。

---

# 19. Epic P2-E3 — Read Models

## P2-T011 ProjectTreeView

一次返回：

```text
Episode
Scene
Shot Summary
```

---

## P2-T012 SceneEditorView

返回：

```text
Scene
Shots
Shot Summary
```

---

## P2-T013 ShotInspectorView

建立 Inspector Read Model 框架。

---

# 20. Phase 2 Gate

必须可以：

```text
Import Story
 ↓
Create Episode
 ↓
Create Scenes
 ↓
Create Shots
 ↓
Bind Characters
 ↓
Close
 ↓
Reopen
```

数据完全保留。

---

# Phase 3 — Asset / Version / Generation

# 21. Phase 3 目标

这是从：

```text
文件生成 Demo
```

升级为：

```text
Production Studio
```

的关键阶段。

---

# 22. Epic P3-E1 — Asset Core

## P3-T001 Asset Entity

实现：

```text
Asset

AssetType

AssetSourceType

AssetStatus
```

---

## P3-T002 Asset Registration

所有生成结果：

必须：

```text
file
 ↓
Asset
```

禁止只返回 filePath。

---

## P3-T003 Asset Import

实现：

```text
Import

Copy Into Project

Checksum

Metadata
```

---

## P3-T004 MediaProbeService

至少支持：

```text
Image

Video

Audio
```

元数据。

---

## P3-T005 Asset Missing Detection

发现文件缺失：

```text
READY → MISSING
```

不能删除 DB Record。

---

# 23. Epic P3-E2 — Version

## P3-T006 Version Group

实现：

```text
Shot Image Versions

Shot Video Versions
```

---

## P3-T007 Version Number

实现安全：

```text
v1
v2
v3
```

分配。

---

## P3-T008 Active Asset

支持：

```text
Set Active
```

必须显式。

---

## P3-T009 Version History API

实现：

```text
GET image versions

GET video versions
```

---

## P3-T010 Character MASTER 完整化

Master 切换时：

产生领域事件。

---

# 24. Epic P3-E3 — Generation

## P3-T011 Generation Entity

实现：

```text
Generation

Status

Target

Provider

Model

WorkflowVersion

PromptVersion
```

---

## P3-T012 GenerationInput

记录：

```text
Asset

PromptVersion

CharacterVersion

LocationVersion
```

---

## P3-T013 GenerationOutput

所有输出：

```text
Generation
→ Asset
```

---

## P3-T014 Immutable Generation

运行开始后禁止修改：

```text
input

prompt

model

workflow

parameters
```

---

## P3-T015 Retry Chain

实现：

```text
Generation 100 failed
 ↓
Generation 101
parent = 100
```

---

## P3-T016 Provenance

实现：

```text
Asset
 ↓
Generation
 ↓
Inputs
```

查询。

---

# 25. Epic P3-E4 — Prompt Version

## P3-T017 Prompt

建立：

```text
Prompt

PromptVersion
```

---

## P3-T018 Active Prompt Version

Shot 使用具体：

```text
PromptVersion ID
```

---

## P3-T019 Prompt History

支持：

```text
创建新版本

查看历史

Activate
```

---

# 26. Phase 3 Gate

必须完成真实闭环：

```text
Shot
 ↓
Prompt v1
 ↓
Generation
 ↓
Image v1

Regenerate
 ↓
Image v2

User chooses
 ↓
v1 ACTIVE
```

并可查询：

```text
Image v2 是怎么生成的？
```

---

# Phase 4 — Provider & ComfyUI Adapter

# 27. Phase 4 目标

让业务层彻底脱离：

```text
ComfyUI Node ID
```

---

# 28. Epic P4-E1 — Provider Abstraction

## P4-T001 ProviderAdapter

定义：

```text
ImageProviderAdapter

VideoProviderAdapter

WorkflowProviderAdapter

LlmProviderAdapter
```

---

## P4-T002 ProviderRegistry

实现：

```text
providerId
 ↓
Adapter
```

---

## P4-T003 ProviderHealthService

支持：

```text
AVAILABLE

UNAVAILABLE

DEGRADED
```

---

# 29. Epic P4-E2 — Workflow

## P4-T004 WorkflowTemplate

实现：

```text
WorkflowTemplate
WorkflowVersion
```

---

## P4-T005 Workflow Schema

逻辑参数：

```text
prompt

referenceImage

duration

resolution
```

---

## P4-T006 Workflow Input Mapping

将逻辑参数：

```text
duration
```

映射：

```text
node 92
```

只允许 Adapter 知道 Node。

---

## P4-T007 Workflow Resolver

优先：

```text
Request Override
 ↓
Project Default
 ↓
System Default
```

---

# 30. Epic P4-E3 — ComfyUI

## P4-T008 ComfyUI Client

实现：

```text
health

submit

status

cancel

history

output
```

---

## P4-T009 ComfyUIWorkflowAdapter

实现：

```text
Logical Input
 ↓
Workflow JSON
 ↓
Node Mapping
```

---

## P4-T010 Shot Image Generation

真实执行：

```text
Shot
→ ComfyUI
→ Asset
```

---

## P4-T011 Shot Video Generation

真实：

```text
Image
→ Video
→ Asset
```

---

## P4-T012 Temporary Output Pipeline

执行：

```text
Temp
 ↓
Validate
 ↓
Commit Storage
 ↓
Asset Register
```

---

# 31. Phase 4 Gate

用户可以：

```text
Generate Shot Image

Generate Shot Video

Regenerate

Switch Version
```

并且业务模块代码中：

```text
不存在 ComfyUI Node ID
```

除 Adapter 外。

---

# Phase 5 — Persistent Job Queue

# 32. Phase 5 目标

从：

```text
一个一个点 Generate
```

升级：

```text
Generate Scene
```

---

# 33. Epic P5-E1 — Job

## P5-T001 Job Entity

实现：

```text
Job
JobStatus
```

---

## P5-T002 JobTask

实现：

```text
Task

Status

Priority

Progress
```

---

## P5-T003 TaskDependency

支持：

```text
Image
 ↓
Video
```

---

## P5-T004 DAG Validator

检查：

```text
Cycle
```

---

# 34. Epic P5-E2 — Queue

## P5-T005 Persistent Queue

DB 是 Source of Truth。

---

## P5-T006 Scheduler

支持：

```text
READY Task

Priority

nextRunAt
```

---

## P5-T007 Worker Pool

分离：

```text
Agent

ComfyUI

Remote

Media
```

---

## P5-T008 ComfyUI Resource Slot

默认：

```text
Concurrency = 1
```

---

# 35. Epic P5-E3 — Failure Handling

## P5-T009 Retry Policy

错误分：

```text
Retryable

NonRetryable

UserActionRequired
```

---

## P5-T010 Backoff

实现：

```text
2s
5s
15s
```

等策略。

Worker 禁止 sleep 等重试。

---

## P5-T011 Partial Failure

Scene 一个 Shot Failed：

其他继续。

---

## P5-T012 Dependency Skip

Image Failed：

Video：

```text
SKIPPED
DEPENDENCY_FAILED
```

---

# 36. Epic P5-E4 — Control & Recovery

## P5-T013 Pause

只停止调度新任务。

---

## P5-T014 Resume

继续 READY Task。

---

## P5-T015 Cancel

取消未运行任务，尝试取消运行 Provider。

---

## P5-T016 Interrupted State

加入：

```text
INTERRUPTED
```

---

## P5-T017 Startup Recovery

重启后检测：

```text
RUNNING
```

异常任务。

---

## P5-T018 Provider Reattach

ComfyUI / Remote Provider：

保存 Execution ID，

尝试恢复。

---

# 37. Epic P5-E5 — Events

## P5-T019 SSE

建立：

```text
Project Event Stream
```

---

## P5-T020 Job Progress Events

支持：

```text
JOB_UPDATED

TASK_UPDATED

GENERATION...
```

---

# 38. Phase 5 Gate

准备：

```text
Scene
20 Shots
```

点击：

```text
Generate Scene
```

系统必须：

```text
自动排队

Image → Video

失败不阻塞其他

可 Retry

可 Pause

可 Resume

可重启恢复
```

---

# Phase 6 — Studio Frontend Core

# 39. Phase 6 目标

将之前所有后端能力真正变成：

```text
可长期使用的桌面 Studio
```

---

# 40. Epic P6-E1 — Shell

## P6-T001 StudioShell

布局：

```text
Top
Left
Center
Right
Bottom
```

---

## P6-T002 Resizable Panel

支持：

```text
resize
collapse
```

---

## P6-T003 Workspace Persistence

保存：

```text
Panel
Tabs
Selection
```

---

## P6-T004 Editor Tabs

支持：

```text
Scene
Shot
Character
Asset
Timeline
```

---

## P6-T005 Selection Store

统一 Inspector Selection。

---

# 41. Epic P6-E2 — Project Navigation

## P6-T006 Project Explorer

实现：

```text
Episode
Scene
Shot
Library
```

---

## P6-T007 Storyboard

实现 Shot Grid。

---

## P6-T008 Virtualized Shot Grid

避免大 Scene 性能问题。

---

## P6-T009 Shot Editor

实现：

```text
Preview

Inspector

Versions
```

---

# 42. Epic P6-E3 — Version UI

## P6-T010 VersionStrip

显示：

```text
ACTIVE
LATEST
STALE
```

---

## P6-T011 Activate Version

显式切换。

---

## P6-T012 Version Compare

Alpha 图片 A/B。

---

## P6-T013 Character Library

实现 Character / Version。

---

## P6-T014 Set MASTER

含：

```text
Impact Preview
```

---

## P6-T015 Location Library

同类实现。

---

# 43. Epic P6-E4 — Asset

## P6-T016 Asset Browser

支持：

```text
Filter
Pagination
Virtual Grid
```

---

## P6-T017 Asset Inspector

---

## P6-T018 Provenance Drawer

---

# 44. Epic P6-E5 — Production UI

## P6-T019 SSE Client

全局唯一。

---

## P6-T020 Event Dispatcher

分 Reducer。

---

## P6-T021 Generation Panel

---

## P6-T022 Job Detail

---

## P6-T023 Retry / Pause / Resume / Cancel

---

## P6-T024 Recovery UI

展示 interrupted jobs。

---

# 45. Phase 6 Gate

用户无需打开 Debug 工具即可完成：

```text
Browse
 ↓
Edit Shot
 ↓
Generate
 ↓
Watch Queue
 ↓
Preview Version
 ↓
Activate
```

并且后台任务不会阻塞 Studio 操作。

---

# Phase 7 — AI Director Agent

# 46. Phase 7 目标

建立：

```text
Planning Plane
```

而不是聊天机器人。

---

# 47. Epic P7-E1 — Agent Foundation

## P7-T001 AgentRun

---

## P7-T002 AgentGateway

Core Backend 不依赖 LangGraph 细节。

---

## P7-T003 Agent Runtime

建立 Python Agent Runtime。

---

## P7-T004 LangGraph Checkpointer

开发不可只用 Memory。

---

# 48. Epic P7-E2 — Context

## P7-T005 ContextResolver

根据：

```text
Story Planning

Shot Planning

Prompt
```

构建不同 Context。

---

## P7-T006 Token Budget

防止整个 Project 全塞 Context。

---

## P7-T007 Context Schemas

结构化输入。

---

# 49. Epic P7-E3 — Agents

## P7-T008 Script Agent

输出：

```text
ScriptPlan
ScenePlan
```

---

## P7-T009 Visual Agent

输出：

```text
ShotPlan
ShotVisualSpec
```

---

## P7-T010 Director Graph

协调：

```text
Script
 ↓
Visual
 ↓
Review
```

---

## P7-T011 Prompt Agent

输出：

```text
CanonicalPromptSpec
```

---

# 50. Epic P7-E4 — Proposal

## P7-T012 AgentProposal

所有修改先 Proposal。

---

## P7-T013 Structured Output Validation

Schema。

---

## P7-T014 Domain Validation

检查：

```text
角色

地点

ID

Revision
```

---

## P7-T015 Proposal Apply

通过 Application Service。

---

## P7-T016 BaseRevision

避免 Agent 覆盖用户编辑。

---

# 51. Epic P7-E5 — Human Review

## P7-T017 Human Interrupt

Agent：

```text
WAITING_HUMAN
```

---

## P7-T018 Resume

批准后继续。

---

## P7-T019 Agent Panel

前端展示 Graph Progress。

---

## P7-T020 Proposal Review

---

## P7-T021 Proposal Conflict UI

---

# 52. Phase 7 Gate

必须可以：

```text
Novel
 ↓
Plan Scene
 ↓
Plan Shots
 ↓
Proposal
 ↓
Review
 ↓
Apply
 ↓
正式 Shot
```

且：

```text
Agent 不直接写 DB
```

---

# Phase 8 — Continuity Engine

# 53. Phase 8 目标

让镜头从：

```text
独立 AI Clip
```

变成：

```text
连续剧情状态
```

---

# 54. Epic P8-E1 — State

## P8-T001 Scene Base State

---

## P8-T002 Shot Delta

---

## P8-T003 Shot Start State

---

## P8-T004 Shot End State

---

## P8-T005 CharacterState

包括：

```text
Version
Costume
Position
Action
Emotion
Physical
```

---

## P8-T006 PropState

---

## P8-T007 EnvironmentState

---

# 55. Epic P8-E2 — Rules

## P8-T008 Costume Rule

---

## P8-T009 Character Version Rule

---

## P8-T010 Location Rule

---

## P8-T011 Prop Holder Rule

---

## P8-T012 Prop Disappearance

---

## P8-T013 Time Rule

---

## P8-T014 Orientation / Position Warning

---

# 56. Epic P8-E3 — Recompute

## P8-T015 Dirty Range

修改 Shot N：

```text
N → end
```

重新计算。

---

## P8-T016 Relevant State Hash

---

## P8-T017 STALE Integration

连续性事实改变：

```text
Asset → STALE
```

但不自动 Regenerate。

---

# 57. Epic P8-E4 — Agent

## P8-T018 Continuity Agent

只负责语义检测。

---

## P8-T019 Continuity Fix Proposal

不能直接修改项目。

---

## P8-T020 Continuity UI

Scene Warning + Shot Inspector。

---

# 58. Epic P8-E5 — Video Bridge

## P8-T021 First Frame Extraction

---

## P8-T022 Last Frame Extraction

---

## P8-T023 Frame Asset

---

## P8-T024 ShotTransition

---

## P8-T025 LAST_TO_FIRST

---

## P8-T026 REFERENCE_ONLY

---

# 59. Phase 8 Gate

必须能处理：

```text
角色换装错误

道具消失

位置变化

状态继承

前序镜头修改

下游 Recompute

Asset STALE

Last Frame → Next Shot
```

---

# Phase 9 — Timeline & Episode Render

# 60. Phase 9 目标

完成：

```text
Production Output
```

---

# 61. Epic P9-E1 — Timeline Domain

## P9-T001 Timeline

---

## P9-T002 TimelineTrack

支持：

```text
VIDEO

VOICE

MUSIC

SUBTITLE
```

---

## P9-T003 TimelineClip

---

## P9-T004 Clip Version Binding

直接绑定具体：

```text
Asset
```

---

# 62. Epic P9-E2 — Frontend

## P9-T005 Timeline Workspace

---

## P9-T006 Video Track

---

## P9-T007 Voice Track

---

## P9-T008 Music Track

---

## P9-T009 Subtitle Track

---

## P9-T010 Clip Drag

---

## P9-T011 Clip Trim

---

## P9-T012 Replace Asset Version

---

# 63. Epic P9-E3 — Preview / Render

## P9-T013 Timeline Preview

---

## P9-T014 Render Planner

---

## P9-T015 Render Job

Timeline Render 同样进入：

```text
Job Queue
```

---

## P9-T016 FINAL_VIDEO Asset

导出后注册：

```text
FINAL_VIDEO
```

---

# 64. Phase 9 Gate

必须能够：

```text
Shot Videos
 ↓
Timeline
 ↓
Voice
 ↓
Subtitle
 ↓
Preview
 ↓
Render
 ↓
Final Video
```

Timeline 不会因为：

```text
Shot Active Version 改变
```

自动偷偷换素材。

---

# Phase 10 — Alpha Hardening

# 65. Phase 10 目标

从：

```text
能运行
```

变：

```text
能持续使用
```

这是 Alpha 和 Demo 的真正区别。

---

# 66. Epic P10-E1 — Recovery

## P10-T001 Project Recovery Mode

---

## P10-T002 Asset Integrity Check

---

## P10-T003 Missing File Repair

---

## P10-T004 Orphan File Recovery

---

## P10-T005 Project Verify

---

# 67. Epic P10-E2 — Backup

## P10-T006 Manual Backup

---

## P10-T007 Migration Backup

---

## P10-T008 Project Restore

---

# 68. Epic P10-E3 — Cleanup

## P10-T009 Cleanup Analyzer

分类：

```text
Protected

Review

Safe
```

---

## P10-T010 Old Version Cleanup

禁止删除：

```text
Active

MASTER

Timeline

Dependency
```

---

# 69. Epic P10-E4 — Audit

## P10-T011 AuditLog

记录：

```text
USER

AGENT

SYSTEM
```

---

## P10-T012 Agent ChangeSet

---

## P10-T013 Basic Undo

优先：

```text
Agent Proposal
Shot Property
Timeline Edit
```

---

# 70. Epic P10-E5 — Performance

## P10-T014 Large Project Test

数据：

```text
1 Project

10 Episodes

80 Scenes

800 Shots

3000 Assets
```

---

## P10-T015 Frontend Virtualization Audit

---

## P10-T016 Database Index Audit

---

## P10-T017 Media Cache Audit

---

# 71. Epic P10-E6 — Stability

## P10-T018 Force Crash Tests

生成过程中 Kill Studio。

---

## P10-T019 Disk Full Test

---

## P10-T020 Provider Disconnect Test

---

## P10-T021 Corrupted Asset Test

---

## P10-T022 Migration Failure Test

---

# 72. Epic P10-E7 — UX Polish

## P10-T023 Empty States

---

## P10-T024 Error UX

---

## P10-T025 Keyboard Navigation

---

## P10-T026 Command Palette

---

## P10-T027 Dark / Light Mode

---

# 73. Phase 10 Gate — Alpha Release Candidate

必须完成一次真实项目测试：

```text
真实小说章节

1 Episode

5～10 Scenes

30～80 Shots

3～8 Characters

3～10 Locations
```

完整走：

```text
Import
 ↓
Director
 ↓
Scene
 ↓
Shot
 ↓
Character
 ↓
Location
 ↓
Storyboard
 ↓
Image
 ↓
Video
 ↓
Voice
 ↓
Continuity
 ↓
Timeline
 ↓
Render
```

---

# 74. Alpha RC 验收指标

建议：

```text
Generation 任务经 Retry 后成功率 > 95%

Job Resume 正确率 > 99%

Project Reopen 数据完整率 = 100%

历史 Generation 可追溯率 = 100%

Active / Latest 不误切换

MASTER Change 不自动生成

Timeline Asset 不自动替换

Agent Proposal 不直接覆盖用户状态
```

---

# 75. 第一条真实 Alpha 验收场景

用户：

```text
创建 Project
```

导入：

```text
小说 Chapter 01
```

Director：

```text
生成 Episode
```

得到：

```text
8 Scenes
52 Shots
```

用户修改：

```text
Shot 17
```

设置：

```text
Character MASTER
```

生成：

```text
Character
Location
Shot Images
Shot Videos
```

---

# 76. 故障模拟

其中：

```text
Shot 12 Video Failed

Shot 18 Image Timeout

ComfyUI temporarily disconnected
```

预期：

```text
其他任务继续

Retry

Resume
```

---

# 77. 版本验证

Shot 17：

```text
Video v1

Video v2

Video v3
```

用户：

```text
v2 ACTIVE
```

Timeline：

```text
使用 v1
```

必须合法。

---

# 78. MASTER 验证

Character：

```text
MASTER v3 → v4
```

预期：

```text
Affected shots STALE
```

禁止：

```text
自动 Regenerate
```

---

# 79. Continuity 验证

Shot 22：

```text
篮球在沈亦右手
```

Shot 23：

```text
篮球消失
```

Continuity：

```text
ERROR
```

修复后：

```text
Downstream State Recompute
```

---

# 80. Recovery 验证

任务：

```text
31 / 80
```

强制关闭 Studio。

重新打开：

```text
31 已完成

剩余可 Resume
```

---

# 81. 最终 Render

全部完成后：

```text
Timeline
 ↓
Render
 ↓
FINAL_VIDEO Asset
```

关闭 Studio。

第二天重新打开：

```text
所有 Project State
Asset
Version
Generation
Job History
Timeline
```

完整存在。

这才算：

> **Alpha 成立。**

---

# 82. Codex 执行顺序规则

Codex 不应该：

```text
同时开 20 个大 Task
```

建议：

```text
1 个主 Task

必要时最多 1～2 个独立子 Task
```

完成后：

```text
Test
 ↓
Commit
 ↓
Next Task
```

---

# 83. Task 依赖

每个 Task Header 增加：

```text
Depends On
```

例如：

```text
P5-T006 Scheduler

Depends On:
P5-T001
P5-T002
P5-T005
```

依赖未 DONE：

Task：

```text
BLOCKED
```

---

# 84. Codex 不可自行跳 Phase

如果 Codex 判断：

```text
Phase 8 功能现在很好做
```

但 Phase 5 没完成，

不得擅自开始。

可以：

```text
记录建议
```

但继续当前 Roadmap。

---

# 85. Architecture Decision Record

如果实现时发现设计必须修改：

不要静默改。

创建：

```text
docs/adr/
```

例如：

```text
ADR-001-use-project-local-sqlite.md

ADR-002-generation-retry-new-record.md
```

内容：

```text
Context

Decision

Alternatives

Consequences
```

---

# 86. Task Completion Report

每一个较大的 Task 完成后 Codex 应输出：

```text
Task

Implemented

Files Changed

Database Changes

API Changes

Tests Added

Known Limitations

Follow-ups
```

---

# 87. Codex 禁止事项

整个 Alpha 开发期间长期禁止：

```text
直接覆盖旧 Generation

重新生成覆盖 Asset

最新版本自动 Active

MASTER 自动升级历史 Shot

MASTER Change 自动重生成

Agent 直接写 DB

Job Queue 只在内存

ComfyUI Node ID 进入业务层

Timeline 自动跟随 Shot Active

Prompt 直接等于 Shot

文件路径等于 Asset

硬删除代替 Archive
```

---

# 88. Alpha 关键架构不变量

Codex 每次修改必须检查：

### 不变量 1

```text
Database
=
Project Source of Truth
```

### 不变量 2

```text
Generation
=
Immutable Execution History
```

### 不变量 3

```text
Asset
!=
File
```

### 不变量 4

```text
Shot
!=
Prompt
```

### 不变量 5

```text
Job
!=
Generation
```

### 不变量 6

```text
Latest
!=
Active
```

### 不变量 7

```text
MASTER
!=
Latest
```

### 不变量 8

```text
Continuity Change
→
STALE
```

不是：

```text
→ Regenerate
```

### 不变量 9

```text
Agent
→ Proposal
→ Application Service
→ Domain
```

### 不变量 10

```text
Workflow
!=
ComfyUI JSON
```

---

# 89. 每个 Phase 的测试要求

每个 Phase 至少：

```text
Unit Test

Integration Test

Happy Path

Failure Path

Persistence / Restart Test
```

涉及生成：

额外：

```text
Provider Failure

Retry

Cancel
```

涉及 DB：

额外：

```text
Migration
Rollback / Recovery
```

---

# 90. Definition of Done

一个 Task 只有同时满足：

```text
Implementation complete

No Type / Compile Errors

Tests pass

Acceptance Criteria pass

No obvious duplicated logic

No architecture rule violation

Documentation updated

Migration included if needed
```

才允许：

```text
DONE
```

---

# 91. Phase Definition of Done

一个 Phase 必须：

```text
所有 P0 / P1 Task DONE

Phase Integration Scenario PASS

关键 Error Case PASS

没有阻塞级 Technical Debt

上游文档与实际实现一致
```

才进入下一 Phase。

---

# 92. 推荐开发节奏

不要按：

```text
Backend 全做完
 ↓
Frontend 全做完
```

这种瀑布方式。

Phase 内推荐纵向闭环。

例如 Phase 3：

```text
Asset Domain
 ↓
Asset API
 ↓
Asset Store
 ↓
Version UI
 ↓
Generation Integration
```

尽早验证真实工作流。

---

# 93. 但是 Agent 暂时不要过早插入

Phase 1～6：

先确保：

```text
人类可以不用 Agent
```

完成核心制作。

这很重要。

AI Director 应：

```text
加速 Studio
```

而不是：

```text
Studio 没 Agent 就不能工作
```

---

# 94. 第一阶段真正开发优先级

如果现在立刻让 Codex 开发：

**不是直接从 P1-T001 开始。**

第一步必须：

# P0-T001 ～ P0-T006

先完成：

```text
MVP Baseline Audit
```

因为当前已经存在 MVP。

否则最容易发生：

```text
重新实现已有功能

架构冲突

数据库重复

API 重复

已有 ComfyUI 接口被废掉
```

---

# 95. 第一条交给 Codex 的总任务

建议给 Codex：

```text
你现在进入 AI 漫剧 Studio Alpha 开发阶段。

先不要实现新功能。

按照
《AI 漫剧 Studio Alpha Codex 分阶段开发任务清单 v0.1》
执行 Phase 0。

完成 P0-T001 ～ P0-T006：

1. Repository Architecture Audit
2. Feature Inventory
3. Domain Model Gap Analysis
4. API Audit
5. Frontend State Audit
6. ComfyUI Integration Audit

要求：

- 只分析，不大规模修改业务代码。
- 基于真实代码，不根据 README 猜测。
- 标明已有、部分实现、缺失、技术债。
- 识别可以复用的能力。
- 对照 Alpha 目标架构分析差距。
- 所有结果输出到 docs/alpha/audit/。
- 最终生成：
  docs/alpha/audit/mvp-baseline-report.md

报告最后必须给出：
- KEEP
- REFACTOR
- MIGRATE
- REMOVE
- BUILD

五类清单。

完成审查前，不进入 Phase 1。
```

---

# 96. Phase 0 之后的 Codex 指令

Baseline 通过以后：

```text
读取：

1. Alpha 架构文档
2. MVP Baseline Report
3. Phase 1 Tasks

根据实际 MVP 现状，
将 Phase 1 每个 Task 标记：

TODO
PARTIAL
DONE

但不得仅因为“存在类似代码”就判断 DONE。

必须根据 Acceptance Criteria 验证。

之后按依赖顺序执行第一个 READY Task。
```

---

# 97. 推荐 Roadmap 文件结构

建议代码仓库加入：

```text
docs/
└── alpha/
    │
    ├── architecture/
    │
    ├── audit/
    │
    ├── roadmap/
    │   ├── alpha-roadmap.md
    │   ├── phase-0.md
    │   ├── phase-1.md
    │   ├── phase-2.md
    │   ├── ...
    │   └── phase-10.md
    │
    ├── adr/
    │
    ├── api/
    │
    ├── database/
    │
    └── testing/
```

---

# 98. Task 文件格式

例如：

```text
docs/alpha/roadmap/tasks/P3-T011-generation-core.md
```

内容：

```text
# P3-T011 Generation Core

Status:
READY

Priority:
P0

Depends On:
P3-T001

Goal:

Scope:

Out of Scope:

Architecture Constraints:

API:

Database:

Implementation Steps:

Acceptance Criteria:

Tests:

Files:

Completion Report:
```

---

# 99. 为什么建议每个重要 Task 单文件

后续 Codex 可以直接：

```text
读取当前 Task 文件
```

而不是每次重新消化：

```text
200 页架构文档
```

降低上下文消耗和跑偏风险。

---

# 100. Task Index

再建立：

```text
task-index.md
```

例如：

| Task    | Status  | Priority | Depends On |
| ------- | ------- | -------: | ---------- |
| P0-T001 | TODO    |       P0 | -          |
| P0-T002 | TODO    |       P0 | P0-T001    |
| P1-T001 | BLOCKED |       P0 | Phase 0    |
| P1-T002 | BLOCKED |       P0 | P1-T001    |
| P2-T004 | BLOCKED |       P0 | P2-T003    |

Codex 每次只更新这里的状态。

---

# 101. 推荐加入 Development Log

```text
docs/alpha/development-log.md
```

记录：

```text
2026-08-xx

Completed:
P1-T003

Decisions:
...

Problems:
...

Next:
P1-T004
```

这样即使更换 Codex Session：

也可以快速恢复上下文。

---

# 102. Alpha Roadmap 最终结构

整个开发项目可以压缩成：

```text
Phase 0
Understand Existing System

Phase 1
Make Project Reliable

Phase 2
Make Story Editable

Phase 3
Make Generation Traceable

Phase 4
Make Providers Replaceable

Phase 5
Make Production Reliable

Phase 6
Make Studio Usable

Phase 7
Make AI Intelligent

Phase 8
Make Shots Continuous

Phase 9
Make Episodes Deliverable

Phase 10
Make Alpha Durable
```

---

# 103. 最终建议执行方式

从现在开始不建议再继续生成第十一、第十二份“大型架构设计”。

现在应该正式执行：

```text
Phase 0
```

并让 Codex 先审查现有 MVP。

得到：

```text
MVP Baseline Report
```

之后再根据真实代码：

```text
重新校准 Phase 1～10
```

因为从这里开始，**代码本身应当重新成为主要事实来源**。

---

# 104. 下一步

下一步最适合继续生成的不是新的系统设计，而是直接给 Codex 使用的：

# 《AI 漫剧 Studio Phase 0 — MVP Baseline Audit Codex 执行提示词 v0.1》

它会把：

```text
P0-T001 ～ P0-T006
```

进一步变成一份可以直接整段复制给 Codex 的执行 Prompt，并规定：

```text
扫描顺序

禁止修改范围

报告模板

架构对照项

审查 Checklist

最终输出文件

Phase 0 Gate
```

完成后，你就可以真正开始让 Codex 对当前 MVP 项目进行 Alpha 前置审查，而不是继续停留在规划阶段。
