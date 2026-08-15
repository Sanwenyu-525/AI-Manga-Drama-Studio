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

revision          INTEGER NOT NULL DEFAULT 1  （乐观锁 P1：PATCH 需提交 revision，冲突 409）
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

analysis_key

status

created_at

updated_at

revision        INTEGER NOT NULL DEFAULT 1  （乐观锁 P1）
```

关系：

```text
Project 1:N Episode
```

analysis_key（P1-E1-T01）：最后一次剧集分析（analyze）的幂等键 —— 实际送入 LLM 的
原文截断文本的 hash 前缀；同一 key 重复提交为 no-op，key 变化触发 AI 场景 replace。
内部字段，不进 API。

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

analysis_key

storyboard_key

status

created_at

updated_at

revision        INTEGER NOT NULL DEFAULT 1  （乐观锁 P1）
```

analysis_key（P1-E1-T01）：所属剧集分析的幂等键；NOT NULL 表示 AI 创建的场景
（replace 时软删除的目标）。storyboard_key：该场景最后一次分镜规划（generate-shots）
的幂等键。均为内部字段，不进 API。

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

P2-T007/T008（角色视觉版本 + MASTER 指针）：

```text
character_versions 表
```
字段：

```text
id

character_id        -- FK → characters.id，ON DELETE CASCADE，索引

version_number      -- 组内自增（v1/v2...），UNIQUE(character_id, version_number)

asset_id            -- FK → assets.id，该版本的代表视觉资产（MVP 用 Asset Import 导入的角色参考图）

name                -- 可选，本版本名称

description         -- 可选，本版本说明

status              -- active | stale | archived；新建默认 stale，激活后才为 active

checksum            -- 可选，代表资产的 SHA-256

created_at

updated_at
```
`characters` 表新增字段：

```text
master_version_id   -- FK → character_versions.id（可空，ADR-002 指针模式）
```

语义：

- MASTER 指针（`characters.master_version_id`）指向项目正式认可的标准角色形象（domain-model-design §32/§39-41）。
- 新 Shot 默认绑定 Character.master_version_id；已生成 Shot 不自动更新，只标记 STALE。
- 版本激活（active）时：旧 active 置 stale → 新版本置 active → master_version_id 指向新版本（单事务）。
- 多个参考图（Front / Side / Full Body）属于同一版本内部，因此指针落在"版本"而非"资产"（§39）。

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

active_image_asset_id

active_video_asset_id

active_prompt_version_id   （ADR-002 便捷指针，权威在 prompts.active_version_id）

analysis_key

status

created_at

updated_at
```

analysis_key（P1-E1-T01）：分镜规划（generate-shots）的幂等键；NOT NULL 表示
AI 创建的镜头（replace 时软删除的目标）。内部字段，不进 API。

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

# 10.5 数据库不变量（P1-E1-T02）

业务不变量由 Service 与数据库共同保护（软删除行不参与唯一性，编号可复用）：

```text
scenes:          UNIQUE (episode_id, scene_number)  WHERE deleted_at IS NULL
shots:           UNIQUE (scene_id, shot_number)     WHERE deleted_at IS NULL
                 UNIQUE (scene_id, shot_order)      WHERE deleted_at IS NULL
shot_characters: UNIQUE (shot_id, character_id)
assets:          UNIQUE (version_group_id, version_number) WHERE version_group_id IS NOT NULL AND deleted_at IS NULL   （ADR-001：版本组内版本号唯一）
generations:     INDEX (status, created_at)                            （Worker DB-poll 查询）
```

- revision 乐观并发为**数据库级条件更新**：`UPDATE ... WHERE id = ? AND revision = ?`，
  两个持有同一旧 revision 的写入者只有一个成功（另一个 409），杜绝先读后写丢失更新。
- reorder 必须提交场景内完整且无重复的镜头 ID 集合（部分/重复/跨场景 → 422，数据不变）；
  编号在两阶段事务内重排（先整体移开、再赋终值），避免唯一约束冲突。
- 迁移先检测历史重复并**失败而非静默丢弃**（`b1e2f3a4c5d6`）。

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

# 15. Prompt 表（ADR-002 已落地：prompts + prompt_versions）

> **ADR-002（docs/adr/ADR-002-prompt-versioning.md）已实现（2026-08）**：
> Prompt 版本化正式落地，Shot 内联 Prompt（`image_prompt/video_prompt/negative_prompt`）
> 保留为**弃用写透缓存**（由 PromptService 同步），权威版本在 `prompts.active_version_id`。
> `shots.active_prompt_version_id` 为便捷指针（SHOT_IMAGE 优先）；
> `generations.prompt_version_id` 记录生成使用的具体版本（provenance）。

`prompts`（每目标每类型一行，active 权威）：

```sql
CREATE TABLE prompts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    target_type TEXT NOT NULL,      -- SHOT（首期；后续 CHARACTER/LOCATION/...）
    target_id TEXT NOT NULL,
    prompt_type TEXT NOT NULL,      -- SHOT_IMAGE | SHOT_VIDEO（首期）
    active_version_id TEXT,         -- 权威 active 指针 → prompt_versions.id
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
-- 索引: idx_prompts_target(target_type, target_id)
--        idx_prompts_type(target_type, target_id, prompt_type)
```

`prompt_versions`（不可变版本链，编辑产生 vN+1）：

```sql
CREATE TABLE prompt_versions (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL REFERENCES prompts(id),
    version_number INTEGER NOT NULL,
    positive_prompt TEXT,
    negative_prompt TEXT,
    structured_spec_json TEXT,      -- Canonical Prompt Spec（Phase 7 Prompt Agent 产出）
    provider TEXT,
    model TEXT,
    generated_by TEXT,              -- user | agent | migration | system
    parent_version_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (prompt_id, version_number)
);
-- 索引: idx_prompt_versions_prompt(prompt_id, version_number)
```

Shot 表新增：`active_prompt_version_id`（便捷指针）。

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

# 16.3 Generation Input / Output（P3-T012/T013，已落地）

generation_inputs（生成请求的输入引用，随 Generation 创建事务写入）：

```text
id              TEXT PK
generation_id   TEXT FK → generations.id（索引）
input_type      TEXT（当前：prompt_version / shot）
reference_type  TEXT（当前：prompt_version / shot）
reference_id    TEXT
role            TEXT（当前默认 primary）
order_index     INTEGER DEFAULT 1000
metadata_json   TEXT
```

generation_outputs（生成结果的资产映射，随完成事务写入）：

```text
generation_id   TEXT PK（复合）
asset_id        TEXT PK（复合）→ assets.id（索引）
role            TEXT（当前：primary）
order_index     INTEGER DEFAULT 1000
```

---

# 16.5 Generation Claim / Lease / 退避字段（P1-E2-T02，已落地）

generations 表（§16）追加 4 个 nullable 字段：

```text
claim_token      认领令牌（谁在跑）

claimed_at       认领时间

lease_expires_at lease 到期时间（进度心跳续期；过期 → 崩溃恢复重排队）

next_attempt_at  重试退避到期时间（未到期的 retrying 行不可认领）
```

状态迁移由 app/generations/state.py 集中校验（非法迁移 → 409）。

**P5 补充语义（不新增列，复用 status 列）：**

```text
interrupted   P5-T016 异常任务检测：running 行 lease 过期且 attempts 达预算 → 系统中断（终态，区别于用户失败 failed）
cancelling    P5-T015 Cancel 持久化：用户取消 running 行 → cancelling（持久标记，重启不丢）；worker 完成前检查 DB 并最终化为 cancelled
```

- `interrupted`、`cancelling` 均不新增 DB 列，status 列即可表达。
- Cancel 持久化路径：`cancel_generation` 仅对 running 行写 `cancelling`；worker 在完成前检查 DB（而非仅进程内 `_cancelled` 集合）并最终化 cancelled。
- 队列级 Pause/Resume（P5-T013/T014）为**进程内标志**，不落库（见 api-event-contract §142 的 /generations/pause|resume|queue-status 端点）。

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

# 19. Asset Version（ADR-001：media_versions 已合并）

> **ADR-001（docs/adr/ADR-001-asset-self-versioning.md）已实现（2026-08）**：
> `media_versions` 表已删除，版本语义并入 `assets` 自版本化：
> - `assets.version_group_id`：确定性组 ID `vg:shot:{shot_id}:{PURPOSE}`（PURPOSE = SHOT_IMAGE / SHOT_VIDEO）
> - `assets.version_number`：组内从 1 递增（max+1 + 唯一索引 `uq_assets_version` 兜底）
> - `assets.status / source_type / checksum / parent_asset_id / generation_id` 见 §13
> - `shots.active_image_asset_id / active_video_asset_id` 指向 Asset（每镜头每媒体类型至多一个 active）
> - 版本不可变语义保留：新生成产生新 Asset 行，旧行永不覆盖；`Set Active` 只翻转指针

字段（`assets` 表）：

```text
id

project_id

type

name

file_path

thumbnail_path

mime_type

width / height / duration / file_size

meta_json

generation_id        （原 source_generation_id，ADR-001 改名）

version_group_id     （ADR-001）

version_number       （ADR-001）

status               （ready|processing|stale|missing|corrupted|failed|archived）

source_type          （generated|imported|edited|derived|captured）

checksum             （SHA-256）

parent_asset_id      （派生关系，Generation Input 仍必须记录）

deleted_at

created_at
```

例如：

```text
Shot 007 Image 版本组 vg:shot:007:SHOT_IMAGE

Image V1 (asset_a)   ← active
Image V2 (asset_b)
Image V3 (asset_c)
```

用户可以选择：

```text
V3 = Active   →  shots.active_image_asset_id = asset_c
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

> **已落地（P4-T004）**：编辑型 `workflows` 全量表（编辑器/上传/变更集）本期不建；
> 落地为只读注册表 `workflow_templates` + `workflow_versions`（见下表后的 P4-T004 说明）。
> 本表保留原始设计参考。

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

> **P4-T004 已落地（2026-08）：WorkflowTemplate 目录注册表（只读，YAGNI）**
> 上文 `workflows` / `comfyui_workflows` 的完整编辑器/上传/差异比对 **本期不做**。
> 落地的是**只读目录注册表**：把本地 `workflows/*.json`（API 格式模板）幂等扫描并
> 快照入库，供 Resolver 解析、目录 API 与版本列表使用（哈希快照，替换差异比对）。
>
> 占位符说明（**P4-T005**）：单个模板允许哪些 `$PLACEHOLDER` token、哪些是**必需**（preflight）、
> 以及逻辑参数名 → token 的映射与类型/范围校验，由代码层声明式 `WorkflowSchema`
> （`providers/comfyui/workflow_schema.py`，`workflow_templates`/`workflow_versions` 不重复存）。

`workflow_templates`（每个 workflow_id 模板一行）：

```text
id                    TEXT PK（UUID）
name                  TEXT
workflow_type         TEXT（image | video，按文件名/约定推断，默认 image）
workflow_id           TEXT（JSON 文件 id，即 settings.workflows_dir 下文件名 stem，如 default_image_api）
active_version_id     TEXT（权威活动版本指针 → workflow_versions.id）
created_at / updated_at
-- UNIQUE (workflow_id, workflow_type)
```

`workflow_versions`（不可变哈希快照；文件内容变化产生 vN+1 并重新激活）：

```text
id                    TEXT PK（UUID）
template_id           TEXT FK → workflow_templates.id（ON DELETE CASCADE）
version_number        INTEGER（从 1 递增）
file_hash             TEXT（模板文件 SHA-256）
file_path             TEXT（相对 workflows_dir 的文件名）
status                TEXT（active | superseded | archived）
created_at
-- UNIQUE (template_id, version_number)
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

字段（P1 已落地，与实现一致）：

```text
project_id                    TEXT PK → projects.id（ON DELETE CASCADE）
language                      TEXT DEFAULT 'zh-CN'
default_llm_provider          TEXT
default_llm_model             TEXT
default_image_provider        TEXT
default_image_model           TEXT
default_video_provider        TEXT
default_video_model           TEXT
default_voice_provider        TEXT
default_voice_model           TEXT
default_image_workflow_id     TEXT
default_video_workflow_id     TEXT
auto_retry                    INTEGER DEFAULT 1
max_retry_count               INTEGER DEFAULT 3
auto_save                     INTEGER DEFAULT 1
continuity_enabled            INTEGER DEFAULT 1
auto_activate_new_generation  INTEGER DEFAULT 0
settings_json                 TEXT（未知键合并存储）
updated_at                    DATETIME
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
 ├─1:N─ Asset（版本化，ADR-001）
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

assets（版本化，ADR-001）

generations

providers
models
```

第二轮加入：

```text
locations

costumes

props

prompts（+ prompt_versions，ADR-002 已实现）

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

---

### 40.1 导入资产命名（P3-T003）

外部文件导入为项目级（**project-scope**，无 shot / version 归属）Asset，存放于
`<proj>/imported/` 目录，命名与生成资产区分：

```text
<PROJECT_ID>_IMP_001.png
<PROJECT_ID>_IMP_002.jpg
```

- 命名由系统自动生成（不要依赖用户手动命名）。
- `source_type = imported`，`version_group_id / version_number` 为 NULL。
- 元数据由 MediaProbeService（纯标准库）探测：图片解析宽高/格式/模式；视频/音频
  用 ffprobe（不可用时返回空元数据，绝不报错）。

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