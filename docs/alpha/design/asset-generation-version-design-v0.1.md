# AI 漫剧 Studio Asset / Generation / Version 系统详细设计 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**上游文档：**

* 《AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1》
* 《AI 漫剧 Studio 核心领域模型详细设计 v0.1》
* 《AI 漫剧 Studio 数据库 Schema 与数据关系设计 v0.1》
* 《AI 漫剧 Studio Alpha Backend API & Service 详细设计 v0.1》

**目标：**

建立 AI 漫剧 Studio 的统一生成基础设施，使角色、场景、分镜图、镜头图、视频、语音、音乐、字幕等所有生产结果都能够：

```text
生成
→ 注册
→ 追溯
→ 版本化
→ 预览
→ 选择
→ 重生成
→ 标记过期
→ 恢复
→ 复用
```

并确保系统不会退化为：

> “调用模型 → 得到文件 → 保存路径”。

---

# 1. 系统定位

Asset / Generation / Version 是 Studio 的生产基础设施。

三者分别解决三个问题：

```text
Asset
=
生成了什么？
```

```text
Generation
=
它是怎么生成出来的？
```

```text
Version
=
多个结果之间是什么关系，
当前应该使用哪个？
```

三者关系：

```text
Generation
     │
     │ produces
     ▼
   Asset
     │
     │ belongs to
     ▼
Version Group
```

同时：

```text
Generation
     ▲
     │ inputs
     │
   Asset
```

最终形成完整生成图：

```text
Asset
  ↓
Generation
  ↓
Asset
  ↓
Generation
  ↓
Asset
```

---

# 2. 为什么这一系统必须独立

AI 漫剧生产与传统文件编辑最大的区别是：

一个最终视频可能经历：

```text
角色参考图
   ↓
镜头 Prompt
   ↓
镜头图片
   ↓
放大图片
   ↓
视频
   ↓
插帧
   ↓
剪辑
   ↓
最终视频
```

每个步骤都可能：

```text
失败

重新生成

修改参数

切换模型

更换参考图

生成多个版本
```

如果系统只记录：

```text
shot_23.mp4
```

很快就无法回答：

```text
这个视频用了哪个角色版本？

为什么这一版比上一版好？

这个视频对应哪张图？

哪一个 Prompt 生成的？

用了哪个 ComfyUI Workflow？

如果角色 MASTER 变了，
哪些镜头需要更新？
```

所以：

> Asset、Generation、Version 必须成为一级领域能力。

---

# 3. 核心设计原则

本系统遵守以下原则。

## 原则 1

```text
Asset != File
```

Asset 是业务对象。

File 是存储实现。

---

## 原则 2

```text
Generation != Asset
```

Generation 是一次执行。

Asset 是执行结果。

---

## 原则 3

```text
Version != Generation
```

一次 Generation 可以：

```text
产生多个 Asset
```

而一个 Version Group 可以包含：

```text
多个不同 Generation 的结果
```

---

## 原则 4

```text
Latest != Active
```

最新生成结果不能自动认为是当前使用版本。

---

## 原则 5

```text
Latest != Master
```

最新角色参考图也不能自动成为 MASTER。

---

## 原则 6

历史 Generation 尽量：

```text
Immutable
```

---

## 原则 7

历史 Asset 默认：

```text
不覆盖
```

---

## 原则 8

依赖改变：

```text
Mark STALE
```

而不是：

```text
Auto Regenerate
```

---

# 4. 三个核心对象

核心模型：

```text
Asset

Generation

VersionGroup
```

辅助模型：

```text
GenerationInput

GenerationOutput

ResourceDependency

AssetUsage

GenerationCache

AssetPreview

AssetIntegrity
```

---

# 5. Asset 定义

Asset 定义：

> Studio 中一个具有业务语义、可以被引用、预览、生成、编辑、复用或进入 Timeline 的媒体资源。

例如：

```text
角色正面参考图

篮球馆场景图

Shot 023 Image

Shot 023 Video

对白语音

背景音乐

字幕

最终视频
```

全部是 Asset。

---

# 6. 什么不是 Asset

以下不一定是 Asset：

```text
Shot

Scene

Character

Prompt

Generation

Job
```

因为这些是：

```text
业务结构 / 执行记录
```

而不是媒体资源。

---

# 7. AssetType

Alpha 第一版：

```text
SOURCE_DOCUMENT

CHARACTER_CONCEPT

CHARACTER_REFERENCE

LOCATION_CONCEPT

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

THUMBNAIL

WORKFLOW_FILE

OTHER
```

---

# 8. AssetSourceType

记录 Asset 来源：

```text
GENERATED

IMPORTED

EDITED

DERIVED

CAPTURED
```

例如：

用户拖入一张人物图：

```text
IMPORTED
```

AI 生成：

```text
GENERATED
```

Photoshop 修改后重新导入：

```text
EDITED
```

Upscale：

```text
DERIVED
```

---

# 9. AssetStatus

建议：

```text
PROCESSING

READY

STALE

MISSING

CORRUPTED

FAILED

ARCHIVED
```

含义：

### PROCESSING

文件尚未完整注册。

### READY

可正常使用。

### STALE

依赖已变化，但仍可以继续使用。

### MISSING

数据库记录存在，但文件不存在。

### CORRUPTED

文件存在但校验失败。

### FAILED

生成出来的资源无法使用。

### ARCHIVED

不在正常 UI 中显示，但保留历史。

---

# 10. Asset 不负责生成状态

不要：

```text
Asset.status = RUNNING
```

运行状态属于：

```text
Generation
```

Asset 只有在文件开始进入注册阶段后才存在。

正常：

```text
Generation RUNNING
```

此时：

```text
还没有 Asset
```

成功后：

```text
Generation
 ↓
Asset
```

---

# 11. Generation 定义

Generation 定义：

> 一次确定输入、模型、参数、Workflow 和输出目标的执行事件。

例如：

```text
2026-08-15 17:20

用：
MiniMax Video Model

输入：
shot_023_image_v3

Prompt：
prompt_video_v2

Duration：
5s

Workflow：
shot_video_standard_v4

结果：
shot_023_video_v5
```

这就是一个 Generation。

---

# 12. GenerationType

Alpha：

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

IMAGE_UPSCALE

VIDEO_UPSCALE

VIDEO_INTERPOLATION

VIDEO_RENDER
```

---

# 13. GenerationStatus

推荐完整状态：

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

Job Task 可以另外存在：

```text
RETRYING
```

Generation 本身不需要：

```text
RETRYING
```

因为 Retry 创建新的 Generation。

---

# 14. Generation 生命周期

正常：

```text
CREATED
   ↓
QUEUED
   ↓
RUNNING
   ↓
SUCCEEDED
```

失败：

```text
RUNNING
 ↓
FAILED
```

取消：

```text
RUNNING
 ↓
CANCEL_REQUESTED
 ↓
CANCELLED
```

异常退出：

```text
RUNNING
 ↓
INTERRUPTED
```

---

# 15. Generation Immutable

Generation 进入：

```text
RUNNING
```

后，以下属性冻结：

```text
generationType

target

provider

model

workflowVersion

promptVersion

parameters

inputs
```

之后不允许：

```text
修改 Prompt
换参考图
换模型
换 Workflow
```

如果需要：

创建新的：

```text
Generation
```

---

# 16. 为什么 Generation 必须 Immutable

如果允许：

```text
Generation #100
```

执行完成后再修改 Prompt，

那么：

```text
output asset
```

已经无法证明：

> 到底是哪个 Prompt 生成的。

所以：

```text
Execution History
```

必须保持可信。

---

# 17. Retry 设计

Generation：

```text
gen_100
FAILED
```

点击 Retry。

创建：

```text
gen_101

parent_generation_id = gen_100
```

而不是：

```text
gen_100
status = QUEUED
```

---

# 18. Retry Chain

例如：

```text
Generation 100
FAILED
   ↓
Generation 101
FAILED
   ↓
Generation 102
SUCCEEDED
```

UI 可以显示：

```text
Attempt 1 Failed
Attempt 2 Failed
Attempt 3 Success
```

---

# 19. Retry 可以修改参数吗

分两种。

## Retry

完全使用原参数：

```text
Retry Generation
```

## Regenerate

允许：

```text
换 Prompt
换参数
换模型
换参考资源
```

所以系统语义必须区分：

```text
Retry
```

和：

```text
Regenerate
```

---

# 20. Retry vs Regenerate

```text
Retry
=
执行失败，
原条件重新执行
```

```text
Regenerate
=
用户主动创建一个新的生成版本
```

两者不能混用。

---

# 21. GenerationTarget

每一次 Generation 都有业务目标。

例如：

```text
targetType = SHOT
targetId = shot_023
```

其他：

```text
CHARACTER

LOCATION

SCENE

EPISODE

TIMELINE

ASSET
```

这样可以查询：

```text
Shot 023 所有 Generation
```

---

# 22. Generation Input

GenerationInput 用于记录所有输入依赖。

例如 Shot Image：

```text
Character Reference

Location Reference

Storyboard

Prompt Version

Style Reference
```

结构：

```text
GenerationInput
{
    generationId

    inputType

    referenceType

    referenceId

    role

    orderIndex
}
```

---

# 23. GenerationInput ReferenceType

推荐：

```text
ASSET

PROMPT_VERSION

CHARACTER_VERSION

LOCATION_VERSION

SHOT

SCENE

WORKFLOW_VERSION

CONTINUITY_STATE
```

---

# 24. GenerationInput Role

对于同一种 ReferenceType，要区分业务意义。

例如 Asset：

```text
CHARACTER_REFERENCE

LOCATION_REFERENCE

FIRST_FRAME

LAST_FRAME

STYLE_REFERENCE

CONTROL_IMAGE

MASK

AUDIO_REFERENCE
```

因此：

```text
role
```

不能省。

---

# 25. Generation Output

所有媒体生成输出必须转换成：

```text
Asset
```

GenerationOutput：

```text
generationId
assetId
role
```

例如一个 Workflow 同时返回：

```text
preview.jpg

final.mp4
```

可以：

```text
PREVIEW

PRIMARY
```

---

# 26. Primary Output

建议 Generation 可以存在：

```text
primary_output_asset_id
```

作为查询优化。

但 Source of Truth 仍然是：

```text
generation_outputs
```

Alpha 也可以先不增加冗余字段。

---

# 27. Generation 与 Asset 关系

```text
Generation
    │
    ├── Inputs
    │     ├── Asset
    │     ├── PromptVersion
    │     └── CharacterVersion
    │
    └── Outputs
          ├── Asset
          └── Asset
```

Asset 可以反查：

```text
generationId
```

形成双向追踪。

---

# 28. Version Group

VersionGroup 定义：

> 一组在业务上具有相同用途、彼此可以替换的 Asset。

例如：

```text
Shot 023 Image
```

是一个 Version Group。

内部：

```text
v1
v2
v3
v4
```

---

# 29. VersionGroup 为什么独立

如果只在 Asset 中：

```text
version_group_id
```

也能工作。

但当需求增长后：

```text
Active Version
Preferred Version
Version Purpose
Owner Type
Owner ID
```

会越来越复杂。

因此建议 Alpha 第一轮可以继续使用：

```text
version_group_id
```

但领域层明确存在：

```text
AssetVersionGroup
```

概念。

Beta 可正式独立成表。

---

# 30. AssetVersionGroup

推荐领域模型：

```text
AssetVersionGroup
{
    id

    projectId

    ownerType
    ownerId

    purpose

    activeAssetId

    createdAt
}
```

---

# 31. Version Owner

例如：

```text
ownerType = SHOT
ownerId = shot_023

purpose = SHOT_IMAGE
```

表示：

```text
Shot 023 Image Versions
```

另一个：

```text
ownerType = SHOT
ownerId = shot_023

purpose = SHOT_VIDEO
```

是视频版本组。

---

# 32. Version Purpose

推荐：

```text
CHARACTER_REFERENCE

LOCATION_REFERENCE

STORYBOARD

SHOT_IMAGE

SHOT_VIDEO

VOICE

SUBTITLE

FINAL_RENDER
```

---

# 33. Active Version

Active 表示：

> 当前业务对象默认使用哪个 Asset。

例如：

```text
Shot 023
```

拥有：

```text
Image Versions

v1
v2
v3 ← ACTIVE
v4
```

用户生成了 v4，

不代表自动替换 v3。

---

# 34. 为什么新版本默认不 Active

因为 AI 新生成版本可能：

```text
更差

角色崩脸

动作错误

背景错误

视频闪烁
```

所以：

```text
Generation Success
```

只代表：

> 技术生成成功。

不代表：

> 创作结果通过。

---

# 35. Activate Asset

业务操作：

```text
ActivateAssetVersion
```

处理：

```text
Validate Asset

Validate Version Group

Set group.activeAssetId

Update Shot.activeImageAssetId
or
Shot.activeVideoAssetId

Publish AssetActivated
```

---

# 36. Active Asset 与 Timeline

非常重要：

```text
Shot.activeVideoAssetId
```

变化：

不强制更新：

```text
TimelineClip.assetId
```

原因：

Timeline 可能故意使用旧版本。

---

# 37. Replace In Timeline

额外业务操作：

```text
ReplaceAssetInTimeline
```

用户明确执行后：

```text
Timeline Clip
old asset
 ↓
new asset
```

---

# 38. MASTER

MASTER 与 Asset Active 不属于完全相同的概念。

MASTER 主要用于：

```text
CharacterVersion

LocationVersion
```

表示：

> 新生成内容默认应该参考的标准版本。

---

# 39. MASTER 不直接等于 Asset

例如：

```text
CharacterVersion v4
```

本身是 MASTER。

v4 内可能有：

```text
Front Reference

Side Reference

Full Body Reference
```

多个 Asset。

因此：

```text
Character.masterVersionId
```

比：

```text
Character.masterAssetId
```

更合理。

---

# 40. MASTER 切换

```text
v4 MASTER
 ↓
v5 MASTER
```

产生事件：

```text
CharacterMasterChanged
```

随后：

```text
DependencyService
```

查找依赖 v4 的资源。

---

# 41. STALE 定义

STALE 表示：

> Asset 当前仍然存在、仍然可用，但它依赖的上游标准资源已经发生变化。

这和：

```text
INVALID
```

不是一个概念。

---

# 42. STALE 示例

原：

```text
Character v4
      ↓
Shot Image v3
      ↓
Shot Video v2
```

现在：

```text
Character MASTER = v5
```

则：

```text
Shot Image v3
=
STALE
```

进一步：

```text
Shot Video v2
=
STALE
```

但仍然可以：

```text
Preview

Export

Use in Timeline
```

---

# 43. 为什么 STALE 不能自动重生成

一部 20 分钟漫剧可能有：

```text
300 Shots
```

角色 MASTER 一改，

如果系统自动重新生成：

```text
300 Image
+
300 Video
```

可能导致：

```text
巨额费用

数小时 GPU 时间

大量已确认镜头被改变
```

所以只能提示。

---

# 44. ResourceDependency

统一依赖模型：

```text
ResourceDependency
{
    source

    target

    dependencyType
}
```

例如：

```text
CharacterVersion v4
 ↓
Shot Image Asset v3
```

---

# 45. DependencyType

```text
HARD

SOFT

REFERENCE
```

### HARD

目标如果失去 source 就无法使用。

例如：

```text
File Dependency
```

### SOFT

source 改变后：

```text
target → STALE
```

### REFERENCE

只记录关系，不触发 Stale。

---

# 46. 推荐默认使用 SOFT

AI 创作领域多数情况：

```text
Character Version
Location Version
Prompt Version
```

变化后，

旧结果依然技术有效。

所以大多数生成依赖：

```text
SOFT
```

---

# 47. Dependency 建立时机

不要依赖后续扫描 Generation 推断。

Generation 成功创建 Asset 时：

立即：

```text
Generation Inputs
      ↓
ResourceDependency
      ↓
Output Asset
```

例如：

```text
CharacterVersion v4
      ↓
Image Asset v3
```

---

# 48. Dependency Propagation

如果：

```text
Image v3
```

变：

```text
STALE
```

并且：

```text
Image v3
 ↓
Video v2
```

则：

```text
Video v2
```

也应该：

```text
STALE
```

形成：

```text
Stale Propagation
```

---

# 49. StalePropagationService

核心接口：

```text
markStale(resource)

findDependents(resource)

propagate(resource)

clearStale(asset)
```

---

# 50. 防止无限传播

依赖图可能出现错误环：

```text
A → B → C → A
```

Propagation 必须：

```text
visitedSet
```

避免死循环。

同时建立依赖时应做：

```text
Cycle Validation
```

---

# 51. StaleReason

建议不要只有：

```text
status = STALE
```

还应该记录原因。

例如：

```text
CHARACTER_MASTER_CHANGED

LOCATION_MASTER_CHANGED

PROMPT_CHANGED

SOURCE_ASSET_CHANGED

WORKFLOW_CHANGED

MANUAL_MARK
```

---

# 52. AssetStaleRecord

Alpha 可以 metadata 存。

后续推荐：

```text
AssetStaleRecord
{
    assetId

    reason

    sourceType
    sourceId

    createdAt

    resolvedAt
}
```

这样 UI 可以显示：

```text
⚠ 当前视频使用沈亦 v4，
当前 MASTER 已更新为 v5。
```

---

# 53. Regenerate

Regenerate 是最核心业务操作之一。

用户：

```text
Regenerate Shot Image
```

系统不能：

```text
覆盖旧 Asset
```

而是：

```text
Create Generation

Generate Asset

Add to Version Group

Keep current Active
```

---

# 54. Regenerate 流程

```text
User
 ↓
Regenerate
 ↓
Resolve Current Context
 ↓
Create Prompt Version if changed
 ↓
Create Generation
 ↓
Execute
 ↓
Create Asset
 ↓
Assign Version Number
 ↓
Add Version Group
 ↓
Notify New Version
```

---

# 55. Version Number 分配

不能：

```text
SELECT MAX(version) + 1
```

在应用层裸执行后再 INSERT，

否则并发可能重复。

应在事务中：

```text
lock / serial transaction
```

分配版本。

SQLite 单写者下相对容易处理。

---

# 56. Version Number 语义

版本号：

```text
v1
v2
v3
```

只是：

```text
展示顺序
```

真正引用使用：

```text
assetId
```

绝不能：

```text
/v3
```

作为唯一定位。

---

# 57. Version Branch

Alpha 暂不实现完整 Branch。

但数据结构不能阻止：

```text
v3
├── v4a
└── v4b
```

Asset 可以已有：

```text
parent_asset_id
```

未来支持。

Alpha UI 暂时表现为线性版本。

---

# 58. Parent Asset

适用于：

```text
Edit

Upscale

Variation
```

例如：

```text
Image v3
 ↓
Upscale
 ↓
Image v4
```

则：

```text
parent_asset_id = v3
```

但 Generation Input 仍然必须记录 v3。

不能只靠 parent。

---

# 59. Provenance

Provenance 表示：

> 一个 Asset 的完整来源链。

API：

```text
GET /assets/{assetId}/provenance
```

---

# 60. Provenance Tree

例如：

```text
Shot Video v3
│
├── Generation
│   ├── Model: MiniMax
│   ├── Workflow: v5
│   ├── Prompt: v7
│   │
│   └── Inputs
│       └── Shot Image v4
│            │
│            └── Generation
│                ├── Character v5
│                ├── Location v2
│                └── Prompt v4
```

这应该能被 UI 图形化。

---

# 61. Provenance 查询深度

避免一次递归：

```text
无限展开
```

API 支持：

```text
depth=1

depth=3
```

例如：

```http
GET /assets/{id}/provenance?depth=3
```

---

# 62. AssetUsage

另一个重要问题：

> 这个 Asset 当前在哪里被使用？

例如：

```text
角色参考图 v4
```

可能被：

```text
30 个 Generation
10 个 Shot
```

引用。

建议：

```text
GET /assets/{id}/usage
```

---

# 63. Asset Usage

返回：

```text
Used By Generations

Used By Timeline Clips

Used As Character Reference

Used As Active Shot Asset
```

这对：

```text
Delete
Archive
Replace
```

至关重要。

---

# 64. Archive Asset

用户：

```text
Archive v2
```

允许：

```text
status = ARCHIVED
```

但如果它：

```text
正在 Timeline 使用
```

UI 必须警告。

---

# 65. Hard Delete Asset

只有满足：

```text
不是 Active

不是 MASTER Reference

不在 Timeline

没有 Generation 依赖

没有 Derived Asset

没有其他 Resource 引用
```

才能真正删除。

---

# 66. HardDeleteService

```text
analyzeDeletion(assetId)
```

先返回：

```text
SAFE

BLOCKED

WARNING
```

例如：

```json
{
  "status": "BLOCKED",
  "references": [
    {
      "type": "TIMELINE_CLIP",
      "id": "clip_01"
    }
  ]
}
```

---

# 67. Asset Storage

AssetService 只处理业务。

StorageService 处理：

```text
文件
```

分离：

```text
AssetService
     ↓
StorageService
```

---

# 68. StorageService

接口：

```text
storeTemp()

commitTemp()

copy()

move()

open()

exists()

checksum()

fileSize()

delete()

resolve()
```

---

# 69. 文件生成必须经过 Temp

Provider 输出：

```text
temp/
```

例如：

```text
tmp/gen_123/output.mp4
```

然后：

```text
Validate
 ↓
Checksum
 ↓
Move
 ↓
Register Asset
```

而不是 Provider 直接输出到正式目录。

---

# 70. 为什么先 Temp

如果生成过程中：

```text
应用崩溃

模型写了一半

磁盘空间不足
```

不会污染：

```text
正式 Asset
```

目录。

---

# 71. Commit Asset

推荐内部流程：

```text
Generation Output
 ↓
TemporaryAsset
 ↓
validate
 ↓
Storage.commit
 ↓
DB transaction
 ↓
Asset READY
```

---

# 72. Media Validation

图片：

```text
Can decode?

Width?

Height?

Mime?
```

视频：

```text
Can probe?

Duration?

Codec?

Resolution?

Frame Count?
```

音频：

```text
Duration?

Codec?

Sample Rate?
```

---

# 73. MediaProbeService

建议独立：

```text
MediaProbeService
```

可以封装：

```text
ffprobe
```

但业务层只知道：

```text
MediaMetadata
```

---

# 74. Asset Metadata

例如视频：

```json
{
  "codec": "h264",
  "fps": 24,
  "bitrate": 8300000,
  "frameCount": 120
}
```

图片：

```json
{
  "colorSpace": "sRGB",
  "hasAlpha": false
}
```

非高频字段进入：

```text
metadata_json
```

---

# 75. Thumbnail

视频 Asset 不应该每次 UI 打开：

```text
实时抽帧
```

建议自动创建：

```text
THUMBNAIL Asset
```

或者 Preview Metadata。

---

# 76. PreviewService

```text
ensurePreview(assetId)
```

图片：

```text
small image
```

视频：

```text
thumbnail
+
low-resolution proxy
```

音频：

```text
waveform data
```

Alpha 第一版：

```text
Image Thumbnail
Video Thumbnail
```

即可。

---

# 77. Preview 不是原 Asset Version

例如：

```text
shot_video_v3.mp4
```

生成：

```text
thumbnail.jpg
```

thumbnail 不属于：

```text
Shot Video Version Group
```

它是：

```text
DERIVED Asset
```

并通过：

```text
parent_asset_id
```

关联。

---

# 78. Proxy Asset

后续大视频编辑可以生成：

```text
Proxy Video
```

类型可扩展：

```text
VIDEO_PROXY
```

Timeline Preview 用 Proxy，

Render 用原文件。

Alpha 可以预留。

---

# 79. Import Asset

用户导入：

```text
人物参考图
```

流程：

```text
Select File
 ↓
Copy into Project
 ↓
Checksum
 ↓
Probe Metadata
 ↓
Create Asset
 ↓
Bind Domain Object
```

不能只：

```text
数据库存原路径
```

---

# 80. External Asset

未来可以支持：

```text
Linked External File
```

但 Alpha 默认采用：

```text
Copy Into Project
```

保证项目可迁移。

---

# 81. Duplicate Import

Checksum 相同：

```text
SHA256 exists
```

不要直接认定：

```text
同一个业务 Asset
```

因为同一文件可能承担不同用途。

可以复用 Storage Blob，

但 Asset 仍可能不同。

Alpha 第一版无需 Blob 去重。

---

# 82. Asset Repair

项目打开时发现：

```text
Asset file missing
```

处理：

```text
READY
 ↓
MISSING
```

UI：

```text
Locate File

Regenerate

Archive
```

---

# 83. Locate File

用户选择新文件后：

```text
checksum matches
```

则：

```text
Repair
```

如果不匹配：

提示：

```text
Selected file differs from original.
```

用户可以：

```text
Replace
```

但 Replace 应创建：

```text
new Asset
```

而不是静默修改历史 Asset。

---

# 84. Corrupted Asset

文件存在，

但是：

```text
checksum changed
```

则：

```text
CORRUPTED
```

不能直接：

```text
READY
```

---

# 85. Orphan File

文件存在，

数据库没有 Asset。

例如：

```text
应用在文件 move 后、DB commit 前崩溃
```

形成：

```text
Orphan File
```

---

# 86. Orphan Cleanup

启动或 Maintenance：

```text
scan known managed folders
```

找到：

```text
No Asset Reference
```

处理：

```text
move to recovery/orphan/
```

不要立刻删除。

---

# 87. Orphan Asset

反过来：

数据库有 Asset，

文件不存在：

```text
MISSING
```

这是：

```text
Orphan Asset Record
```

保留数据库历史。

---

# 88. Storage Directory

建议：

```text
assets/
├── characters/
├── locations/
├── storyboard/
├── images/
├── videos/
├── audio/
├── subtitles/
├── workflow/
└── derived/
```

不要严格按：

```text
Episode/Scene/Shot
```

作为 Source of Truth。

目录只用于可读性。

---

# 89. Storage Naming

推荐：

```text
{assetId}.{ext}
```

例如：

```text
01K3XYZ.mp4
```

而不是：

```text
shot23_final_final_v4_ok.mp4
```

业务信息都在数据库。

---

# 90. 人类可读路径

可以：

```text
videos/e01/s03/
01Kxxx.mp4
```

兼顾可读性。

但：

```text
assetId
```

仍然必须是文件唯一基础名。

---

# 91. Generation Cache

AI 生成成本高，

需要为未来缓存预留。

GenerationCacheKey：

```text
generationType

provider

model

workflowVersion

prompt content hash

parameters

input asset checksums
```

---

# 92. Generation Hash

伪公式：

```text
SHA256(
 generationType
 + provider
 + model
 + workflowVersion
 + promptHash
 + parameterHash
 + sortedInputHashes
)
```

---

# 93. Cache Hit

新生成请求：

```text
generation_hash
```

已有：

```text
SUCCEEDED Generation
```

且输出 Asset：

```text
READY
```

则可以提示：

```text
Identical output already exists.
```

选项：

```text
Reuse

Generate Anyway
```

Alpha 默认不要偷偷 Cache。

---

# 94. 为什么不自动 Cache

生成模型即使：

```text
Prompt 相同
Seed 未固定
```

也可能期待：

```text
新结果
```

因此必须考虑：

```text
deterministic
```

与：

```text
creative regeneration
```

的差异。

---

# 95. Seed

Generation Parameters 应记录：

```text
seed
```

如果 Provider 支持。

这对：

```text
复现
```

很重要。

---

# 96. Reproducibility

Generation Detail UI 应尽量展示：

```text
Provider

Model

Model Version

Workflow Version

Prompt Version

Seed

Input Assets

Parameters
```

但需要接受：

> 云端模型可能无法 100% 复现历史结果。

系统保证的是：

```text
请求可追溯
```

不是：

```text
输出绝对可复现
```

---

# 97. Provider Model Version

不要只存：

```text
model = minimax-video
```

如果 Provider 提供明确模型版本：

```text
modelVersion
```

也应保存。

否则未来同名模型升级后历史难解释。

---

# 98. Workflow Version 固定

Generation 创建时必须 Resolve：

```text
具体 WorkflowVersion
```

不能只保存：

```text
workflowTemplateId
```

因为：

```text
Template active version
```

未来会变化。

---

# 99. Prompt Version 固定

同理：

```text
promptVersionId
```

必须保存具体版本。

不能 Generation 只指向：

```text
Prompt
```

否则 active Prompt 变化后历史失真。

---

# 100. Character Version 固定

如果 Shot Image 用：

```text
沈亦 v4
```

GenerationInput 必须：

```text
CHARACTER_VERSION:v4
```

而不能：

```text
CHARACTER:沈亦
```

后者无法准确追踪。

---

# 101. AssetReferencePolicy

GenerationPlanner 解析引用时：

```text
Character
 ↓
MasterVersion
 ↓
ReferenceAssets
```

并把最终解析结果冻结到：

```text
GenerationInput
```

---

# 102. Generation Context Snapshot

对于某些复杂 LLM / Agent 执行，

可以保存：

```text
context_snapshot_json
```

或者 Hash。

Alpha 至少保存：

```text
关键结构化输入
```

避免 Agent 未来无法解释。

---

# 103. Cost Tracking

Generation 统一保存：

```text
usage_json
```

例如 LLM：

```json
{
  "inputTokens": 13000,
  "outputTokens": 2100,
  "cachedTokens": 8200
}
```

视频：

```json
{
  "seconds": 5,
  "credits": 15
}
```

---

# 104. Generation Duration

记录：

```text
queuedAt
startedAt
finishedAt
```

可计算：

```text
Queue Time

Execution Time

Total Time
```

未来 Studio 可以分析：

```text
哪个 Provider 最慢？
```

---

# 105. Generation Quality Review

成功生成后，

建议未来增加：

```text
ReviewStatus
```

例如：

```text
UNREVIEWED

APPROVED

REJECTED
```

Alpha 可以先放在 Asset Metadata。

后续正式建模。

---

# 106. Rejected Asset

用户看完：

```text
角色脸崩
```

可以：

```text
Reject
```

不代表：

```text
FAILED
```

因为技术生成是成功的。

所以：

```text
Generation = SUCCEEDED
```

Asset：

```text
READY
```

Review：

```text
REJECTED
```

这三个语义必须分开。

---

# 107. 为什么不能把 Reject 设 FAILED

FAILED 表示：

```text
执行异常
```

而：

```text
画面不好看
```

是：

```text
Creative Review
```

完全不同。

---

# 108. Asset Rating

Beta 可以增加：

```text
rating 1-5

favorite
```

帮助：

```text
版本比较
```

Alpha 可暂缓。

---

# 109. Version Compare

UI：

```text
v3 vs v4
```

图片：

```text
Side-by-side
```

视频：

```text
A/B Preview
```

数据层只需要能够快速查询：

```text
Version Group
```

全部 Asset。

---

# 110. Version Group API

建议：

```text
GET /version-groups/{groupId}

GET /version-groups/{groupId}/assets

POST /version-groups/{groupId}/activate
```

或者对外保持业务 API：

```text
GET /shots/{shotId}/image-versions

POST /shots/{shotId}/image-versions/{assetId}/activate
```

后者更适合前端。

---

# 111. AssetService 与 VersionService 分离

建议：

```text
AssetService
```

负责：

```text
Asset Lifecycle
```

而：

```text
AssetVersionService
```

负责：

```text
Version Group
Version Number
Active
```

避免 AssetService 无限膨胀。

---

# 112. 推荐核心 Service

```text
AssetService

AssetVersionService

AssetStorageService

AssetIntegrityService

AssetPreviewService

GenerationApplicationService

GenerationPlanner

GenerationExecutor

GenerationHistoryService

GenerationCacheService

DependencyService

StalePropagationService

ProvenanceService
```

---

# 113. AssetService

职责：

```text
registerGeneratedAsset()

importAsset()

archiveAsset()

restoreAsset()

markMissing()

markCorrupted()

markStale()

getAsset()
```

---

# 114. AssetVersionService

职责：

```text
createVersionGroup()

assignVersion()

activate()

getVersions()

getActive()

compare()
```

---

# 115. GenerationHistoryService

用于：

```text
Shot Inspector

Generation Panel

Debug
```

接口：

```text
findByTarget()

findRetryChain()

getDetails()

getInputs()

getOutputs()
```

---

# 116. ProvenanceService

接口：

```text
buildProvenance(assetId, depth)

findAncestors()

findDescendants()

findUsage()
```

---

# 117. DependencyService

职责：

```text
createDependencies()

removeInvalidDependencies()

findDependents()

findDependencies()

markAffectedStale()
```

---

# 118. Shot Image 生成完整案例

当前：

```text
Shot 023

Character:
沈亦 v4

Location:
Gym v2

Prompt:
Image Prompt v3
```

点击：

```text
Generate Image
```

---

# 119. Planner

生成：

```text
GenerationPlan
```

```text
Type:
SHOT_IMAGE

Target:
shot_023

Provider:
COMFYUI_LOCAL

Workflow:
shot_image_standard v5

Prompt:
prompt_v3

Inputs:
shenyi_v4
gym_v2

Parameters:
1080x1920
seed=random
```

---

# 120. 创建 Generation

```text
Generation gen_100
status = CREATED
```

注册 Input：

```text
CharacterVersion v4

LocationVersion v2

PromptVersion v3

WorkflowVersion v5
```

---

# 121. Queue

```text
gen_100
 ↓
QUEUED
 ↓
RUNNING
```

---

# 122. Provider 输出

ComfyUI：

```text
temp/gen_100/output.png
```

---

# 123. Validate

系统检查：

```text
PNG valid
1080x1920
file complete
```

计算：

```text
SHA256
```

---

# 124. Asset 注册

创建：

```text
Asset asset_403

type = SHOT_IMAGE

version_group = shot023_image

version = 4

status = READY

generation_id = gen_100
```

---

# 125. Generation Output

创建：

```text
gen_100
 ↓
asset_403
```

然后：

```text
Generation = SUCCEEDED
```

---

# 126. Dependency

建立：

```text
CharacterVersion v4
        ↓
Asset 403

LocationVersion v2
        ↓
Asset 403

PromptVersion v3
        ↓
Asset 403

WorkflowVersion v5
        ↓
Asset 403
```

---

# 127. Active 策略

如果 Shot 从未生成图片：

```text
activeImageAssetId = null
```

则：

```text
自动设 asset_403
```

如果已有：

```text
asset_399
```

则：

```text
保持 asset_399
```

通知：

```text
New version available.
```

---

# 128. Shot Video 案例

当前 Active Image：

```text
asset_403
```

生成 Video：

```text
Generation gen_101
```

输入：

```text
asset_403

Video Prompt v2

Workflow v7
```

输出：

```text
video asset_501
```

Dependency：

```text
asset_403
   ↓
asset_501
```

---

# 129. 修改 Character MASTER

沈亦：

```text
v4 → v5
```

Dependency：

```text
v4
 ↓
asset_403
 ↓
asset_501
```

结果：

```text
asset_403
STALE

asset_501
STALE
```

---

# 130. 用户选择“不重生成”

这是合法状态：

```text
Shot Active Image
=
STALE v4-based

Shot Active Video
=
STALE v4-based
```

Studio 只显示：

```text
⚠ Outdated reference
```

---

# 131. 用户 Regenerate Image

创建：

```text
gen_102
```

使用：

```text
Character v5
```

生成：

```text
asset_404
Image v5
```

---

# 132. asset_404 不自动影响旧视频

当前 Video：

```text
asset_501
```

仍然依赖：

```text
asset_403
```

所以：

```text
asset_501
```

仍是 STALE。

---

# 133. 用户生成新 Video

创建：

```text
gen_103
```

Input：

```text
asset_404
```

输出：

```text
asset_502
```

现在：

```text
asset_502 = READY
```

---

# 134. 用户 Activate

Image：

```text
asset_404
```

Video：

```text
asset_502
```

Shot：

```text
activeImageAssetId = 404

activeVideoAssetId = 502
```

旧版本全部保留。

---

# 135. Clear Stale

Asset 自己的 STALE 不应该因为：

```text
有新版本产生
```

就变回 READY。

例如：

```text
asset_403
```

仍然是：

```text
STALE
```

因为它确实基于旧 Character。

只是：

```text
不再 Active
```

---

# 136. Stale 是历史事实

这点非常重要：

```text
STALE
```

不是：

> “当前需要处理的待办”。

而是：

> “这个 Asset 的依赖相对于当前标准已经过期”。

所以旧资产的 Stale 可以永久存在。

---

# 137. Current Health

UI 如果想知道：

```text
Shot 当前有没有问题？
```

应该查看：

```text
Active Asset Status
```

而不是：

```text
Shot 所有历史 Asset
```

---

# 138. Generation Cancel

用户取消：

```text
gen_120 RUNNING
```

系统：

```text
CANCEL_REQUESTED
```

如果 Provider 支持 cancel：

```text
Provider.cancel()
```

成功：

```text
CANCELLED
```

---

# 139. Cancel 后 Provider 仍返回文件

如果 API 不支持真正取消：

输出回来时：

```text
Generation 已 CANCEL_REQUESTED
```

则：

不要作为正常 Active 候选。

可以：

```text
移到 orphan/recovery
```

或者注册：

```text
ARCHIVED Asset
```

Alpha 推荐：

```text
不注册正式 Asset
```

但保留日志。

---

# 140. Generation Failure

如果 Provider：

```text
HTTP 500
```

Generation：

```text
FAILED
```

记录：

```text
errorCode

errorMessage

providerError
```

不要创建：

```text
FAILED Asset
```

除非 Provider 确实产出了损坏文件，需要 Debug。

---

# 141. Partial Output

有些 Workflow：

```text
生成 4 张图
```

其中：

```text
3 成功
1 失败
```

Generation 可以：

```text
SUCCEEDED_WITH_WARNINGS
```

是否增加该状态可后续决定。

Alpha 简化：

```text
SUCCEEDED
```

同时：

```text
warnings_json
```

---

# 142. Batch Generation 不属于一个 Generation

例如：

```text
Generate 20 Shot Images
```

不要创建：

```text
1 Generation → 20 Shot
```

正确：

```text
1 Job

20 Tasks

20 Generations
```

因为每一个 Shot 都需要独立：

```text
Retry

History

Version

Cost

Status
```

---

# 143. Job 与 Version

Job 不参与：

```text
Version
```

Job 只是组织执行。

版本归属于：

```text
Asset / VersionGroup
```

---

# 144. Generation 与 Timeline 解耦

Generation 成功：

```text
不直接写 Timeline
```

否则：

```text
AI Generation
```

会修改用户编辑结果。

应该：

```text
Generation
 ↓
Asset
```

然后：

```text
TimelineApplicationService
```

决定是否使用。

---

# 145. Generation 与 MASTER 解耦

生成 Character Reference：

```text
v6
```

不能：

```text
自动 Set Master
```

除非：

```text
First Character Version
```

可以采用自动 MASTER。

建议策略：

```text
First version:
auto master

Subsequent:
manual master
```

---

# 146. Import Character Reference

导入图也应该：

```text
Create Asset
 ↓
Create CharacterVersion
 ↓
Bind Asset
```

而不是 Character 表直接：

```text
referencePath
```

---

# 147. Edit Existing Asset

用户外部编辑：

```text
v3.png
```

重新导入。

不能：

```text
覆盖 v3 文件
```

应：

```text
New Asset v4

sourceType = EDITED

parentAssetId = v3
```

保持历史。

---

# 148. Replace File 禁止语义

Studio 默认不提供：

```text
Replace physical file of Asset
```

因为会破坏 Generation Provenance。

正确概念永远是：

```text
Create New Version
```

---

# 149. Exception：Repair

只有：

```text
MISSING Asset
```

通过 Locate 找回完全相同 checksum 文件，

可以恢复原 Asset。

这不是 Version。

---

# 150. Asset Export

用户：

```text
Export Asset
```

只是：

```text
copy file
```

不能修改：

```text
Asset storage path
```

Export 不等于 Move。

---

# 151. Project Export

未来：

```text
Export Project
```

应包括：

```text
project.db
assets/
workflows/
project.json
```

完整 Version / Generation History。

---

# 152. Cleanup Strategy

AI 生产会迅速产生大量版本。

需要：

```text
Storage Cleanup
```

但不能粗暴删除旧版本。

---

# 153. Cleanup Candidate

可以建议清理：

```text
Rejected

Non-active

Non-master

Not used in timeline

Not referenced downstream

Older than X

Large file
```

---

# 154. Cleanup Analyzer

```text
CleanupService.analyze()
```

返回：

```text
Safe to Remove

Review Recommended

Protected
```

---

# 155. Protected Asset

以下永远默认保护：

```text
Active Asset

Timeline Asset

Character MASTER Reference

Location MASTER Reference

Generation Input of Active Asset

Final Export
```

---

# 156. Storage Dashboard

后续 UI：

```text
Project Storage

Images     2.1 GB
Videos    18.4 GB
Audio      0.8 GB
Cache      4.2 GB

Unused Versions 6.7 GB
```

Alpha 可以先不实现 UI，

但 Asset Metadata 必须支持统计。

---

# 157. Generation Debug Package

对于失败 Generation，

未来可以导出：

```text
generation-debug.zip
```

包含：

```text
generation.json

workflow.json

parameters.json

error.log
```

不包含敏感 API Key。

对于 ComfyUI 排错非常有价值。

---

# 158. ComfyUI Execution ID

Generation 应保存：

```text
externalExecutionId
```

例如：

```text
ComfyUI prompt_id
```

便于：

```text
queryStatus
cancel
debug
```

---

# 159. Provider Response Snapshot

建议：

```text
provider_response_json
```

只保存必要元数据。

不要将：

```text
超大 Base64
```

塞数据库。

---

# 160. Generation Executor 幂等

Worker 意外重复消费：

```text
Task
```

不能执行两次。

Executor 开始前必须：

```text
Atomic transition

QUEUED → RUNNING
```

只有成功更新状态的 Worker 才执行。

---

# 161. Generation Success 幂等

如果 Provider 回调重复：

```text
callback 1
callback 2
```

必须保证：

```text
只创建一套正式 Asset
```

可以使用：

```text
externalExecutionId
+
output role
```

做去重。

---

# 162. Asset Registration 幂等

注册生成文件时可通过：

```text
generationId + outputRole + outputIndex
```

建立唯一约束。

避免重复注册。

---

# 163. Generation Callback

云端视频模型可能：

```text
异步 callback
```

架构要兼容：

```text
Submit
 ↓
externalExecutionId
 ↓
WAITING_PROVIDER
 ↓
Callback
```

Alpha 状态可以继续使用：

```text
RUNNING
```

无需增加 WAITING 状态。

---

# 164. Polling Provider

ComfyUI：

```text
poll status
```

云端：

```text
callback / poll
```

这些差异全部封装在：

```text
ProviderAdapter
```

Generation 层不关心。

---

# 165. GenerationExecutor 模式

```text
GenerationExecutor
     ↓
ProviderAdapter
```

Adapter 返回统一：

```text
ExecutionHandle
```

```text
ExecutionResult
```

---

# 166. ExecutionResult

概念：

```text
ExecutionResult
{
    externalExecutionId

    outputs[]

    usage

    providerMetadata

    warnings
}
```

outputs：

```text
TempFile
URL
BinaryStream
```

由 Infrastructure 转换成 Storage。

---

# 167. Remote URL Output

如果 Provider 返回：

```text
https://provider/output.mp4
```

必须：

```text
download into project
```

然后注册 Local Asset。

不要永久把第三方临时 URL 当：

```text
storage_path
```

---

# 168. Remote Asset Future

未来 Cloud Studio 可以：

```text
storageProvider = S3
```

但仍然是 Studio 自己控制的长期 Storage。

---

# 169. Asset Integrity Check 分级

启动时不需要全部 SHA256：

大型视频很多。

建议：

## Quick

```text
file exists
file size
```

## Full

```text
checksum
media probe
```

用户触发：

```text
Verify Project
```

时再 Full。

---

# 170. Version Consistency Check

Project Repair 还应检查：

```text
Active Asset 是否属于正确 Version Group

Version number 是否重复

MASTER 是否唯一

Generation Output Asset 是否存在

Asset generationId 是否一致
```

---

# 171. RepairService

```text
ProjectRepairService
```

包含：

```text
checkAssets()

checkVersions()

checkGenerationLinks()

checkDependencies()

checkStorage()

repairSafeIssues()
```

---

# 172. Audit Events

关键操作：

```text
ASSET_IMPORTED

ASSET_ARCHIVED

ASSET_ACTIVATED

VERSION_CREATED

CHARACTER_MASTER_CHANGED

GENERATION_CREATED

GENERATION_SUCCEEDED

GENERATION_FAILED

ASSET_MARKED_STALE
```

建议进入：

```text
AuditLog
```

---

# 173. Asset API

推荐：

```text
GET  /projects/{projectId}/assets

POST /projects/{projectId}/assets/import

GET  /assets/{assetId}

GET  /assets/{assetId}/preview

GET  /assets/{assetId}/provenance

GET  /assets/{assetId}/usage

POST /assets/{assetId}/archive

POST /assets/{assetId}/restore

POST /assets/{assetId}/verify
```

---

# 174. Version API

业务化：

```text
GET /shots/{shotId}/image-versions

GET /shots/{shotId}/video-versions

POST /shots/{shotId}/image-versions/{assetId}/activate

POST /shots/{shotId}/video-versions/{assetId}/activate
```

Character：

```text
GET /characters/{id}/versions

POST /characters/{id}/versions/{versionId}/set-master
```

---

# 175. Generation API

```text
GET /generations/{generationId}

GET /generations/{generationId}/inputs

GET /generations/{generationId}/outputs

GET /generations/{generationId}/retry-chain

POST /generations/{generationId}/retry

POST /generations/{generationId}/cancel
```

---

# 176. Regenerate API

不要统一：

```text
POST /generations/regenerate
```

前端更应该使用：

```text
POST /shots/{id}/generate-image

POST /shots/{id}/generate-video

POST /characters/{id}/generate-reference
```

因为 Regenerate 是领域行为。

---

# 177. Asset Browser Read Model

返回：

```text
assetId

type

thumbnail

name

owner

version

isActive

isMasterReference

status

reviewStatus

createdAt

provider

model
```

避免 UI 再 JOIN 多个接口。

---

# 178. Generation Inspector

UI 详情：

```text
Generation #1023

Status
Succeeded

Type
Shot Video

Target
Shot 023

Provider
MiniMax

Model
...

Workflow
v4

Prompt
v7

Inputs
4

Outputs
1

Queue Time
2.3s

Execution Time
38.2s

Cost
...

[Retry]
```

---

# 179. Asset Inspector

```text
Shot Video v3

Status
READY

Active
Yes

File
...

Resolution
1080 × 1920

Duration
5.0s

Generated By
Generation #1023

Dependencies
Image v4
Prompt v7

Used In
Timeline Episode 01
```

---

# 180. Version History UI

建议：

```text
Shot 023 Video

v5   New
v4   Rejected
v3   ★ Active
v2   Stale
v1   Archived
```

让版本体系成为用户可理解的核心交互，而不是隐藏技术结构。

---

# 181. Generation Panel

底部：

```text
Running
────────────────

Shot 31 Video      67%

Shot 32 Image      21%

Queued
────────────────

Shot 32 Video

Failed
────────────────

Shot 28 Video
Network Timeout

[Retry]
```

点击任意任务打开：

```text
Generation Inspector
```

---

# 182. Alpha 第一阶段实现范围

不要一次实现本文全部能力。

## AGV Phase 1

优先完成：

```text
Asset

Generation

GenerationInput

GenerationOutput

Version Group

Active Version

Local Storage

Generated Asset Registration
```

---

# 183. Phase 1 验收

必须能：

```text
生成 Shot Image

生成 Shot Video

每次生成新版本

查看历史版本

切换 Active

查询 Generation Detail
```

---

# 184. AGV Phase 2

增加：

```text
Provenance

Asset Import

Thumbnail

Archive

Integrity

Missing File Detection

Retry Chain
```

---

# 185. Phase 2 验收

能够回答：

```text
这个视频怎么生成的？

用了哪张图？

哪一个角色版本？

哪一个 Workflow？

哪一个 Prompt？
```

---

# 186. AGV Phase 3

增加：

```text
ResourceDependency

STALE

Stale Propagation

MASTER Change Integration

Usage Query
```

---

# 187. Phase 3 验收

Character：

```text
MASTER v4 → v5
```

自动：

```text
找到受影响 Asset

标记 Stale

通知前端
```

但：

```text
不重生成
```

---

# 188. AGV Phase 4

增加：

```text
Generation Cache

Cleanup

Orphan Recovery

Project Repair

Cost Metadata
```

进入长期可用 Alpha。

---

# 189. 推荐 Codex 开发任务

## Task 01

实现 Asset Domain Model。

## Task 02

实现 LocalStorageService。

## Task 03

实现 AssetRepository。

## Task 04

实现 Asset Import。

## Task 05

实现 Generation Domain。

## Task 06

实现 GenerationInput / Output。

## Task 07

实现 Generation History Query。

## Task 08

实现 Asset Version Group。

## Task 09

实现 Version Number 分配。

## Task 10

实现 Activate Asset Version。

---

# 190. 第二批 Codex Task

```text
Task 11
Generated Asset Registration

Task 12
Generation Executor Integration

Task 13
Asset Preview

Task 14
Media Probe

Task 15
Checksum

Task 16
Asset Provenance

Task 17
Asset Usage

Task 18
Asset Archive

Task 19
Generation Retry Chain

Task 20
Generation Cancel
```

---

# 191. 第三批 Codex Task

```text
Task 21
Resource Dependency

Task 22
Stale Record

Task 23
Stale Propagation

Task 24
Character MASTER Integration

Task 25
Location MASTER Integration

Task 26
Shot Stale Summary

Task 27
Asset Missing Detection

Task 28
Orphan File Recovery

Task 29
Project Asset Repair

Task 30
Storage Cleanup Analyzer
```

---

# 192. AGV 系统禁止事项

## 禁止 1

```text
生成结果直接返回 filePath，
不创建 Asset。
```

---

## 禁止 2

```text
重新生成覆盖旧文件。
```

---

## 禁止 3

```text
Generation 成功后自动替换所有 Active。
```

---

## 禁止 4

```text
Generation Retry 修改原 Generation。
```

---

## 禁止 5

```text
Character MASTER 更新后自动重生成。
```

---

## 禁止 6

```text
Generation 只记录 Model，
不记录 Prompt / Workflow / Inputs。
```

---

## 禁止 7

```text
通过文件目录推断 Version。
```

---

## 禁止 8

```text
Asset 直接存第三方临时 URL。
```

---

## 禁止 9

```text
失败 Generation 创建空 Asset。
```

---

## 禁止 10

```text
Timeline 自动跟随最新生成版本。
```

---

# 193. 系统最终调用链

一个完整 Shot：

```text
Shot
 ↓
Visual Spec
 ↓
Prompt Version
 ↓
Generation Plan
 ↓
Generation
 ↓
Generation Inputs
 ↓
Provider
 ↓
Temporary Output
 ↓
Validate
 ↓
Storage
 ↓
Asset
 ↓
Version Group
 ↓
Resource Dependency
 ↓
Review
 ↓
Activate
 ↓
Timeline
```

---

# 194. 最核心生成图

```text
Character MASTER
        │
        │
Location MASTER
        │
        │
Prompt Version
        │
        ▼
    Generation A
        │
        ▼
   Shot Image v4
        │
        ▼
    Generation B
        │
        ▼
   Shot Video v3
        │
        ▼
      Timeline
```

当：

```text
Character MASTER
```

发生变化：

```text
Dependency Graph
 ↓
Shot Image v4 = STALE
 ↓
Shot Video v3 = STALE
```

而：

```text
Timeline
```

保持不变。

这就是 Studio 的核心可控性。

---

# 195. Alpha AGV 完成定义

当用户可以完成以下操作：

1. 生成 Shot Image v1；
2. 再生成 v2；
3. 对比 v1 / v2；
4. 将 v1 设为 Active；
5. 使用 v1 生成 Video v1；
6. 修改 Prompt；
7. 重新生成 Image v3；
8. v1 / v2 / v3 全部保留；
9. 将 v3 设 Active；
10. Video v1 被识别为依赖旧图；
11. 重新生成 Video v2；
12. Timeline 仍保留 Video v1；
13. 用户手动替换 Timeline 为 v2；
14. 可以查看 Video v2 的完整 Provenance；
15. Character MASTER 更新后相关 Asset 自动 STALE；
16. 关闭软件重新打开后所有历史和版本仍存在。

则：

> **Asset / Generation / Version Core v0.1 完成。**

---

# 196. 下一份设计文档

Asset / Generation / Version 系统确定后，下一块最应该单独设计的是：

# 《AI 漫剧 Studio Job Queue & Generation State Machine 详细设计 v0.1》

原因是现在已经解决：

```text
生成什么
如何记录
怎么版本化
```

下一步要解决：

```text
几十上百个生成任务怎么稳定执行？
```

重点包括：

```text
Job

Task

DAG Dependency

Persistent Queue

Worker Pool

Priority

Concurrency

ComfyUI 单 GPU 调度

Retry Policy

Backoff

Pause

Resume

Cancel

Interrupted Recovery

Checkpoint

Progress

SSE

Partial Failure

Scene Batch Generation

Episode Batch Generation
```

这会直接决定：

> Studio 能不能从“单镜头生成工具”，真正升级为“能够稳定生产完整 Episode 的 AI 漫剧生产系统”。

推荐下一步直接进入这份文档。
