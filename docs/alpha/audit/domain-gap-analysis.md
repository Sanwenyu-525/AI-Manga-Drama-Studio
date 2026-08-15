# 数据模型差距审查报告（P0-T003）

> Phase 0 审查 · AI 漫剧 Studio · 只读分析（未修改任何代码）
> 审查对象：MVP 0.1（Stage A–D + P1 收尾）现状 vs Alpha 目标领域模型
> 目标文档：`docs/incoming/domain-model-design-v0.1.md`、`docs/incoming/database-schema-design-v0.1.md`
> 现状事实源：`docs/database-v0.1.md`（MVP 版）、`docs/api-event-contract-v0.1.md`

**重要语境**：当前代码的"事实文档"是 MVP 版 `database-v0.1.md` / `api-event-contract-v0.1.md`，其模型约束（`deleted_at` 命名、`revision` 字段、`EpisodeStatus` 枚举等）与 Alpha 目标设计（`archived_at`、`order_index REAL`、`parent_generation_id` 等）并不完全一致。因此本报告区分「MVP 已实现但命名/细部冲突」与「Alpha 新增能力缺失」两类缺口。

---

## 1. 逐实体核对（对照 Alpha 目标领域模型）

| Alpha 目标实体 | 现状 | 证据（文件+字段） | 判定 |
|---|---|---|---|
| **Project** | 已实现 | `backend/app/db/models/project.py`：`id/name/description/status/style_config/default_language/aspect_ratio/fps/cover_path/deleted_at/created_at/updated_at` | **部分实现** |
| **ProjectSetting** | **缺失** | 全仓库无 `project_settings` 表/模型（已 grep `__tablename__` 确认） | 缺失 |
| **Episode** | 已实现 | `backend/app/db/models/episode.py`：`id/project_id/episode_number/title/source_text/script_text/summary/analysis_key/status/deleted_at/...` | 部分实现（缺 description/target_duration/order_index/source_document_id） |
| **Scene** | 已实现 | `backend/app/db/models/scene.py`：`id/episode_id/scene_number/name/location_id/time_of_day/lighting/weather/mood/description/scene_order/analysis_key/storyboard_key/status/deleted_at` | 部分实现（`location_id` 是弱 Text 引用，无 locations 表；无 narrative_purpose/estimated_duration/continuity_state_id） |
| **Shot** | 已实现 | `backend/app/db/models/shot.py`：`shot_type/camera_angle/camera_movement/lens/duration/action/emotion/dialogue/environment_description/image_prompt/video_prompt/negative_prompt/previous_shot_id/next_shot_id/active_image_version_id/active_video_version_id/status/dirty_state/revision/analysis_key` | **部分实现，且与目标有结构冲突** |
| **ShotVisualSpec** | **缺失**（字段内联进 Shot） | 无 `shot_visual_specs` 表；`shot.py` 直接持有 `action/emotion/environment_description/lens` 等 | 缺失/结构冲突 |
| **Character** | 已实现（MVP 级别） | `backend/app/db/models/character.py`：身份字段 + `revision` + 软删；`visual_prompt` 内联 | 部分实现 |
| **CharacterVersion（含 MASTER）** | **缺失** | 无 `character_versions` 表；`character.py` 无 `active_version_id/master_version_id`；`default_costume_id` 是弱 Text 引用 | **缺失（Alpha 关键缺口）** |
| **Location** | **缺失** | `scene.py.location_id` 指向不存在的 locations 表；无 Location/LocationVersion 模型 | **缺失** |
| **Costume** | **缺失** | `character.py.default_costume_id` 弱引用 | 缺失 |
| **Prop** | **缺失** | 无 | 缺失 |
| **Asset** | 部分实现 | `backend/app/db/models/asset.py`：`id/project_id/type/name/file_path/thumbnail_path/mime_type/width/height/duration/file_size/meta_json/source_generation_id/deleted_at/created_at` | **部分实现**（缺 source_type/storage_provider/checksum/parent_asset_id/version_group_id/status） |
| **Prompt / PromptVersion** | **缺失** | 无 prompts/prompt_versions 表；Prompt 字符串内联在 `shot.image_prompt` 与 `generation.parameters` 中 | **缺失（Alpha 核心缺口）** |
| **Generation** | 已实现 | `backend/app/db/models/generation.py`：`type/provider/model/workflow_id/status/parameters/output_asset_id/error_message/progress/stage/retry_of/attempts/max_attempts/claim_token/claimed_at/lease_expires_at/next_attempt_at/cost/provider_ref/deleted_at/...` | **部分实现（immutable 未落库强制；缺 parent_generation_id）** |
| **GenerationInput / GenerationOutput** | **缺失** | 无 `generation_inputs/generation_outputs` 关系表；输入输出靠 `generation.parameters`(JSON) + `generation.output_asset_id`(弱引用) | **缺失（Alpha 关键缺口）** |
| **Job / JobTask / JobTaskDependency** | **缺失** | 无 jobs/job_tasks/job_task_dependencies 表；MVP 用 `generations` 表自身做队列（`status in queued/retrying` + claim/lease） | 缺失 |
| **WorkflowTemplate / WorkflowVersion** | **缺失**（仅内置文件目录） | `workflows.py` 只读列出 `workflows/*.json`；无 workflow_templates/workflow_versions 表；`generation.workflow_id` 是弱字符串 | 缺失 |
| **ResourceDependency** | **缺失** | 无 `resource_dependencies` 表；`shot.dirty_state` 是手工标记 | 缺失 |
| **ContinuityState** | **缺失** | 无 `continuity_states` 表；`shot_characters.position/pose/action/emotion/screen_direction` 仅预留字段但未建模状态链 | **缺失（Alpha 关键缺口）** |
| **Timeline / TimelineTrack / TimelineClip** | **缺失** | 无 | 缺失 |
| **Workspace / SourceDocument / 全局 DB** | **缺失** | 单 SQLite（未按 project-db 拆分） | 缺失 |
| **AuditLog / DomainEvent 持久化** | **部分（仅内存 Bus）** | `events/bus.py` 内存 EventBus；无 `audit_logs` / `domain_events` 表 | 缺失 |

---

## 2. 与目标设计的冲突点（逐条）

### ① Shot 直接持有 Prompt 字符串，而非 PromptVersion 引用（违反领域规则 1 "Shot != Prompt"）
- 证据：`shot.py:49-51` `image_prompt/video_prompt/negative_prompt` 为内联 Text；`GenerationCreate.prompt`（`domain/generation.py:12`）与 `generation_service.py` 将 prompt 直接塞进 `parameters` JSON（`generation_service.py:79-88`）。
- 不存在 `prompts` / `prompt_versions` 表。Alpha 目标要求 `Shot → Prompt → PromptVersion`，`Shot.active_prompt_version_id` 指向版本。

### ② Active 版本表达方式冲突（MVP 用 `shot.active_image_version_id`，目标用 `shot.active_image_asset_id`）
- 证据：`shot.py:55-56` `active_image_version_id / active_video_version_id` 指向 `media_versions.id`；`media_version.py` 是独立的**不可变** `MediaVersion` 行（`version_number`、`is_active`，`media_version.py:23-32`）。
- Alpha 目标 `Asset` 自带 `version_group_id + version_number`（`assets` 表 `active_image_asset_id` 直接指 asset）。**两套版本模型并存是 Alpha 必须决策的迁移点**：MVP 的 `media_versions` 表在目标设计中不存在（Asset 自身版本化）。

### ③ Project 字段冲突
- MVP：`projects` 有 `style_config(default_language/aspect_ratio/fps)` 与 `cover_path`；Alpha：`projects` 有 `project_type/cover_asset_id/default_resolution/active_episode_id/last_opened_at/archived_at`，生成策略拆到 `project_settings`。
- 证据：`project.py:19-24`。
- MVP 用 `deleted_at`；Alpha 用 `archived_at`（domain §11、database §11）。命名不统一（见冲突⑦）。

### ④ 软删除字段命名不统一（`deleted_at` vs Alpha `archived_at`）
- 证据：核对 8 个模型，`project/episode/scene/shot/character/asset/generation` 全部是 `deleted_at`；`media_version` 无任何归档字段。Alpha 设计统一 `archived_at`。会触发广泛 MIGRATE。

### ⑤ Generation 是否 immutable —— 代码层面"不覆盖"但有状态可变字段
- 证据：`generation_service.py:149-175` retry 用 `retry_of` 创建新行；`cancel_generation` 直接改 `generation.status`（`generation_service.py:177-196`）；worker 会更新 `progress/stage/status/output_asset_id`。所以"历史不被覆盖"成立（符合红线 9），但**持久层没有 immutable 约束**：`status/output_asset_id/progress` 都是可写列。
- Alpha 期望 `parameters/prompt_version/provider/model` 固定（domain §56）；MVP 至少把 prompt/provider 写死在 `parameters`（`generation_service.py:79`），这点 OK；但 **无 `parent_generation_id` 外键**（用 `retry_of` 文本），也**无 `workflow_template_id/workflow_version_id/prompt_version_id/target_type/target_id`**（Alpha §47）。

### ⑥ revision 乐观锁：仅 Shot 与 Character 有，Scene/Episode/Project 无
- 证据：`shot.py:60`、`character.py:35` 有 `revision`；`project.py/episode.py/scene.py` **均无** revision 字段。Alpha 红线 10 要求 Scene/Shot/Character/Workflow 均支持。Scene/Episode 目标（Alpha API §23）也有 revision 诉求。

### ⑦ `media_versions` 与 `assets` 的关系（单对一包装）
- 证据：`media_version.py:24-28` `asset_id` FK → assets；`generations → output_asset_id` 弱文本；`asset.source_generation_id` 反向 provenance（`asset.py:27`）。关系是**单层**：Asset ← MediaVersion，Generation.output_asset_id 指向单 Asset。
- Alpha 期望多对多的 `generation_outputs`（一个 generation 产出多 asset）与 `generation_inputs`（多输入）。

### ⑧ `generations` 表没有 `parent_generation_id`
- 证据：`generation.py` 无该列，只有 `retry_of`（文本）。Alpha §47 需要 `parent_generation_id` FK + 索引。

### ⑨ 是否已有 `jobs` 表 —— 没有
- 证据：grep 全 backend 无 `job`；队列即 `generations` 表（`generation_service.py` + `generations/worker.py` DB-poll）。Alpha 需要独立 Job/JobTask/依赖表（§56-59），并区分「Job=批任务 / Task=调度单元 / Generation=执行历史」（domain §77）。

### ⑩ continuity / timeline 是否存在 —— 均不存在
- 证据：无 `continuity_states`、`timelines`、`timeline_tracks`、`timeline_clips` 表。`shot_characters`（`character.py:55-62`）预留了 `role/position/pose/action/emotion/screen_direction/costume_id` 但**无 character_version_id**（Alpha §37）。

### ⑪ `character_versions`（含 MASTER）不存在
- 这是 Alpha 「Character MASTER 机制 / Stale 传播」的根基，MVP 完全没有。`Character` 只有 `visual_prompt` 单字符串，无版本。

### ⑫ `order_index`：MVP 用 int 序号，Alpha 用 REAL 间隔
- 证据：MVP 用 `scene_number/shot_order/shot_number`（int）排序（`scene.py:25`、`shot.py:37-38`）；Alpha §89/§19 要求 `order_index REAL`（1000/2000 间隔）且**对象 ID 永不因重排改变**。
- MVP `reorder_shots`（`shot_service.py:308-341`）是改写 shot_number/shot_order 的 in-place 实现——行为目标一致（id 不变），但字段类型/间隔与目标不同，且无 Episode/Scene 级 reorder。

---

## 3. 特别核对汇总

| 核对项 | 结果 |
|---|---|
| `characters/character_versions`（含 MASTER） | **只有 `characters`，无版本无 MASTER**（缺失） |
| `media_versions` 与 assets | **单对一包装关系**存在；目标 Asset 自版本化 → 需重构 |
| `generations.parent_generation_id` | **无，用 `retry_of`** |
| `jobs` 表 | **无** |
| `continuity/timeline` | **均无** |

---

## 4. 关键结论（Domain）

- **MVP 基础设施质量很高**：分层、软删除、revision 乐观锁、事件总线、不可变版本思想在 Shot/Generation/Character 上已落地，可复用（KEEP）。
- **最大的领域缺口集中在 Alpha「版本化 + provenance」三角**：`CharacterVersion(MASTER)`、`Location/Version`、`Prompt/PromptVersion`、`GenerationInput/Output`、`Asset 自版本化`。这是 Stage→Alpha 的主迁移线（对应领域文档 §100 第一/二轮）。
- **最硬的结构性冲突是版本模型**：MVP 用独立 `media_versions` 包装 Asset，Alpha 要求 Asset 自带 `version_group_id/version_number` 且 Shot 直接指向 `active_*_asset_id`；以及 prompt 内联 vs `Shot.active_prompt_version_id`。这两处需要明确 MIGRATE 策略。
- **Job/Continuity/Timeline 三块是纯增量**（现在完全没有），应作为 Alpha 迭代的独立 BUILD。
