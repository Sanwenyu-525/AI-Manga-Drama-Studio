
> 状态：**DONE（2026-08）** — P9-T001~T016 全部落地（详见 AGENTS.md「P9」条目）。
> Timeline 域（timelines/timeline_tracks/timeline_clips + 版本绑定）、前端时间线工作台（拖拽/裁剪/替换版本/预览）、
> Episode Render（type=render 生成队列 → RenderProvider mock/ffmpeg → FINAL_VIDEO 资产导出）。Phase 9 Gate 已验收。
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
