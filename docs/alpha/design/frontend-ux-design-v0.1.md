# AI 漫剧 Studio Alpha 前端 UX / 信息架构与交互设计 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**目标：** 将已经确定的 Project / Shot / Asset / Generation / Job / Agent / Continuity 等后端能力，组织成一个真正适合持续制作 AI 漫剧的桌面 Studio。

---

# 1. 产品形态

AI 漫剧 Studio 不应设计成：

```text
聊天框
+
几个生成按钮
```

也不应只是：

```text
ComfyUI 的简化版
```

目标形态应该更接近：

```text
Premiere
+
ComfyUI
+
Cursor
+
AI Director
```

但 Alpha 不复制这些软件的复杂度。

核心原则：

> 所有界面都围绕“项目 → Scene → Shot → Asset → Version → Generation”组织。

---

# 2. Alpha UX 核心目标

用户进入 Studio 后，应能快速回答：

```text
我现在在哪个 Project？

正在制作哪一集？

正在编辑哪个 Scene？

当前选中了哪个 Shot？

这个 Shot 当前用了哪个版本？

AI 正在生成什么？

哪些东西失败了？

哪些资产过期了？

AI Director 建议修改什么？

哪里存在连续性问题？
```

---

# 3. 顶层信息架构

建议：

```text
App
│
├── Home
│   ├── Recent Projects
│   ├── Create Project
│   ├── Import Project
│   └── Settings
│
└── Studio
    │
    ├── Story
    ├── Characters
    ├── Locations
    ├── Storyboard
    ├── Assets
    ├── Workflow
    ├── Timeline
    └── Settings
```

但不要将这些设计成完全独立的软件页面。

核心仍然是：

```text
Studio Workspace
```

---

# 4. Studio Shell

推荐整体布局：

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar                                                      │
├──────────────┬───────────────────────────┬───────────────────┤
│              │                           │                   │
│ Project      │                           │ Inspector         │
│ Explorer     │        Main Area          │                   │
│              │                           │                   │
│              │                           │                   │
├──────────────┴───────────────────────────┴───────────────────┤
│ Timeline / Generation / Agent / Console                     │
└──────────────────────────────────────────────────────────────┘
```

这是整个 Alpha 最重要的布局。

---

# 5. 四大区域

固定四区：

```text
Top Bar

Left Panel

Main Area

Right Inspector

Bottom Panel
```

其中：

* 左侧负责 **导航与项目结构**
* 中央负责 **当前任务**
* 右侧负责 **当前对象属性**
* 底部负责 **跨对象流程状态**

---

# 6. Top Bar

Top Bar 不要塞太多功能。

建议：

```text
Project Name

Current Episode

Undo / Redo

Save Status

AI Director

Generate

Export

Provider Status

Settings
```

例如：

```text
最后一种打法 / Episode 01

Saved ✓

ComfyUI ●
MiniMax ●

[AI Director] [Generate] [Export]
```

---

# 7. 保存状态

桌面 Studio 应明确显示：

```text
Saved

Saving...

Unsaved

Error
```

用户不应该猜：

> 当前工程到底保存没有。

---

# 8. Provider Status

右上角可以显示：

```text
● ComfyUI
● LLM
● Video API
```

正常只显示状态点。

点击展开：

```text
ComfyUI Local
Connected

Video Provider
Available

LLM
Available
```

---

# 9. Project Explorer

左侧是 Studio 的核心导航。

结构：

```text
PROJECT

▾ Episode 01
   ▾ Scene 01
      Shot 001
      Shot 002
      Shot 003
   ▸ Scene 02

▸ Episode 02

LIBRARY

Characters

Locations

Props

Assets
```

---

# 10. Project Explorer 不只是文件树

它表示的是：

```text
业务结构
```

而不是：

```text
磁盘目录
```

所以：

```text
Episode
Scene
Shot
```

来自数据库。

不能因为用户移动文件：

```text
Project Tree
```

就改变。

---

# 11. Tree Node 状态

每个节点可以通过小状态标记表达：

```text
✓ Approved

● Generating

⚠ Stale

! Failed

○ Draft
```

例如：

```text
Shot 013      ✓

Shot 014      ⚠

Shot 015      ●
```

---

# 12. 不要滥用颜色

优先：

```text
Icon
+
Label
+
Tooltip
```

颜色只辅助。

例如：

```text
⚠ Stale
```

比单纯黄色文字更清晰。

---

# 13. Scene Node Summary

Scene 可以显示：

```text
Scene 05

12 Shots
9 Ready
2 Stale
1 Failed
```

Hover 或展开时显示。

---

# 14. Shot Thumbnail

Shot 节点后期可以增加：

```text
small thumbnail
```

但 Alpha 第一版不要让 Tree 太宽。

推荐：

```text
Shot Number
+
Status
```

即可。

---

# 15. Tree Context Menu

右键 Shot：

```text
Open

Duplicate

Generate Image

Generate Video

Regenerate

Mark Approved

Move

Archive
```

Scene：

```text
Open

AI Plan Shots

Generate Scene

Review Continuity

Duplicate

Archive
```

---

# 16. Main Area

中央区域根据当前 Mode 显示不同 Workspace。

建议：

```text
Story

Storyboard

Shot

Assets

Timeline

Workflow
```

---

# 17. Workspace Tabs

顶部或中央内部：

```text
Story | Storyboard | Shot | Timeline
```

用户切换的是：

```text
工作模式
```

不是 Project 页面。

---

# 18. Story Workspace

用于：

```text
Source Novel

Episode Script

Scene Planning
```

布局：

```text
Source Text
│
├── Episode Outline
│
└── Scene Cards
```

---

# 19. Story Workspace 重点

不要做复杂文字编辑器。

Alpha 重点：

```text
源文本

Scene 拆分

Director Proposal

脚本修改
```

---

# 20. Scene Card

每个 Scene：

```text
Scene 05

地点
篮球馆

时间
晚上

角色
沈亦 / 教练

目的
训练结束后的师徒对话

12 Shots

[Open Storyboard]
```

---

# 21. Storyboard Workspace

这是 Alpha 最重要的 Workspace 之一。

推荐：

```text
Scene 05

[ Shot 01 ][ Shot 02 ][ Shot 03 ]
[ Shot 04 ][ Shot 05 ][ Shot 06 ]
```

卡片式 Shot Grid。

---

# 22. Storyboard Card

每张：

```text
┌──────────────────┐
│ thumbnail        │
│                  │
├──────────────────┤
│ Shot 023         │
│ Medium Close Up  │
│ 4.5s             │
│                  │
│ ✓ Image   ⚠ Video│
└──────────────────┘
```

---

# 23. Shot Card 状态

显示：

```text
Image

Video

Continuity

Approval
```

但不要显示全部技术细节。

例如：

```text
IMG v4 ✓

VID v2 ⚠
```

---

# 24. Storyboard 批量操作

用户多选：

```text
Shot 10
Shot 11
Shot 12
```

工具栏：

```text
Generate Images

Generate Videos

Regenerate

Approve

Archive
```

---

# 25. Shot Workspace

用户双击 Shot：

进入：

```text
Shot Editor
```

这是 Alpha 使用频率最高的单体编辑界面。

---

# 26. Shot Editor 布局

推荐：

```text
┌─────────────────────────────────────┐
│ Shot 023                            │
│                                     │
│           Media Preview             │
│                                     │
├─────────────────────────────────────┤
│ Image Versions / Video Versions     │
└─────────────────────────────────────┘
```

右侧 Inspector 管属性。

---

# 27. Media Preview

顶部切换：

```text
Image

Video

Compare
```

如果没有视频：

默认显示 Active Image。

---

# 28. Preview Controls

Video：

```text
Play

Pause

Loop

Frame Step

Volume

Fullscreen
```

不要在 Alpha 做专业剪辑控件。

---

# 29. Shot Header

显示：

```text
Shot 023

Scene 05

4.5s

APPROVED / DRAFT / STALE
```

操作：

```text
Generate Image

Generate Video

Regenerate

Approve
```

---

# 30. Generate Button

不要只有一个：

```text
Generate
```

建议主要按钮：

```text
Generate
```

Dropdown：

```text
Generate Image

Generate Video

Generate Image + Video
```

减少按钮数量。

---

# 31. Regenerate

当已有 Active Asset：

按钮：

```text
Regenerate
```

不写：

```text
Generate
```

语义更清晰。

---

# 32. 新版本提示

生成成功后：

不要自动切 Active。

显示：

```text
New version generated

Video v4

[Preview]
[Use Version]
```

---

# 33. Version Strip

Preview 下方：

```text
v1   v2   v3★   v4 NEW
```

其中：

```text
★
```

表示 Active。

---

# 34. Image / Video 分开版本

不要混：

```text
v1 image
v2 video
v3 image
```

应该：

```text
Image Versions

v1 v2 v3

Video Versions

v1 v2
```

---

# 35. Compare Mode

选择：

```text
v3
vs
v4
```

图片：

```text
左右并排
```

视频：

Alpha 可以：

```text
A / B switch
```

不一定做同步双播放器。

---

# 36. Version Context Menu

```text
Use Version

Compare

View Generation

View Provenance

Archive
```

---

# 37. Active 与 Latest UI

必须明确区分：

```text
ACTIVE

LATEST
```

例如：

```text
v3 ACTIVE

v4 LATEST
```

不能只通过排序让用户猜。

---

# 38. MASTER UI

Character / Location 的版本页：

```text
v1

v2

v3 ★ MASTER

v4 NEW
```

操作：

```text
Set as Master
```

必须是显式行为。

---

# 39. STALE UI

如果 Active Asset：

```text
STALE
```

在 Preview 上方显示：

```text
⚠ This version uses outdated references.
```

展开：

```text
Character ShenYi
Used: v4
Current Master: v5
```

操作：

```text
Regenerate

Keep Current

Ignore
```

---

# 40. Right Inspector

右侧 Inspector 完全由：

```text
Selection
```

驱动。

统一：

```text
Selection {
  type,
  id
}
```

---

# 41. Selection 类型

```text
PROJECT

EPISODE

SCENE

SHOT

CHARACTER

LOCATION

ASSET

GENERATION

JOB

TIMELINE_CLIP
```

---

# 42. Inspector 动态切换

点击：

```text
Shot
```

→ Shot Inspector。

点击：

```text
Character
```

→ Character Inspector。

点击：

```text
Asset
```

→ Asset Inspector。

不要同时弹多个属性面板。

---

# 43. Shot Inspector

建议分 Section：

```text
General

Camera

Characters

Continuity

Prompt

Generation

Output
```

---

# 44. General

```text
Duration

Description

Narrative Beat

Status
```

---

# 45. Camera

```text
Shot Type

Camera Angle

Movement

Composition
```

---

# 46. Characters

例如：

```text
沈亦
Version v4
Costume 白色7号

教练
Version v2
```

---

# 47. Continuity Section

显示：

```text
Position

Action

Held Prop

Physical State

Warnings
```

不要把完整 JSON 暴露给普通用户。

---

# 48. Prompt Section

显示：

```text
Canonical Prompt

Image Prompt

Video Prompt
```

默认折叠长文本。

操作：

```text
Edit

AI Improve

History
```

---

# 49. Prompt 修改

编辑 Prompt 后：

创建：

```text
Prompt Version
```

UI 应提示：

```text
This will create Prompt v5.
```

而不是覆盖。

---

# 50. Generation Section

显示当前 Active Asset 的：

```text
Provider

Model

Workflow

Seed

Generated At

Duration

Cost
```

操作：

```text
View Details
```

---

# 51. Character Library

左侧点击：

```text
Characters
```

中央进入 Library Grid。

---

# 52. Character Card

```text
┌────────────────┐
│ Master Image   │
├────────────────┤
│ 沈亦           │
│ 主角           │
│ MASTER v4      │
└────────────────┘
```

---

# 53. Character Detail

推荐：

```text
Reference Gallery

Identity

Appearance

Body

Costumes

Versions

Generation History
```

---

# 54. Reference Gallery

可以显示：

```text
Front

Side

Full Body

Expression
```

绑定到当前 CharacterVersion。

---

# 55. Set Master

用户选择版本：

```text
Set as Master
```

弹出轻量确认：

```text
This may mark dependent shots as stale.

23 shots may be affected.

[Cancel]
[Set Master]
```

---

# 56. 不自动再生成

确认后：

```text
23 shots marked stale
```

而不是：

```text
23 shots regenerating
```

---

# 57. Location Library

与 Character Library 类似。

卡片：

```text
篮球馆

MASTER v2

Used in 8 scenes
```

---

# 58. Asset Browser

Asset Browser 不是文件浏览器。

它是：

```text
Project Media Library
```

过滤：

```text
All

Characters

Locations

Storyboard

Images

Videos

Voice

Music

Subtitle
```

---

# 59. Asset Browser 顶部筛选

```text
Type

Scene

Shot

Status

Source

Provider

Date
```

---

# 60. Asset Card

```text
thumbnail

Shot 023 Video

v3

ACTIVE

READY
```

---

# 61. Asset Inspector

显示：

```text
Asset Type

Version

Status

File

Resolution

Duration

Generated By

Used By
```

操作：

```text
View Provenance

Reveal in Folder

Archive
```

---

# 62. Provenance UI

推荐抽屉或 Modal：

```text
Shot Video v3
   ↑
Generation #183
   ↑
Shot Image v4
Prompt v6
ShenYi v4
Gym v2
Workflow v5
```

不要一开始做复杂节点 Canvas。

---

# 63. Generation Queue

Bottom Panel 默认 Tab：

```text
Generation
```

---

# 64. Queue Layout

```text
Running
──────────────────────
Shot 23 Video       67%

Queued
──────────────────────
Shot 24 Video
Shot 25 Image

Failed
──────────────────────
Shot 18 Video
Timeout
```

---

# 65. Job Group

批量 Scene 生成：

```text
Scene 05

13 / 24

54%
```

展开：

```text
Shot 01 Image ✓
Shot 01 Video ✓
Shot 02 Image ●
Shot 02 Video BLOCKED
```

---

# 66. Generation Queue 核心操作

Job：

```text
Pause

Resume

Cancel

Retry Failed
```

Task：

```text
Retry

Cancel

View Generation
```

---

# 67. 不显示假进度

Provider 没有百分比：

显示：

```text
Generating…
```

可以显示：

```text
elapsed 42s
```

但不要：

```text
73%
```

伪造进度。

---

# 68. Agent Panel

Bottom Panel 第二个核心 Tab：

```text
AI Director
```

---

# 69. Agent Panel

例如：

```text
AI Director — Scene 05

✓ Load Context
✓ Script Planning
● Visual Planning
○ Continuity
○ Review
```

---

# 70. Agent Result

完成后：

```text
12 shots proposed

2 continuity warnings

[Review Proposal]
```

---

# 71. Proposal Review

必须设计得清楚。

推荐：

```text
Current
vs
Proposal
```

---

# 72. Scene Proposal Diff

例如：

```text
CURRENT

8 shots

PROPOSED

6 shots
```

变化：

```text
Shot 03 removed

Shot 05 duration 6s → 4s

Shot 07 camera changed
```

---

# 73. Review 操作

```text
Approve All

Approve Selected

Reject

Ask AI to Revise
```

---

# 74. Alpha 可以先简化

第一版：

```text
Approve

Reject

Revise
```

后期再做：

```text
Partial Approval
```

---

# 75. Human Review Interrupt

Agent WAITING_HUMAN 时：

Bottom Panel：

```text
AI Director requires review
```

Top Bar 也显示一个：

```text
Review 1
```

避免用户错过。

---

# 76. Proposal Conflict

如果用户在 AI 生成 Proposal 后修改了 Scene：

显示：

```text
⚠ This proposal is based on an older version.
```

操作：

```text
Regenerate Proposal

View Diff
```

Alpha 不建议：

```text
Apply Anyway
```

默认隐藏。

---

# 77. Continuity Panel

Bottom Panel 或 Right Inspector 都可以出现 Continuity。

推荐：

* 单 Shot → Inspector
* 整 Scene → Bottom Panel / dedicated view

---

# 78. Scene Continuity View

例如：

```text
Continuity — Scene 05

ERROR  1
WARNING 3
INFO 2
```

下面：

```text
Shot 12 → 13
Costume Changed

Shot 19 → 20
Basketball disappeared
```

---

# 79. Warning Item

显示：

```text
ERROR

Shot 19 → 20

Basketball disappeared without transition.

[Open Shot 20]
[Ignore]
```

---

# 80. Fix Proposal

如果 Agent 给出修复建议：

```text
Suggested:
Keep basketball in ShenYi's right hand.
```

操作：

```text
Apply Fix

Review
```

---

# 81. Timeline Workspace

Alpha Timeline 目标：

> 将生成 Shot 组织成可预览 Episode。

不是替代 Premiere。

---

# 82. Timeline Layout

```text
Video     | Shot01 | Shot02 | Shot03 |

Voice     | V01    | V02    | V03    |

Music     |          BGM          |

Subtitle  | S01    | S02    | S03    |
```

---

# 83. Timeline Alpha 功能

只做：

```text
Select

Move

Trim

Delete

Replace Version

Mute

Preview
```

---

# 84. 暂不做

```text
复杂转场编辑

调色

多层特效

Mask

Keyframe Animation

高级音频混音
```

---

# 85. Timeline Clip Inspector

点击 Clip：

右侧：

```text
Source Asset

Shot

Start

Duration

Source In / Out

Version

Replace
```

---

# 86. Shot Active Version 不自动改变 Timeline

如果：

```text
Shot Active Video v3 → v4
```

Timeline 仍然：

```text
v3
```

UI 提示：

```text
Newer shot version available.
```

操作：

```text
Replace
```

---

# 87. Replace All

未来可以：

```text
Update timeline to latest active shot versions
```

但必须是用户显式操作。

---

# 88. Bottom Panel Tabs

推荐 Alpha：

```text
Generation

AI Director

Continuity

Console
```

Timeline 在 Timeline Workspace 时可以占主要底部区域。

---

# 89. Console

Console 面向高级用户 / Debug。

显示：

```text
Backend Logs

Provider Logs

Generation Events
```

不要让普通用户默认看到。

---

# 90. Resizable Panels

Left：

```text
200～400px
```

Right：

```text
280～480px
```

Bottom：

```text
150～500px
```

全部：

```text
Resizable
```

---

# 91. Panel Collapse

支持：

```text
Collapse Left

Collapse Inspector

Collapse Bottom
```

最大化 Preview。

---

# 92. Layout Persistence

Studio 重启后恢复：

```text
Panel Width

Bottom Height

Collapsed State

Active Workspace

Open Tabs

Selected Shot
```

建议保存：

```text
workspace_layout
```

本地状态。

---

# 93. 不全部写 Project DB

布局属于：

```text
User Workspace State
```

不是：

```text
Project Business State
```

可以存在：

```text
local app settings
```

---

# 94. Main Tabs

允许用户同时打开：

```text
Scene 05

Shot 23

沈亦

Timeline E01
```

形成：

```text
Editor Tabs
```

类似 IDE。

---

# 95. Tab 内容

例如：

```text
Scene 05 ×
Shot 023 ×
沈亦 ×
```

---

# 96. Tab 恢复

软件重启：

可以恢复：

```text
上次 Tabs
```

但如果资源已归档：

显示：

```text
Resource unavailable
```

而不是崩溃。

---

# 97. Breadcrumb

中央上方：

```text
Episode 01 > Scene 05 > Shot 023
```

方便快速定位。

---

# 98. Command Palette

Alpha 很值得加入：

```text
Ctrl / Cmd + K
```

打开：

```text
Generate Current Shot

Open Character ShenYi

Go to Shot 23

Review Continuity

Open Generation Queue
```

---

# 99. 为什么值得做

Studio 功能越来越多，

不能所有功能：

```text
都塞按钮
```

Command Palette 可以减少 UI 密度。

---

# 100. Global Search

Command Palette 可以同时搜索：

```text
Scene

Shot

Character

Location

Asset
```

---

# 101. Keyboard Shortcuts

Alpha 建议：

```text
Ctrl/Cmd + S
Save

Ctrl/Cmd + K
Command Palette

Space
Play / Pause

Delete
Archive / Remove Clip

Esc
Clear Selection / Close Modal
```

不要一开始做几十个快捷键。

---

# 102. Undo / Redo

前端必须区分：

```text
UI Undo
```

和：

```text
Project Change Undo
```

Alpha 优先支持：

```text
Shot property changes

Timeline changes
```

AI 大批量 Proposal 后期通过：

```text
ChangeSet
```

撤销。

---

# 103. Auto Save

业务修改：

```text
用户结束输入
```

后：

```text
debounce
```

自动保存。

不需要用户频繁：

```text
Ctrl + S
```

但仍保留 Save 状态。

---

# 104. Optimistic Update

简单字段：

```text
Shot duration
```

可前端先更新。

失败：

```text
rollback
```

---

# 105. Revision Conflict

如果：

```text
409
```

显示：

```text
This shot changed elsewhere.

[Reload]
```

Alpha 不需要复杂 merge。

---

# 106. Store 架构

推荐前端状态按 Domain 分：

```text
projectStore

episodeStore

sceneStore

shotStore

characterStore

assetStore

generationStore

jobStore

agentStore

continuityStore

timelineStore

uiStore
```

---

# 107. 不使用巨大 Store

避免：

```text
studioStore
```

保存全部东西。

后期会极难维护。

---

# 108. Normalize

核心实体：

```text
shotsById

scenesById

charactersById
```

而不是：

```text
project.episodes[0].scenes[0].shots
```

深层嵌套。

---

# 109. Query State 与 Domain State

前端需要明确：

```text
Server State
```

与：

```text
UI State
```

---

# 110. Server State

例如：

```text
Shot

Asset

Generation

Job
```

来自后端。

---

# 111. UI State

例如：

```text
Panel Width

Selected Tab

Inspector Section

Zoom

Grid Size
```

本地保存。

---

# 112. SSE Integration

Generation / Agent / Continuity 事件统一进入：

```text
EventStore / EventService
```

然后更新：

```text
jobStore

generationStore

assetStore

shotStore
```

---

# 113. 不让组件自己订阅 SSE

错误：

```text
ShotCard
连接 SSE

Inspector
连接 SSE
```

正确：

```text
Global Event Client
 ↓
Stores
 ↓
Components
```

---

# 114. SSE 断线

显示：

```text
Realtime disconnected
```

自动重连。

重连后：

```text
refresh active jobs
```

---

# 115. Toast 使用原则

适合：

```text
Generation started

Version activated

Asset imported
```

不适合：

```text
严重 Job Failure
```

严重错误应该在：

```text
Generation Panel
```

持续可见。

---

# 116. Notification Center

Alpha 暂时不需要完整通知中心。

Bottom Panel 已足够承载：

```text
Job
Agent
Continuity
```

---

# 117. Empty State

例如没有 Character：

不要只写：

```text
No data
```

应该：

```text
No characters yet.

Create manually or let AI extract them from the story.

[Create Character]
[Extract with AI]
```

---

# 118. Loading State

避免全页面：

```text
Loading...
```

使用：

```text
Skeleton
```

保持 Studio 布局稳定。

---

# 119. Long-running Generation

Generation 期间：

用户仍然可以：

```text
编辑别的 Scene

查看 Asset

修改 Prompt

播放 Timeline
```

不能用全屏 Loading。

---

# 120. Modal 使用

只有：

```text
不可逆 / 高风险
```

操作需要 Modal。

例如：

```text
Set Master affecting 43 shots

Cancel large Job

Hard Delete
```

普通编辑：

不要弹 Modal。

---

# 121. Archive 而不是 Delete

UI 文案默认：

```text
Archive
```

而不是：

```text
Delete
```

符合项目历史与版本机制。

---

# 122. Hard Delete

放在：

```text
Advanced
```

或者：

```text
Storage Cleanup
```

中。

---

# 123. Error UX

所有错误最好回答三件事：

```text
发生了什么？

影响了什么？

用户现在能做什么？
```

---

# 124. 错误示例

不推荐：

```text
Error 500
```

推荐：

```text
Video generation failed.

Shot 023 was not changed.

Provider timed out.

[Retry]
[View Details]
```

---

# 125. Missing Asset

显示：

```text
Video file is missing.

The project record is still intact.

[Locate File]
[Regenerate]
[Archive]
```

---

# 126. Provider Offline

Generation Panel：

```text
ComfyUI disconnected.

7 tasks are waiting.

[Reconnect]
[Settings]
```

任务不立即显示失败。

---

# 127. Agent Error

例如：

```text
AI Director could not produce a valid shot plan.

No project changes were applied.

[Retry]
[View Run]
```

这句话非常关键：

```text
No project changes were applied.
```

用户会知道数据安全。

---

# 128. Home

Home 保持简单。

```text
AI Comic Studio

Recent Projects

[New Project]

[Open Project]
```

---

# 129. Recent Project Card

```text
Cover

Project Name

Last Opened

Episode Progress
```

例如：

```text
最后一种打法

Episode 01

Last opened 2h ago
```

---

# 130. Create Project

Wizard 不要太长。

第一步：

```text
Project Name

Aspect Ratio

Resolution
```

第二步：

```text
Import Story
```

第三步可跳过：

```text
AI Provider
```

---

# 131. 项目创建后

直接进入：

```text
Story Workspace
```

引导：

```text
Import or paste your story.
```

---

# 132. Onboarding Flow

Alpha 推荐：

```text
Create Project
 ↓
Import Story
 ↓
Extract Characters / Locations
 ↓
Plan Episode
 ↓
Review Scenes
 ↓
Open Storyboard
 ↓
Generate Character Masters
 ↓
Generate Shots
 ↓
Timeline
 ↓
Export
```

---

# 133. 不用做强制 Wizard

用户始终可以：

```text
Skip
```

进入 Studio。

高级用户讨厌被流程锁死。

---

# 134. Project Status Surface

Top Bar 可以展示：

```text
Project Health
```

点击看到：

```text
2 stale shots

1 failed generation

3 continuity warnings
```

---

# 135. 为什么有用

用户制作几十个 Scene 后，

最需要的不是：

```text
更多按钮
```

而是：

> 现在还有什么没处理完？

---

# 136. Scene Health

Scene 卡片：

```text
12 Shots

10 Approved

1 Stale

1 Failed
```

---

# 137. Episode Health

Episode：

```text
8 Scenes

74 Shots

68 Ready

4 Stale

2 Failed
```

---

# 138. Production Dashboard

Beta 可以增加：

```text
Production Overview
```

Alpha 暂不独立做 Dashboard。

Project Tree Summary 足够。

---

# 139. Workflow Workspace

Alpha Workflow Workspace 不是完整节点编辑器。

主要：

```text
Workflow Template List

Provider Mapping

Input Mapping

Validation
```

---

# 140. Workflow Card

```text
SHOT_VIDEO_STANDARD

Provider
ComfyUI Local

Version
v5

Status
Valid
```

操作：

```text
View

Import Version

Set Project Default
```

---

# 141. ComfyUI Workflow

如果需要高级编辑：

可以：

```text
Open in ComfyUI
```

而不是 Studio 内重造节点编辑器。

---

# 142. Workflow Inspector

显示逻辑字段：

```text
prompt

referenceImage

duration

resolution
```

高级展开：

```text
Node Mapping
```

普通用户不需要看到 Node 87。

---

# 143. Settings IA

Settings 分：

```text
Project

AI Models

Providers

Generation

Storage

Appearance

Advanced
```

---

# 144. Project Settings

```text
Language

Aspect Ratio

FPS

Director Profile
```

---

# 145. AI Models

配置：

```text
Director Model

Script Model

Visual Model

Prompt Model

Continuity Model
```

高级模式才展开。

普通模式可以：

```text
Balanced

Quality

Fast
```

---

# 146. Generation Settings

```text
Auto Retry

Retry Count

Local GPU Concurrency

Auto Activate First Version
```

---

# 147. Storage

显示：

```text
Project Size

Assets

Videos

Cache
```

操作：

```text
Verify Project

Cleanup
```

---

# 148. Appearance

Alpha 建议支持：

```text
Light

Dark

System
```

Studio 类应用通常 Dark 使用率较高，但不要只做 Dark。

---

# 149. Visual Style

建议整体：

```text
简洁

低装饰

大面积中性色

明确层级

高密度但不拥挤
```

避免：

```text
过多渐变

夸张玻璃拟态

发光边框

AI 科幻感堆叠
```

这是生产工具，不是 Landing Page。

---

# 150. Material 风格

可以采用：

```text
Material-inspired
```

但控制：

```text
Card Border

Surface Elevation

State Color
```

不要每块都做大卡片。

---

# 151. 圆角

推荐：

```text
6～10px
```

不要大量：

```text
20～30px
```

会降低专业工具密度。

---

# 152. 间距

基本单位：

```text
4px / 8px
```

核心：

```text
8

12

16

24
```

---

# 153. Typography

建议：

```text
12
13
14
16
20
```

层级即可。

Studio 不需要大量大标题。

---

# 154. Status Color

建议语义：

```text
Success
Approved / Ready

Warning
Stale / Attention

Error
Failed / Broken

Info
Running
```

但所有状态都配 Icon / Text。

---

# 155. Dark Mode

媒体 Preview 区：

始终可以保持：

```text
dark surface
```

即使 Light Theme。

这样图片 / 视频观看体验更稳定。

---

# 156. Responsive

这是桌面 Studio。

优先支持：

```text
1280×720
+
1920×1080
+
2K
+
4K
```

不需要为手机做 Studio 编辑界面。

---

# 157. 最小窗口

建议：

```text
1200 × 720
```

再小：

提示：

```text
Window is too small for Studio layout.
```

---

# 158. Alpha 页面清单

真正需要做的页面 / Workspace：

```text
Home

Studio Shell

Story Workspace

Storyboard Workspace

Shot Workspace

Character Library

Location Library

Asset Browser

Timeline Workspace

Workflow Workspace

Settings
```

---

# 159. 核心浮层

```text
Command Palette

Generation Detail

Proposal Review

Version Compare

Provenance

Set Master Confirmation

Job Cancel Confirmation
```

---

# 160. Alpha 最核心组件

```text
StudioShell

TopBar

ProjectExplorer

EditorTabs

MainWorkspace

Inspector

BottomPanel

ShotCard

MediaPreview

VersionStrip

AssetGrid

GenerationQueue

JobProgress

AgentRunPanel

ProposalReview

ContinuityWarningList

Timeline

CommandPalette
```

---

# 161. Component Tree

推荐：

```text
StudioShell
│
├── TopBar
│
├── Sidebar
│   └── ProjectExplorer
│
├── EditorArea
│   ├── EditorTabs
│   └── WorkspaceRouter
│
├── InspectorPanel
│
└── BottomPanel
    ├── GenerationPanel
    ├── AgentPanel
    ├── ContinuityPanel
    └── ConsolePanel
```

---

# 162. Workspace Router

根据：

```text
activeTab.type
```

渲染：

```text
Scene

Shot

Character

Asset

Timeline
```

不是传统：

```text
URL page
```

全部切换。

---

# 163. Router 与 Editor Tab

Router 负责：

```text
Project / Workspace
```

Editor Tabs 负责：

```text
打开资源
```

例如 URL：

```text
/projects/{id}/studio
```

内部 Tabs：

```text
Shot23
Character ShenYi
```

---

# 164. API Read Models

前端不要自行拼大量接口。

建议后端直接提供：

```text
ProjectTreeView

SceneEditorView

ShotInspectorView

CharacterDetailView

AssetBrowserView

GenerationQueueView

AgentRunView

ContinuitySceneView

TimelineView
```

---

# 165. SceneEditorView

一次返回：

```text
Scene

Shots

Thumbnails

Active Asset Status

Generation Status

Continuity Summary
```

避免 Storyboard：

```text
每张卡请求 5 次
```

---

# 166. ShotInspectorView

一次：

```text
Shot

VisualSpec

Characters

Prompt

ActiveAssets

VersionSummary

Continuity

GenerationSummary
```

---

# 167. Lazy Loading

完整：

```text
Generation History

Provenance

Prompt History
```

用户展开时再加载。

---

# 168. Asset Thumbnail Cache

前端不要每次从原始：

```text
4K Image
```

加载。

使用：

```text
Preview Asset
```

---

# 169. Large Project Virtualization

当：

```text
500+ Shots
```

Storyboard Grid 和 Asset Browser：

必须：

```text
Virtualized
```

Alpha 最好一开始就采用虚拟列表 / Grid。

---

# 170. Project Tree Virtualization

如果 Episode 极长：

Tree 也应避免一次渲染几千 Node。

可以：

```text
lazy expand Scene
```

---

# 171. Drag and Drop

Alpha 支持：

```text
Shot reorder

Timeline clip move

Asset import
```

---

# 172. 不允许拖 Asset 直接改变 Domain

例如拖一个角色图到 Shot：

必须解释为：

```text
Bind Reference
```

而不是神秘自动修改。

---

# 173. Storyboard Drag

Shot reorder：

```text
Drag card
```

Backend：

```text
MoveShotCommand
```

不修改 Shot ID。

---

# 174. Optimistic Drag

可以先更新 UI，

后台保存 orderIndex。

失败：

恢复位置。

---

# 175. Loading Project

打开项目时：

不要一次加载：

```text
全部 Asset

全部 Generation

全部 Continuity
```

先：

```text
Project Summary

Tree

Last Workspace
```

---

# 176. Project Open 流程

```text
Open Project
 ↓
Load Project
 ↓
Load Tree
 ↓
Restore Workspace
 ↓
Connect SSE
 ↓
Check Recovery Jobs
```

---

# 177. Interrupted Job

如果发现：

```text
1 Interrupted Job
```

进入 Studio 后顶部轻提示：

```text
An interrupted generation job can be resumed.

[Review]
```

---

# 178. 不弹强制 Modal

用户可能只想打开项目查看内容。

让他决定是否 Resume。

---

# 179. Recovery Center

点击 Review：

显示：

```text
Generate Scene 05

17 / 40 completed

Last run:
Yesterday 22:10

[Resume]
[Cancel]
```

---

# 180. First-run ComfyUI

如果用户点击 Local Generation 但：

```text
ComfyUI 未连接
```

显示：

```text
Local ComfyUI is not connected.

[Configure]
```

不要让 Task 创建后直接神秘失败。

---

# 181. Provider Resolution

生成前 UI 可展示：

```text
Provider
Auto
```

高级用户可 Override：

```text
ComfyUI Local

MiniMax
...
```

---

# 182. 默认隐藏 Provider 复杂度

大多数用户只需要：

```text
Quality

Fast

Local
```

Studio 后端映射 Provider。

---

# 183. Generate Dialog

不要每次点击 Generate 都弹复杂参数 Modal。

默认：

```text
One-click Generate
```

旁边：

```text
▼
```

高级选项：

```text
Provider

Workflow

Seed

Duration
```

---

# 184. Advanced Generation

可以在 Inspector：

```text
Generation Settings
```

中持久配置 Shot Overrides。

---

# 185. Shot Override

优先级：

```text
Shot Override
>
Project Default
>
System Default
```

UI 显示：

```text
Using project default
```

避免用户不知道来源。

---

# 186. AI Suggestion UI

AI 建议不能与正式数据长得完全一样。

建议使用：

```text
Suggestion Surface
```

明确：

```text
AI Proposal
```

标签。

---

# 187. Applied Data

真正写入 Project 后：

不再显示：

```text
AI generated
```

作为主要身份。

它已经成为项目正式数据。

可以 Audit 查看来源。

---

# 188. Director Chat

右侧或 Bottom 可以有：

```text
Ask Director
```

但不要占据主界面。

---

# 189. Natural Language Edit

例如用户：

```text
让 Shot 23 更有压迫感
```

AI 返回：

```text
Proposal:
Camera angle → LOW_ANGLE
Movement → PUSH_IN
Lighting → stronger contrast
```

用户：

```text
Apply
```

---

# 190. Chat ≠ State

即使通过聊天完成修改，

最终仍然必须：

```text
Proposal → Domain
```

---

# 191. Accessibility

至少保证：

```text
Keyboard focus

Tooltip

Contrast

Non-color status

Resizable text
```

Studio 属于高频长时使用工具。

---

# 192. 性能目标

UI 建议目标：

```text
打开 Project Tree
< 300ms

切换 Scene
< 200ms 感知

打开 Shot Inspector
< 200ms

切换本地 Version
< 100ms

Generation Event 更新
< 500ms
```

---

# 193. 不阻塞主线程

视频元信息：

```text
Media Probe
```

放后端。

前端不要：

```text
解析大型媒体
```

---

# 194. Alpha Frontend Phase F1

先实现：

```text
Studio Shell

Project Explorer

Editor Tabs

Storyboard Workspace

Shot Workspace

Inspector

Basic Stores
```

---

# 195. F1 验收

能够：

```text
打开 Project

浏览 Episode / Scene / Shot

打开 Scene

打开 Shot

编辑 Shot 属性

恢复上次布局
```

---

# 196. Phase F2

增加：

```text
Media Preview

Version Strip

Character Library

Location Library

Asset Browser
```

---

# 197. F2 验收

用户可以：

```text
浏览 Image / Video 版本

切换 Active

查看 Character MASTER

Set Master

看到 Stale
```

---

# 198. Phase F3

增加：

```text
Generation Queue

Job Detail

SSE

Retry

Pause

Resume

Cancel
```

---

# 199. F3 验收

Scene 批量生成时：

用户可以持续编辑 Studio，

同时看到：

```text
实时 Job Progress
```

---

# 200. Phase F4

增加：

```text
Agent Panel

Proposal Review

Proposal Diff

Human Review

Agent Resume
```

---

# 201. F4 验收

Director：

```text
Plan Scene
```

完成后：

Studio 显示 Proposal，

用户审核后 Apply。

---

# 202. Phase F5

增加：

```text
Continuity Inspector

Warning List

State Diff

Stale Explanation
```

---

# 203. Phase F6

增加：

```text
Timeline

Clip Replace

Episode Preview

Render
```

完成整个 Alpha Studio。

---

# 204. Codex 第一批任务

```text
Task 01
建立 Studio Shell

Task 02
实现 Resizable Layout

Task 03
实现 Project Explorer

Task 04
实现 Editor Tabs

Task 05
实现 Selection Model

Task 06
实现 Inspector Framework

Task 07
实现 Project Tree Store

Task 08
实现 Scene Workspace

Task 09
实现 Storyboard Grid

Task 10
实现 Shot Card
```

---

# 205. 第二批任务

```text
Task 11
实现 Shot Workspace

Task 12
实现 Media Preview

Task 13
实现 Shot Inspector

Task 14
实现 Camera Editor

Task 15
实现 Prompt Editor

Task 16
实现 Image Version Strip

Task 17
实现 Video Version Strip

Task 18
实现 Active Version Switch

Task 19
实现 Stale Badge

Task 20
实现 Version Compare
```

---

# 206. 第三批任务

```text
Task 21
实现 Character Library

Task 22
实现 Character Detail

Task 23
实现 Character Versions

Task 24
实现 Set Master Flow

Task 25
实现 Location Library

Task 26
实现 Asset Browser

Task 27
实现 Asset Inspector

Task 28
实现 Provenance Drawer

Task 29
实现 Asset Filtering

Task 30
实现 Preview Cache
```

---

# 207. 第四批任务

```text
Task 31
实现 SSE Client

Task 32
实现 Generation Store

Task 33
实现 Job Store

Task 34
实现 Generation Queue

Task 35
实现 Job Detail

Task 36
实现 Retry

Task 37
实现 Pause / Resume

Task 38
实现 Cancel

Task 39
实现 Provider Status

Task 40
实现 Recovery Job UI
```

---

# 208. 第五批任务

```text
Task 41
实现 Agent Store

Task 42
实现 Agent Panel

Task 43
实现 Agent Run Progress

Task 44
实现 Proposal Review

Task 45
实现 Proposal Diff

Task 46
实现 Human Review Flow

Task 47
实现 Agent Resume

Task 48
实现 Proposal Conflict UI

Task 49
实现 Continuity Warning Panel

Task 50
实现 Continuity Inspector
```

---

# 209. 第六批任务

```text
Task 51
实现 Timeline Workspace

Task 52
实现 Timeline Tracks

Task 53
实现 Timeline Clip

Task 54
实现 Clip Drag

Task 55
实现 Clip Trim

Task 56
实现 Replace Asset Version

Task 57
实现 Timeline Preview

Task 58
实现 Render Job UI

Task 59
实现 Command Palette

Task 60
实现 Workspace Persistence
```

---

# 210. 必须测试的 UX 场景

```text
打开大型 Project

切换 Scene

打开 Shot

编辑 Shot

后台生成不中断编辑

新版本生成

Active 不自动切换

Set Character Master

Stale 提示

Scene Batch Generation

Job Partial Failure

Retry Failed

Pause / Resume

Studio 重启恢复 Job

Agent Proposal

Agent Proposal Conflict

Continuity Warning

Missing Asset

Provider Offline

Timeline 使用旧版本
```

---

# 211. 核心 UX 测试 A

用户：

```text
Generate Shot Video
```

新：

```text
v4
```

生成成功。

预期：

```text
v3 ACTIVE

v4 NEW
```

不能：

```text
自动切 v4
```

---

# 212. Test B

Character：

```text
MASTER v4 → v5
```

预期：

```text
23 affected shots
```

显示 Stale。

不能：

```text
23 generation jobs automatically start
```

---

# 213. Test C

Scene Batch 正在生成。

用户打开：

```text
Character Library
```

并编辑其他 Character。

Studio：

```text
不得锁屏或阻塞。
```

---

# 214. Test D

Agent Proposal：

```text
8 Shot → 6 Shot
```

用户在 Proposal 生成后修改 Scene。

Apply：

必须提示：

```text
Proposal outdated
```

---

# 215. Test E

Timeline 使用：

```text
Video v2
```

Shot Active 改：

```text
v3
```

Timeline：

仍：

```text
v2
```

并提示：

```text
New version available
```

---

# 216. 前端禁止事项

## 禁止 1

```text
做成 AI 聊天软件。
```

---

## 禁止 2

```text
所有功能都放 Modal。
```

---

## 禁止 3

```text
所有数据一次加载。
```

---

## 禁止 4

```text
前端自行推导业务状态。
```

例如：

```text
根据文件名判断 Version。
```

---

## 禁止 5

```text
组件直接连接 SSE。
```

---

## 禁止 6

```text
新 Generation 自动切换 Active。
```

---

## 禁止 7

```text
Character MASTER 更新后自动触发生成。
```

---

## 禁止 8

```text
Shot Active Version 自动替换 Timeline。
```

---

## 禁止 9

```text
用颜色作为唯一状态表达。
```

---

## 禁止 10

```text
Alpha 就重做完整 Premiere / ComfyUI。
```

---

# 217. Alpha 最核心用户链

```text
Open Project
 ↓
Select Episode
 ↓
Select Scene
 ↓
Storyboard
 ↓
Open Shot
 ↓
Edit Visual Spec
 ↓
Generate
 ↓
Watch Job Progress
 ↓
Preview New Version
 ↓
Activate
 ↓
Review Continuity
 ↓
Timeline
 ↓
Render
```

---

# 218. AI Director 链

```text
Select Scene
 ↓
AI Director
 ↓
Plan Shots
 ↓
Agent Running
 ↓
Proposal Ready
 ↓
Review Diff
 ↓
Approve
 ↓
Project Tree / Storyboard Update
```

---

# 219. MASTER 链

```text
Character Library
 ↓
Open Character
 ↓
Select Version
 ↓
Set Master
 ↓
Affected Shots Warning
 ↓
Confirm
 ↓
Shots Marked Stale
 ↓
User Chooses Regenerate
```

---

# 220. Continuity 链

```text
Open Scene
 ↓
Continuity
 ↓
3 Warnings
 ↓
Open Shot 19
 ↓
Inspect State Diff
 ↓
Apply Fix / Ignore
 ↓
Downstream Recompute
 ↓
Affected Asset Stale
```

---

# 221. Alpha 前端完成定义

当用户能够：

1. 从 Home 打开 Project；
2. 使用 Project Explorer 浏览 Episode / Scene / Shot；
3. 使用 Storyboard 查看整个 Scene；
4. 打开任意 Shot；
5. 编辑 Shot 属性；
6. 编辑 ShotVisualSpec；
7. 查看 Active Image / Video；
8. 查看历史 Version；
9. 对比版本；
10. 手动切换 Active；
11. 查看 Character Library；
12. 查看 Character Versions；
13. 显式设置 MASTER；
14. MASTER 更新后看到影响范围；
15. 清楚看到 STALE；
16. 使用 Asset Browser；
17. 查看 Asset Provenance；
18. 发起单 Shot Generation；
19. 发起 Scene Batch Generation；
20. 实时看到 Generation Queue；
21. Retry 失败任务；
22. Pause / Resume / Cancel Job；
23. Studio 重启后看到可恢复 Job；
24. 使用 AI Director 规划 Scene；
25. 查看 Agent Run；
26. 审核 Proposal；
27. Proposal 冲突不会覆盖用户修改；
28. 查看 Continuity Warning；
29. 修复或 Ignore Continuity Warning；
30. 将 Video Asset 放入 Timeline；
31. Timeline 可以继续使用旧版本；
32. 手动替换 Timeline Clip Version；
33. Render Episode；
34. 面板布局可调；
35. 软件重启后布局和 Tabs 可恢复。

则：

> **AI 漫剧 Studio Alpha Frontend UX v0.1 成立。**

---

# 222. 至此 Alpha 主体架构已经完整

当前已经形成完整链路：

```text
Product
 ↓
Domain
 ↓
Database
 ↓
Backend API
 ↓
Asset / Version
 ↓
Generation
 ↓
Job Queue
 ↓
AI Director
 ↓
Continuity Engine
 ↓
Frontend Studio UX
```

这意味着现在已经不适合继续无限向下写“大架构文档”。

下一阶段应该开始进入：

> **实现规格 + Codex 开发计划。**

---

# 223. 推荐下一份文档

下一份建议正式做：

# 《AI 漫剧 Studio Alpha 前端 Component / Store / API Contract 详细设计 v0.1》

它会把当前 UX 继续转成真正代码结构：

```text
Vue / React Component Tree

Layout Components

Workspace Components

Inspector Components

Pinia / Zustand Stores

Selection Store

Project Tree Store

Shot Store

Asset Store

Generation Store

Agent Store

Continuity Store

Timeline Store

SSE Event Reducer

API Client

DTO

Frontend Error Model

Optimistic Update

Cache

Virtual List

Workspace Persistence
```

这份文档完成后，就可以直接继续生成：

# 《AI 漫剧 Studio Alpha Codex 分阶段开发任务清单 v0.1》

届时就不再是架构设计，而是可以按：

```text
Phase
→ Epic
→ Task
→ Files
→ Acceptance Criteria
→ Test
```

直接交给 Codex 开始持续开发。
