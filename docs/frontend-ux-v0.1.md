# AI 漫剧 Studio 前端 UX / 信息架构设计 v0.1

> 文档类型：**Frontend UX / Information Architecture Specification**
> 状态：**draft**（主创定稿，前端实现与 Director UI 的事实源）
> 目标阶段：MVP → V1
> 产品形态：桌面级 AI 漫剧制作 Studio
> 核心交互模型：Project + Workspace + AI Director + Production Timeline
> 前端技术建议：React + TypeScript + React Flow + Zustand + TanStack Query
> 关联文档：[PRD v0.1](./prd-v0.1.md) · [系统架构设计 v0.1](./architecture-v0.1.md) · [数据库与 ER 模型设计 v0.1](./database-v0.1.md) · [后端 API 与 Service 架构 v0.1](./backend-architecture-v0.1.md) · [AI Director Agent 详细设计 v0.1](./agent-director-v0.1.md)

---

# 1. 前端设计目标

AI 漫剧 Studio 的前端不能设计成：

```text
一个聊天框
+
几个生成按钮
```

而应该设计成：

> **一个围绕漫剧项目持续生产的 AI 原生创作工作台。**

用户真正需要管理的是：

```text
项目
剧集
场景
镜头
角色
素材
版本
生成任务
AI 操作
时间线
```

因此前端的核心必须围绕：

> **Project State 可视化。**

AI Director 是整个 Studio 的智能操作入口，但不是整个产品唯一入口。

---

# 2. UX 核心原则

## 2.1 Project First

用户打开软件首先进入：

```text
Project
```

而不是：

```text
New Chat
```

---

## 2.2 Visual First

漫剧属于视觉创作。

用户应该优先看到：

```text
Storyboard
Image
Video
Timeline
Asset
```

而不是大量文字。

---

## 2.3 Selection Driven AI

AI Director 必须理解：

> 用户当前选中了什么。

例如用户点击 Shot 05，然后说：

> "这个改成近景。"

系统必须知道：

```text
这个
=
Shot 05
```

---

## 2.4 Progressive Disclosure

普通用户看到：

```text
镜头
角色
场景
生成
```

高级用户才展开：

```text
模型
Workflow
Seed
LoRA
ControlNet
ComfyUI 参数
```

不要把 ComfyUI 的复杂度直接暴露给所有用户。

---

# 3. 整体信息架构

顶层建议分为五个区域：

```text
┌─────────────────────────────────────────────────────────────┐
│                     Top Command Bar                         │
├───────────────┬───────────────────────────┬─────────────────┤
│               │                           │                 │
│ Project       │                           │ AI Director     │
│ Explorer      │       Main Workspace      │                 │
│               │                           │                 │
│               │                           │                 │
├───────────────┴───────────────────────────┴─────────────────┤
│                  Timeline / Task Dock                       │
└─────────────────────────────────────────────────────────────┘
```

五个区域：

```text
Top Command Bar

Project Explorer

Main Workspace

AI Director

Bottom Dock
```

---

# 4. Top Command Bar

顶部负责：

```text
项目级导航
当前工作区
全局动作
生成状态
模型状态
```

建议布局：

```text
[项目名]

[Script]
[Storyboard]
[Canvas]
[Assets]
[Timeline]

              [Generate] [Undo] [Redo]

              [ComfyUI ●]
              [Agent ●]
```

---

# 5. Project Explorer

左侧是整个项目的结构导航。

建议：

```text
PROJECT

最后一种打法

▼ Episode 01

   ▼ Scene 01
      Shot 001
      Shot 002
      Shot 003

   ▼ Scene 02
      Shot 004
      Shot 005

▼ Characters

   沈亦
   顾言

▼ Locations

   体育馆
   教室

▼ Assets

▼ Workflows
```

---

# 6. Project Explorer 的作用

不只是文件树。

它同时承担：

```text
导航
结构理解
选择 Context
拖拽排序
状态提示
```

例如 Shot：

```text
● Shot 05
```

状态可以用图标表达：

```text
○ Draft

◐ Generating

● Ready

! Failed

◆ Approved
```

---

# 7. Main Workspace

中央区域是主要创作空间。

根据工作模式切换：

```text
Script

Storyboard

Director Canvas

Asset Library

Timeline

Preview
```

不要所有功能同时显示。

---

# 8. Script Workspace

目标：

> 从小说 / 剧本进入结构化制作。

建议布局：

```text
┌──────────────────┬────────────────────┐
│ Source Text      │ Structured Script  │
│                  │                    │
│ 小说原文         │ Scene 01           │
│                  │ Scene 02           │
│                  │ Scene 03           │
└──────────────────┴────────────────────┘
```

用户可以：

```text
导入小说

选择章节

AI 分析

拆 Scene

编辑剧本
```

---

# 9. Script → Scene UX

AI 分析后不要立即直接写入项目。

建议先出现：

```text
AI 分析结果
```

例如：

```text
检测到：

角色：4

场景：6

主要冲突：2

预计镜头：32
```

用户：

```text
[创建 Scenes]
```

然后正式进入 Project State。

---

# 10. Storyboard Workspace

这是整个产品最重要的 Workspace。

建议采用 Card Grid。

例如：

```text
┌────────────┐ ┌────────────┐ ┌────────────┐

│ Shot 01    │ │ Shot 02    │ │ Shot 03    │

│            │ │            │ │            │

│   Image    │ │   Image    │ │   Image    │

│            │ │            │ │            │

│ Medium     │ │ Close Up   │ │ Wide       │

│ 3.0s       │ │ 2.5s       │ │ 4.0s       │

└────────────┘ └────────────┘ └────────────┘
```

---

# 11. Storyboard Card

每张 Shot Card 显示：

```text
Shot Number

Preview

Shot Type

Duration

Character

Status
```

Hover 后显示：

```text
Generate

Regenerate

Edit

Versions

More
```

---

# 12. Shot Inspector

点击 Shot 后：

中央保持 Storyboard。

右边在 AI Director 前可以增加一个 Inspector Tab。

建议右侧：

```text
[Inspector] [AI Director]
```

Inspector 包含：

```text
Shot 05

Camera
Close-up

Angle
Low Angle

Movement
Static

Duration
3.2s

Characters
沈亦

Action
急停

Emotion
紧张
```

---

# 13. Inspector 高级设置

默认折叠：

```text
Advanced Generation
```

展开：

```text
Image Provider

Workflow

Seed

Resolution

Reference

LoRA

Custom Parameters
```

这样兼顾：

```text
普通用户
+
ComfyUI 高级用户
```

---

# 14. AI Director Panel

右侧 AI Director 不应该只是 Chat。

应该被设计为：

> **AI Command Center**

内部至少包含四种内容：

```text
Conversation

Plan

Actions

Approval
```

---

# 15. AI Director 基础状态

建议 UI 支持：

```text
Idle

Understanding

Planning

Waiting Approval

Executing

Generating

Reviewing

Completed

Failed
```

---

# 16. AI Director Idle

例如：

```text
AI Director

当前选择：
Scene 03 / Shot 05

你可以说：

"改成近景"

"重新生成"

"检查和上一镜是否连贯"
```

Selection Context 明确展示。

---

# 17. Planning UI

用户：

> "把第三场节奏改紧一点。"

AI 不要只显示：

```text
正在思考……
```

而是：

```text
计划

1. 分析 Scene 03

2. 调整 Shot 12–16

3. 合并两个重复镜头

4. 检查连续性

预计影响：5 个镜头
```

---

# 18. Execution UI

执行过程中：

```text
修改 Shot 12      ✓

修改 Shot 13      ✓

合并 Shot 14/15   ●

更新 Prompt       ○

连续性检查         ○
```

这让用户理解：

> AI 正在操作 Studio，而不是聊天。

---

# 19. Approval Card

高风险操作必须出现 Card。

例如：

```text
重新生成整个 Scene？

将生成：

8 张图片
6 个视频

预计影响：
Shot 12–19

旧版本会保留。

[确认生成]

[只生成图片]

[取消]
```

---

# 20. ChangeSet UI

AI 批量修改后展示：

```text
本次修改

Modified
Shot 12
Shot 13
Shot 16

Merged
Shot 14 + Shot 15

Created
Shot 17
```

动作：

```text
[查看修改]

[全部撤销]
```

---

# 21. Diff UI

点击查看修改：

```text
Shot 12

Camera

Medium
→
Close-up

Duration

4.0s
→
2.8s

Emotion

Calm
→
Tense
```

这是 AI Studio 非常重要的信任机制。

---

# 22. Director Canvas

Canvas 不做成 ComfyUI。

节点应该使用：

> 影视生产语义。

例如：

```text
Novel
   ↓
Script Analysis
   ↓
Scene Planning
   ↓
Storyboard
   ↓
Image
   ↓
Review
   ↓
Video
   ↓
Voice
   ↓
Composition
```

---

# 23. Canvas Node 类型

第一版建议：

```text
Source

AI Process

Scene

Shot Group

Generation

Review

Output
```

---

# 24. Canvas 的价值

Canvas解决：

```text
流程结构
依赖关系
批量生产
失败定位
生产可视化
```

例如用户可以看到：

```text
Storyboard ✓

Image
  12/15

Video
  7/15

Review
  5/15
```

---

# 25. Canvas 与 ComfyUI 的关系

Studio Canvas：

```text
Image Generation
```

底层：

```text
ComfyUI Workflow XYZ
```

用户右键：

```text
Advanced
→ Open Workflow Settings
```

才看到底层 Workflow。

---

# 26. Asset Library

资产库建议分：

```text
Characters

Locations

Props

Images

Videos

References

Audio
```

---

# 27. Character Asset 页面

角色卡：

```text
沈亦

[Portrait]

Primary Character

References: 6

Costumes: 3

Used in: 42 Shots
```

进入后：

```text
Basic Info

Appearance

Costumes

References

Generated Assets

Used Shots
```

---

# 28. Character Reference Board

类似：

```text
Front

Side

Full Body

Expression

Costume A

Costume B
```

AI生成 Shot 时自动获取相关 Reference。

---

# 29. Location Asset

例如：

```text
体育馆

References

Day

Night

Crowded

Empty
```

Location 应成为可复用实体。

---

# 30. Generation Queue

Bottom Dock 第一块：

```text
Generation Queue
```

例如：

```text
Shot 05 Image

ComfyUI

68%

█████████░░░


Shot 08 Image

Queued


Shot 11 Video

Failed

[Retry]
```

---

# 31. Queue 筛选

支持：

```text
All

Running

Queued

Failed

Completed
```

以及：

```text
Image

Video

Audio
```

---

# 32. Timeline

Storyboard管理：

> 镜头。

Timeline管理：

> 时间。

建议：

```text
Video Track

[SH01][SH02][SH03][SH04]


Voice Track

──── Audio ─────


Music Track

──────── BGM ─────────


Subtitle

[TXT][TXT][TXT]
```

---

# 33. Timeline 第一版

MVP 不需要 Premiere 级剪辑。

只做：

```text
镜头顺序

Duration

Preview

简单 Voice

简单 Subtitle
```

够用。

---

# 34. Bottom Dock

底部 Dock 可以切换：

```text
Timeline

Generation Queue

Agent Tasks

Logs
```

默认：

```text
Timeline
```

生成时可以自动显示 Queue。

---

# 35. Preview Workspace

用于：

```text
单图预览

视频预览

Scene Preview

版本比较
```

例如：

```text
Shot 05

Version 3

[ Main Preview ]

< V2      V3      V4 >
```

---

# 36. Version UI

每个 Shot 都有：

```text
Versions
```

例如：

```text
V1

V2

V3 ● Active

V4
```

操作：

```text
Compare

Set Active

Restore

Delete
```

---

# 37. Compare View

图片：

```text
V2 | V3
```

支持：

```text
Side by Side

Slider Compare
```

文本字段：

```text
Prompt Diff

Shot Parameter Diff
```

---

# 38. Continuity UX

这应该成为产品特色功能。

在 Storyboard 中：

```text
Shot 08
      │
      ⚠
      │
Shot 09
```

点击警告：

```text
Continuity Issue

角色：
沈亦

Shot 08:
篮球在右手

Shot 09:
篮球变成左手

Suggestion:
保持右手持球。
```

---

# 39. Continuity Score

Scene 层可以展示：

```text
Continuity

92%
```

但不要成为单纯炫技分数。

必须能展开具体 Issue。

---

# 40. Shot Relation

Storyboards 可选择显示：

```text
Previous / Next
```

例如：

```text
Shot 08 → Shot 09
```

点击连线：

```text
Action Continuation

Camera Direction

Character State
```

---

# 41. Context Menu

Shot 右键：

```text
Generate Image

Generate Video

Regenerate

Duplicate

Split

Delete

Check Continuity

Versions
```

AI Director 不应该成为所有功能唯一入口。

---

# 42. Command Palette

强烈建议增加：

```text
Ctrl / Cmd + K
```

Command Palette：

```text
Generate Selected Shot

Open Character

Check Continuity

Ask AI Director

Create Scene

Switch Workflow
```

这对专业用户非常有价值。

---

# 43. AI Command Palette

也可以输入：

```text
> 第三场改紧凑
```

然后自动进入 Director。

形成：

```text
GUI
+
Natural Language
```

双操作模式。

---

# 44. Selection Model

前端需要统一 Selection Store。

例如：

```typescript
interface StudioSelection {

  projectId?: string

  episodeId?: string

  sceneId?: string

  shotIds: string[]

  assetIds: string[]

  workspace: WorkspaceType
}
```

Agent每次请求都带：

```text
StudioSelection
```

---

# 45. Selection 多选

Storyboard 支持：

```text
Shift Click

Ctrl Click

Drag Select
```

例如选择 Shot 5–10。

用户直接：

> "全部重新生成。"

Agent就知道 Scope。

---

# 46. Workspace Context

AI Director应显示：

```text
当前工作区

Storyboard

选择：
6 Shots
```

防止用户误操作。

---

# 47. Global Search

建议：

```text
Ctrl + P
```

支持搜索：

```text
Scene

Shot

Character

Asset

Workflow
```

例如：

```text
沈亦
```

结果：

```text
Character 沈亦

Shot 003

Shot 014

Shot 028
```

---

# 48. Notification System

生成完成不要弹巨大 Modal。

使用：

```text
Toast
+
Notification Center
```

例如：

```text
✓ Shot 05 图片生成完成
```

---

# 49. Error UX

错误必须分：

```text
User Error

Model Error

Generation Error

ComfyUI Error

System Error
```

例如：

```text
Shot 05 生成失败

ComfyUI:
Node 32 输入图片不存在。

[Retry]

[Open Details]
```

不要只说：

```text
Something went wrong.
```

---

# 50. ComfyUI Connection UX

Settings：

```text
ComfyUI

Server

http://127.0.0.1:8188

Status:
● Connected

Version:

...

[Test Connection]
```

---

# 51. Provider Settings

建议：

```text
AI Models

Text

Image

Video

Vision

Audio
```

每一类选择默认 Provider。

例如：

```text
Image

Default:
GPT Image

Secondary:
ComfyUI
```

---

# 52. Per-Shot Provider

Shot Inspector：

```text
Generator

Project Default
```

展开：

```text
GPT Image

ComfyUI

MiniMax
```

---

# 53. Smart Provider Mode

未来：

```text
Auto
```

系统根据：

```text
任务类型

质量

价格

速度

参考图需求
```

自动选择。

MVP先不做智能路由。

---

# 54. Settings 信息架构

建议：

```text
General

Models

ComfyUI

Generation

Storage

Agent

Appearance

Advanced
```

---

# 55. Agent Settings

例如：

```text
AI Director Model

Approval Mode

Auto Save Version

Generation Cost Confirmation

Automatic Continuity Check
```

---

# 56. Approval Mode

可以设置：

```text
Safe

Balanced

Autonomous
```

Safe：

```text
大量修改需要确认。
```

Balanced：

```text
普通修改自动执行。
```

Autonomous：

```text
除删除外大部分自动。
```

---

# 57. Project Dashboard

打开项目时不要直接扔进复杂 Storyboard。

可以提供 Project Overview：

```text
Episode 01

Scenes       8

Shots        42

Images       37 / 42

Videos       18 / 42

Continuity   91%

Failed Tasks 2
```

下面：

```text
[Continue Storyboard]

[Open Timeline]
```

---

# 58. New Project Flow

第一步：

```text
Create Project
```

输入：

```text
Project Name

Aspect Ratio

Style

Default Generator
```

---

# 59. Import Flow

创建项目后：

```text
What do you want to start from?

Import Novel

Import Script

Blank Project

Existing Storyboard
```

MVP重点：

```text
Import Novel
```

---

# 60. Novel Import

步骤：

```text
1 Import

2 Analyze

3 Review

4 Create Project Structure
```

AI分析后用户能调整：

```text
Scenes

Characters

Locations
```

再创建。

---

# 61. First Generation Flow

用户：

```text
Novel
 ↓
Scene
 ↓
Storyboard
 ↓
Shot 01
 ↓
Generate
```

生成按钮需要明确：

```text
Generate Image
```

不要一开始就：

```text
Run
```

---

# 62. Generate Menu

点击 Generate：

```text
Generate Image

Generate Video

Generate Selected Shots

Generate Scene
```

---

# 63. Batch Generation

如果选择 12 Shots：

```text
Generate 12 Images

Provider:
ComfyUI

Estimated Tasks:
12

[Start]
```

未来可加成本。

---

# 64. Undo / Redo

传统 UI 修改：

```text
Ctrl + Z
```

Agent修改：

```text
ChangeSet Undo
```

两者可以统一到历史系统。

---

# 65. History Panel

未来可以：

```text
18:23

AI Director
Modified 5 Shots


18:20

User
Changed Shot 03 duration


18:15

Generation
Shot 05 V3 created
```

---

# 66. Activity Model

所有用户、Agent、Generation操作都形成：

```text
Activity
```

这对 Debug 和版本管理都很有价值。

---

# 67. Keyboard UX

专业 Studio 必须支持快捷键。

例如：

```text
Space
Preview

G
Generate

R
Regenerate

V
Versions

A
AI Director

Delete
Delete Selection

Ctrl + Z
Undo

Ctrl + K
Commands
```

---

# 68. Drag & Drop

支持：

```text
Shot 拖动排序

Asset 拖入 Shot

Character 拖入 Shot

Reference Image 拖入 Character

Video 拖入 Timeline
```

---

# 69. Empty State

Storyboard为空：

```text
还没有分镜

[AI 生成 Storyboard]

[手动添加 Shot]
```

不要显示空白白板。

---

# 70. Loading State

AI拆分 Scene：

```text
正在分析剧情结构…

已识别角色 4

已识别场景 3

正在生成 Scene 4…
```

让用户知道系统在做什么。

---

# 71. Generation State

图片 Card 生成中：

```text
Shot 05

Generating

56%
```

用户仍然可以继续编辑其他 Shot。

不要阻塞整个界面。

---

# 72. AI 与 UI 双向操作

用户通过 UI：

```text
修改 Shot Camera
```

AI马上读取新 State。

用户通过 AI：

```text
修改 Shot
```

UI马上刷新。

因此：

> UI 和 AI 必须操作同一套 Domain Service。

这与后端架构保持一致。

---

# 73. 不要把 AI Director 做成 Modal

AI Director必须：

```text
Persistent
```

用户在 Storyboard / Asset / Timeline 之间切换时：

Agent Session 不丢失。

---

# 74. AI Panel 可收缩

状态：

```text
Expanded

Compact

Hidden
```

Compact：

```text
AI Director ●

Current:
Waiting for approval
```

---

# 75. Workspace Layout 可保存

专业用户可能：

```text
隐藏 Inspector

扩大 Storyboard

打开 Timeline

缩小 AI
```

建议保存：

```text
Workspace Layout
```

---

# 76. MVP 前端页面

第一阶段只需要：

```text
Project Home

Script

Storyboard

Assets

AI Director

Generation Queue

Settings
```

---

# 77. MVP 暂不做

```text
完整 Timeline Editor

完整 Canvas Editor

专业 Video Editing

多人协作

Cloud Asset Library

Plugin Marketplace

复杂 Animation Editor
```

---

# 78. MVP 主界面

建议最终：

```text
┌────────────────────────────────────────────────────────────┐
│ 最后一种打法      Storyboard        Generate     ● ComfyUI │
├──────────────┬─────────────────────────────┬───────────────┤
│ Project      │                             │ Inspector     │
│              │ Shot01  Shot02  Shot03      │               │
│ Ep01         │                             │ Shot 03       │
│ Scene01      │ Shot04  Shot05  Shot06      │ Camera        │
│ Scene02      │                             │ Duration      │
│              │                             ├───────────────┤
│ Characters   │                             │ AI Director   │
│ Assets       │                             │               │
│              │                             │ Ask anything  │
├──────────────┴─────────────────────────────┴───────────────┤
│ Generation Queue                                           │
│ Shot05  █████████░ 82%                                    │
└────────────────────────────────────────────────────────────┘
```

---

# 79. 推荐组件结构

React：

```text
AppShell

├── TopBar

├── ProjectExplorer

├── Workspace
│   ├── ScriptWorkspace
│   ├── StoryboardWorkspace
│   ├── AssetWorkspace
│   ├── CanvasWorkspace
│   └── TimelineWorkspace

├── RightPanel
│   ├── Inspector
│   └── AIDirector

└── BottomDock
    ├── Timeline
    ├── GenerationQueue
    └── Logs
```

---

# 80. Zustand Store

建议拆：

```text
projectStore

selectionStore

workspaceStore

agentStore

generationStore

uiStore
```

不要建立：

```text
globalStore
```

然后把全部状态放进去。

---

# 81. Server State

这些：

```text
Project

Scene

Shot

Asset

Generation
```

使用：

```text
TanStack Query
```

管理。

不要长期复制进 Zustand。

---

# 82. Local UI State

Zustand负责：

```text
当前 Workspace

Selection

Panel Size

Panel Visibility

Canvas Camera

Local Preferences
```

---

# 83. Event Layer

WebSocket事件：

```text
shot.updated

asset.created

generation.started

generation.progress

generation.completed

agent.plan.created

agent.approval.required

agent.completed
```

前端 Event Handler：

```text
Event
 ↓
Invalidate Query
 ↓
Update UI
```

---

# 84. Agent State Store

例如：

```typescript
interface AgentUIState {

  runId?: string

  status:
    | "idle"
    | "planning"
    | "waiting_approval"
    | "executing"
    | "reviewing"
    | "completed"
    | "failed"

  plan?: AgentPlan

  currentAction?: AgentAction

  approval?: ApprovalRequest

  changeSet?: ChangeSet
}
```

---

# 85. Generation State Store

只保存实时临时状态：

```text
progress

speed

queue_position
```

最终 Generation 仍来自服务器。

---

# 86. 前端 Domain Components

推荐组件：

```text
ShotCard

SceneSection

CharacterCard

AssetCard

GenerationCard

AgentPlanCard

ApprovalCard

ChangeSetCard

ContinuityIssueCard

VersionCard
```

这些组件直接对应领域对象。

---

# 87. 不要设计成页面堆积

传统软件可能：

```text
Shots Page

Characters Page

Assets Page
```

Studio 更适合：

```text
Workspace
```

用户始终处于一个 Project 中。

---

# 88. 用户核心路径

整个产品最重要的路径：

```text
New Project

↓

Import Novel

↓

AI Analyze

↓

Review Scenes

↓

Generate Storyboard

↓

Review Shots

↓

Generate Images

↓

Review / Version

↓

Generate Video

↓

Timeline

↓

Export
```

这个路径必须比所有高级功能更优先。

---

# 89. AI 辅助路径

每一步用户都可以调用 Director：

```text
Script

"这一场冲突再强一点"

Storyboard

"拆成六镜"

Shot

"改近景"

Generation

"重新生成这个"

Continuity

"为什么接不上？"

Timeline

"这里节奏太慢"
```

AI不是独立流程。

它贯穿整个工作区。

---

# 90. AI 原生 UX 最终原则

传统软件：

```text
用户找功能
↓
点击按钮
↓
修改参数
```

AI Studio：

```text
用户可以直接操作 UI

或者

表达目标
↓
AI 找功能
↓
AI 执行
```

两种路径必须并存。

---

# 91. 最终信息架构

```text
AI Manga Drama Studio

PROJECT
│
├── Episodes
│   └── Scenes
│       └── Shots
│
├── Characters
├── Locations
├── Props
├── Assets
├── Workflows
└── Versions


WORKSPACES
│
├── Script
├── Storyboard
├── Canvas
├── Assets
├── Preview
└── Timeline


AI
│
├── Director
├── Plan
├── Approval
├── ChangeSet
└── Review


PRODUCTION
│
├── Generation Queue
├── Workflow Runs
├── Failures
└── Progress


SYSTEM
│
├── Providers
├── ComfyUI
├── Models
└── Settings
```

---

# 92. 产品 UX 核心竞争力

真正值得重点打磨的不是：

```text
聊天气泡好不好看
```

而是以下六件事情：

### 1. Storyboard-first

让用户以镜头为中心工作。

### 2. Selection-aware AI

AI永远理解当前用户正在编辑什么。

### 3. Visual Project Memory

角色、场景、镜头、版本全部可视化。

### 4. AI Change Transparency

用户知道 AI 改了什么。

### 5. Production Visibility

用户知道生成任务进行到哪里。

### 6. Complexity Hiding

ComfyUI 很复杂，但用户不必感受到复杂。

---

# 93. MVP 前端验收标准

MVP至少必须能够完整实现：

```text
创建 Project

↓

导入小说

↓

显示 Scene

↓

显示 Storyboard

↓

选择 Shot

↓

AI Director 能理解 Selection

↓

修改 Shot

↓

点击 Generate

↓

显示 Generation Progress

↓

生成图片自动进入 Shot

↓

查看历史 Version

↓

重新生成
```

如果这一套体验顺畅：

> 第一版 Studio UX 已经成立。

---

# 94. 前端最终定位

AI 漫剧 Studio 的 UI 不应该让用户感觉：

> "我正在操作很多 AI 工具。"

而应该让用户感觉：

> **"我正在导演一部漫剧。"**

底层的：

```text
LangChain
LangGraph
LLM
ComfyUI
Workflow
Provider
API
```

全部应该逐渐退到后台。

用户面对的是：

```text
剧情

角色

场景

镜头

画面

节奏

版本

成片
```

这才是最终需要形成的产品体验。
