# ADR-001：Asset 自版本化 — 合并 media_versions 进入 Asset 版本模型

> 状态：**Accepted**（2026-08 用户批准；已实现：迁移 d3e4f5a6b7c8 + AssetVersionService + worker 单事务完成链，dev 库回填验证通过）
> 日期：2026-08
> 关联文档：《AI 漫剧 Studio 核心领域模型详细设计 v0.1》§28-44、§58-61；《数据库 Schema 与数据关系设计 v0.1》§39-43、§101；《Asset/Generation/Version 系统详细设计 v0.1》§28-37、§59-66
> 关联任务：P3-T006~T009（Version Group / Version Number / Active / History API）、P3-E3（Generation）、P1-E2-T03（完成链原子化）

---

## 1. Context

### 现状（MVP，代码事实）

- `assets` 表是纯文件登记：id / project_id / type / name / file_path / thumbnail_path / mime_type / width / height / duration / file_size / meta_json / source_generation_id / deleted_at / created_at（`backend/app/db/models/asset.py`）。**没有任何版本语义**。
- `media_versions` 表是"每 Shot 每媒体类型"的版本包装：shot_id / asset_id / media_type(image|video) / version_number / generation_id / is_active / rating / notes（`media_version.py`）。约束：`uq_media_versions_shot_number(shot_id, media_type, version_number)` 唯一、`uq_media_versions_active(shot_id) WHERE is_active=1` 单 active。
- `shots.active_image_version_id / active_video_version_id` 指向 media_versions.id（`shot.py`）。
- `VersionService`（`version_service.py`）：create_media_version 用 `MAX(version_number)+1` 分配、写前先 `_clear_active`（ORM 逐个置 0）、`make_active=True` 默认、事件 `shot.active_version.changed`。版本不可变语义靠"只翻 is_active、永不 UPDATE 旧行"实现。
- 写路径：Generation worker `_persist_output` → `AssetService.register_asset`（拷贝文件→缩略图→DB commit）→ `VersionService.create_media_version`（commit）→ shot active 指针（同一 commit 内），**asset / version / shot / generation 完成分属多次 commit**（P1-E2-T03 遗留 P0）。

### 与 Alpha 目标的冲突

1. **两套版本语义**：Alpha 要求 Asset 自身版本化（`version_group_id + version_number`、`status`、`source_type`、`checksum`、`parent_asset_id`），Shot 指向 `active_*_asset_id`；现状版本元数据在独立包装表，Asset 无版本概念。
2. **版本组泛化**：Alpha 需要 `ownerType+ownerId+purpose` 的 VersionGroup（SHOT_IMAGE / SHOT_VIDEO / CHARACTER_REFERENCE / LOCATION_REFERENCE / ...）；media_versions 只能表达"Shot × image|video"两种，Character/Location 参考图版本化无处安放。
3. **Provenance 断层**：`generation_outputs(generation_id, asset_id, role)` 目标要求 Generation 多输出指向 Asset；现状 `generations.output_asset_id` 单值弱引用 + media_versions.generation_id 文本，无法回答"这个视频用了哪张图、哪个角色版本"。
4. **查询分散**：版本列表、Active、历史分布在 media_versions + shot 指针 + asset 三处，Alpha 的 `GET /assets/{id}/provenance`、`GET /shots/{id}/image-versions` 无法单表完成。

## 2. Decision

### 2.1 Asset 表升级为自版本化

`assets` 新增列（Alembic，SQLite batch mode）：

| 列 | 类型 | 说明 |
|---|---|---|
| version_group_id | TEXT | 确定性版本组 ID（见 2.2），NULL 表示未版本化（如 thumbnail/临时文件） |
| version_number | INTEGER | 组内版本号，从 1 开始 |
| status | TEXT NOT NULL DEFAULT 'ready' | ready / processing / stale / missing / corrupted / failed / archived |
| source_type | TEXT NOT NULL DEFAULT 'generated' | generated / imported / edited / derived / captured |
| checksum | TEXT | SHA-256（生成/导入时计算） |
| parent_asset_id | TEXT FK→assets.id | 派生关系（upscale/edit），Generation Input 仍必须记录 |
| generation_id | TEXT | 由 source_generation_id 迁移改名（一次性 RENAME） |

约束：
- 部分唯一索引 `uq_assets_version(version_group_id, version_number) WHERE version_group_id IS NOT NULL AND deleted_at IS NULL`（并发保护，SQLite 单写者下与 max+1 配合）。
- 索引 `idx_assets_version_group(version_group_id)`、`idx_assets_generation(generation_id)`、`idx_assets_parent(parent_asset_id)`。

### 2.2 Version Group 表示

**不建物理 `version_groups` 表**（遵循领域文档 §29-30：Alpha 第一轮用 `version_group_id` 字符串，Beta 再独立成表），组 ID 采用确定性格式：

```text
vg:{owner_type}:{owner_id}:{purpose}
示例：vg:shot:01Kxxx:SHOT_IMAGE / vg:shot:01Kxxx:SHOT_VIDEO
```

Active 版本表达：
- **Shot 媒体**：`shots.active_image_asset_id / active_video_asset_id`（新列，替代 active_*_version_id）——与 Alpha DB 设计 §22 一致。
- **Character/Location 参考**：由 CharacterVersion/LocationVersion 的 `is_master` 表达（P2-T007~T009 落地），不占 assets。

### 2.3 删除 media_versions

- 迁移（同一版本内完成）：为每条 media_versions 行在 assets 上回填 version_group_id/version_number；`is_active=1` → 写入对应 `shots.active_*_asset_id`；验证后 **DROP media_versions** 与 `shots.active_*_version_id` 列。
- 回滚：down revision 从 assets 重建 media_versions（active 指针回填 is_active）。数据不丢失（asset 行全部保留）。
- 语义保持：版本不可变（新行不覆盖旧行）、每 shot 每 purpose 单 active（迁移时校验，违反即失败停止）。

### 2.4 写路径调整（顺带解决 P1-E2-T03 的一部分）

`Generation 完成` 事务收拢为**单个 commit**（在 SQLite 单写者下可行）：
```text
TX: INSERT asset（含 version_group_id/version_number）
  + UPDATE generation status=completed/output_asset_id
  + 首版本时写 shot.active_*_asset_id
  COMMIT
```
版本号分配仍在事务内 max+1（唯一索引兜底）；`set-active` 仍是显式业务操作（POST …/activate），写 `shots.active_*_asset_id` 并发布 `shot.active_version.changed`。

### 2.5 API 契约（与 backend 设计 §110 对齐）

- `GET /shots/{shotId}/image-versions`、`GET /shots/{shotId}/video-versions`（返回 Asset 摘要 + active/latest/status）
- `POST /shots/{shotId}/image-versions/{assetId}/activate`、video 同理
- `GET /assets/{assetId}/provenance`（依赖 generation_inputs/outputs，随 P3-T012/T013 落地）
- 保留 `POST /media-versions/{id}/activate` 过渡别名？**不保留**——同步迁移前端 VersionStrip/VersionReviewPage（同一变更集内完成，前端只调新端点）。

## 3. Alternatives

| 方案 | 评估 |
|---|---|
| A. 保留 media_versions 包装 + Asset 加版本列（双轨） | ❌ 版本语义两处、provenance 查询断裂、Character/Location 无版本家、generation_outputs 无法指向包装表。双轨过渡期收益 < 维护成本 |
| B. 万能版本表（entity_type/entity_id/snapshot_json） | ❌ 领域文档 §59 已否：约束弱、JSON 难查询、迁移困难 |
| C. 现在就建物理 version_groups 表 | ⭕ 可接受，但 Alpha 只有 shot 媒体需要 active 表达（在 shot 列），其余组无额外属性；领域文档明确 Beta 再独立。**推迟**，避免过度建模 |
| D. 保留 media_versions 作为只读兼容视图 | ❌ 任何写入路径都要同步两套表，bug 温床；一次性迁移更安全 |

## 4. Consequences

### 迁移步骤（Alembic，单迁移 + 回填 + 验证）

1. batch_alter assets 加列；RENAME source_generation_id → generation_id；建索引。
2. 建 shots.active_image_asset_id / active_video_asset_id（可空）。
3. 回填脚本：遍历 media_versions（按 shot 排序），组 ID 按 2.2 生成；`is_active=1` 写 shot 指针；校验（每组的 active 唯一、版本号连续）。
4. 校验通过后 DROP media_versions、shots.active_*_version_id。
5. down revision：从 assets 重建 media_versions（version_group_id=vg:shot:…:PURPOSE → shot_id+media_type；active 指针 → is_active）。

### 代码变更

- VersionService：改为 AssetVersionService 语义（组解析、assign、activate、list），或保留类名但改实现（建议按 Alpha 模块化重命名）。
- Generation worker：_persist_output 合并事务 + 版本分配（见 2.4）。
- 前端：VersionStrip/VersionReviewPage/ShotInspector 改调新端点；version item 展示 active/latest/status/thumbnail。
- 测试：版本唯一索引冲突、单 active 不变量、迁移 round-trip（从空库 + 从现有库升级）、完成链单事务失败注入。

### 风险与缓解

- 迁移回填失败 → 迁移在事务内执行 + down 可回滚；先在 staging 数据上 dry-run。
- 前端同变更集改端点 → 无灰度窗口；桌面本地应用可接受（Alpha 未发布）。
- `source_generation_id` 改名影响：全库 grep 替换（models/worker/asset_service/API），一次性。

### 关联任务

P3-T006/T007/T008/T009、P3-T011~T016（Generation 实体与 provenance 随此模型）、P1-E2-T03（完成链原子化）、前端 F041~F050（AssetStore/VersionStrip/Provenance）。

---

## 5. 决定人

需用户（项目负责人）评审确认本 ADR 后，P3 版本系统任务方可按此落地。本 ADR 批准前禁止开始 media_versions 相关迁移编码。
