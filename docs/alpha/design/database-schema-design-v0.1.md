# AI 漫剧 Studio 数据库 Schema 与数据关系设计 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**上游文档：**

* 《AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1》
* 《AI 漫剧 Studio 核心领域模型详细设计 v0.1》

**目标：** 将 `Project → Episode → Scene → Shot → Generation → Asset` 核心领域模型正式转换为可持久化的数据结构，为 Backend API、Service、Job Queue、Agent、Continuity Engine 和 Studio 前端提供统一的数据基础。

---

# 1. 数据库设计结论

Alpha 阶段推荐：

```text
SQLite
+
WAL Mode
+
Local File Storage
```

即：

```text
SQLite
负责：
- Project
- Episode
- Scene
- Shot
- Character
- Asset Metadata
- Generation
- Version
- Job
- Workflow
- Timeline
- Continuity
- Dependency

文件系统
负责：
- 图片
- 视频
- 音频
- ComfyUI Workflow JSON
- 小说原文件
- 缩略图
- 导出文件
```

禁止：

```text
BLOB
```

直接存储大型：

```text
PNG
MP4
WAV
```

数据库仅保存：

```text
storage_path
```

和对应 Asset Metadata。

---

# 2. 为什么 Alpha 使用 SQLite

当前 Alpha 的产品形态是：

```text
Single User
+
Desktop Studio
+
Local-first
+
Local ComfyUI
+
Remote Provider 可选
```

因此没有必要过早引入：

```text
PostgreSQL Server
Redis
Kafka
对象存储
```

增加部署复杂度。

SQLite 足以支撑：

```text
几十个 Project
数百 Episode
数万 Shot
几十万 Asset / Generation Record
```

Studio 真正的大数据量来自媒体文件，而不是关系数据。

媒体文件不会进入 SQLite。

---

# 3. 为未来 PostgreSQL 留迁移边界

虽然 Alpha 使用 SQLite，但业务层禁止出现：

```text
SQLite-specific business logic
```

架构保持：

```text
Domain
   ↓
Repository Interface
   ↓
SQLite Repository
```

未来：

```text
Domain
   ↓
Repository Interface
   ├── SQLite Repository
   └── PostgreSQL Repository
```

当进入：

```text
多人协作
云项目
远程同步
Web Studio
Team Workspace
```

时，再迁移 PostgreSQL。

---

# 4. SQLite 初始化

建议：

```sql
PRAGMA journal_mode = WAL;

PRAGMA foreign_keys = ON;

PRAGMA synchronous = NORMAL;

PRAGMA busy_timeout = 5000;
```

其中：

```text
WAL
```

对于 Studio 特别重要。

因为系统可能同时存在：

```text
UI Read
Agent Read
Generation Update
Job Progress Update
Asset Insert
```

---

# 5. 命名规范

数据库全部采用：

```text
snake_case
```

例如：

```text
project_id
episode_id
scene_id
created_at
```

表名使用：

```text
复数
```

例如：

```text
projects
episodes
scenes
shots
assets
generations
```

---

# 6. ID 规范

推荐：

```text
ULID
```

数据库类型：

```sql
TEXT
```

例如：

```text
01K2QJF7AFD5S2MY4T0A6W3JBF
```

统一：

```sql
id TEXT PRIMARY KEY
```

不建议：

```text
INTEGER AUTOINCREMENT
```

作为领域 ID。

原因：

* 未来远程同步更安全
* 跨模块生成 ID 不冲突
* 不依赖数据库
* 日志中可直接使用
* ULID 本身具有时间排序特性

---

# 7. 时间规范

数据库统一使用：

```text
UTC
```

推荐 ISO-8601：

```text
2026-08-15T09:00:00.000Z
```

SQLite：

```sql
TEXT
```

前端根据用户时区转换显示。

禁止数据库存：

```text
2026-08-15 17:00 JST
```

之类的本地时间语义。

---

# 8. Boolean

SQLite 中统一：

```sql
INTEGER NOT NULL DEFAULT 0
```

语义：

```text
0 = false
1 = true
```

例如：

```sql
is_master INTEGER NOT NULL DEFAULT 0
```

---

# 9. Enum

Alpha 阶段建议：

```text
TEXT + Application Enum
```

例如：

```sql
status TEXT NOT NULL
```

存：

```text
ACTIVE
ARCHIVED
GENERATING
SUCCEEDED
```

而不是数据库 Integer Enum：

```text
0
1
2
3
```

这样数据库调试和迁移更加直观。

---

# 10. JSON 字段

SQLite Alpha：

```text
JSON → TEXT
```

应用层负责：

```text
Serialize
Deserialize
Validate
```

例如：

```sql
metadata_json TEXT
parameters_json TEXT
visual_spec_json TEXT
```

但：

> 核心可搜索字段禁止全部藏在 JSON 中。

例如：

```text
provider
model
status
asset_type
scene_id
shot_id
```

必须独立成列。

---

# 11. Archive 与 Delete 策略

核心业务对象默认：

```text
Archive
```

不使用物理删除。

统一增加：

```sql
archived_at TEXT
```

或者：

```sql
status = 'ARCHIVED'
```

推荐核心 Aggregate 同时保留：

```text
status
archived_at
```

便于审计。

物理删除只用于：

```text
Temp Cache
Expired Preview
Broken Upload
Unreferenced Generated Temp File
```

---

# 12. 数据库总体关系

```text
projects
│
├── project_settings
│
├── source_documents
│
├── episodes
│   │
│   ├── scenes
│   │   │
│   │   └── shots
│   │       ├── shot_visual_specs
│   │       └── shot_characters
│   │
│   └── timelines
│
├── characters
│   ├── character_versions
│   └── costumes
│
├── locations
│   └── location_versions
│
├── props
│
├── assets
│
├── prompts
│   └── prompt_versions
│
├── generations
│   ├── generation_inputs
│   └── generation_outputs
│
├── workflow_templates
│   └── workflow_versions
│
├── jobs
│   └── job_tasks
│
├── continuity_states
│
└── resource_dependencies
```

---

# 13. projects

Project 是最高业务容器。

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,

    name TEXT NOT NULL,
    description TEXT,

    status TEXT NOT NULL DEFAULT 'DRAFT',
    project_type TEXT NOT NULL DEFAULT 'MANGA_DRAMA',

    cover_asset_id TEXT,

    aspect_ratio TEXT NOT NULL DEFAULT '9:16',
    default_width INTEGER,
    default_height INTEGER,
    default_fps REAL,

    active_episode_id TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_opened_at TEXT,
    archived_at TEXT
);
```

---

# 14. Project Index

```sql
CREATE INDEX idx_projects_status
ON projects(status);

CREATE INDEX idx_projects_updated_at
ON projects(updated_at);

CREATE INDEX idx_projects_last_opened_at
ON projects(last_opened_at);
```

Studio 首页：

```text
Recent Projects
```

主要依赖：

```text
last_opened_at
```

---

# 15. project_settings

```sql
CREATE TABLE project_settings (
    project_id TEXT PRIMARY KEY,

    language TEXT NOT NULL DEFAULT 'zh-CN',

    default_llm_provider TEXT,
    default_llm_model TEXT,

    default_image_provider TEXT,
    default_image_model TEXT,

    default_video_provider TEXT,
    default_video_model TEXT,

    default_voice_provider TEXT,
    default_voice_model TEXT,

    default_image_workflow_id TEXT,
    default_video_workflow_id TEXT,

    auto_retry INTEGER NOT NULL DEFAULT 1,
    max_retry_count INTEGER NOT NULL DEFAULT 3,

    auto_save INTEGER NOT NULL DEFAULT 1,

    continuity_enabled INTEGER NOT NULL DEFAULT 1,

    auto_activate_new_generation INTEGER NOT NULL DEFAULT 0,

    settings_json TEXT,

    updated_at TEXT NOT NULL,

    FOREIGN KEY(project_id)
        REFERENCES projects(id)
        ON DELETE CASCADE
);
```

这里的：

```text
ON DELETE CASCADE
```

只有执行项目真正 Hard Delete 时才生效。

正常业务不调用 Hard Delete。

---

# 16. source_documents

小说、剧本、设定等原始输入统一保存：

```sql
CREATE TABLE source_documents (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    document_type TEXT NOT NULL,

    title TEXT NOT NULL,

    content TEXT,

    source_asset_id TEXT,

    metadata_json TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id)
);
```

类型：

```text
NOVEL
SCRIPT
OUTLINE
REFERENCE
SETTING
OTHER
```

---

# 17. episodes

```sql
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    episode_number INTEGER,
    order_index REAL NOT NULL,

    title TEXT NOT NULL,
    description TEXT,

    source_document_id TEXT,
    source_text TEXT,

    script TEXT,

    target_duration REAL,

    status TEXT NOT NULL DEFAULT 'DRAFT',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    FOREIGN KEY(source_document_id)
        REFERENCES source_documents(id)
);
```

---

# 18. Episode Index

```sql
CREATE INDEX idx_episodes_project_order
ON episodes(project_id, order_index);

CREATE INDEX idx_episodes_project_status
ON episodes(project_id, status);
```

---

# 19. order_index 设计

不要直接：

```text
1
2
3
4
```

推荐使用：

```text
1000
2000
3000
4000
```

移动对象时：

```text
Shot A = 1000
Shot B = 2000
```

在中间插入：

```text
Shot X = 1500
```

避免每次拖拽都 UPDATE 后面几百个 Shot。

字段因此使用：

```sql
REAL
```

后续可定期：

```text
Rebalance Order
```

---

# 20. scenes

```sql
CREATE TABLE scenes (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,
    episode_id TEXT NOT NULL,

    scene_number INTEGER,

    order_index REAL NOT NULL,

    title TEXT,
    description TEXT,

    narrative_purpose TEXT,

    location_id TEXT,

    time_of_day TEXT,
    weather TEXT,

    estimated_duration REAL,

    status TEXT NOT NULL DEFAULT 'DRAFT',

    continuity_state_id TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    FOREIGN KEY(episode_id)
        REFERENCES episodes(id)
);
```

---

# 21. Scene Index

```sql
CREATE INDEX idx_scenes_episode_order
ON scenes(episode_id, order_index);

CREATE INDEX idx_scenes_project_status
ON scenes(project_id, status);

CREATE INDEX idx_scenes_location
ON scenes(location_id);
```

---

# 22. shots

Shot 是 Studio 查询频率最高的数据表之一。

```sql
CREATE TABLE shots (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,
    episode_id TEXT NOT NULL,
    scene_id TEXT NOT NULL,

    shot_number INTEGER,

    order_index REAL NOT NULL,

    title TEXT,
    description TEXT,

    narrative_beat TEXT,

    duration REAL,

    shot_type TEXT,
    camera_angle TEXT,
    camera_movement TEXT,

    status TEXT NOT NULL DEFAULT 'DRAFT',

    active_prompt_version_id TEXT,

    active_image_asset_id TEXT,
    active_video_asset_id TEXT,
    active_voice_asset_id TEXT,

    continuity_state_id TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    FOREIGN KEY(episode_id)
        REFERENCES episodes(id),

    FOREIGN KEY(scene_id)
        REFERENCES scenes(id)
);
```

---

# 23. Shot Index

非常重要：

```sql
CREATE INDEX idx_shots_scene_order
ON shots(scene_id, order_index);

CREATE INDEX idx_shots_episode
ON shots(episode_id);

CREATE INDEX idx_shots_project_status
ON shots(project_id, status);

CREATE INDEX idx_shots_updated_at
ON shots(updated_at);
```

前端：

```text
Project Explorer
Scene Editor
Timeline
```

都会大量查询 Shot。

---

# 24. Shot Number 与 ID

例如：

```text
Shot 023
```

其中：

```text
023
```

只是展示编号。

真正引用始终使用：

```text
shot.id
```

用户拖动 Shot 顺序后：

```text
shot.id
```

永远不改变。

---

# 25. shot_visual_specs

Shot 本身只保存高频检索字段。

复杂视觉参数放：

```text
shot_visual_specs
```

```sql
CREATE TABLE shot_visual_specs (
    id TEXT PRIMARY KEY,

    shot_id TEXT NOT NULL UNIQUE,

    composition TEXT,

    location_id TEXT,

    lighting TEXT,
    mood TEXT,

    action TEXT,
    facial_expression TEXT,

    environment TEXT,

    style_instructions TEXT,
    negative_instructions TEXT,

    spec_json TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY(shot_id)
        REFERENCES shots(id)
        ON DELETE CASCADE
);
```

---

# 26. 为什么 ShotVisualSpec 独立

避免：

```text
shots
```

最终变成 80～100 个字段。

同时允许以后扩展：

```text
depth_of_field
lens
focal_length
camera_speed
motion_strength
composition_rules
light_direction
```

而不破坏 Shot 核心表。

---

# 27. characters

```sql
CREATE TABLE characters (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    name TEXT NOT NULL,
    alias TEXT,

    role_type TEXT,

    description TEXT,

    gender TEXT,
    age INTEGER,
    nationality TEXT,

    height_cm REAL,
    body_description TEXT,

    personality TEXT,

    active_version_id TEXT,
    master_version_id TEXT,

    voice_profile_id TEXT,

    status TEXT NOT NULL DEFAULT 'ACTIVE',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id)
);
```

---

# 28. Character Constraint

项目内部角色名称可以设置：

```sql
CREATE UNIQUE INDEX uq_characters_project_name_active
ON characters(project_id, name)
WHERE archived_at IS NULL;
```

意味着：

同一个 Project 不能同时存在两个：

```text
沈亦
```

但归档后可以重新建立。

---

# 29. character_versions

```sql
CREATE TABLE character_versions (
    id TEXT PRIMARY KEY,

    character_id TEXT NOT NULL,

    version_number INTEGER NOT NULL,

    name TEXT,

    appearance_spec TEXT,
    face_spec TEXT,
    body_spec TEXT,
    hairstyle_spec TEXT,

    default_costume_id TEXT,

    prompt_template TEXT,

    spec_json TEXT,
    is_master INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL,

    FOREIGN KEY(character_id)
        REFERENCES characters(id),

    UNIQUE(character_id, version_number)
);
```

---

# 30. MASTER 约束

理想状态：

一个 Character：

```text
最多一个 MASTER
```

SQLite 可以：

```sql
CREATE UNIQUE INDEX uq_character_master
ON character_versions(character_id)
WHERE is_master = 1;
```

即：

```text
Character 001
├── v1
├── v2
└── v3 ★
```

只能一个：

```text
is_master = 1
```

---

# 31. character_version_assets

角色版本可以有多张参考图：

```sql
CREATE TABLE character_version_assets (
    character_version_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,

    role TEXT,

    order_index REAL NOT NULL DEFAULT 1000,

    PRIMARY KEY(character_version_id, asset_id),

    FOREIGN KEY(character_version_id)
        REFERENCES character_versions(id),

    FOREIGN KEY(asset_id)
        REFERENCES assets(id)
);
```

`role`：

```text
FACE_REFERENCE
BODY_REFERENCE
FRONT_VIEW
SIDE_VIEW
BACK_VIEW
EXPRESSION
STYLE_REFERENCE
```

---

# 32. costumes

```sql
CREATE TABLE costumes (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,
    character_id TEXT NOT NULL,

    name TEXT NOT NULL,
    description TEXT,

    prompt_spec TEXT,

    active_version INTEGER,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    FOREIGN KEY(character_id)
        REFERENCES characters(id)
);
```

Alpha 可以暂时不建立：

```text
CostumeVersion
```

等需求出现再拆。

---

# 33. locations

```sql
CREATE TABLE locations (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    name TEXT NOT NULL,
    description TEXT,

    location_type TEXT,

    active_version_id TEXT,
    master_version_id TEXT,

    status TEXT NOT NULL DEFAULT 'ACTIVE',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id)
);
```

---

# 34. location_versions

```sql
CREATE TABLE location_versions (
    id TEXT PRIMARY KEY,

    location_id TEXT NOT NULL,

    version_number INTEGER NOT NULL,

    visual_spec TEXT,
    prompt_template TEXT,

    spec_json TEXT,

    is_master INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL,

    FOREIGN KEY(location_id)
        REFERENCES locations(id),

    UNIQUE(location_id, version_number)
);
```

MASTER：

```sql
CREATE UNIQUE INDEX uq_location_master
ON location_versions(location_id)
WHERE is_master = 1;
```

---

# 35. location_version_assets

```sql
CREATE TABLE location_version_assets (
    location_version_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,

    role TEXT,

    order_index REAL NOT NULL DEFAULT 1000,

    PRIMARY KEY(location_version_id, asset_id),

    FOREIGN KEY(location_version_id)
        REFERENCES location_versions(id),

    FOREIGN KEY(asset_id)
        REFERENCES assets(id)
);
```

---

# 36. props

```sql
CREATE TABLE props (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    name TEXT NOT NULL,
    description TEXT,

    prop_type TEXT,

    active_asset_id TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id)
);
```

Alpha 只创建：

> 需要跨镜头保持连续性的关键道具。

---

# 37. shot_characters

Shot 和 Character 是多对多关系。

```sql
CREATE TABLE shot_characters (
    id TEXT PRIMARY KEY,

    shot_id TEXT NOT NULL,
    character_id TEXT NOT NULL,

    role TEXT NOT NULL DEFAULT 'SECONDARY',

    character_version_id TEXT,
    costume_id TEXT,

    position TEXT,
    pose TEXT,
    expression TEXT,
    action TEXT,

    state_json TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY(shot_id)
        REFERENCES shots(id)
        ON DELETE CASCADE,

    FOREIGN KEY(character_id)
        REFERENCES characters(id),

    FOREIGN KEY(character_version_id)
        REFERENCES character_versions(id),

    FOREIGN KEY(costume_id)
        REFERENCES costumes(id),

    UNIQUE(shot_id, character_id)
);
```

---

# 38. Shot Character Version 固定原则

创建 Shot 时：

```text
沈亦 MASTER = v4
```

绑定：

```text
shot_characters.character_version_id = v4
```

后面：

```text
沈亦 MASTER → v5
```

不能自动更新：

```text
Shot.characterVersion
```

否则旧镜头无法重现。

---

# 39. assets

Asset 是数据库设计最核心的表之一。

```sql
CREATE TABLE assets (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    asset_type TEXT NOT NULL,

    name TEXT,

    source_type TEXT NOT NULL,

    storage_provider TEXT NOT NULL DEFAULT 'LOCAL',
    storage_path TEXT NOT NULL,

    mime_type TEXT,

    file_size INTEGER,

    width INTEGER,
    height INTEGER,
    duration REAL,

    checksum TEXT,

    generation_id TEXT,

    parent_asset_id TEXT,

    version_group_id TEXT,
    version_number INTEGER,

    status TEXT NOT NULL DEFAULT 'READY',

    metadata_json TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    FOREIGN KEY(parent_asset_id)
        REFERENCES assets(id)
);
```

---

# 40. Asset Storage Path

禁止存：

```text
C:\Users\xxx\Project\...
```

作为数据库永久路径。

推荐存：

```text
相对项目根目录
```

例如：

```text
assets/characters/shenyi/v4/front.png
```

或者：

```text
generated/episodes/e01/scenes/s03/shot_023/video/v3.mp4
```

项目迁移电脑后不会全部失效。

---

# 41. Asset Version Group

例如同一个 Shot Image：

```text
version_group_id = vg_shot23_image

v1
v2
v3
v4
```

数据库：

```text
asset_1  vg_001  1
asset_2  vg_001  2
asset_3  vg_001  3
asset_4  vg_001  4
```

建议：

```sql
CREATE UNIQUE INDEX uq_asset_version
ON assets(version_group_id, version_number)
WHERE version_group_id IS NOT NULL;
```

---

# 42. Asset Index

```sql
CREATE INDEX idx_assets_project_type
ON assets(project_id, asset_type);

CREATE INDEX idx_assets_generation
ON assets(generation_id);

CREATE INDEX idx_assets_version_group
ON assets(version_group_id, version_number);

CREATE INDEX idx_assets_parent
ON assets(parent_asset_id);

CREATE INDEX idx_assets_status
ON assets(project_id, status);
```

---

# 43. Asset Checksum

建议生成：

```text
SHA-256
```

用途：

```text
重复文件检测
Cache
文件完整性检查
Project Repair
```

例如：

```text
文件存在
+
checksum 不一致
```

则：

```text
Asset Status = MISSING / CORRUPTED
```

未来可增加：

```text
CORRUPTED
```

状态。

---

# 44. prompts

```sql
CREATE TABLE prompts (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,

    prompt_type TEXT NOT NULL,

    active_version_id TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY(project_id)
        REFERENCES projects(id)
);
```

---

# 45. prompt_versions

```sql
CREATE TABLE prompt_versions (
    id TEXT PRIMARY KEY,

    prompt_id TEXT NOT NULL,

    version_number INTEGER NOT NULL,

    positive_prompt TEXT,
    negative_prompt TEXT,

    structured_spec_json TEXT,

    provider TEXT,
    model TEXT,

    generated_by TEXT,

    parent_version_id TEXT,

    created_at TEXT NOT NULL,

    FOREIGN KEY(prompt_id)
        REFERENCES prompts(id),

    FOREIGN KEY(parent_version_id)
        REFERENCES prompt_versions(id),

    UNIQUE(prompt_id, version_number)
);
```

---

# 46. Prompt Index

```sql
CREATE INDEX idx_prompts_target
ON prompts(target_type, target_id);

CREATE INDEX idx_prompt_versions_prompt
ON prompt_versions(prompt_id, version_number);
```

获取：

```text
Shot 023 当前 Prompt
```

只需要：

```text
shots.active_prompt_version_id
```

无需扫描版本历史。

---

# 47. generations

Generation 是 AI 执行审计核心表。

```sql
CREATE TABLE generations (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    generation_type TEXT NOT NULL,

    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,

    provider TEXT,
    model TEXT,

    workflow_template_id TEXT,
    workflow_version_id TEXT,

    prompt_version_id TEXT,

    parameters_json TEXT,

    status TEXT NOT NULL DEFAULT 'CREATED',

    parent_generation_id TEXT,

    created_at TEXT NOT NULL,
    queued_at TEXT,
    started_at TEXT,
    finished_at TEXT,

    error_code TEXT,
    error_message TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    FOREIGN KEY(parent_generation_id)
        REFERENCES generations(id)
);
```

---

# 48. Generation 不可变性

Generation 从：

```text
RUNNING
```

开始以后，以下字段禁止修改：

```text
provider
model
workflow_version_id
prompt_version_id
parameters
inputs
```

Retry 创建新记录：

```text
Generation A FAILED
       ↓
Generation B
parent_generation_id = A
```

而不是覆盖 A。

---

# 49. Generation Index

Generation 数据增长速度会非常快。

必须：

```sql
CREATE INDEX idx_generations_project_created
ON generations(project_id, created_at);

CREATE INDEX idx_generations_target
ON generations(target_type, target_id);

CREATE INDEX idx_generations_status
ON generations(status);

CREATE INDEX idx_generations_parent
ON generations(parent_generation_id);

CREATE INDEX idx_generations_type
ON generations(project_id, generation_type);
```

---

# 50. generation_inputs

Generation 可以接收任意领域对象。

采用多态引用：

```sql
CREATE TABLE generation_inputs (
    id TEXT PRIMARY KEY,

    generation_id TEXT NOT NULL,

    input_type TEXT NOT NULL,

    reference_type TEXT NOT NULL,
    reference_id TEXT NOT NULL,

    role TEXT,

    order_index REAL NOT NULL DEFAULT 1000,

    metadata_json TEXT,

    FOREIGN KEY(generation_id)
        REFERENCES generations(id)
        ON DELETE CASCADE
);
```

例：

```text
generation_1001

CHARACTER_REFERENCE
 → ASSET / asset_10

LOCATION_REFERENCE
 → ASSET / asset_21

PROMPT
 → PROMPT_VERSION / prompt_v4
```

---

# 51. generation_outputs

Generation Output 强制指向 Asset。

```sql
CREATE TABLE generation_outputs (
    generation_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,

    role TEXT,

    order_index REAL NOT NULL DEFAULT 1000,

    PRIMARY KEY(generation_id, asset_id),

    FOREIGN KEY(generation_id)
        REFERENCES generations(id),

    FOREIGN KEY(asset_id)
        REFERENCES assets(id)
);
```

因此：

```text
Generation
```

永远不直接返回：

```text
file path
```

而是：

```text
Asset
```

---

# 52. Generation Provenance

完整数据链：

```text
Shot
 ↓
PromptVersion
 ↓
Generation
 ├── Input
 │    ├── Character Asset
 │    ├── Location Asset
 │    └── Storyboard Asset
 │
 └── Output
      ↓
Asset
```

任何时候都可以回答：

> “这个视频到底怎么生成出来的？”

---

# 53. workflow_templates

```sql
CREATE TABLE workflow_templates (
    id TEXT PRIMARY KEY,

    project_id TEXT,

    name TEXT NOT NULL,

    workflow_type TEXT NOT NULL,

    provider_type TEXT NOT NULL,

    active_version_id TEXT,

    builtin INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);
```

`project_id IS NULL`：

```text
系统级 Workflow
```

有 Project：

```text
项目自定义 Workflow
```

---

# 54. workflow_versions

```sql
CREATE TABLE workflow_versions (
    id TEXT PRIMARY KEY,

    workflow_template_id TEXT NOT NULL,

    version_number INTEGER NOT NULL,

    schema_json TEXT,

    provider_config_json TEXT,

    input_mapping_json TEXT,

    output_mapping_json TEXT,

    raw_workflow_asset_id TEXT,

    created_at TEXT NOT NULL,

    FOREIGN KEY(workflow_template_id)
        REFERENCES workflow_templates(id),

    FOREIGN KEY(raw_workflow_asset_id)
        REFERENCES assets(id),

    UNIQUE(workflow_template_id, version_number)
);
```

---

# 55. ComfyUI Workflow 存储

例如：

```text
WorkflowTemplate

SHOT_VIDEO_STANDARD
```

↓

```text
WorkflowVersion v3
```

↓

```text
raw_workflow_asset_id
```

↓

```text
Asset
```

↓

```text
workflows/comfyui/shot_video_standard/v3.json
```

因此数据库不会直接理解：

```text
ComfyUI Node 87
```

这些细节属于：

```text
Workflow Adapter
```

---

# 56. jobs

Job 表达用户层的一次业务操作。

```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    job_type TEXT NOT NULL,

    target_type TEXT NOT NULL,
    target_id TEXT,

    status TEXT NOT NULL DEFAULT 'CREATED',

    total_tasks INTEGER NOT NULL DEFAULT 0,
    completed_tasks INTEGER NOT NULL DEFAULT 0,
    failed_tasks INTEGER NOT NULL DEFAULT 0,

    progress REAL NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(id)
);
```

---

# 57. job_tasks

```sql
CREATE TABLE job_tasks (
    id TEXT PRIMARY KEY,

    job_id TEXT NOT NULL,

    task_type TEXT NOT NULL,

    target_type TEXT NOT NULL,
    target_id TEXT,

    status TEXT NOT NULL DEFAULT 'CREATED',

    priority INTEGER NOT NULL DEFAULT 0,

    generation_id TEXT,

    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retry_count INTEGER NOT NULL DEFAULT 3,

    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,

    error_message TEXT,

    FOREIGN KEY(job_id)
        REFERENCES jobs(id)
        ON DELETE CASCADE,

    FOREIGN KEY(generation_id)
        REFERENCES generations(id)
);
```

---

# 58. job_task_dependencies

不要把：

```text
dependencyTaskIds[]
```

直接放 JSON。

因为 Queue 高频查询依赖。

建立：

```sql
CREATE TABLE job_task_dependencies (
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,

    dependency_type TEXT NOT NULL DEFAULT 'HARD',

    PRIMARY KEY(task_id, depends_on_task_id),

    FOREIGN KEY(task_id)
        REFERENCES job_tasks(id)
        ON DELETE CASCADE,

    FOREIGN KEY(depends_on_task_id)
        REFERENCES job_tasks(id)
        ON DELETE CASCADE
);
```

---

# 59. Task Dependency 示例

```text
Task A
Generate Shot Image

       ↓ HARD

Task B
Generate Shot Video
```

数据库：

```text
task_id = B
depends_on_task_id = A
```

Queue 查询：

```text
A = SUCCEEDED
```

后：

```text
B → QUEUED
```

---

# 60. Job Index

```sql
CREATE INDEX idx_jobs_project_status
ON jobs(project_id, status);

CREATE INDEX idx_job_tasks_job_status
ON job_tasks(job_id, status);

CREATE INDEX idx_job_tasks_priority
ON job_tasks(status, priority);

CREATE INDEX idx_job_dependencies_parent
ON job_task_dependencies(depends_on_task_id);
```

---

# 61. resource_dependencies

这是局部重生成和 Stale 系统的核心。

```sql
CREATE TABLE resource_dependencies (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,

    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,

    dependency_type TEXT NOT NULL DEFAULT 'SOFT',

    created_at TEXT NOT NULL,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    UNIQUE(
        source_type,
        source_id,
        target_type,
        target_id
    )
);
```

---

# 62. Dependency 示例

```text
CharacterVersion v4
         ↓
Asset shot23_image_v3
         ↓
Asset shot23_video_v2
```

数据库：

```text
CHARACTER_VERSION:v4
    →
ASSET:image_v3
```

以及：

```text
ASSET:image_v3
    →
ASSET:video_v2
```

---

# 63. Character MASTER 更新

原来：

```text
沈亦 MASTER = v4
```

变：

```text
MASTER = v5
```

DependencyService 查询：

```text
source_type = CHARACTER_VERSION
source_id = v4
```

找到：

```text
Shot 03 Image
Shot 18 Image
Shot 31 Image
```

标记：

```text
STALE
```

不会立即重生成。

---

# 64. continuity_states

```sql
CREATE TABLE continuity_states (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,

    parent_state_id TEXT,

    character_states_json TEXT,
    prop_states_json TEXT,
    environment_state_json TEXT,
    temporal_state_json TEXT,

    metadata_json TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    FOREIGN KEY(parent_state_id)
        REFERENCES continuity_states(id),

    UNIQUE(scope_type, scope_id)
);
```

---

# 65. Continuity State Chain

例如：

```text
Scene 05 Base State
        ↓
Shot 21
        ↓
Shot 22
        ↓
Shot 23
```

可以形成：

```text
parent_state_id
```

链。

但不要无限读取：

```text
Shot 1 → Shot 2 → ... → Shot 500
```

Service 应周期生成：

```text
Resolved Snapshot
```

或者 Scene Base Snapshot。

---

# 66. timelines

```sql
CREATE TABLE timelines (
    id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,
    episode_id TEXT NOT NULL UNIQUE,

    duration REAL,

    width INTEGER,
    height INTEGER,
    fps REAL,

    status TEXT NOT NULL DEFAULT 'DRAFT',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY(project_id)
        REFERENCES projects(id),

    FOREIGN KEY(episode_id)
        REFERENCES episodes(id)
);
```

---

# 67. timeline_tracks

```sql
CREATE TABLE timeline_tracks (
    id TEXT PRIMARY KEY,

    timeline_id TEXT NOT NULL,

    track_type TEXT NOT NULL,

    name TEXT,

    order_index REAL NOT NULL,

    locked INTEGER NOT NULL DEFAULT 0,
    muted INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(timeline_id)
        REFERENCES timelines(id)
        ON DELETE CASCADE
);
```

---

# 68. timeline_clips

```sql
CREATE TABLE timeline_clips (
    id TEXT PRIMARY KEY,

    timeline_id TEXT NOT NULL,
    track_id TEXT NOT NULL,

    asset_id TEXT NOT NULL,

    shot_id TEXT,

    start_time REAL NOT NULL,
    end_time REAL NOT NULL,

    source_in REAL NOT NULL DEFAULT 0,
    source_out REAL,

    order_index REAL NOT NULL,

    enabled INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY(timeline_id)
        REFERENCES timelines(id),

    FOREIGN KEY(track_id)
        REFERENCES timeline_tracks(id),

    FOREIGN KEY(asset_id)
        REFERENCES assets(id),

    FOREIGN KEY(shot_id)
        REFERENCES shots(id)
);
```

---

# 69. Timeline Index

```sql
CREATE INDEX idx_timeline_tracks
ON timeline_tracks(timeline_id, order_index);

CREATE INDEX idx_timeline_clips_track_time
ON timeline_clips(track_id, start_time);

CREATE INDEX idx_timeline_clips_shot
ON timeline_clips(shot_id);
```

---

# 70. Timeline Active Asset

注意：

Timeline Clip：

```text
asset_id
```

直接绑定具体版本。

例如：

```text
Shot Video
v1
v2
v3 ← Active Shot Version
```

Timeline 可以仍然：

```text
使用 v2
```

因此：

```text
Shot.active_video_asset_id
```

和：

```text
TimelineClip.asset_id
```

不要求始终相同。

这给专业编辑留下自由度。

---

# 71. audit_logs

Alpha 后期建议加入基础审计：

```sql
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY,

    project_id TEXT,

    action TEXT NOT NULL,

    entity_type TEXT,
    entity_id TEXT,

    actor_type TEXT,

    before_json TEXT,
    after_json TEXT,

    created_at TEXT NOT NULL
);
```

actor：

```text
USER

DIRECTOR_AGENT

SCRIPT_AGENT

VISUAL_AGENT

SYSTEM
```

---

# 72. 为什么需要 Audit

例如 Agent：

```text
修改了 24 个 Shot
```

用户需要知道：

```text
谁改的？
什么时候？
改了什么？
```

未来才能实现：

```text
Undo Agent Changes
```

---

# 73. domain_events

Alpha 第一阶段可以只做应用内 Event Bus。

如果需要持久化：

```sql
CREATE TABLE domain_events (
    id TEXT PRIMARY KEY,

    project_id TEXT,

    event_type TEXT NOT NULL,

    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,

    payload_json TEXT,

    processed INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL,
    processed_at TEXT
);
```

这不是 Event Sourcing。

只是：

```text
Reliable Domain Event
```

辅助机制。

---

# 74. 关键外键原则

不要对所有 FK 使用：

```text
ON DELETE CASCADE
```

否则一次错误 Delete：

```text
Project
 ↓
几十万记录消失
```

只有纯从属 Entity 使用 Cascade。

例如：

```text
shot_visual_specs
job_task_dependencies
timeline_tracks
```

可以 Cascade。

核心历史：

```text
Asset
Generation
PromptVersion
CharacterVersion
```

禁止轻易 Cascade。

---

# 75. 删除规则矩阵

| Entity        | 默认行为    | Hard Delete   |
| ------------- | ------- | ------------- |
| Project       | Archive | 极少            |
| Episode       | Archive | 手动 Cleanup    |
| Scene         | Archive | 手动 Cleanup    |
| Shot          | Archive | 手动 Cleanup    |
| Character     | Archive | 依赖检查          |
| Location      | Archive | 依赖检查          |
| Asset         | Archive | 无引用后          |
| Generation    | 永久保留    | Debug Cleanup |
| PromptVersion | 永久保留    | 不建议           |
| Job           | 保留      | Cleanup       |
| Temp Asset    | Delete  | 自动            |
| Cache         | Delete  | 自动            |

---

# 76. 文件系统目录设计

推荐每个 Project 独立目录：

```text
projects/
└── {projectId}/
    │
    ├── project.db
    │
    ├── source/
    │
    ├── assets/
    │   ├── characters/
    │   ├── locations/
    │   ├── props/
    │   ├── storyboard/
    │   ├── images/
    │   ├── videos/
    │   ├── audio/
    │   └── subtitles/
    │
    ├── workflows/
    │
    ├── cache/
    │
    ├── thumbnails/
    │
    ├── exports/
    │
    └── logs/
```

推荐：

> 一个 Project 一个数据库。

而不是所有项目共享一个巨大数据库。

---

# 77. 为什么采用 Project Database

推荐：

```text
global.db

projects/
├── projectA/project.db
├── projectB/project.db
└── projectC/project.db
```

其中：

```text
global.db
```

只保存：

```text
Project Registry
Recent Projects
Workspace Settings
Provider Registry
Application Settings
```

Project 业务全部进入：

```text
project.db
```

优势：

### 1. 项目迁移简单

直接复制：

```text
Project Folder
```

即可。

### 2. 项目备份简单

不用从全局数据库抽取关联数据。

### 3. 数据损坏隔离

Project A 损坏不会影响 B。

### 4. Archive 简单

整个目录即可。

### 5. 后续支持项目压缩包

例如：

```text
.project
```

格式。

---

# 78. Global DB

建议：

```text
app.db
```

只包含：

```text
project_registry

app_settings

provider_profiles

recent_projects

workspace_settings
```

不要包含：

```text
Shot
Asset
Generation
```

---

# 79. Provider Secret

API Key：

```text
OpenAI Key
MiniMax Key
Kling Key
```

禁止直接存：

```text
project.db
```

建议：

```text
OS Keychain
Windows Credential Manager
macOS Keychain
```

数据库最多存：

```text
credential_id
```

---

# 80. Project Registry

全局：

```sql
CREATE TABLE project_registry (
    project_id TEXT PRIMARY KEY,

    name TEXT NOT NULL,

    project_path TEXT NOT NULL UNIQUE,

    cover_path TEXT,

    status TEXT,

    last_opened_at TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Studio 首页加载：

```text
app.db
```

无需打开每个：

```text
project.db
```

---

# 81. Transaction 边界

典型操作：

```text
Create Shot
```

一个事务：

```text
INSERT shot
INSERT shot_visual_spec
INSERT shot_character
INSERT audit_log
```

任意失败：

```text
ROLLBACK
```

---

# 82. Generation 成功事务

模型执行本身不能包含在长数据库事务里。

错误：

```text
BEGIN

调用 ComfyUI 等 4 分钟

INSERT Asset

COMMIT
```

正确：

```text
Transaction 1
Generation → RUNNING
COMMIT

↓

调用 Provider

↓

文件写入

↓

Transaction 2
INSERT Asset
INSERT GenerationOutput
Generation → SUCCEEDED
JobTask → SUCCEEDED
COMMIT
```

---

# 83. 文件写入与 DB 一致性

媒体文件和 SQLite 无法做真正 Distributed Transaction。

推荐流程：

```text
Generate
 ↓
Write Temporary File
 ↓
Validate
 ↓
Move to Final Storage
 ↓
DB Transaction
 ↓
Register Asset
```

如果数据库事务失败：

```text
记录 Orphan File
```

后续 Cleanup。

---

# 84. Asset Repair

启动 Project 时可以进行轻量检查：

```text
Asset
 ↓
storage_path exists?
```

异常：

```text
不存在
```

则：

```text
Asset.status = MISSING
```

不要删除 Asset。

这样用户重新连接文件后仍能恢复。

---

# 85. Generation Cache

未来可以根据：

```text
Provider
Model
Prompt
Parameters
Input Asset Checksums
Workflow Version
```

计算：

```text
generation_hash
```

可以增加：

```sql
generation_hash TEXT
```

索引：

```sql
CREATE INDEX idx_generation_hash
ON generations(generation_hash);
```

重复请求时：

```text
Cache Hit
```

直接复用 Asset。

Alpha v0.1 可暂不启用，但 Schema 应预留。

---

# 86. Optimistic Lock

前端、Agent、后台任务可能同时修改 Shot。

建议高频实体加入：

```sql
revision INTEGER NOT NULL DEFAULT 0
```

例如：

```text
shots
characters
scenes
```

UPDATE：

```sql
UPDATE shots
SET
    description = ?,
    revision = revision + 1
WHERE id = ?
AND revision = ?;
```

影响：

```text
0 rows
```

说明数据已被别人修改。

即使 Alpha 单用户，也可能存在：

```text
User
+
Agent
+
Background Job
```

并发。

---

# 87. 推荐加入 revision 的表

```text
projects

episodes

scenes

shots

characters

locations

timelines
```

---

# 88. 数据完整性：Project Scope

必须保证：

```text
Shot.project_id
Scene.project_id
Episode.project_id
```

一致。

SQLite FK 无法直接表达：

```text
shot.project_id == scene.project_id
```

因此由：

```text
Domain Service
```

保证。

Repository 不允许跨 Project 绑定。

---

# 89. N+1 查询控制

例如加载：

```text
Scene
→ 50 Shots
```

禁止：

```text
50 次 Shot
+
50 次 Character
+
50 次 Asset
```

API 应有专门 Query：

```text
SceneEditorView
```

一次获取：

```text
Scene
Shots
Shot Characters
Active Assets
Generation Status
```

这里属于：

```text
Read Model
```

不需要完全遵循 Aggregate 加载规则。

---

# 90. CQRS-lite

Alpha 不需要完整 CQRS。

但推荐区分：

```text
Command Repository
```

与：

```text
Studio Query
```

例如：

```text
ShotRepository
```

负责：

```text
save()
findById()
```

而：

```text
SceneEditorQueryService
```

负责复杂 JOIN。

---

# 91. 前端 Project Tree Query

典型 SQL：

```text
Project
 ↓
Episode
 ↓
Scene
 ↓
Shot
```

不要每次递归 API。

推荐一次返回：

```json
{
  "episodes": [],
  "scenes": [],
  "shots": []
}
```

前端 Normalize 后：

```text
episodesById
scenesById
shotsById
```

---

# 92. Generation History Query

Inspector：

```text
Shot 023
```

需要查看：

```text
Image v1
Image v2
Video v1
Video v2
```

查询：

```text
generations.target_type = SHOT
generations.target_id = shot_023
```

然后 JOIN：

```text
generation_outputs
assets
```

这也是：

```text
idx_generations_target
```

存在的原因。

---

# 93. 数据库阶段划分

不要一次建完全部表。

推荐分三批 Migration。

---

# 94. Migration Phase 1 — Core

第一批：

```text
projects
project_settings

source_documents

episodes
scenes
shots
shot_visual_specs

characters
character_versions

locations
location_versions

shot_characters

assets

prompts
prompt_versions

generations
generation_inputs
generation_outputs
```

这批完成后：

> 已经可以完成一个 Shot 的完整生成闭环。

---

# 95. Migration Phase 2 — Production

第二批：

```text
workflow_templates
workflow_versions

jobs
job_tasks
job_task_dependencies

resource_dependencies

costumes
props
```

完成：

> Scene / Episode 批量生成 + Retry + Resume + Stale。

---

# 96. Migration Phase 3 — Studio

第三批：

```text
continuity_states

timelines
timeline_tracks
timeline_clips

audit_logs
domain_events
```

完成：

> Continuity + Timeline + Agent Audit。

---

# 97. Migration 文件命名

如果使用 Flyway 风格：

```text
V001__create_project_core.sql

V002__create_story_structure.sql

V003__create_character_location.sql

V004__create_asset_system.sql

V005__create_prompt_system.sql

V006__create_generation_system.sql

V007__create_workflow_system.sql

V008__create_job_system.sql

V009__create_dependency_system.sql

V010__create_continuity_system.sql

V011__create_timeline_system.sql

V012__create_audit_system.sql
```

---

# 98. Migration 原则

已经发布的：

```text
V006
```

禁止直接修改。

错误：

```text
修改 V006 内容
```

正确：

```text
V013__alter_generation_schema.sql
```

数据库 Schema 必须：

```text
Forward Migration
```

---

# 99. Backup Before Migration

每次 Project Schema 升级：

```text
Project Open
 ↓
Detect Schema Version
 ↓
Backup project.db
 ↓
Migration
 ↓
Integrity Check
 ↓
Open Project
```

例如：

```text
backups/
project_20260815_170000.db
```

迁移失败：

```text
Restore
```

避免用户项目被升级过程破坏。

---

# 100. Project Schema Version

建议 Project 目录增加：

```text
project.json
```

例如：

```json
{
  "formatVersion": 1,
  "databaseVersion": 12,
  "projectId": "01K..."
}
```

但真正数据库版本仍以 Migration Table 为准。

`project.json` 用于：

```text
快速识别
兼容性判断
项目导入
```

---

# 101. 数据库最核心 ER

```text
PROJECT
   │
   ▼
EPISODE
   │
   ▼
SCENE
   │
   ▼
SHOT
   │
   ├───────────────┐
   │               │
   ▼               ▼
VISUAL SPEC     CHARACTER
   │               │
   │               ▼
   │        CHARACTER VERSION
   │               │
   └───────┬───────┘
           ▼
       PROMPT VERSION
           │
           ▼
       GENERATION
        │       │
        │       │
        ▼       ▼
      INPUT   OUTPUT
                 │
                 ▼
               ASSET
                 │
                 ▼
              TIMELINE
```

---

# 102. 一个真实 Shot 的数据库记录

例如：

```text
Shot 023

沈亦结束训练后看向教练。
```

### shots

```text
id = shot_023

scene_id = scene_05

shot_type = MEDIUM_CLOSE_UP

camera_angle = EYE_LEVEL

camera_movement = PUSH_IN

duration = 4.5

active_image_asset_id = asset_img_v3

active_video_asset_id = asset_video_v2
```

---

### shot_characters

```text
shot_id = shot_023

character_id = shenyi

character_version_id = shenyi_v4

costume_id = white_uniform_07

expression = restrained
```

---

### prompts

```text
target_type = SHOT

target_id = shot_023

prompt_type = SHOT_IMAGE
```

---

### prompt_versions

```text
v1

v2

v3 ← active
```

---

### generations

```text
Generation 1001
SHOT_IMAGE
FAILED
```

↓

```text
Generation 1002
parent = 1001
SHOT_IMAGE
SUCCEEDED
```

---

### generation_inputs

```text
ShenYi MASTER v4

Basketball Gym MASTER v2

Prompt v3
```

---

### generation_outputs

```text
asset_img_v3
```

---

### assets

```text
asset_img_v3

SHOT_IMAGE

images/scene05/shot023/v3.png
```

---

### 第二次生成

```text
Generation 1003
SHOT_VIDEO
```

Input：

```text
asset_img_v3
```

Output：

```text
asset_video_v2
```

最终：

```text
Shot.active_video_asset_id
=
asset_video_v2
```

整个生产链完整可追溯。

---

# 103. Alpha 核心查询必须达到的能力

数据库完成后必须轻松回答：

### Query 1

> 一个 Episode 有哪些 Scene？

### Query 2

> 一个 Scene 有哪些 Shot？

### Query 3

> Shot 023 当前使用哪张图和哪个视频？

### Query 4

> Shot 023 所有历史生成版本有哪些？

### Query 5

> video_v3 是使用哪个 Prompt 和模型生成的？

### Query 6

> video_v3 使用了哪个角色参考图？

### Query 7

> ShenYi MASTER 改变后哪些 Shot 可能过期？

### Query 8

> 当前有哪些 Generation 正在执行？

### Query 9

> 哪些 Task 失败了？

### Query 10

> 应用崩溃后哪些 Job 可以 Resume？

如果任何一个问题需要：

```text
扫描文件目录
解析 Prompt
询问 Agent Memory
解析 ComfyUI JSON
```

说明数据库设计出现了问题。

---

# 104. Alpha 性能目标

数据库层目标：

```text
打开 Project Tree
< 200ms

加载 Scene + Shots
< 100ms

获取 Shot Inspector
< 100ms

查询 Generation History
< 200ms

更新 Job Progress
< 50ms
```

真正耗时部分应该是：

```text
AI Generation
Video Processing
```

而不是数据库。

---

# 105. SQLite 写操作规则

SQLite：

```text
Single Writer
```

因此后端建议所有写操作进入统一：

```text
DB Write Queue
```

或者保证：

```text
Connection Pool
```

不会产生大量竞争写。

尤其：

```text
Generation Progress
```

不要每：

```text
100ms
```

写数据库一次。

建议：

```text
500ms～2s
```

批量更新 UI Progress。

关键状态变化：

```text
RUNNING
SUCCEEDED
FAILED
```

必须立即持久化。

---

# 106. 不把 Token Stream 写入数据库

LLM Streaming：

```text
token
token
token
token
```

禁止每个 Token：

```text
INSERT / UPDATE
```

只在：

```text
Agent Run Completed
```

后保存最终：

```text
Structured Output
Prompt
Proposal
```

必要时日志文件单独保存 Stream。

---

# 107. SQLite Integrity Check

项目启动或 Migration 后可以运行：

```sql
PRAGMA quick_check;
```

异常时：

```text
进入 Project Recovery Mode
```

而不是继续写入数据库。

---

# 108. Project Backup

Alpha 至少实现：

```text
Manual Backup

Auto Backup Before Migration
```

Beta 再增加：

```text
Scheduled Snapshot
```

备份的核心单位：

```text
整个 Project Folder
```

而不只是：

```text
project.db
```

因为媒体 Asset 同样属于工程。

---

# 109. Alpha Schema 最终核心表

第一优先级：

```text
projects

project_settings

source_documents

episodes

scenes

shots

shot_visual_specs

shot_characters

characters

character_versions

locations

location_versions

assets

prompts

prompt_versions

generations

generation_inputs

generation_outputs
```

第二优先级：

```text
workflow_templates

workflow_versions

jobs

job_tasks

job_task_dependencies

resource_dependencies

costumes

props
```

第三优先级：

```text
continuity_states

timelines

timeline_tracks

timeline_clips

audit_logs

domain_events
```

---

# 110. 数据层禁止事项

后续编码必须遵守：

## 禁止 1

```text
把图片/视频存 SQLite BLOB
```

---

## 禁止 2

```text
用文件名作为业务 ID
```

---

## 禁止 3

```text
通过目录结构推断业务关系
```

例如禁止：

```text
因为文件在 scene03/
所以属于 Scene03
```

数据库才是 Source of Truth。

---

## 禁止 4

```text
覆盖旧生成 Asset
```

每次生成创建新 Asset。

---

## 禁止 5

```text
修改历史 Generation
```

Retry 创建新 Generation。

---

## 禁止 6

```text
Character MASTER 更新后自动替换历史 Shot
```

只标记 STALE。

---

## 禁止 7

```text
Job 与 Generation 合并
```

必须保持：

```text
Job
→ Task
→ Generation
```

---

## 禁止 8

```text
把所有复杂数据全部塞 JSON
```

核心搜索字段必须结构化。

---

## 禁止 9

```text
Agent 直接执行数据库 SQL
```

必须：

```text
Agent
 ↓
Application Service
 ↓
Domain
 ↓
Repository
```

---

## 禁止 10

```text
ComfyUI Workflow JSON 成为业务模型
```

必须：

```text
WorkflowTemplate
 ↓
WorkflowVersion
 ↓
ComfyUI Adapter
```

---

# 111. Alpha 数据库完成定义

当数据库层可以稳定支撑：

```text
Create Project
 ↓
Import Novel
 ↓
Create Episode
 ↓
Create Scene
 ↓
Create Shot
 ↓
Bind Character
 ↓
Create Prompt Version
 ↓
Create Generation
 ↓
Register Inputs
 ↓
Execute Provider
 ↓
Create Asset
 ↓
Register Output
 ↓
Set Active Version
 ↓
Create Timeline Clip
```

并且完整保留：

```text
History
Version
Dependency
Retry
```

即可认为：

> AI 漫剧 Studio Alpha Database Core 完成。

---

# 112. 与 Backend Service 的映射

数据库确定之后，Backend 不应该围绕：

```text
Table CRUD
```

设计 API。

错误：

```text
POST /generation-inputs

POST /generation-outputs

PUT /assets/{id}
```

直接暴露数据表。

应该围绕业务操作：

```text
CreateProject

PlanEpisode

CreateShot

UpdateShotVisualSpec

GenerateShotImage

RegenerateShotVideo

SetCharacterMaster

ActivateAssetVersion

GenerateScene

RetryGeneration

ResumeJob

RenderEpisode
```

数据库只是实现细节。

---

# 113. 下一份设计文档

数据库 Schema 固化后，下一层已经可以正式设计后端 Application / Service。

下一份建议：

# 《AI 漫剧 Studio Alpha Backend API & Service 详细设计 v0.1》

重点将解决：

```text
Controller / API

Application Service

Domain Service

Repository

DTO

Command / Query

Transaction

GenerationService

AssetService

VersionService

JobService

WorkflowService

ContinuityService

Provider Adapter

WebSocket / SSE Progress

Error Model

API Versioning
```

并正式确定一条完整调用链：

```text
Studio UI
 ↓
API
 ↓
Application Service
 ↓
Domain
 ↓
Generation Planner
 ↓
Job Queue
 ↓
Provider Adapter
 ↓
ComfyUI / AI Model
 ↓
Asset Registration
 ↓
Event
 ↓
UI Progress Update
```

从这一份开始，整个 Alpha 架构就会从“设计模型”进入可以直接交给 Codex 分模块编码的阶段。
