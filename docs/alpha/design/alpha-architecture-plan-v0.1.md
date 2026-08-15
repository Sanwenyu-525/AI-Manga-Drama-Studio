# AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**目标：** 将“能够完成一次漫剧生成”的 MVP，升级为“能够持续编辑、局部重生成、管理资产并稳定完成真实漫剧项目”的 AI 漫剧生产 Studio。

---

# 1. Alpha 阶段定位

MVP 阶段主要回答一个问题：

> 整条 AI 漫剧生产链路能不能跑通？

Alpha 阶段需要回答另一个问题：

> 用户能不能真正使用这个软件持续制作一部漫剧？

因此 Alpha 不再以增加模型数量和增加生成能力为核心，而是围绕以下五个关键词建设：

1. **Project**
2. **Asset**
3. **Version**
4. **Generation**
5. **Continuity**

Alpha 的核心转变：

```text
MVP

Novel
 ↓
AI
 ↓
Workflow
 ↓
Generated Files
 ↓
Final Video
```

升级为：

```text
Alpha

Project
 ├── Story
 ├── Episode
 │    ├── Scene
 │    │    ├── Shot
 │    │    │    ├── Prompt
 │    │    │    ├── Asset
 │    │    │    ├── Generation
 │    │    │    └── Version
 │    │    └── ...
 │    └── ...
 │
 ├── Character Library
 ├── Location Library
 ├── Prop Library
 ├── Voice Library
 ├── Workflow
 ├── Timeline
 └── Generation History
```

---

# 2. Alpha 核心目标

Alpha 阶段完成后，系统应至少具备以下能力。

## 2.1 项目化生产

用户能够：

* 创建漫剧项目
* 导入小说或剧本
* 创建 Episode
* 将 Episode 拆解成 Scene
* 将 Scene 拆解成 Shot
* 对每一个 Shot 单独管理
* 保存整个漫剧工程状态
* 退出后重新打开继续制作

---

## 2.2 资产化管理

所有生成结果不再只是磁盘文件。

系统应把以下内容全部视为 Asset：

```text
Character
Location
Prop
Costume
Reference Image
Storyboard
Shot Image
Shot Video
Voice
Music
Sound Effect
Subtitle
Final Video
```

每个 Asset 都具有：

```text
Asset
├── id
├── type
├── projectId
├── source
├── metadata
├── file
├── preview
├── generationId
├── version
├── status
└── createdAt
```

---

# 3. Alpha 产品原则

Alpha 阶段遵守以下原则。

## 原则 1：一切皆项目资源

不要允许模型生成完成后，仅返回：

```text
output/abc123.png
```

而应该立即转换为：

```text
Asset
```

由 Studio 统一管理。

---

## 原则 2：任何生成都必须可追溯

每一个 AI 结果必须知道：

* 谁生成的
* 使用哪个模型
* 使用哪个 Workflow
* Prompt 是什么
* 输入资产是什么
* 参数是什么
* 什么时候生成
* 属于哪个 Shot
* 是哪个版本

因此：

```text
Generation
```

必须成为一级领域对象。

---

## 原则 3：任何节点都允许局部重生成

例如：

```text
Episode 01
 └── Scene 03
      └── Shot 08
```

用户修改 Shot 08 后：

只重新执行：

```text
Shot Image
   ↓
Shot Video
```

不能重新执行整个 Episode。

---

## 原则 4：历史版本不能被覆盖

禁止：

```text
shot_08.png
```

直接被下一次生成覆盖。

应该：

```text
Shot 08

Image
├── v1
├── v2
├── v3
└── v4 MASTER
```

---

## 原则 5：AI 只负责建议和执行，不拥有最终工程状态

真正的 Source of Truth 应该是：

```text
Studio Project State
```

而不是：

* LLM Context
* LangChain Memory
* ComfyUI Workflow
* Prompt
* 某个 Agent 的 Memory

---

# 4. Alpha 总体架构

推荐整体采用：

```text
┌──────────────────────────────────────────────┐
│                 Desktop Studio               │
│                                              │
│ Project Explorer │ Canvas │ Inspector        │
│ Timeline         │ Assets │ Generation       │
└──────────────────────┬───────────────────────┘
                       │
                       │ API / IPC
                       ▼
┌──────────────────────────────────────────────┐
│               Studio Backend                 │
│                                              │
│ Project Service                              │
│ Story Service                                │
│ Asset Service                                │
│ Generation Service                           │
│ Version Service                              │
│ Workflow Service                             │
│ Timeline Service                             │
│ Continuity Service                           │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                Agent Layer                   │
│                                              │
│ Director Agent                               │
│ Script Agent                                 │
│ Storyboard Agent                             │
│ Character Agent                              │
│ Camera Agent                                 │
│ Continuity Agent                             │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│          Generation Orchestration            │
│                                              │
│ Job Manager                                  │
│ Task Queue                                   │
│ Retry                                        │
│ Checkpoint                                   │
│ Dependency Graph                             │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│             Provider Adapter                 │
│                                              │
│ ComfyUI Adapter                              │
│ Image Provider                               │
│ Video Provider                               │
│ Voice Provider                               │
│ LLM Provider                                 │
└──────────────────────┬───────────────────────┘
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          ComfyUI    Cloud AI    Local Model
```

---

# 5. 核心领域模型

Alpha 阶段最重要的工作之一，就是正式建立领域模型。

推荐：

```text
Workspace
   │
   └── Project
        │
        ├── Episode
        │    │
        │    └── Scene
        │          │
        │          └── Shot
        │
        ├── Asset
        ├── Character
        ├── Location
        ├── Generation
        ├── Workflow
        └── Timeline
```

---

# 6. Project

Project 是整个 Studio 的最高业务容器。

```text
Project
```

建议字段：

```text
id
name
description

status

projectType
aspectRatio
resolution
fps

defaultImageModel
defaultVideoModel
defaultVoiceModel

stylePresetId

createdAt
updatedAt
lastOpenedAt
```

状态：

```text
DRAFT
ACTIVE
PAUSED
COMPLETED
ARCHIVED
```

---

# 7. Episode

Episode 对应：

* 一集
* 一话
* 一个完整视频

```text
Project
   ↓
Episode
```

字段：

```text
id
projectId

episodeNumber
title

sourceText
script

durationTarget

status

createdAt
updatedAt
```

状态：

```text
DRAFT
SCRIPTING
STORYBOARDING
GENERATING
EDITING
COMPLETED
```

---

# 8. Scene

Scene 表示：

> 时间、空间和剧情连续的一组镜头。

例如：

```text
Scene 12

地点：
篮球馆

时间：
晚上

人物：
沈亦
教练
队友

剧情：
训练结束后，教练单独留下沈亦谈话。
```

字段：

```text
id
episodeId

sceneNumber
title
description

locationId

timeOfDay
weather

storyPurpose

startTime
duration

status
```

---

# 9. Shot

Shot 是整个 AI 漫剧 Studio 最关键的数据单元。

后续：

* Prompt
* 图像
* 视频
* 运镜
* 人物状态
* 连贯性
* 重生成

几乎全部围绕 Shot 展开。

推荐：

```text
Shot
├── Narrative
├── Visual
├── Camera
├── Characters
├── Prompt
├── Assets
├── Generations
└── Continuity
```

基础字段：

```text
id
sceneId

shotNumber
orderIndex

description

duration

shotType
cameraAngle
cameraMovement

status
```

---

# 10. Shot Visual Specification

不要只保存自然语言 Prompt。

应该引入结构化视觉规格：

```json
{
  "shotType": "MEDIUM_CLOSE_UP",
  "cameraAngle": "EYE_LEVEL",
  "cameraMovement": "SLOW_PUSH_IN",
  "subject": ["character_shenyi"],
  "location": "basketball_gym",
  "time": "night",
  "lighting": "cool_indoor",
  "mood": "restrained",
  "action": "looks toward coach",
  "duration": 4.5
}
```

然后由 Prompt Agent 根据结构化信息生成真正 Prompt。

即：

```text
Shot Specification
       ↓
Prompt Agent
       ↓
Model-specific Prompt
```

而不是：

```text
Shot = Prompt
```

这是非常重要的一层抽象。

---

# 11. Character Domain

Character 不应该只是：

```text
角色名字 + Prompt
```

而应该逐步成为：

```text
Character
├── Identity
├── Appearance
├── Body
├── Costume
├── Voice
├── Reference Assets
└── Versions
```

例如：

```text
Character: 沈亦

Identity
├── age: 15
├── gender: male
└── nationality: Chinese

Body
├── height: 204cm
├── wingspan: 219cm
├── build: elite basketball athlete
└── bodyVersion: 3

Face
├── faceShape
├── eyes
├── eyebrows
├── nose
├── jaw
└── masterReference
```

---

# 12. Character Master

Alpha 必须加入：

```text
MASTER
```

概念。

例如：

```text
沈亦

v1 Initial
v2 Face refinement
v3 Hairstyle refinement
v4 Final

★ MASTER = v4
```

未来生成新镜头：

```text
Character Resolver
       ↓
Master Version
       ↓
Reference Asset
       ↓
Generation
```

这样才能保证角色长期一致。

---

# 13. Asset Domain

统一设计：

```text
Asset
```

而不是为每一种文件创建完全不同的数据体系。

Asset Type：

```text
CHARACTER_REFERENCE

LOCATION_REFERENCE

PROP_REFERENCE

STORYBOARD

SHOT_IMAGE

SHOT_VIDEO

VOICE

BGM

SFX

SUBTITLE

FINAL_VIDEO
```

---

# 14. Asset 数据结构

```text
Asset

id
projectId

type
name

storageType
storagePath

mimeType

width
height
duration
fileSize

sourceType

generationId

version
isMaster

metadata

createdAt
updatedAt
```

sourceType：

```text
GENERATED
IMPORTED
EDITED
DERIVED
```

---

# 15. Generation Domain

Alpha 阶段应正式增加：

```text
Generation
```

一个 Generation 代表一次模型执行。

例如：

> 使用某个 ComfyUI Workflow 根据角色参考图生成 Shot 15 的视频。

Generation：

```text
id

projectId

targetType
targetId

generationType

provider
model

workflowId
workflowVersion

prompt
negativePrompt

parameters

inputAssets

outputAssets

status

startedAt
finishedAt

errorCode
errorMessage
```

---

# 16. Generation Type

```text
SCRIPT_GENERATION

SCENE_EXTRACTION

SHOT_GENERATION

PROMPT_GENERATION

CHARACTER_IMAGE

LOCATION_IMAGE

STORYBOARD_IMAGE

SHOT_IMAGE

SHOT_VIDEO

VOICE

MUSIC

SUBTITLE

FINAL_RENDER
```

---

# 17. Generation 状态机

推荐：

```text
CREATED
   ↓
QUEUED
   ↓
RUNNING
   ↓
SUCCEEDED
```

异常：

```text
RUNNING
 ↓
FAILED
```

以及：

```text
CANCELLED
RETRYING
PAUSED
```

完整状态：

```text
CREATED
QUEUED
RUNNING
SUCCEEDED
FAILED
CANCELLED
PAUSED
RETRYING
```

---

# 18. Generation 与 Asset 的关系

非常重要：

```text
Generation
    │
    ├── Input Asset[]
    │
    └── Output Asset[]
```

例如：

```text
Generation #824

Input
├── shenyi_master.png
├── basketball_gym.png
└── shot_15_storyboard.png

Output
└── shot_15_v3.mp4
```

这样就建立完整 Provenance。

---

# 19. Version 系统

Alpha 必须建立通用 Version 系统。

适用：

```text
Character
Asset
Prompt
Shot
Workflow
Generation Output
```

推荐不是直接删除旧版本，而采用：

```text
Version Chain
```

例如：

```text
Shot Image

v1
 ↓
v2
 ↓
v3
 ↓
v4
```

并允许：

```text
Set Master
Restore
Compare
Branch
```

---

# 20. Master 与 Active Version

区分：

```text
MASTER
```

和：

```text
ACTIVE
```

例如：

Character：

```text
Master = 官方角色形象
```

Shot：

```text
Active = 当前 Timeline 正在使用版本
```

这样就可以：

```text
Shot 12 Video

v1
v2
v3 ← Active
v4
```

而不用删除 v4。

---

# 21. 局部重新生成

Alpha 核心用户体验：

```text
Regenerate
```

用户进入：

```text
Scene 03
→ Shot 08
```

修改：

```text
Camera:
MEDIUM_SHOT

→

CLOSE_UP
```

系统进行 Dependency Analysis：

```text
Shot Specification
       ↓ changed
Prompt
       ↓ stale
Shot Image
       ↓ stale
Shot Video
       ↓ stale
Timeline
```

系统应提示：

```text
Affected outputs:

✓ Prompt
✓ Image
✓ Video

Unaffected:

Character
Location
Voice
```

然后只执行必要节点。

---

# 22. Dependency Graph

这里建议正式加入：

```text
Dependency Graph
```

例如：

```text
Character MASTER ────────┐
                         │
Location MASTER ─────────┼──→ Shot Image
                         │
Storyboard ──────────────┘
                               │
                               ↓
                          Shot Video
                               │
                               ↓
                           Timeline
```

发生变化：

```text
Character MASTER Changed
```

系统可以知道：

```text
Shot 03 → stale
Shot 07 → stale
Shot 19 → stale
```

但不是立即自动全部重新生成。

而应该：

```text
Mark as Stale
```

由用户决定是否更新。

---

# 23. Stale 状态

推荐 Asset 增加：

```text
FRESH
STALE
```

例如：

```text
沈亦 MASTER

v4 → v5
```

于是使用 v4 的镜头标记：

```text
⚠ Character reference outdated
```

而不是直接自动重新生成。

这是专业创作软件应该有的行为。

---

# 24. Task / Job 系统

当一个 Episode 有几十甚至上百个镜头后，不可能同步执行。

因此 Alpha 必须开始建设 Job 系统。

结构：

```text
Job
 └── Task
      └── Generation
```

例如：

```text
Generate Episode 01
```

创建：

```text
Job #1002
├── Shot 001 Image
├── Shot 001 Video
├── Shot 002 Image
├── Shot 002 Video
├── Shot 003 Image
└── ...
```

---

# 25. Job 数据结构

```text
Job

id
projectId

type

status

totalTasks
completedTasks
failedTasks

progress

createdAt
startedAt
finishedAt
```

Job Status：

```text
CREATED
QUEUED
RUNNING
PAUSED
COMPLETED
PARTIAL_FAILED
FAILED
CANCELLED
```

---

# 26. Task Queue

任务调度必须支持：

```text
priority

dependency

retry

cancel

pause

resume
```

例如：

```text
Shot Video
```

依赖：

```text
Shot Image
```

必须：

```text
Image Success
      ↓
Video Start
```

---

# 27. Checkpoint

Alpha 强烈建议实现最基础 Checkpoint。

例如用户正在：

```text
Generate Episode 01

31 / 80
```

电脑重启。

重新打开项目：

```text
Generation interrupted.

31 completed
49 pending

[Resume]
```

而不是：

```text
Start Again
```

---

# 28. Retry

Generation 可以配置：

```text
maxRetryCount = 3
```

例如：

```text
Video Generation
 ↓
Timeout
 ↓
Retry #1
 ↓
GPU error
 ↓
Retry #2
 ↓
Success
```

并完整保留日志。

---

# 29. Workflow Adapter

Studio 不应该直接依赖某个 ComfyUI JSON。

推荐业务层调用：

```text
generateCharacter()

generateLocation()

generateShotImage()

generateShotVideo()

generateVoice()
```

Adapter：

```text
GenerationService
       ↓
ProviderRouter
       ↓
ComfyUIAdapter
       ↓
WorkflowResolver
       ↓
ComfyUI Workflow
```

---

# 30. Workflow Template

定义：

```text
WorkflowTemplate
```

例如：

```text
SHOT_VIDEO_STANDARD
```

而内部：

```text
ComfyUI
└── minimax_hailuo_02.json
```

后续：

```text
SHOT_VIDEO_STANDARD
```

可以映射：

```text
MiniMax
Seedance
Kling
Veo
Local Model
```

业务层不需要修改。

---

# 31. Workflow 输入定义

不要通过硬编码：

```text
node["87"]["inputs"]["text"]
```

传递参数。

应该定义：

```text
Workflow Input Schema
```

例如：

```json
{
  "prompt": {
    "type": "string",
    "required": true
  },
  "referenceImage": {
    "type": "asset",
    "required": true
  },
  "duration": {
    "type": "number",
    "default": 5
  }
}
```

Adapter 再将：

```text
prompt
```

映射：

```text
Node 87 → text
```

---

# 32. AI Director Alpha

MVP：

```text
Novel
 ↓
Director
 ↓
Scenes
 ↓
Shots
```

Alpha：

Director 不再直接生成一大块 JSON。

推荐：

```text
Director Agent
      │
      ├── Story Analysis
      ├── Episode Planning
      ├── Scene Planning
      ├── Shot Planning
      └── Review
```

---

# 33. Director 职责

Director Agent 负责：

```text
Narrative Intent
Pacing
Scene Structure
Shot Strategy
Character Focus
Visual Consistency
```

但不直接操作：

```text
ComfyUI Node
文件路径
数据库
```

---

# 34. Agent 分层

推荐 Alpha 先不要一次实现十几个 Agent。

采用：

```text
Director Agent
│
├── Script Agent
│
├── Visual Agent
│
└── Continuity Agent
```

先三个子 Agent。

---

# 35. Script Agent

职责：

```text
小说理解

剧情提取

对白提取

Scene 分解

人物行为

叙事节奏
```

输出结构化：

```text
Episode
Scene
Narrative Beat
Dialogue
Action
```

---

# 36. Visual Agent

职责：

```text
Scene → Shot

构图
景别
镜头角度
运镜
人物站位
光照
视觉 Prompt
```

输出：

```text
Shot Specification
```

---

# 37. Continuity Agent

职责：

检查：

```text
角色

服装

时间

地点

天气

道具

位置

动作

镜头方向
```

例如：

Shot 20：

```text
沈亦手中有篮球
```

Shot 21：

```text
篮球突然不存在
```

Continuity Agent 应产生：

```text
Warning:
Prop continuity broken.
```

---

# 38. Continuity State

为 Scene / Shot 保存：

```text
ContinuityState
```

例如：

```json
{
  "characters": {
    "shenyi": {
      "costume": "white_7_uniform",
      "position": "left_wing",
      "emotion": "focused",
      "sweat": true
    }
  },
  "props": {
    "basketball": {
      "holder": "shenyi"
    }
  }
}
```

下一 Shot 默认继承。

---

# 39. Context Resolver

Agent 不应读取整个项目。

加入：

```text
Context Resolver
```

请求：

```text
Generate Shot 31
```

系统只提供：

```text
Project Style

Current Scene

Shot 29
Shot 30

Current Character State

Relevant Character MASTER

Relevant Location

Story Context
```

减少：

* Token
* 干扰信息
* 上下文漂移

---

# 40. Studio 前端信息架构

Alpha 推荐：

```text
Studio
│
├── Home
│
├── Project
│   │
│   ├── Story
│   ├── Characters
│   ├── Locations
│   ├── Episodes
│   ├── Assets
│   └── Settings
│
└── Editor
```

---

# 41. Editor 核心布局

推荐：

```text
┌─────────────────────────────────────────────────────────┐
│ TopBar                                                  │
├──────────────┬─────────────────────────┬────────────────┤
│              │                         │                │
│ Project      │                         │ Inspector      │
│ Explorer     │      Main Canvas        │                │
│              │                         │                │
├──────────────┴─────────────────────────┴────────────────┤
│ Timeline                                                │
├─────────────────────────────────────────────────────────┤
│ Agent / Generation / Console                            │
└─────────────────────────────────────────────────────────┘
```

---

# 42. Project Explorer

结构：

```text
Project
│
├── Episode 01
│    ├── Scene 01
│    │    ├── Shot 001
│    │    ├── Shot 002
│    │    └── Shot 003
│    └── Scene 02
│
├── Episode 02
│
├── Characters
│
├── Locations
│
└── Assets
```

---

# 43. Inspector

用户选中：

```text
Shot 023
```

右侧展示：

```text
SHOT 023

Duration
4.5s

Camera
Medium Close Up

Angle
Eye Level

Movement
Slow Push In

Character
沈亦

Location
Basketball Gym

Prompt
...

Generation
Image v4
Video v3

[Regenerate]
```

---

# 44. Generation Panel

底部：

```text
Generation

Running
────────────────────────

Shot 023 Image
██████████████░░ 82%

Queued
Shot 024 Image
Shot 024 Video

Failed
Shot 017 Video

[Retry]
```

---

# 45. Timeline Alpha

Alpha Timeline 暂时不要做 Premiere 级复杂度。

第一版只需要：

```text
Video Track

Voice Track

Music Track

Subtitle Track
```

结构：

```text
V1 │ Shot01 │ Shot02 │ Shot03 │
A1 │ Voice1 │ Voice2 │ Voice3 │
A2 │       Background Music    │
S1 │ Sub01  │ Sub02  │ Sub03   │
```

支持：

```text
排序
Trim
删除
替换版本
预览
```

即可。

---

# 46. Alpha 暂不做的功能

为了控制范围，以下建议延后。

## 暂缓 1

复杂节点式 Workflow Editor。

MVP 已经通过 ComfyUI 承担底层 Workflow。

Studio Alpha 不需要重新造一个完整 ComfyUI。

---

## 暂缓 2

Marketplace。

例如：

```text
Workflow Marketplace

Agent Marketplace

Model Marketplace
```

Beta / V1 再做。

---

## 暂缓 3

多人实时协作。

第一阶段：

```text
Single User
```

即可。

---

## 暂缓 4

云端大规模 GPU Scheduler。

先支持：

```text
Local
+
简单 Remote Provider
```

---

## 暂缓 5

专业级视频剪辑。

不要试图在 Alpha 阶段替代：

```text
Premiere
DaVinci Resolve
```

Timeline 只服务于 AI 漫剧。

---

# 47. Alpha 开发 Epic

整个 Alpha 推荐拆为 8 个 Epic。

```text
A1 Project Core

A2 Asset System

A3 Generation System

A4 Version System

A5 Job & Queue

A6 Agent Alpha

A7 Continuity

A8 Studio UX
```

---

# 48. Epic A1：Project Core

目标：

建立：

```text
Project
Episode
Scene
Shot
```

完成：

* 创建项目
* 打开项目
* 保存项目
* Episode CRUD
* Scene CRUD
* Shot CRUD
* Shot 排序
* 项目恢复

验收：

> 关闭应用后重新打开，一个完整 Episode 的 Scene / Shot 数据不能丢失。

---

# 49. Epic A2：Asset System

完成：

```text
Asset Manager

Import

Preview

Delete / Archive

Type

Metadata

Project Binding
```

支持：

```text
Character Reference
Location Reference
Shot Image
Shot Video
Voice
```

---

# 50. Epic A3：Generation System

完成统一接口：

```text
GenerationService
```

所有：

```text
Image
Video
Voice
LLM
```

必须通过统一 Generation 模型。

验收：

> 任意生成结果都能追溯其模型、参数、Prompt 和输入资产。

---

# 51. Epic A4：Version System

完成：

```text
Asset Version
Prompt Version
MASTER
ACTIVE
Restore
```

第一阶段不用实现复杂 Branch。

---

# 52. Epic A5：Job & Queue

完成：

```text
Job
Task
Queue
Progress
Cancel
Retry
Resume
```

验收：

> 生成 20 个 Shot 时，其中一个失败，其他任务仍然能够继续。

---

# 53. Epic A6：Agent Alpha

第一阶段：

```text
Director
Script
Visual
```

做到：

```text
Novel
 ↓
Episode
 ↓
Scene
 ↓
Shot
 ↓
Shot Specification
```

全部结构化输出。

---

# 54. Epic A7：Continuity

第一版只解决：

```text
Character

Costume

Location

Time

Prop
```

五种连续性。

不要一开始就解决所有物理动作连续性。

---

# 55. Epic A8：Studio UX

完成：

```text
Project Explorer

Shot Editor

Inspector

Asset Browser

Generation Panel

Basic Timeline
```

---

# 56. 推荐开发顺序

实际开发不要严格按照 Epic 编号一次全部完成。

推荐：

```text
阶段 1

Project
Episode
Scene
Shot
```

↓

```text
阶段 2

Asset
Generation
```

↓

```text
阶段 3

单 Shot 生成
单 Shot 重生成
```

↓

```text
阶段 4

Version
MASTER
ACTIVE
```

↓

```text
阶段 5

Job
Queue
Retry
Resume
```

↓

```text
阶段 6

Director Agent
Script Agent
Visual Agent
```

↓

```text
阶段 7

Continuity
```

↓

```text
阶段 8

Timeline
Studio UX Polish
```

---

# 57. Alpha 第一个技术里程碑

建议：

## Milestone A0

目标：

> 把“生成结果”正式纳入工程体系。

必须完成：

```text
Project

Episode

Scene

Shot

Asset

Generation
```

以及关系：

```text
Project
 ↓
Episode
 ↓
Scene
 ↓
Shot
 ↓
Generation
 ↓
Asset
```

这是 Alpha 的架构地基。

---

# 58. Alpha 第二个技术里程碑

## Milestone A1

目标：

> 一个 Shot 可以被反复编辑和重生成。

必须完成：

```text
Shot Editor

Prompt

Image Generation

Video Generation

Version

Regenerate
```

达到：

```text
Shot 08

v1
v2
v3
```

可自由切换。

---

# 59. Alpha 第三个技术里程碑

## Milestone A2

目标：

> 可以生成一个完整 Scene。

例如：

```text
Scene 01

Shot 01
Shot 02
Shot 03
Shot 04
Shot 05
Shot 06
```

系统能够自动：

```text
Queue

Generate

Retry

Track Progress

Resume
```

---

# 60. Alpha 第四个技术里程碑

## Milestone A3

目标：

> 可以完成一个完整 Episode。

包括：

```text
Scene
Shot
Video
Voice
Subtitle
Timeline
Render
```

达到：

> 使用 Studio 制作一集真实 AI 漫剧，而不是技术 Demo。

---

# 61. Alpha 验收测试

至少选择一个真实小说章节。

建议测试：

```text
1 Episode

5～10 Scenes

30～80 Shots

3～8 Characters

3～10 Locations
```

完整跑：

```text
Novel
 ↓
Script
 ↓
Scenes
 ↓
Shots
 ↓
Character Assets
 ↓
Location Assets
 ↓
Storyboard
 ↓
Shot Images
 ↓
Shot Videos
 ↓
Voice
 ↓
Timeline
 ↓
Final Video
```

---

# 62. Alpha 核心指标

建议记录以下指标。

## Generation Success Rate

```text
成功任务 / 总任务
```

目标：

```text
> 95%
```

包含自动 Retry 后结果。

---

## Resume Success Rate

应用异常关闭后：

```text
恢复成功率 > 99%
```

---

## Shot Regeneration Cost

修改一个 Shot：

不能触发无关 Scene 重新生成。

目标：

```text
局部重生成比例接近 100%
```

---

## Character Consistency

人工评估：

```text
PASS
WARNING
FAIL
```

并记录失败原因。

---

## Manual Intervention

统计制作一个 Episode：

```text
人工操作次数
```

Alpha 初期不要求极低。

但必须开始记录。

因为未来 Agent 优化的目标就是降低这个数字。

---

# 63. Alpha 完成定义

当以下场景成立，可以认为 Alpha 完成：

用户：

1. 创建一个漫剧项目；
2. 导入一章小说；
3. Director 自动拆 Episode / Scene / Shot；
4. 用户修改几个 Shot；
5. 生成角色 MASTER；
6. 生成场景资产；
7. 自动生成所有 Shot；
8. 某几个镜头失败；
9. 系统自动 Retry；
10. 用户单独修改 Shot 17；
11. 只重新生成 Shot 17；
12. 选择 Shot 17 Video v3；
13. Timeline 自动更新；
14. 配音和字幕生成；
15. 导出最终视频；
16. 第二天重新打开项目仍然能够继续编辑。

如果这一整条链路稳定运行：

```text
AI 漫剧 Studio Alpha
```

才算真正成立。

---

# 64. Alpha 后的软件定位

MVP 是：

> AI 漫剧生成工具。

Alpha 应成为：

> AI 原生漫剧制作工作站。

Beta 再进一步成为：

> AI Agent 驱动的漫剧生产系统。

最终 V1：

> 面向长篇连续内容生产的 AI 漫剧 Studio。

---

# 65. 下一阶段文档拆分

本规划确定以后，建议按以下顺序继续输出详细设计：

```text
01
AI 漫剧 Studio
核心领域模型详细设计 v0.1

02
数据库 Schema 与数据关系设计 v0.1

03
Alpha Backend API & Service 详细设计 v0.1

04
Asset / Generation / Version 系统详细设计 v0.1

05
Job Queue & Generation State Machine 详细设计 v0.1

06
AI Director Agent Alpha 架构设计 v0.2

07
Continuity Engine 详细设计 v0.1

08
Studio Alpha 前端 UX 与页面设计 v0.1

09
ComfyUI Workflow Adapter 详细设计 v0.1

10
Alpha 测试与验收方案 v0.1
```

## 推荐下一步

**下一份优先编写：**

> 《AI 漫剧 Studio 核心领域模型详细设计 v0.1》

原因是接下来的：

```text
数据库
API
Service
Agent
前端状态
版本系统
任务系统
```

全部依赖：

```text
Project
Episode
Scene
Shot
Asset
Generation
Version
```

这些领域对象。

如果核心领域模型没有先定下来，越往后开发，重构成本越高。
