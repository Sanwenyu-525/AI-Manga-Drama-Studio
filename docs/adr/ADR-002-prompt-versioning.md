# ADR-002：Prompt 版本化 — Shot 内联 Prompt 迁移到 Prompt/PromptVersion

> 状态：**Proposed**（待评审）
> 日期：2026-08
> 关联文档：《核心领域模型详细设计 v0.1》§45-48（Prompt Domain）；《数据库 Schema 与数据关系设计 v0.1》§44-46（prompts/prompt_versions）；《Asset/Generation/Version 系统详细设计 v0.1》§98-100（版本固定原则）；《AI Director Agent Alpha 架构设计 v0.2》§68-72（Prompt Agent 与版本化）
> 关联任务：P3-T017~T019（Prompt/PromptVersion/History/Activate）、P7-T011（Prompt Agent）、前端 F037（PromptSection）

---

## 1. Context

### 现状（MVP，代码事实）

- `shots.image_prompt / video_prompt / negative_prompt` 三个 Text 列内联存 Prompt 字符串（`shot.py`）。
- `generations.parameters` JSON 里复制 prompt（`generation_service.py` 入队时写入），无任何版本、历史、来源（谁生成的/哪个模型）信息。
- 修改 Prompt 即覆盖列值，无历史可回溯；AGENTS.md 红线 8（架构红线）明确 "Prompt 直接等于 Shot" 是被禁止的模式。
- 不存在 prompts / prompt_versions 表（全库 grep 确认）。

### 为什么必须版本化（Alpha 目标）

1. **可追溯**：Generation 必须能回答"用的是哪个 Prompt 版本"，现状只能看 parameters 里一次性字符串，修改后无法还原。
2. **编辑与恢复**：用户/AI 修改 Prompt 应产生 vN+1 而非覆盖；可回退、可对比。
3. **Provider 转译**：Canonical Prompt Spec → Provider-specific Prompt 需要版本化的中间产物（Prompt Agent 产出）。
4. **红线合规**：领域规则 1"Shot != Prompt"，Prompt 是 Shot 的生成表示，独立建模后 Generation 才能准确引用。

## 2. Decision

### 2.1 新表

`prompts`（每目标每类型一行）：

| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| project_id | TEXT FK→projects.id | |
| target_type | TEXT | SHOT（Alpha 首期；后续 CHARACTER/LOCATION/SCENE） |
| target_id | TEXT | 如 shot.id |
| prompt_type | TEXT | SHOT_IMAGE / SHOT_VIDEO（首期两型；后续扩展） |
| active_version_id | TEXT | **权威 active 指针**（指向 prompt_versions.id） |
| created_at / updated_at | TEXT | |

`prompt_versions`（不可变版本链）：

| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| prompt_id | TEXT FK→prompts.id | |
| version_number | INTEGER | 组内从 1 递增 |
| positive_prompt | TEXT | |
| negative_prompt | TEXT | |
| structured_spec_json | TEXT | Canonical Prompt Spec（Phase 7 Prompt Agent 产出） |
| provider / model | TEXT | 生成该版本的模型上下文（可空） |
| generated_by | TEXT | user / agent / migration / system |
| parent_version_id | TEXT FK→prompt_versions.id | 版本链（可选） |
| created_at | TEXT | |

约束：`UNIQUE(prompt_id, version_number)`；索引 `idx_prompts_target(target_type, target_id)`、`idx_prompt_versions_prompt(prompt_id, version_number)`。

### 2.2 Shot 指针与歧义处理

- `shots.active_prompt_version_id`（新增列，可空）保留为**便捷指针**，指向该 Shot 最近一次主生成（image）使用的 PromptVersion；**非权威**。
- **权威 active 在 prompts.active_version_id**（每 prompt_type 一行各自持有）。
- Generation 记录 `generations.prompt_version_id`（新增列，FK 语义），GenerationPlanner 按 (target=shot, prompt_type=SHOT_IMAGE/SHOT_VIDEO) → prompts.active_version_id 解析；**provenance 不依赖 shot 便捷指针**，歧义消除。
- 视频/图像 Prompt 各自独立版本链（两个 prompts 行），互不覆盖。

### 2.3 Shot 内联列处置：弃用缓存（Deprecated Cache）

- `shots.image_prompt / video_prompt / negative_prompt` **保留但标记弃用**：
  - 读：兼容 MVP UI（PromptSection 未迁移前仍可显示）；
  - 写：更新路径改为"写 prompt_versions（新版本）+ 同步 shot 列（写透缓存）+ active 指针"，两处值由 Service 保证一致；
  - 终态：前端切换至 Prompt API 后，随 P3-T019 完成的下一个迁移 DROP 这三列。
- 好处：迁移与前端改造解耦，单次变更集不必同时改 UI；风险：缓存与版本行可能漂移 → 由 Service 单一写入口 + 迁移后校验（随机抽样比对）控制。

### 2.4 Generation 引用

- `generations.prompt_version_id` 新增；worker 从 prompt_versions 行取 positive/negative 组装请求；`parameters` 仍保留 prompt 副本（审计冗余，不改）。
- 没有版本行的历史 Generation（迁移前）：parameters 兜底，`prompt_version_id` 为 NULL，可追溯性降级但不丢数据。

### 2.5 API（与 backend 设计 §34 对齐）

- `GET /shots/{shotId}/prompts`（两型 prompt 摘要 + activeVersionId）
- `POST /shots/{shotId}/prompts`（无版本时创建 v1）
- `POST /prompts/{promptId}/versions`（新版本 vN+1）
- `GET /prompts/{promptId}/versions`（历史）
- `POST /prompts/{promptId}/versions/{versionId}/activate`
- `POST /shots/{shotId}/prompts/generate`（AI Improve，Phase 7 随 Prompt Agent 落地，本期可先 501/占位）

## 3. Alternatives

| 方案 | 评估 |
|---|---|
| A. 继续内联 + 加一个 version 字符串列 | ❌ 无结构化版本、无历史查询、无法链式恢复；Generation 引用仍模糊；违反红线 |
| B. 万能版本表（entity_type/entity_id/snapshot_json） | ❌ 领域文档 §59 否决理由同上（弱约束、JSON 难查询） |
| C. 立即删除 Shot 内联列（彻底迁移） | ⭕ 干净，但要求前端 PromptSection + 全部读写路径同变更集完成，风险集中在一次；**折衷采用 2.3 弃用缓存**，分两步走 |
| D. 双列指针（active_image_prompt_version_id + active_video_prompt_version_id） | ⭕ 更显式，但与 Alpha DB 设计 §22 的单列不一致；权威 per-type active 已在 prompts 表，shot 单列仅作便捷指针，**无需加列** |

## 4. Consequences

### 迁移步骤

1. 建 prompts / prompt_versions 表 + 索引；加 shots.active_prompt_version_id、generations.prompt_version_id。
2. 回填：遍历有 image_prompt/video_prompt 的 shots → 建 prompts 行（SHOT_IMAGE/SHOT_VIDEO）+ v1 版本（positive=对应列，negative=negative_prompt，generated_by='migration'）→ 写 prompts.active_version_id 与 shot.active_prompt_version_id（image 优先）。
3. 写路径改造：shot 更新（image_prompt 等字段）→ VersionService/PromptService 统一入口创建 vN+1 并同步缓存列；worker 读取 prompt_versions。
4. 校验：抽查存量 shots 的 shot 列与 v1 版本一致；API 冒烟。
5. （后续迁移，P3-T019 完成后）DROP shots.image_prompt/video_prompt/negative_prompt。

### 代码变更

- 新增 PromptService + PromptVersionService（或合一的 PromptService：create_version/activate/list/backfill）。
- ShotService.update_shot：image_prompt/video_prompt/negative_prompt 更新走 PromptService（事务内建版本）。
- GenerationPlanner（P3 引入）：按 (shot, type) 解析 active prompt_version_id。
- Worker：_persist_output 前解析 prompt 版本；Generation DTO/API 返回 prompt_version_id。
- 前端：PromptSection 展示当前版本 + 历史（F037）；生成详情显示 prompt_version（F038）。
- 测试：版本唯一索引、activate 切换、回填幂等（analysis_key 复用）、写透缓存一致性、迁移 round-trip。

### 风险与缓解

- 回填量大（每 shot 2 行 prompts + 1 行 versions）→ 单事务分批执行。
- 弃用缓存漂移 → Service 单一写入口 + 抽样校验 + 文档标注 DEPRECATED。
- 前端 PromptSection 在 P3-T017 前仍读 shot 列 → 缓存保证可读性，无破坏。

### 关联任务

P3-T017/T018/T019、P3-T011/T014（Generation 引用 prompt_version_id）、P7-T011/T012（Prompt Agent + Proposal）、前端 F037/F038；与 ADR-001（版本模型）无冲突，可并行迁移但建议同批上线（同一 Alembic 链）。

---

## 5. 决定人

需用户（项目负责人）评审确认本 ADR 后，P3 Prompt 相关任务方可按此落地。批准前禁止 prompt 迁移编码。
