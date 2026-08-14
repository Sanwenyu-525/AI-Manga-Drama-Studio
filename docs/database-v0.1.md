# AI 漫剧 Studio 数据库与 ER 模型设计 v0.1

> 状态：**draft**（主创定稿，作为领域层与数据库实现的事实源）
> 关联文档：[PRD v0.1](./prd-v0.1.md) · [系统架构设计 v0.1](./architecture-v0.1.md)
> 核心原则：**数据库中的 Project State 是唯一可信状态**；LLM Context、聊天记录、Prompt 都不能作为最终状态来源。

---

## 1. 设计目标

数据库不是单纯保存项目文件，而是整个 Studio 的"长期记忆层"。

它必须负责保存：

- 项目结构
- 剧集
- 场景
- 镜头
- 角色
- 场景资产
- 道具
- Prompt
- 生成任务
- 图片 / 视频
- 版本
- Workflow
- 模型配置
- 连续性状态
- Agent 操作记录

核心原则：

**数据库中的 Project State 是唯一可信状态。**

LLM Context、聊天记录、Prompt 都不能作为最终状态来源。

---

# 2. 核心 ER 结构

```text
Project
  │
  ├── Episode
  │     │
  │     └── Scene
  │           │
  │           └── Shot
  │
  ├── Character
  ├── Location
  ├── Prop
  ├── Asset
  ├── Workflow
  └── Generation
```

Shot 再关联：

```text
Shot
 ├── Character
 ├── Asset
 ├── Prompt
 ├── ContinuityState
 ├── Generation
 └── ShotVersion
```

---

# 3. Project 表

```sql
projects
```

字段：

```text
id                UUID / TEXT PK

name              TEXT

description       TEXT

status            TEXT

style_config      JSON

default_language  TEXT

aspect_ratio      TEXT

fps               INTEGER

created_at        DATETIME

updated_at        DATETIME
```

status 建议：

```text
draft
active
archived
completed
```

---

# 4. Episode 表

```sql
episodes
```

字段：

```text
id

project_id

episode_number

title

source_text

script_text

summary

status

created_at

updated_at
```

关系：

```text
Project 1:N Episode
```

---

# 5. Scene 表

```sql
scenes
```

字段：

```text
id

episode_id

scene_number

name

location_id

time_of_day

lighting

weather

mood

description

scene_order

status

created_at

updated_at
```

---

# 6. Location 表

地点不要直接写死在 Scene 中。

建立：

```sql
locations
```

字段：

```text
id

project_id

name

description

visual_prompt

style_prompt

reference_asset_id

created_at

updated_at
```

例如：

```text
学校体育馆

主角卧室

城市天台

地下停车场
```

这样多个 Scene 可以复用同一个 Location。

---

# 7. Character 表

```sql
characters
```

字段：

```text
id

project_id

name

alias

gender

age_description

appearance

personality

visual_prompt

negative_prompt

default_costume_id

status

created_at

updated_at
```

注意：

Character 保存的是"身份"。

服装单独管理。

---

# 8. Costume 表

```sql
costumes
```

字段：

```text
id

character_id

name

description

visual_prompt

reference_asset_id

created_at
updated_at
```

例如：

```text
沈亦

├── 校服
├── 篮球队服
├── 日常服
└── 比赛服
```

---

# 9. Prop 表

```sql
props
```

字段：

```text
id

project_id

name

description

visual_prompt

reference_asset_id

created_at

updated_at
```

例如：

```text
篮球

手机

项链

武器

汽车
```

---

# 10. Shot 表

这是整个数据库最核心的表。

```sql
shots
```

建议字段：

```text
id

scene_id

shot_number

shot_order

title

description

shot_type

camera_angle

camera_movement

composition

lens

duration

action

emotion

dialogue

environment_description

image_prompt

video_prompt

negative_prompt

previous_shot_id

next_shot_id

active_image_version_id

active_video_version_id

status

created_at

updated_at
```

Shot status：

```text
draft

planned

storyboard_ready

image_generating

image_ready

video_generating

video_ready

approved

failed
```

---

# 11. Shot 与 Character 关系

因为一个 Shot 可能有多个角色。

使用中间表：

```sql
shot_characters
```

字段：

```text
id

shot_id

character_id

costume_id

role

position

pose

action

emotion

screen_direction
```

例如：

```text
Shot 08

沈亦
位置：画面左侧

顾言
位置：画面右侧
```

这对连续性非常重要。

---

# 12. Shot 与 Prop 关系

```sql
shot_props
```

字段：

```text
id

shot_id

prop_id

character_id

position

state
```

例如：

```text
篮球

held_by = 沈亦

state = right_hand
```

---

# 13. Asset 表

所有真实文件统一进入 Asset System。

```sql
assets
```

字段：

```text
id

project_id

type

name

file_path

thumbnail_path

mime_type

width

height

duration

file_size

metadata

created_at
```

Asset type：

```text
image

video

audio

reference

document

workflow

thumbnail
```

---

# 14. Asset Relation

为了让资产可以挂在不同对象上，推荐建立：

```sql
asset_links
```

字段：

```text
id

asset_id

entity_type

entity_id
relation_type
```

例如：

```text
asset_001

entity_type = character

entity_id = character_001

relation_type = face_reference
```

或者：

```text
relation_type = storyboard
```

这样不用不断增加：

```text
character_asset

shot_asset

scene_asset
```

---

# 15. Prompt 表

Prompt 不建议全部只写在 Shot 里。

后期需要管理历史 Prompt。

```sql
prompts
```

字段：

```text
id

project_id

entity_type

entity_id

prompt_type

provider

model

content

negative_content

metadata

created_at
```

prompt_type：

```text
character

scene

image

video

storyboard

rewrite
```

---

# 16. Generation 表

每一次模型调用都必须记录。

```sql
generations
```

字段：

```text
id

project_id

shot_id

generation_type

provider

model

workflow_id

status

input_parameters

output_asset_id

error_message

cost

started_at

completed_at

created_at
```

generation_type：

```text
text

image

video

audio

vision_review
```

status：

```text
pending

queued

running

success

failed

cancelled

retrying
```

---

# 17. Generation Attempt

建议不要覆盖失败请求。

建立：

```sql
generation_attempts
```

字段：

```text
id

generation_id

attempt_number

request_payload

response_payload

error

started_at

completed_at
```

这样以后可以分析：

```text
为什么失败

失败多少次

哪种 Workflow 最稳定
```

---

# 18. Shot Version

Shot 本身也要支持版本。

```sql
shot_versions
```

字段：

```text
id

shot_id

version_number

data_snapshot

created_by

created_at
```

data_snapshot 保存：

```json
{
  "camera_angle": "...",
  "action": "...",
  "image_prompt": "...",
  "duration": 4
}
```

---

# 19. Media Version

图片和视频建议单独做版本。

```sql
media_versions
```

字段：

```text
id

shot_id

asset_id

media_type

version_number

generation_id

is_active

rating

notes

created_at
```

例如：

```text
Shot 007

Image V1
Image V2
Image V3
```

用户可以选择：

```text
V3 = Active
```

但 V1、V2 不删除。

---

# 20. Continuity State

这是整个产品未来非常核心的数据。

```sql
continuity_states
```

字段：

```text
id

shot_id

character_id

position

body_direction

face_direction

pose

costume_id

emotion

held_prop_id

lighting

camera_state

action_start

action_end

custom_state

created_at

updated_at
```

---

# 21. Shot Transition

为了处理相邻镜头连接：

```sql
shot_transitions
```

字段：

```text
id

from_shot_id

to_shot_id

transition_type

continuity_score

issues

suggestions

approved

created_at
```

transition_type：

```text
direct

cut

match_cut

fade

camera_move

action_continuation
```

---

# 22. Continuity Example

Shot 12：

```text
人物：沈亦

位置：画面右侧

球：右手

动作结束：急停

身体方向：左前方
```

Shot 13：

```text
人物：沈亦

位置：画面右侧

球：右手

动作开始：后撤
```

Continuity Engine 可以判断：

```text
动作连续

人物方向一致

道具状态一致
```

如果 Shot 13 写成：

```text
球突然变成左手
```

则产生 Issue。

---

# 23. Workflow 表

```sql
workflows
```

字段：

```text
id

project_id

name

type

provider

definition

version

is_default

created_at

updated_at
```

Workflow type：

```text
image

video

storyboard

review

production
```

---

# 24. ComfyUI Workflow

ComfyUI Workflow 建议另外保存：

```sql
comfyui_workflows
```

字段：

```text
id

workflow_id

workflow_json

api_format_json

parameter_schema

output_mapping

created_at
```

parameter_schema 示例：

```json
{
  "prompt": {
    "node": "12",
    "field": "text"
  },

  "seed": {
    "node": "18",
    "field": "seed"
  }
}
```

---

# 25. Model Provider

```sql
providers
```

字段：

```text
id

name

provider_type

base_url

configuration

enabled

created_at
```

provider_type：

```text
llm

image

video

vision

audio
```

API Key 不建议明文存数据库。

桌面端建议放：

```text
OS Keychain / Secure Storage
```

---

# 26. Model 表

```sql
models
```

字段：

```text
id

provider_id

model_name

display_name

capabilities

configuration

enabled
```

capabilities：

```json
{
  "text": true,
  "vision": true,
  "image_generation": false
}
```

---

# 27. Agent Session

虽然 Project 是核心，但仍然需要保存 Agent 操作。

```sql
agent_sessions
```

字段：

```text
id

project_id

created_at

updated_at
```

---

# 28. Agent Messages

```sql
agent_messages
```

字段：

```text
id

session_id

role

content

tool_calls

created_at
```

role：

```text
user

assistant

system
tool
```

但注意：

这里是历史记录。

不是 Project State。

---

# 29. Agent Action Log

建议增加：

```sql
agent_actions
```

字段：

```text
id

project_id

session_id

action_type

entity_type

entity_id

before_state

after_state

reason

created_at
```

例如：

```text
AI 修改 Shot 8

camera:

medium shot
→
close-up
```

这可以实现：

```text
Undo

Audit

AI 修改追踪
```

---

# 30. Workflow Run

```sql
workflow_runs
```

字段：

```text
id

project_id

workflow_id

status

progress

started_at

completed_at
```

---

# 31. Workflow Task

```sql
workflow_tasks
```

字段：

```text
id

workflow_run_id

task_type

entity_type

entity_id

status

dependencies

input

output

retry_count

error

started_at

completed_at
```

例如：

```text
task_01

generate_image

shot_01
```

---

# 32. Timeline Item

后续做剪辑时间线时：

```sql
timeline_items
```

字段：

```text
id

episode_id

track_type

asset_id
shot_id

start_time

end_time

track_index

metadata
```

track_type：

```text
video

audio

voice

subtitle

music
```

第一版可以先不实现。

---

# 33. Project Settings

```sql
project_settings
```

字段：

```text
project_id

default_llm

default_image_provider

default_video_provider

default_vision_provider

default_image_workflow

default_video_workflow

settings
```

这样不同项目可以用不同模型。

---

# 34. 推荐数据库关系

核心关系：

```text
Project
 │
 ├─1:N─ Episode
 │        │
 │        └─1:N─ Scene
 │                 │
 │                 └─1:N─ Shot
 │
 ├─1:N─ Character
 │
 ├─1:N─ Location
 │
 ├─1:N─ Prop
 │
 ├─1:N─ Asset
 │
 ├─1:N─ Workflow
 │
 └─1:N─ Generation
```

Shot：

```text
Shot
 │
 ├─N:M─ Character
 ├─N:M─ Prop
 ├─1:N─ Generation
 ├─1:N─ MediaVersion
 ├─1:N─ Prompt
 ├─1:N─ ContinuityState
 └─1:N─ ShotVersion
```

---

# 35. ER 图

```text
PROJECT
│
├──────── EPISODE
│            │
│            └──── SCENE
│                     │
│                     └──── SHOT
│                           │
│                           ├──── SHOT_CHARACTER ─── CHARACTER
│                           │
│                           ├──── SHOT_PROP ──────── PROP
│                           │
│                           ├──── PROMPT
│                           │
│                           ├──── GENERATION
│                           │          │
│                           │          └──── ASSET
│                           │
│                           ├──── MEDIA_VERSION
│                           │
│                           ├──── SHOT_VERSION
│                           │
│                           └──── CONTINUITY_STATE
│
├──────── CHARACTER
│            │
│            └──── COSTUME
│
├──────── LOCATION
│
├──────── PROP
│
├──────── ASSET
│
├──────── WORKFLOW
│            │
│            └──── COMFYUI_WORKFLOW
│
└──────── WORKFLOW_RUN
             │
             └──── WORKFLOW_TASK
```

---

# 36. 第一版 MVP 数据表

不要第一天就建全部表。

MVP 第一轮只需要：

```text
projects

episodes

scenes

shots

characters

shot_characters

assets

generations

media_versions

providers
models
```

第二轮加入：

```text
locations

costumes

props

prompts

workflows

comfyui_workflows
```

第三轮：

```text
continuity_states

shot_transitions

shot_versions

workflow_runs

workflow_tasks

agent_actions
```

---

# 37. SQLite 第一版建议

第一阶段推荐：

```text
SQLite
```

而不是直接 PostgreSQL。

原因：

- 桌面应用本地优先
- 无服务器依赖
- 一个项目一个 DB 也可以
- 备份简单
- 部署简单
- 性能完全足够 MVP

后续如果推出：

```text
Cloud Studio

Team Collaboration
```

再迁移：

```text
PostgreSQL
```

---

# 38. 数据库模式选择

推荐：

```text
一个 Studio 主数据库
+
项目目录文件
```

而不是：

```text
每一个 Project 一个独立 SQLite
```

第一版 Studio DB：

```text
studio.db
```

管理所有项目元信息。

项目媒体放：

```text
/projects/{project_id}/
```

---

# 39. 项目目录设计

```text
projects/

  project_xxx/

    source/

    characters/

    locations/

    references/

    storyboard/

    images/

    videos/

    audio/

    workflows/

    exports/

    cache/
```

数据库只保存相对路径。

例如：

```text
images/shot_005/v003.png
```

而不是：

```text
C:\Users\xxx\Desktop\...
```

这样整个项目可以迁移。

---

# 40. 文件命名规范

建议系统自动生成：

```text
EP01_SC03_SH005_IMG_V003.png
```

视频：

```text
EP01_SC03_SH005_VIDEO_V002.mp4
```

Storyboard：

```text
EP01_SC03_SH005_STORYBOARD_V001.png
```

不要依赖用户手动命名。

---

# 41. 删除策略

核心数据不要直接硬删除。

建议增加：

```text
deleted_at
```

实现 Soft Delete。

尤其：

- Shot
- Scene
- Asset
- Generation
- Version

因为 AI 很可能误删。

用户必须可以 Undo。

---

# 42. 数据变更策略

所有 AI 自动修改重要对象时：

```text
Before State
↓
Agent Action
↓
After State
```

至少保留：

```text
shot_versions
```

这样 AI Director 才敢大胆修改项目。

---

# 43. 最重要的数据模型原则

必须坚持：

### 第一

```text
Project State ≠ LLM Context
```

### 第二

```text
Shot 是生产原子单位
```

### 第三

```text
Asset 与业务对象解耦
```

### 第四

```text
Generation 永不覆盖历史
```

### 第五

```text
Provider 与业务逻辑解耦
```

### 第六

```text
AI 修改必须可追踪
```

### 第七

```text
所有长任务必须有状态
```

---

# 44. 第一阶段真正需要实现的数据链路

```text
Create Project
      ↓
projects

Import Script
      ↓
episodes

AI Analyze
      ↓
scenes

AI Storyboard
      ↓
shots

Generate Image
      ↓
generations

ComfyUI Result
      ↓
assets

Create Version
      ↓
media_versions

Update Shot
      ↓
active_image_version
```

到这里，数据库 MVP 就形成完整闭环。

---

# 45. 数据库之后的开发顺序

数据库领域模型确定后，下一阶段应该依次实现：

```text
1. Domain Entity

2. Repository Layer

3. Service Layer

4. REST API

5. Project CRUD

6. Scene CRUD

7. Shot CRUD

8. Asset Service

9. Generation Service

10. ComfyUI Adapter
```

然后再进入：

```text
Studio 前端
```

最后才加入：

```text
AI Director
```

原因非常简单：

**先让软件本身会管理漫剧，再让 AI 学会操作这个软件。**
