# AI 漫剧 Studio 系统架构设计文档 v0.1

> 状态：**draft**（主创定稿，指导后续开发）
> 关联文档：[PRD v0.1](./prd-v0.1.md)
> 约定：本文档为架构决策的事实源；业务逻辑不得写在 API Controller 中；UI 不得直接调用 ComfyUI API。

---

## 1. 架构目标

AI 漫剧 Studio 不应被设计成单一聊天 Agent，而应设计成：

**桌面创作软件 + Agent Runtime + 工作流引擎 + 项目数据库 + 多模型适配层 + ComfyUI 渲染后端。**

系统需要满足以下目标：

- 长期保存漫剧项目状态
- 支持复杂、多步骤 AI 任务
- 支持任务暂停、恢复、失败重试
- 支持本地 ComfyUI
- 支持云端生成 API
- 支持本地大模型
- 支持云端大模型
- 支持多模态模型
- 模型与业务逻辑解耦
- 支持未来扩展多 Agent
- 支持镜头级版本管理
- 支持可视化 Workflow
- 支持跨镜头连续性

---

# 2. 总体架构

```text
┌─────────────────────────────────────────────┐
│                Desktop Studio               │
│                                             │
│ Project / Script / Storyboard / Timeline    │
│ Canvas / Assets / AI Director / Settings    │
└───────────────────┬─────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│             Application Core                │
│                                             │
│ Project Service                             │
│ Asset Service                               │
│ Shot Service                                │
│ Version Service                             │
│ Configuration Service                       │
└───────────────────┬─────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│               Agent Runtime                 │
│                                             │
│ Director Agent                              │
│ Context Manager                             │
│ Memory Manager                              │
│ Skill Registry                              │
│ Tool Registry                               │
│ Planning / Execution Loop                   │
└───────────┬─────────────────┬───────────────┘
            │                 │
            ▼                 ▼
┌───────────────────┐ ┌───────────────────────┐
│ Workflow Engine   │ │    Model Gateway      │
│                   │ │                       │
│ DAG               │ │ LLM                   │
│ Task Queue        │ │ Vision                │
│ Retry             │ │ Image                 │
│ Dependency        │ │ Video                 │
│ State Machine     │ │ Audio                 │
└─────────┬─────────┘ └────────────┬──────────┘
          │                        │
          ▼                        ▼
┌───────────────────┐ ┌───────────────────────┐
│ ComfyUI Adapter   │ │ Provider Adapters     │
│                   │ │                       │
│ Workflow Mapping  │ │ OpenAI                │
│ Queue             │ │ Gemini                │
│ WebSocket         │ │ MiniMax               │
│ Result Import     │ │ Local Models          │
└───────────────────┘ └───────────────────────┘

                    │
                    ▼
┌─────────────────────────────────────────────┐
│                 Storage                     │
│                                             │
│ SQLite / PostgreSQL                         │
│ Local File Storage                          │
│ Project Assets                              │
│ Generation Cache                            │
│ Model Configurations                        │
└─────────────────────────────────────────────┘
```

---

# 3. 第一原则：Project 是整个系统的核心

传统 Agent 通常是：

```text
Conversation
  ↓
Message
  ↓
Tool
```

漫剧 Studio 应采用：

```text
Project
 ↓
Episode
 ↓
Scene
 ↓
Shot
 ↓
Asset
 ↓
Generation
 ↓
Version
```

Conversation 只是控制 Project 的一种方式。

因此：

**聊天记录不是系统真相。**

数据库中的 Project State 才是系统真相。

---

# 4. Project Domain Model

## Project

表示一个完整漫剧工程。

核心字段：

```text
id
name
description
style
status
created_at
updated_at
```

一个 Project 包含多个 Episode。

---

## Episode

一集漫剧。

```text
id
project_id
episode_number
title
source_text
script
status
```

---

## Scene

一个连续剧情场景。

例如：

```text
体育馆 / 夜晚 / 比赛结束后
```

字段：

```text
id
episode_id
name
location
time
lighting
description
mood
scene_order
```

---

## Shot

系统中最重要的生产对象。

一个 Shot 对应一个最终视频镜头。

字段至少包含：

```text
id

scene_id

shot_number

shot_type

camera_angle

camera_movement

composition

character_ids

action

emotion

dialogue

environment

image_prompt

video_prompt

duration

status

previous_shot_id

next_shot_id
```

---

# 5. Shot 应成为整个系统的原子生产单位

系统绝大部分功能围绕 Shot 工作。

例如：

```text
Shot
 ├── Script
 ├── Storyboard
 ├── Character
 ├── Scene
 ├── Prompt
 ├── Image
 ├── Video
 ├── Audio
 ├── Continuity
 └── Versions
```

这样用户说：

"重新生成第五镜。"

系统可以直接找到：

```text
Shot_005
```

而不是重新解析整个对话。

---

# 6. Asset System

资产必须与 Shot 分离。

主要 Asset 类型：

```text
Character

Environment

Prop

Costume

Image

Video

Audio

Reference

Workflow
```

例如角色：

```text
Character: 沈亦

├── 基础设定
├── 脸部参考
├── 正面
├── 侧面
├── 全身
├── 服装 A
├── 服装 B
├── LoRA
├── Prompt
└── Version
```

Shot 只引用 Character ID。

不能把完整角色描述复制进每个 Shot。

---

# 7. Agent Runtime

系统表面可以表现成一个 AI Director。

但内部 Agent Runtime 至少包含：

```text
Director Agent

Context Manager

Memory Manager

Skill Registry

Tool Registry

Planner

Executor

Reflection / Review
```

---

# 8. Director Agent

Director Agent 是系统唯一需要直接面对用户的主要 Agent。

它负责：

### Understand

理解：

"第三场太平了，改得更紧张。"

### Locate

定位：

```text
Scene 03
```

### Plan

形成修改计划：

```text
调整 Scene 情绪

↓

修改 Shot 12–18

↓

改变镜头节奏

↓

生成新的 Shot Prompt

↓

标记对应图片需要重新生成
```

### Execute

调用 Skill。

### Update

修改 Project State。

---

# 9. Agent Loop

核心循环建议采用：

```text
User Intent

↓

Observe Project State

↓

Plan

↓

Select Skill / Tool

↓

Execute

↓

Observe Result

↓

Validate

↓

Update Project State

↓

Continue / Stop
```

不要简单采用：

```text
Prompt
↓
LLM
↓
回答
```

---

# 10. Context Manager

这是非常关键的一层。

不能把整个项目全部塞进模型 Context。

Context Manager 根据当前任务动态提取信息。

例如：

用户：

"让第 14 镜接第 13 镜自然一点。"

Context Manager 只加载：

```text
Scene 03

Shot 13

Shot 14

Character References

Continuity State

Relevant Generation Results
```

然后发送给模型。

---

# 11. Memory 架构

建议区分三类 Memory。

## Session Memory

当前操作。

例如：

```text
用户刚刚修改了第三场。
```

---

## Project Memory

真正持久化的数据。

例如：

```text
角色设定

Shot

Scene

Generation

Version
```

存数据库。

---

## Semantic Memory

用于 RAG。

例如：

- 小说原文
- 世界观
- 人设文档
- 风格指南
- 创作要求

通过 Embedding Search 检索。

---

# 12. Skill 系统

不要第一版就做十几个真正的独立 Agent。

推荐：

```text
一个 Director Agent
+
多个 Skills
```

Skills：

```text
analyze_script

extract_characters

extract_scenes

create_shots

modify_shots

generate_prompt

generate_storyboard

generate_image

generate_video

check_continuity

review_generation

manage_assets
```

后面复杂度增加再拆成 Sub-Agent。

---

# 13. Tool System

Skill 与 Tool 必须区别。

Skill：

```text
create_storyboard
```

表示一种高级能力。

Tool：

```text
database.query

database.update

comfyui.generate

openai.image.generate

filesystem.read

filesystem.write

vision.analyze
```

表示具体可执行操作。

结构：

```text
Agent
 ↓
Skill
 ↓
Tool
 ↓
External System
```

---

# 14. Workflow Engine

这是整个产品最值得投入的后台模块之一。

Agent 不应该自己负责等待所有生成任务。

例如用户要求：

"生成这一场全部 18 个镜头。"

Agent 创建：

```text
Workflow Run
```

Workflow Engine 接管。

---

# 15. Workflow 数据结构

例如：

```text
Scene Generate Workflow

Shot 01 Image
      ↓
Shot 01 Review
      ↓
Shot 01 Video
      ↓
Shot 01 Video Review

Shot 02 Image
      ↓
Shot 02 Review
      ↓
Shot 02 Video
```

不同 Shot 可以并行。

---

# 16. Workflow Task 状态

建议：

```text
PENDING

QUEUED

RUNNING

WAITING

SUCCESS

FAILED

CANCELLED

RETRYING
```

一定不要只做：

```text
running / done
```

后面会非常难扩展。

---

# 17. Generation Router

一定要从第一版开始抽象。

不要写：

```text
generateImageWithComfyUI()
```

业务层应该调用：

```text
imageGenerator.generate()
```

然后 Router 决定：

```text
ComfyUI

OpenAI Image

MiniMax

Other API
```

---

# 18. Model Gateway

建议统一抽象：

```text
LLMProvider

VisionProvider

ImageProvider

VideoProvider

AudioProvider
```

所有 Provider 实现相同接口。

例如 Image Provider：

```text
generate()

edit()

variations()

getStatus()

cancel()
```

---

# 19. Local Model Adapter

本地模型建议优先支持：

```text
OpenAI-compatible API
```

这样可直接适配大量本地服务。

例如：

```text
localhost:xxxx/v1
```

用户配置：

```text
Base URL

API Key

Model Name
```

Studio 无需知道具体模型是什么。

---

# 20. ComfyUI Adapter

ComfyUI 不直接暴露给业务层。

架构：

```text
Shot
 ↓
Generation Request
 ↓
ComfyUI Adapter
 ↓
Workflow Template
 ↓
Parameter Injection
 ↓
ComfyUI Queue
 ↓
WebSocket Monitor
 ↓
Result
 ↓
Asset
```

---

# 21. ComfyUI Workflow Template

用户可以导入一个 Workflow。

Studio 保存：

```text
WorkflowDefinition
```

再定义参数 Mapping。

例如：

```text
prompt
→
Node 12.inputs.text

seed
→
Node 31.inputs.seed

reference_image
→
Node 5.inputs.image
```

因此 Studio 不需要理解：

```text
KSampler

CLIP

VAE
```

Studio 只知道：

```text
prompt

seed

reference image
```

---

# 22. Continuity Engine

这是产品与普通生成工具拉开差距的核心模块。

每个 Shot 保存：

```text
ContinuityState
```

例如：

```text
character_position

body_direction

face_direction

costume

held_object

emotion

lighting

camera_position

previous_action

next_action
```

---

# 23. Continuity Graph

不是单纯：

```text
Shot 1

Shot 2

Shot 3
```

而是：

```text
Shot 1
 │
 ▼
End State
 │
 ▼
Shot 2 Start State
 │
 ▼
End State
 │
 ▼
Shot 3 Start State
```

这会成为未来自动连续镜头生成的重要基础。

---

# 24. Version System

所有重要生产结果采用 immutable version。

例如：

```text
Shot 14

Image Version 1

Image Version 2

Image Version 3
```

用户选择：

```text
Active Version = Version 3
```

不要直接覆盖旧文件。

---

# 25. Generation 数据模型

建议：

```text
Generation

id

shot_id

type

provider

model

workflow

parameters

status

created_at

completed_at

cost

error

output_asset_id
```

这样以后可以统计：

```text
生成成功率

模型成本

平均耗时

不同模型质量
```

---

# 26. 前端架构

推荐：

```text
React
+
TypeScript
```

主要 Workspace：

```text
Project Explorer

Script Editor

Storyboard

Director Canvas

Asset Library

Timeline

Generation Queue

AI Director

Settings
```

---

# 27. 桌面容器

优先考虑：

```text
Tauri
```

或者：

```text
Electron
```

第一版如果团队熟悉 Web 开发：

Electron 开发成本最低。

如果非常重视：

- 安装包大小
- 内存占用
- 原生性能

则选择 Tauri。

> **实现注记（2026-08）**：桌面窗口使用**自定义标题栏**（`tauri.conf.json` 窗口 `decorations: false`；
> 前端 `components/TitleBar.tsx` 提供拖拽区 `data-tauri-drag-region` 与最小化/最大化/关闭按钮，
> 仅 Tauri 运行时渲染，浏览器构建保持原生浏览器 chrome）。相关 window 权限在
> `src-tauri/capabilities/default.json`：`allow-start-dragging / allow-minimize /
> allow-toggle-maximize / allow-close / allow-is-maximized`。

---

# 28. 后端

推荐两种路线。

### 路线 A

```text
Frontend
React

Desktop
Tauri / Electron

Backend
Python + FastAPI
```

优势：

AI / ComfyUI / ML 生态非常好。

这是当前项目更推荐的方案。

---

### 路线 B

```text
React

Electron

Node.js
```

然后 AI 相关功能使用 Python Sidecar。

架构复杂度会稍高。

第一版不建议。

---

# 29. 推荐技术栈

第一版建议：

```text
Frontend

React

TypeScript

Zustand

TanStack Query

React Flow

Tailwind
```

桌面：

```text
Tauri
```

后台：

```text
Python

FastAPI

Pydantic

SQLAlchemy
```

数据库：

```text
SQLite
```

任务：

第一阶段自研轻量 Task Engine。

后续需要时切换：

```text
Redis + Celery

或 Temporal
```

---

# 30. 本地文件结构

例如：

```text
MyDramaProject/

project.db

assets/

  characters/

  environments/

  props/

  images/

  videos/

  audio/

generations/

workflows/

cache/

exports/
```

这样项目可以整体复制。

---

# 31. SQLite 与文件系统分工

SQLite 保存：

```text
Metadata

Relations

States

Versions

Configurations
```

文件系统保存：

```text
Images

Videos

Audio

Workflow Files

Reference Files
```

不要把大视频 Blob 放数据库。

---

# 32. API 架构

内部 API 大致分：

```text
/api/projects

/api/episodes

/api/scenes

/api/shots

/api/assets

/api/generations

/api/workflows

/api/agents

/api/providers
```

---

# 33. Event Bus

推荐尽早引入内部事件机制。

例如：

```text
SHOT_UPDATED

GENERATION_STARTED

GENERATION_COMPLETED

GENERATION_FAILED

ASSET_CREATED

WORKFLOW_COMPLETED
```

前端监听事件刷新状态。

Agent 也可以监听事件。

---

# 34. MVP 系统边界

第一版只做：

```text
Project

Episode

Scene

Shot

Character

Storyboard

Director Agent

ComfyUI Image Generation

Generation Queue

Version

Project Save
```

暂时不要做：

```text
专业剪辑

音频工作站

复杂多 Agent

云协作

多人编辑

插件市场

自动成片

完整节点编辑器
```

---

# 35. MVP 技术闭环

第一阶段必须先打通：

```text
创建 Project

↓

导入小说文本

↓

AI 分析

↓

生成 Scene

↓

生成 Shot

↓

Storyboard UI 显示

↓

点击 Shot

↓

Generate

↓

调用 ComfyUI

↓

生成图片

↓

自动导入 Asset

↓

建立 Version

↓

展示在 Storyboard
```

只要这个闭环稳定工作，MVP 就成立。

---

# 36. 开发模块划分

建议建立：

```text
apps/

  desktop/

services/

  api/

packages/

  domain/

  agent/

  workflow/

  model-gateway/

  comfyui/

  database/

  shared/
```

如果采用 Python 后端，也可以：

```text
backend/

  api/

  domain/

  models/

  services/

  agents/

  skills/

  workflows/

  providers/

  comfyui/

  database/
```

重点是：

**业务逻辑不要写在 API Controller 中。**

---

# 37. 核心依赖关系

最重要的规则：

```text
UI

可以依赖

Application

Application

可以依赖

Domain

Agent

可以调用

Application Services

Generation

只能通过 Provider Interface

访问外部模型
```

绝对不要：

```text
Shot 页面

直接调用 ComfyUI API
```

否则未来换生成模型会非常痛苦。

---

# 38. 第一版开发顺序

建议严格按照：

### Phase 1

Domain Model

Project

Scene

Shot

Asset

Generation

Version

### Phase 2

Database

### Phase 3

REST API

### Phase 4

Studio 基础 UI

### Phase 5

ComfyUI Adapter

### Phase 6

Storyboard

### Phase 7

Director Agent

### Phase 8

Workflow Engine

### Phase 9

Continuity

### Phase 10

Video

不要先写 Agent。

因为：

**Agent 必须建立在稳定的 Project Domain 上。**

---

# 39. 最关键的架构判断

整个项目真正的核心不是：

```text
LLM
```

不是：

```text
ComfyUI
```

也不是：

```text
Agent Chat
```

真正的核心是：

```text
Project State

+

Production Graph

+

Workflow Engine
```

AI Agent 是控制这些系统的智能接口。

ComfyUI 是这些系统调用的渲染引擎。

---

# 40. 最终系统定义

最终整个产品应该形成：

```text
                  AI Director
                       │
                       ▼
                  Project State
                       │
            ┌──────────┴─────────┐
            ▼                    ▼
      Production Graph      Asset System
            │                    │
            └──────────┬─────────┘
                       ▼
               Workflow Engine
                       │
                       ▼
               Generation Router
              /        |         \
             /         |          \
        ComfyUI    GPT Image    Video API
```

从架构层面来看：

**这是一个 AI 驱动的垂直生产系统，而不是一个套了 UI 的聊天机器人。**
