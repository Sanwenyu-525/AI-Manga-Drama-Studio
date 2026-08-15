# AI 漫剧 Studio 核心领域模型详细设计 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**上游文档：**《AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1》
**目标：** 固化 Studio 的核心业务对象、边界、关系、生命周期与约束，为数据库 Schema、Backend API、Service、Agent、任务系统和前端状态管理提供统一语义。

---

# 1. 设计目标

AI 漫剧 Studio 的领域模型不能围绕某一个模型、某一个 ComfyUI Workflow 或某一个 Prompt 设计。

核心模型必须描述的是：

> **一部漫剧是如何被组织、编辑、生成、版本化和最终交付的。**

因此领域层应独立于：

* ComfyUI
* MiniMax
* Seedance
* Kling
* OpenAI
* LangChain
* LangGraph
* 本地模型
* 云端模型

这些都应该位于基础设施层或 Adapter 层。

核心领域应长期稳定。

---

# 2. 顶层领域结构

第一版领域结构确定为：

```text
Workspace
└── Project
    ├── Episode
    │   └── Scene
    │       └── Shot
    │
    ├── Character
    ├── Location
    ├── Prop
    ├── Asset
    ├── Prompt
    ├── Generation
    ├── Workflow
    ├── Job
    ├── Timeline
    └── ProjectSetting
```

辅助领域：

```text
Version
ContinuityState
GenerationDependency
Tag
Metadata
AuditLog
```

---

# 3. 聚合边界设计

领域模型不要把整个 Project 做成一个巨大的 Aggregate。

推荐划分以下 Aggregate Root。

## 3.1 核心 Aggregate Root

```text
Project
Episode
Scene
Shot
Character
Location
Asset
Generation
Job
Timeline
WorkflowTemplate
```

原因：

如果：

```text
Project
```

直接持有整个：

```text
Episode
Scene
Shot
Asset
Generation
```

对象树，

一个大型 Episode 可能包含数百个 Shot 和几千个 Asset。

加载 Project 时就会产生严重性能问题。

因此使用：

```text
ID Reference
```

而不是深层实体直接嵌套。

---

# 4. Workspace

Workspace 是本地 Studio 工作空间。

负责：

* 项目目录
* 本地缓存
* Provider 配置
* ComfyUI 连接信息
* 模型配置
* 用户工作环境

但它不是漫剧业务核心对象。

结构：

```text
Workspace
├── id
├── name
├── rootPath
├── projectIds[]
├── settings
└── createdAt
```

Workspace 与 Project：

```text
Workspace
1
│
└────── *
       Project
```

一个 Workspace 可以管理多个项目。

---

# 5. Project Aggregate

Project 是最高业务容器。

例如：

```text
《最后一种打法》
```

本身就是一个 Project。

---

# 6. Project 基础属性

```text
Project
{
    id
    name
    description

    status
    projectType

    coverAssetId

    aspectRatio
    defaultResolution
    defaultFps

    defaultStylePresetId

    activeEpisodeId

    createdAt
    updatedAt
    lastOpenedAt
}
```

---

# 7. ProjectStatus

```text
DRAFT

ACTIVE

PAUSED

COMPLETED

ARCHIVED
```

状态流：

```text
DRAFT
  ↓
ACTIVE
  ↓
PAUSED
  ↓
ACTIVE
  ↓
COMPLETED
```

以及：

```text
DRAFT
ACTIVE
PAUSED
COMPLETED
   ↓
ARCHIVED
```

ARCHIVED 原则：

> 归档，不物理删除。

---

# 8. ProjectType

预留：

```text
MANGA_DRAMA

ANIME_SHORT

MOTION_COMIC

STORY_VIDEO

CUSTOM
```

Alpha 第一版主要使用：

```text
MANGA_DRAMA
```

但领域模型不写死。

---

# 9. ProjectSetting

项目的生成策略不要全部直接放在 Project 表中。

拆分：

```text
ProjectSetting
```

结构：

```text
ProjectSetting
{
    projectId

    language

    defaultImageProvider
    defaultImageModel

    defaultVideoProvider
    defaultVideoModel

    defaultLlmProvider
    defaultLlmModel

    defaultVoiceProvider

    defaultImageWorkflowId
    defaultVideoWorkflowId

    autoRetry
    maxRetryCount

    autoSave
    continuityEnabled
}
```

这样可以避免 Project 无限膨胀。

---

# 10. Episode Aggregate

Episode 对应：

> 一集、一话或一个最终可以独立输出的视频单元。

关系：

```text
Project
1
│
└────── *
       Episode
```

---

# 11. Episode 数据结构

```text
Episode
{
    id
    projectId

    episodeNumber
    title
    description

    sourceDocumentId
    sourceText

    script

    targetDuration

    status

    orderIndex

    createdAt
    updatedAt
}
```

---

# 12. EpisodeStatus

```text
DRAFT

ANALYZING

SCRIPTING

STORYBOARDING

GENERATING

EDITING

RENDERING

COMPLETED
```

状态不代表强制工作流。

用户仍然可以：

```text
GENERATING
```

状态时回去修改剧本。

所以它更接近：

> 当前主要阶段。

而不是严格状态锁。

---

# 13. Source Document

不要长期把整本小说直接放：

```text
Episode.sourceText
```

后续建议引入：

```text
SourceDocument
```

例如：

```text
SourceDocument
{
    id
    projectId

    type

    title
    content

    sourceFileAssetId

    metadata
}
```

Type：

```text
NOVEL

SCRIPT

OUTLINE

REFERENCE

OTHER
```

Alpha 可以先做基础版本。

---

# 14. Scene Aggregate

Scene 定义：

> 一个具有相对连续时间、空间和叙事目的的剧情单元。

关系：

```text
Episode
1
│
└────── *
       Scene
```

---

# 15. Scene 数据结构

```text
Scene
{
    id
    projectId
    episodeId

    sceneNumber
    orderIndex

    title
    description

    narrativePurpose

    locationId

    timeOfDay
    weather

    estimatedDuration

    status

    continuityStateId

    createdAt
    updatedAt
}
```

---

# 16. SceneStatus

```text
DRAFT

PLANNED

READY

GENERATING

PARTIAL

COMPLETED

LOCKED
```

其中：

```text
LOCKED
```

表示用户已经确认该 Scene，AI 不应随意改写结构。

---

# 17. Scene 与 Location

Scene 可以只有一个主 Location：

```text
Scene.locationId
```

但是现实中可能存在：

```text
篮球馆
+
观众席
+
球员通道
```

因此长期建议：

```text
SceneLocation
```

建立多对多关系。

Alpha 初期可以先使用主 Location。

---

# 18. Shot Aggregate

Shot 是 AI 漫剧 Studio 的核心 Aggregate。

定义：

> 一个具有明确画面构图、持续时间和生成目标的最小镜头单元。

关系：

```text
Scene
1
│
└────── *
       Shot
```

---

# 19. Shot 基础结构

```text
Shot
{
    id

    projectId
    episodeId
    sceneId

    shotNumber
    orderIndex

    title
    description

    narrativeBeat

    duration

    shotType
    cameraAngle
    cameraMovement

    visualSpecId

    status

    activeImageAssetId
    activeVideoAssetId

    continuityStateId

    createdAt
    updatedAt
}
```

---

# 20. ShotStatus

推荐：

```text
DRAFT

READY

GENERATING

GENERATED

REVIEW

APPROVED

STALE

FAILED

LOCKED
```

一个典型流程：

```text
DRAFT
 ↓
READY
 ↓
GENERATING
 ↓
GENERATED
 ↓
REVIEW
 ↓
APPROVED
```

依赖改变：

```text
APPROVED
   ↓
STALE
```

重新生成：

```text
STALE
 ↓
GENERATING
```

---

# 21. ShotVisualSpec

自然语言 Prompt 不能成为 Shot 唯一描述。

引入结构化：

```text
ShotVisualSpec
```

---

# 22. ShotVisualSpec 数据结构

```text
ShotVisualSpec
{
    id
    shotId

    shotType

    cameraAngle
    cameraMovement

    composition

    subjectIds[]

    locationId

    lighting

    mood

    action

    facialExpression

    environment

    styleInstructions

    negativeInstructions

    metadata
}
```

---

# 23. ShotType

建议基础 Enum：

```text
EXTREME_WIDE_SHOT

WIDE_SHOT

FULL_SHOT

MEDIUM_FULL_SHOT

MEDIUM_SHOT

MEDIUM_CLOSE_UP

CLOSE_UP

EXTREME_CLOSE_UP

OVER_THE_SHOULDER

POV

INSERT
```

UI 层可以显示中文：

```text
全景
中景
近景
特写
```

领域层统一使用稳定代码。

---

# 24. CameraAngle

```text
EYE_LEVEL

HIGH_ANGLE

LOW_ANGLE

BIRD_EYE

WORM_EYE

DUTCH_ANGLE

OVERHEAD
```

---

# 25. CameraMovement

```text
STATIC

PAN_LEFT

PAN_RIGHT

TILT_UP

TILT_DOWN

PUSH_IN

PULL_OUT

DOLLY

TRACKING

ORBIT

HANDHELD

CRANE

ZOOM_IN

ZOOM_OUT
```

允许：

```text
CUSTOM
```

并保留自然语言参数。

---

# 26. Shot Character Binding

Shot 不应该只通过 Prompt 写人物名字。

建立：

```text
ShotCharacter
```

关系：

```text
Shot
*
│
└────── *
       Character
```

中间实体：

```text
ShotCharacter
{
    shotId
    characterId

    role

    characterVersionId

    costumeId

    position

    pose

    expression

    action

    referenceAssetIds[]
}
```

---

# 27. ShotCharacterRole

```text
PRIMARY

SECONDARY

BACKGROUND

CROWD
```

这能帮助 Prompt Agent 判断：

> 哪个角色必须强一致性，哪个角色可以弱化。

---

# 28. Character Aggregate

Character 定义：

> 项目中可持续复用、需要身份一致性的角色实体。

---

# 29. Character 数据结构

```text
Character
{
    id
    projectId

    name
    alias

    roleType

    description

    gender
    age

    nationality

    height
    bodyDescription

    personality

    activeVersionId
    masterVersionId

    voiceProfileId

    status

    createdAt
    updatedAt
}
```

---

# 30. CharacterRoleType

```text
PROTAGONIST

DEUTERAGONIST

SUPPORTING

ANTAGONIST

EXTRA
```

---

# 31. CharacterVersion

Character 的视觉定义必须版本化。

```text
CharacterVersion
{
    id
    characterId

    versionNumber

    name

    appearanceSpec

    faceSpec

    bodySpec

    hairstyleSpec

    defaultCostumeId

    referenceAssetIds[]

    promptTemplate

    isMaster

    createdAt
}
```

---

# 32. Character Master 语义

Character：

```text
masterVersionId
```

表示：

> 当前被项目正式认可的标准角色形象。

新 Shot 默认绑定：

```text
Character.masterVersionId
```

但已生成 Shot 不自动更新。

例如：

```text
沈亦

MASTER v4
```

Shot 21 创建时绑定：

```text
v4
```

后来：

```text
MASTER → v5
```

Shot 21 仍保存：

```text
characterVersionId = v4
```

系统只将其标记为：

```text
STALE
```

而不是偷偷替换。

---

# 33. Costume

服装不要直接写在 Character Prompt 里。

建立：

```text
Costume
```

数据：

```text
Costume
{
    id
    projectId
    characterId

    name
    description

    promptSpec

    referenceAssetIds[]

    activeVersionId
}
```

例如：

```text
沈亦
├── 私服
├── 白色7号球衣
├── 黑色训练服
└── 国家队球衣
```

---

# 34. Location Aggregate

Location 定义：

> 可以跨 Scene / Shot 复用并需要视觉一致性的空间。

例如：

```text
高中篮球馆
沈亦家
更衣室
纽约街道
```

---

# 35. Location 数据结构

```text
Location
{
    id
    projectId

    name
    description

    locationType

    environmentSpec

    activeVersionId
    masterVersionId

    status
}
```

---

# 36. LocationVersion

```text
LocationVersion
{
    id
    locationId

    versionNumber

    visualSpec

    referenceAssetIds[]

    promptTemplate

    isMaster

    createdAt
}
```

Character 和 Location 采用类似 MASTER 机制。

---

# 37. Prop Aggregate

Prop 表示：

> 会影响剧情、角色动作或者连续性的物件。

例如：

```text
篮球
手机
文件
武器
汽车
奖杯
```

---

# 38. Prop 数据结构

```text
Prop
{
    id
    projectId

    name
    description

    propType

    referenceAssetIds[]

    activeVersionId
}
```

不是所有背景小物件都要创建 Prop。

只对：

> 有连续性要求的对象。

---

# 39. Asset Aggregate

Asset 是项目中所有媒体文件的统一抽象。

这是 Alpha 的关键领域对象。

---

# 40. Asset 数据结构

```text
Asset
{
    id
    projectId

    assetType

    name

    sourceType

    storageProvider
    storagePath

    mimeType

    fileSize

    width
    height
    duration

    checksum

    generationId

    parentAssetId

    versionGroupId
    versionNumber

    status

    metadata

    createdAt
    updatedAt
}
```

---

# 41. AssetType

推荐：

```text
SOURCE_DOCUMENT

CHARACTER_REFERENCE

CHARACTER_CONCEPT

LOCATION_REFERENCE

LOCATION_CONCEPT

PROP_REFERENCE

STORYBOARD

SHOT_IMAGE

SHOT_VIDEO

VOICE

BGM

SFX

SUBTITLE

FINAL_VIDEO

THUMBNAIL

OTHER
```

---

# 42. AssetSourceType

```text
GENERATED

IMPORTED

EDITED

DERIVED

CAPTURED
```

---

# 43. AssetStatus

```text
PROCESSING

READY

STALE

MISSING

FAILED

ARCHIVED
```

---

# 44. Asset Parent

通过：

```text
parentAssetId
```

记录简单派生关系。

例如：

```text
shot.png
  ↓
upscaled.png
```

但复杂 AI 输入输出关系不能依赖 Parent。

复杂 Provenance 统一由：

```text
Generation
```

负责。

---

# 45. Prompt Domain

不要只在 Generation 表中保存一段字符串。

后续 Prompt 需要：

* 编辑
* 版本
* 恢复
* AI 优化
* 比较
* 不同 Provider 转译

所以引入：

```text
Prompt
```

---

# 46. Prompt 数据结构

```text
Prompt
{
    id
    projectId

    targetType
    targetId

    promptType

    activeVersionId

    createdAt
}
```

PromptVersion：

```text
PromptVersion
{
    id
    promptId

    versionNumber

    positivePrompt
    negativePrompt

    structuredSpec

    provider
    model

    generatedBy

    createdAt
}
```

---

# 47. PromptType

```text
CHARACTER

LOCATION

STORYBOARD

SHOT_IMAGE

SHOT_VIDEO

VOICE

MUSIC

DIRECTOR_INSTRUCTION

CUSTOM
```

---

# 48. Structured Prompt First

推荐数据流：

```text
Domain Data
     ↓
Structured Specification
     ↓
Prompt Builder
     ↓
Provider Prompt
```

而不是：

```text
Domain Data
     ↓
String Prompt
```

例如：

```json
{
  "character": "shenyi",
  "expression": "restrained",
  "shotType": "close_up",
  "lighting": "cool",
  "cameraMovement": "slow_push_in"
}
```

然后不同 Provider：

```text
MiniMax Prompt Builder
Seedance Prompt Builder
Image Prompt Builder
```

分别生成。

---

# 49. Generation Aggregate

Generation 定义：

> 一次明确的 AI / 渲染 / Workflow 执行记录。

这是所有生成行为的审计边界。

---

# 50. Generation 数据结构

```text
Generation
{
    id
    projectId

    generationType

    targetType
    targetId

    provider
    model

    workflowTemplateId
    workflowVersion

    promptVersionId

    parameters

    status

    attempt

    parentGenerationId

    startedAt
    finishedAt

    errorCode
    errorMessage

    createdAt
}
```

---

# 51. GenerationTarget

targetType：

```text
PROJECT

EPISODE

SCENE

SHOT

CHARACTER

LOCATION

ASSET

TIMELINE
```

例如：

```text
targetType = SHOT
targetId = shot_031
generationType = SHOT_VIDEO
```

---

# 52. GenerationType

建议第一版：

```text
STORY_ANALYSIS

SCRIPT_GENERATION

SCENE_PLANNING

SHOT_PLANNING

PROMPT_GENERATION

CHARACTER_IMAGE

LOCATION_IMAGE

STORYBOARD_IMAGE

SHOT_IMAGE

SHOT_VIDEO

VOICE

MUSIC

SUBTITLE

VIDEO_RENDER
```

---

# 53. GenerationInput

Generation 输入不能只塞 JSON。

建议关系表：

```text
GenerationInput
{
    generationId

    inputType

    referenceType
    referenceId

    role
}
```

例如：

```text
Generation #1001

CHARACTER_REFERENCE → asset_201
LOCATION_REFERENCE  → asset_350
STORYBOARD           → asset_501
PROMPT               → prompt_version_72
```

---

# 54. GenerationOutput

同样：

```text
GenerationOutput
{
    generationId
    assetId

    role
}
```

例如：

```text
Generation #1001
 ├── preview.mp4
 └── final.mp4
```

---

# 55. GenerationStatus

```text
CREATED

QUEUED

RUNNING

PAUSED

SUCCEEDED

FAILED

CANCELLED

RETRYING
```

---

# 56. Generation 不可变原则

一旦 Generation 开始运行，其：

```text
provider
model
promptVersion
parameters
inputs
```

原则上不可修改。

如果用户改 Prompt：

创建：

```text
PromptVersion v4
```

重新生成：

```text
Generation #102
```

而不是修改：

```text
Generation #101
```

这样保证可追溯性。

---

# 57. Generation Retry

Retry 可以有两种方式。

## 方式 A：同 Generation attempt

```text
generationId = 1001
attempt = 2
```

## 方式 B：新 Generation

```text
1001
 ↓
1002 parentGenerationId=1001
```

推荐采用：

> **方式 B。**

因为一次模型请求就是一次独立历史事件。

因此：

```text
Generation
```

应尽量保持 immutable。

---

# 58. Version 体系

Version 不建议设计成一个万能 Version 表承载全部业务数据。

应该采用：

> 各领域对象自己拥有 Version Entity。

例如：

```text
CharacterVersion

LocationVersion

PromptVersion

WorkflowVersion
```

Asset 使用：

```text
versionGroupId + versionNumber
```

Shot 本身暂不需要完整快照版本。

---

# 59. 为什么不做 UniversalVersion

类似：

```text
Version
{
    entityType
    entityId
    snapshotJson
}
```

看起来灵活，

但很快会导致：

* 数据约束弱
* JSON 难查询
* 类型混乱
* 迁移困难
* 业务逻辑难维护

因此只把：

```text
Audit / Snapshot
```

作为辅助能力。

核心仍然使用强类型模型。

---

# 60. Master 与 Active

统一定义：

## MASTER

表示：

> 官方标准版本。

主要用于：

```text
Character
Location
Style
```

## ACTIVE

表示：

> 当前项目/镜头实际使用版本。

主要用于：

```text
Shot Image
Shot Video
Prompt
Timeline Clip
```

MASTER 不等于 ACTIVE。

例如：

```text
Character MASTER = v5

Shot 20 Active Character = v4
```

这是合法状态。

---

# 61. Stale 机制

Stale 是 Alpha 必须正式建模的概念。

定义：

> 当前产物仍然可用，但其依赖已经发生变化。

例如：

```text
Character v4
 ↓
Shot Image v2
 ↓
Shot Video v1
```

Character MASTER 更新成：

```text
v5
```

则：

```text
Shot Image v2 = STALE
Shot Video v1 = STALE
```

但仍然允许继续使用。

---

# 62. Dependency Domain

建立：

```text
GenerationDependency
```

或者更通用：

```text
ResourceDependency
```

结构：

```text
ResourceDependency
{
    sourceType
    sourceId

    targetType
    targetId

    dependencyType
}
```

例如：

```text
CharacterVersion v4
       ↓
Shot Image Asset 105
```

---

# 63. DependencyType

```text
HARD

SOFT

REFERENCE
```

含义：

### HARD

变化后目标原则上必须重新生成。

### SOFT

变化后目标应标记 STALE。

### REFERENCE

只是信息引用。

Alpha 阶段大多数生成依赖可以先使用：

```text
SOFT
```

避免自动级联重生成。

---

# 64. Continuity Domain

Continuity 不能完全依赖 Agent 临时理解。

必须存在结构化状态。

定义：

```text
ContinuityState
```

---

# 65. ContinuityState

```text
ContinuityState
{
    id
    projectId

    scopeType
    scopeId

    characterStates

    propStates

    environmentState

    temporalState

    metadata

    createdAt
    updatedAt
}
```

---

# 66. Character Continuity State

例如：

```json
{
  "characterId": "shenyi",
  "characterVersionId": "v4",
  "costumeId": "uniform_white_7",
  "position": "left_wing",
  "orientation": "toward_basket",
  "emotion": "focused",
  "physicalState": {
    "sweating": true,
    "injured": false
  }
}
```

---

# 67. Prop Continuity State

```json
{
  "propId": "basketball_01",
  "holderCharacterId": "shenyi",
  "position": "right_hand",
  "state": "normal"
}
```

---

# 68. Environment Continuity State

```json
{
  "locationId": "gym_01",
  "timeOfDay": "night",
  "lighting": "cool_indoor",
  "weather": null,
  "crowdState": "full"
}
```

---

# 69. Continuity Scope

scopeType：

```text
SCENE

SHOT
```

Scene 保存基础状态：

```text
Scene Continuity
```

Shot 保存差异：

```text
Shot Continuity Delta
```

推荐最终实现：

```text
Scene Base State
        +
Previous Shot State
        +
Current Shot Delta
        =
Current Shot State
```

减少重复数据。

---

# 70. Timeline Aggregate

Timeline 表示：

> Episode 最终媒体编排。

关系：

```text
Episode
1
│
└────── 1
       Timeline
```

---

# 71. Timeline 数据结构

```text
Timeline
{
    id
    projectId
    episodeId

    duration

    resolution
    fps

    status

    createdAt
    updatedAt
}
```

---

# 72. TimelineTrack

```text
TimelineTrack
{
    id
    timelineId

    trackType

    orderIndex

    locked
    muted
}
```

TrackType：

```text
VIDEO

VOICE

MUSIC

SFX

SUBTITLE
```

---

# 73. TimelineClip

```text
TimelineClip
{
    id
    timelineId
    trackId

    assetId

    shotId

    startTime
    endTime

    sourceIn
    sourceOut

    orderIndex

    enabled
}
```

Shot 与 TimelineClip 不做一对一假设。

未来一个 Shot 可以：

```text
多个 Clip
```

或者一个 Clip 跨镜头。

---

# 74. Job Aggregate

Generation 是一次执行。

Job 是：

> 用户层面的一批业务任务。

例如：

```text
Generate Scene 03
```

这可能产生 20 个 Generation。

---

# 75. Job 数据结构

```text
Job
{
    id
    projectId

    jobType

    targetType
    targetId

    status

    totalTasks
    completedTasks
    failedTasks

    progress

    createdAt
    startedAt
    finishedAt
}
```

---

# 76. JobTask

```text
JobTask
{
    id
    jobId

    taskType

    targetType
    targetId

    status

    priority

    dependencyTaskIds[]

    generationId

    retryCount
}
```

---

# 77. Job 和 Generation 区别

例如用户点击：

```text
Generate Scene
```

产生：

```text
Job: Generate Scene 01
│
├── Task: Shot01 Image
│      └── Generation 100
│
├── Task: Shot01 Video
│      └── Generation 101
│
├── Task: Shot02 Image
│      └── Generation 102
│
└── Task: Shot02 Video
       └── Generation 103
```

所以：

```text
Job = 业务批处理

Task = 调度单元

Generation = AI执行历史
```

三者必须分开。

---

# 78. WorkflowTemplate Aggregate

业务层不要直接保存：

```text
ComfyUI workflow.json
```

应该抽象：

```text
WorkflowTemplate
```

---

# 79. WorkflowTemplate

```text
WorkflowTemplate
{
    id

    projectId nullable

    name

    workflowType

    providerType

    activeVersionId

    builtin

    createdAt
}
```

workflowType：

```text
CHARACTER_IMAGE

LOCATION_IMAGE

SHOT_IMAGE

SHOT_VIDEO

VOICE

CUSTOM
```

---

# 80. WorkflowVersion

```text
WorkflowVersion
{
    id
    workflowTemplateId

    versionNumber

    schema

    providerConfig

    inputMapping

    outputMapping

    rawWorkflowAssetId

    createdAt
}
```

对于 ComfyUI：

```text
rawWorkflowAssetId
```

指向 JSON Asset。

---

# 81. Provider Config 不进入核心业务

例如：

```text
ComfyUI URL
API Key
Model Path
GPU Index
```

不要放在：

```text
Project
Generation
```

业务 Entity 中。

应该属于：

```text
ProviderConfiguration
```

基础设施配置。

Generation 只记录：

```text
provider
model
```

用于审计。

---

# 82. Domain Event

Alpha 阶段建议开始引入领域事件。

不一定需要复杂 Event Sourcing。

至少定义事件语义。

例如：

```text
ProjectCreated

EpisodeCreated

ShotUpdated

CharacterMasterChanged

AssetGenerated

AssetMarkedStale

GenerationStarted

GenerationSucceeded

GenerationFailed

JobCompleted
```

---

# 83. CharacterMasterChanged

例如：

```text
CharacterMasterChanged
{
    characterId
    oldVersionId
    newVersionId
}
```

事件消费者：

```text
DependencyService
```

查询依赖：

```text
Character v4
```

的资源，

然后标记：

```text
STALE
```

---

# 84. GenerationSucceeded

事件：

```text
GenerationSucceeded
{
    generationId
    outputAssetIds[]
}
```

消费者可以执行：

```text
AssetService

JobService

ShotService

TimelineService
```

例如 Shot Image Generation 成功：

```text
Shot.activeImageAssetId
```

是否切换由策略决定。

---

# 85. 自动切换 Active 策略

建议：

第一次成功生成：

```text
无 Active
```

则：

```text
自动设为 Active
```

已有 Active：

```text
v2
```

重新生成：

```text
v3
```

默认：

```text
不自动覆盖 Active
```

UI 显示：

```text
New version available
```

用户预览后决定：

```text
Use Version
```

这样更加安全。

Alpha 如果追求效率，也可以提供项目设置：

```text
autoActivateNewGeneration = true/false
```

---

# 86. Archive 与 Delete

对以下核心对象：

```text
Project
Episode
Scene
Shot
Character
Location
Asset
```

优先：

```text
Archive
```

而不是物理删除。

尤其 Asset。

因为 Generation 历史可能引用。

---

# 87. Referential Integrity 原则

一旦：

```text
GenerationInput
```

引用某 Asset，

该 Asset 不允许直接永久删除。

只能：

```text
ARCHIVED
```

除非执行明确：

```text
Hard Cleanup
```

并经过完整依赖检查。

---

# 88. ID 规范

建议所有业务 ID 使用：

```text
UUID / ULID
```

推荐：

```text
ULID
```

原因：

* 全局唯一
* 可排序
* 比 UUID 更适合日志和数据库索引

例如：

```text
01K2M8TH38...
```

如果当前后端已经统一 UUID，也不需要为了 ULID 重构。

**一致性比形式更重要。**

---

# 89. OrderIndex

Episode、Scene、Shot 一律不要依赖：

```text
sceneNumber
shotNumber
```

排序。

必须使用：

```text
orderIndex
```

展示编号可以重新计算：

```text
Shot 001
Shot 002
```

但对象 ID 永远不变。

例如移动：

```text
Shot 18
```

到前面，

不应该改变其：

```text
shotId
```

---

# 90. JSON 字段使用原则

可以使用 JSON：

```text
metadata

parameters

structuredSpec

continuity details
```

但核心可查询字段：

```text
status
projectId
episodeId
sceneId
shotId
provider
model
assetType
```

必须使用明确数据库列。

禁止把整个领域对象全部塞 JSON。

---

# 91. 前端 State 对应关系

前端不要维护一套和后端不同的概念。

推荐：

```text
projectStore

episodeStore

sceneStore

shotStore

assetStore

generationStore

jobStore

timelineStore
```

但正常情况下不要：

```text
projectStore.project.episodes[0].scenes[0].shots...
```

构建巨大嵌套对象。

推荐 Normalize：

```text
projectsById

episodesById

scenesById

shotsById
```

---

# 92. Inspector Selection Model

前端 Studio 推荐统一：

```text
Selection
{
    type
    id
}
```

例如：

```text
SHOT / shot_31

CHARACTER / character_shenyi

ASSET / asset_100
```

Inspector 根据：

```text
Selection.type
```

加载对应面板。

避免每种对象单独维护选中状态。

---

# 93. Agent 与 Domain 的边界

Agent 不能直接：

```text
INSERT database

UPDATE shot

DELETE asset
```

正确流程：

```text
Agent
 ↓
Structured Proposal
 ↓
Application Service
 ↓
Validation
 ↓
Domain
 ↓
Repository
```

例如 Script Agent：

```text
建议创建 Scene 1~8
```

不是直接写数据库。

---

# 94. Agent Proposal

建议后期统一：

```text
AgentProposal
```

例如：

```json
{
  "type": "SHOT_PLAN",
  "targetId": "scene_01",
  "operations": [
    {
      "action": "CREATE_SHOT",
      "data": {}
    }
  ]
}
```

用户可以：

```text
Apply

Edit

Reject
```

MVP/Alpha 自动模式可以默认 Apply。

---

# 95. Domain Service

需要跨 Aggregate 的业务逻辑放 Domain Service。

建议：

```text
ProjectLifecycleService

ShotPlanningService

AssetVersionService

DependencyService

ContinuityService

GenerationPlanningService
```

---

# 96. Application Service

建议后端 Application Layer：

```text
ProjectApplicationService

EpisodeApplicationService

SceneApplicationService

ShotApplicationService

CharacterApplicationService

AssetApplicationService

GenerationApplicationService

JobApplicationService

TimelineApplicationService
```

负责：

```text
Authorization

Transaction

DTO Mapping

Domain orchestration
```

---

# 97. Repository

建议：

```text
ProjectRepository

EpisodeRepository

SceneRepository

ShotRepository

CharacterRepository

LocationRepository

AssetRepository

GenerationRepository

JobRepository

TimelineRepository
```

Repository 只解决：

> Aggregate 持久化。

不要塞业务逻辑。

---

# 98. 推荐模块边界

后端可以按业务模块组织：

```text
studio
│
├── project
├── story
├── character
├── location
├── shot
├── asset
├── generation
├── workflow
├── job
├── continuity
├── timeline
└── provider
```

如果使用 Java：

```text
com.xxx.studio.project

com.xxx.studio.shot

com.xxx.studio.asset
```

比：

```text
controller
service
repository
entity
```

全局分层更加适合长期大型项目。

---

# 99. 推荐 Package 内部结构

例如：

```text
shot
├── api
├── application
├── domain
│   ├── model
│   ├── service
│   ├── event
│   └── repository
└── infrastructure
```

这样未来 Agent、ComfyUI、数据库都不会侵入领域核心。

---

# 100. 第一阶段最低领域模型

如果现在马上进入编码，

不需要一次实现本设计全部内容。

Alpha 第一轮只落地：

```text
Project

ProjectSetting

Episode

Scene

Shot

ShotVisualSpec

Character

CharacterVersion

Location

Asset

Prompt
PromptVersion

Generation
GenerationInput
GenerationOutput
```

第二轮：

```text
Job
JobTask

WorkflowTemplate
WorkflowVersion

ResourceDependency
```

第三轮：

```text
ContinuityState

Timeline
TimelineTrack
TimelineClip

Costume
Prop
```

---

# 101. 第一轮 Entity 关系图

```text
Project
│
├──── Episode
│       │
│       └──── Scene
│               │
│               └──── Shot
│                       │
│                       └──── ShotVisualSpec
│
├──── Character
│       │
│       └──── CharacterVersion
│
├──── Location
│
├──── Asset
│
├──── Prompt
│       │
│       └──── PromptVersion
│
└──── Generation
        │
        ├──── GenerationInput
        │
        └──── GenerationOutput
```

---

# 102. 最核心的数据链

Studio 整个 Alpha 最终围绕以下链路运转：

```text
Novel
 ↓
Episode
 ↓
Scene
 ↓
Shot
 ↓
ShotVisualSpec
 ↓
PromptVersion
 ↓
Generation
 ↓
Asset
 ↓
Active Version
 ↓
Timeline
```

角色和场景资产从侧面注入：

```text
Character MASTER ─────┐
                      │
Location MASTER ──────┼──→ Generation
                      │
ShotVisualSpec ───────┤
                      │
PromptVersion ────────┘
```

---

# 103. 一个完整示例

项目：

```text
Project
《最后一种打法》
```

↓

```text
Episode 01
```

↓

```text
Scene 05

高中篮球馆
夜晚
```

↓

```text
Shot 023

沈亦停下训练，看向教练。
```

结构化：

```text
ShotVisualSpec

Medium Close Up

Eye Level

Slow Push In

沈亦

Focused / Restrained

Basketball Gym
```

↓

角色：

```text
Character
沈亦

MASTER = v4
```

↓

场景：

```text
Location
高中篮球馆

MASTER = v2
```

↓

Prompt：

```text
PromptVersion v3
```

↓

执行：

```text
Generation #1021

SHOT_IMAGE
MiniMax / Image Model
```

↓

输出：

```text
Asset

shot_023_image_v4.png
```

↓

执行：

```text
Generation #1022

SHOT_VIDEO
```

↓

输出：

```text
Asset

shot_023_video_v3.mp4
```

↓

用户：

```text
Set Active
```

↓

Timeline：

```text
Clip
→ shot_023_video_v3
```

这一条链必须做到完全可追踪。

---

# 104. 核心不可违反约束

后续开发需要长期遵守以下规则。

## 规则 1

```text
Shot != Prompt
```

Prompt 只是 Shot 的一个生成表示。

---

## 规则 2

```text
Asset != File
```

File 是存储对象。

Asset 是领域对象。

---

## 规则 3

```text
Job != Generation
```

Job 是批任务。

Generation 是一次执行。

---

## 规则 4

```text
Character != Character Image
```

Character 是身份。

Character Image 是 Asset。

---

## 规则 5

```text
Workflow != ComfyUI JSON
```

ComfyUI JSON 是某个 WorkflowVersion 的 Provider 实现。

---

## 规则 6

```text
MASTER != Latest Version
```

最新版本不一定最好。

MASTER 必须显式选择。

---

## 规则 7

AI 不直接拥有项目状态。

```text
Database / Project State
```

永远是 Source of Truth。

---

# 105. 本文档的落地结果

完成本领域模型后，后续设计已经可以正式进入数据库阶段。

下一层需要把这些对象转换为：

```text
Table

Primary Key

Foreign Key

Index

Unique Constraint

JSON Column

Cascade Rule

Archive Strategy

Migration Strategy
```

因此下一份文档应正式进入：

# 《AI 漫剧 Studio 数据库 Schema 与数据关系设计 v0.1》

该文档需要重点解决：

```text
Project / Episode / Scene / Shot 表结构

Character / Version 表结构

Asset 与文件存储结构

Generation 输入输出关系

Prompt Version

Job / Task

Workflow Version

Continuity

Timeline

索引

外键

软删除

JSON 字段

Flyway Migration
```

并直接给出能够用于后端实现的数据库设计。
