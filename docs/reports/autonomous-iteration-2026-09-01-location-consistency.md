# Autonomous Iteration Report 03 — 场景一致性闭环（地点库 + 场景绑定 + 生成注入地点参考图）

> 自主产品迭代第三轮（Post-MVP） · 2026-09-01
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`
> 上一轮：`docs/reports/autonomous-iteration-2026-09-01-batch-shot-operations.md`

---

## Current Product Status

MVP 全部 Stage（A–D）+ P1/P2 关键项 + 真实链路验证已交付；Post-MVP 自主迭代第 3 轮。
核心生产链（Project → Script → Character → Scene → Storyboard → Image → Video → Audio → Asset → Export）全部可走通；
角色一致性（M1 参考图）已闭环；本轮把「场景一致性」从自由文本提升为与角色同构的可复用资产。

## Opportunities Found（Top 6）

| Opportunity | Problem | Value | Cost | Priority |
|---|---|---|---|---|
| **地点库前端闭环**（功能存在但零入口） | Location 后端 100% 落地，前端无法创建/管理地点 | 高 | 低（复用后端） | **P1 本轮选** |
| **场景绑定地点 + 生成注入地点参考图** | `scene.location_id` 自由文本；生成无地点参考 → 同场景画面环境漂移 | 很高（核心评价标准 Scene Consistency） | 中（复用 M1 管道） | **P1 本轮选** |
| 契约防回归 CI | 契约断点类 P0 无自动防线 | 中（DX） | 低 | P1（未选） |
| M2 多参考图 role 化 | 单张 MASTER 覆盖不了多角度/服装 | 高 | 高 | P2（未选，需 M1 使用反馈） |
| 地点覆盖健康度（Project Health 深化） | 工作区不显示未绑定地点/无 MASTER 的场景 | 中 | 低 | P2（新进候选） |
| AI Director 刷新恢复 | 刷新丢失对话流 | 中 | 中 | P2（未选） |

## Selected Opportunity

**场景一致性闭环：地点（Location）生产级管理 + 场景绑定 + 生成自动注入地点 MASTER 参考图**。

### Why This
- **来源 1 优先级最高的缺口**：Location 后端（Service/VersionService/API/事件/契约/前端类型/queryKeys/EntityVersionBlock `kind="location"`）全部就绪，但前端**零入口**——用户无法创建地点、上传地点视觉版本、设置 MASTER。这是「功能存在，但还没有形成完整体验」的教科书案例。
- **核心评价标准 Scene Consistency**：一致性引擎已覆盖角色（M1 参考图）与连续性规则（P8），但「场景视觉一致」缺失——同一场景多个镜头注入相同地点 MASTER 参考图，环境稳定。
- **复用优先、零新依赖**：完整复用 M1 参考图管道（write 溯源行 → worker 读行 → ImageRequest → ComfyUI 注入）+ EntityVersionBlock + CharactersSection 模式 + queryKeys/mediaUrl/ApiErrorPanel。

### Why Now
- M1 参考图前端闭环（迭代 01）已验证管道可用 → 把同一管道扩展到场景维度的**增量成本最低**。
- Location 后端是「沉睡资产」，越早闭环越好；三轮审计 + 迭代 02 后基线稳定（pytest 617 / vitest 276），适合纯增量。
- Sprint 04 实证 K2 一致性是头号痛点（`real-chain-validation-report.md`）——角色已解决，场景是下一个最痛维度。

### Why Not Others
- **M2 多参考图 role 化**：依赖 M1 真实使用反馈（Value Gate），Dev Cost 高；场景维度是比「多角度角色图」更基础的一致性层，先补齐。
- **契约防回归 CI**：DX 防线价值真实但属工具链，适合独立小轮或搭车。
- **AI Director 刷新恢复**：UX 缺口但非核心生产链，提案可经 server query 恢复。
- **地点覆盖健康度**：本轮交付后可自然成为下一轮候选（已入候选池）。

## What Was Built

### 后端（纯增量，零 Schema 变更）
| 变更 | 位置 |
|---|---|
| `_location_references(shot_id)`——shot → scene.location_id → Location MASTER → active LocationVersion asset（未绑定/无 MASTER/非 active → 空） | [generation_service.py](../../backend/app/services/generation_service.py) |
| `create_generation` 自动路径在角色参考后追加 `role=location_reference` 行（order_index 4000 > 角色 3000.x → worker 取前 MAX_REFERENCE_IMAGES 张时**角色优先、地点兜底**；显式 `reference_asset_ids` REPLACE 全部自动解析含地点） | 同上 |
| `preview_references` / `generation_references` 返回地点引用（location_id/location_name，与 create 同源） | 同上 |
| worker `_load_reference_asset_ids` 过滤条件扩展为 `role.in_(("character_reference","location_reference"))`（顺序保持，去重不变） | [worker.py](../../backend/app/generations/worker.py) |
| DTO `ShotReferenceRead`/`GenerationReferenceRead` 增 `location_id`/`location_name`（additive，默认 None）；API 端点构造侧同步透传 | [domain/generation.py](../../backend/app/domain/generation.py) · [api/generations.py](../../backend/app/api/generations.py) |
| `INPUT_ROLES` 常量补 `LOCATION_REFERENCE`（消除 P3 报告记录的陈旧常量） | [generation_io.py](../../backend/app/db/models/generation_io.py) |
| 契约 §35 reference 语义更新 | [api-event-contract-v0.1.md](../../docs/api-event-contract-v0.1.md) |

### 前端（复用优先，零新依赖）
| 变更 | 位置 |
|---|---|
| **活动栏新增「地点」模块**：`LocationsWorkspacePage` + `LocationsSection`（列表 / 内联创建·编辑·删除 / EntityVersionBlock(`kind="location"`) 视觉版本链 / 关联设定文档，镜像 CharactersSection） | [LocationsSection.tsx](../../frontend/src/features/libraries/LocationsSection.tsx)（新）· [RailWorkspacePages.tsx](../../frontend/src/features/navigation/RailWorkspacePages.tsx) · [ActivityRail.tsx](../../frontend/src/components/shell/ActivityRail.tsx) · [router.tsx](../../frontend/src/app/router.tsx) · DESIGN.md 冻结序同步 |
| **StoryboardView 场景头部地点绑定选择器**：从项目地点库选择/取消绑定（`PATCH /scenes/{id}`，绑定后 accent 高亮 + 无参考图标注 + 空态引导去地点库） | [StoryboardView.tsx](../../frontend/src/features/storyboard/StoryboardView.tsx) |
| **ReferenceImagePicker 自动模式区分角色/地点参考**：地点缩略图「场景」徽标 + accent 描边；空态文案覆盖「场景未绑定地点」 | [ReferenceImagePicker.tsx](../../frontend/src/features/storyboard/ReferenceImagePicker.tsx) |
| 类型 `LocationUpdatePatch`/`LocationUpdateRequest` + `ShotReferenceRead`/`GenerationReferenceRead` 地点字段；CSS（location-menu / has-location / reference-thumb-location / reference-kind-badge / menu-empty） | [types.ts](../../frontend/src/api/types.ts) · [styles.css](../../frontend/src/styles.css) |

### 数据流闭环
UI Entry（活动栏「地点」→ 创建地点 + 上传参考图 + 设 MASTER；分镜板场景头 → 绑定地点）→ User Operation → Frontend State（queryKeys 各级 invalidate）→ API（locations CRUD / versions activate / PATCH scene.location_id）→ Backend（LocationService 既有 + SceneService 校验；GenerationService 自动解析追加地点参考）→ Persistence（generation_inputs `location_reference` 行）→ Result（preview 预览 / worker 注入 / 明细溯源）→ Frontend Feedback（ReferenceImagePicker 徽标 + 场景头 accent）→ Reuse（EntityVersionBlock / CharactersSection 模式 / M1 管道全复用）。

## Validation

- 后端：pytest 全量 **623 passed, 1 skipped**（新增 7：地点+角色并存且顺序正确、仅地点、未绑定与无 MASTER 跳过、显式替换含地点、预览含地点名、明细溯源、worker 路径注入 `[角色, 地点]`）。既有 1 例 flaky `test_generation_atomicity` 单跑通过（与本次无关，AGENTS.md 已记录）。
- 前端：vitest 全量 **285 passed**（新增 5：LocationsSection 列表/创建/删除 3 + ReferenceImagePicker 地点徽标/仅地点 2；activityRail 冻结序同步「地点」）。
- tsc -b 0 错 · eslint 0 错 · ruff `app` All checks passed · vite build ✅
- **live HTTP smoke**（`backend/scripts/smoke_location_ref.py`，mock providers）：7 步全通——health → 建项目/集/场景 → 地点+版本+MASTER → 场景绑定 → 预览返回地点 MASTER（含 location_name）→ generation_inputs 有 `LOCATION_REFERENCE` 行 → 生成明细 references 地点溯源（source=auto）。

## Core Flow Regression

改动面 = 一致性资产（Location）+ 生成参考解析（Storyboard→Image 一环）。角色参考行为零变更（地点仅在自动路径追加、排在角色后，显式 REPLACE 语义不变）；worker 仅扩过滤集合（character+location），既有 character 行为不受影响；`PATCH /scenes/{id}` 复用既有校验（LocationService 早已落地）；无 DB Schema / 破坏性契约变更；全量 pytest/vitest 通过即证。activityRail 冻结序新增「地点」一项（新能力，非重排，DESIGN.md 已同步）。

## Remaining Risks

1. **3 槽位预算**：一场 3 角色 + 1 地点时地点被裁剪（角色保面容优先）——设计如此，UI 提示「角色优先、地点兜底」；多角色场景如需地点需手动模式精选。
2. **真实引擎遵循度**：Z-Image Omni 对地点参考图的遵循度未在真实链路实测（依赖 M1 已建立的 ComfyUI 模板与 upload 通道；本轮仅 mock 验证）——留真实 ComfyUI 冒烟待后续。
3. 绑定地点不改已生成图片（Latest ≠ MASTER、不自动重生成红线）——用户需重新生成受影响镜头才能吃到场景一致性。
4. `scene.location_id` 兼容：既有场景若带自由文本 location_id（非库内 id），PATCH 校验会 422——UI 提供「不绑定」入口可纠正。

## Backlog Changes

- **Done**：场景一致性闭环（→ FEATURE_MAP Location 行 + Storyboard/Image 行）；「locations 表落地」旧候选因本轮交付从候选池移除。
- **新进 Candidate**：地点覆盖健康度（P2，Project Health 深化）；镜头级地点覆盖（P3，多地点场景）。
- 维持：M2 多参考图 role 化（P2）、契约防回归 CI（P1）、recent/change-sets 分页（P1）等。

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **地点覆盖健康度（P2）**——本轮交付后工作区概览可显示「X 个场景未绑定地点 / 无 MASTER」，让场景一致性缺口可见、可一键跳转补齐（与 #25 Project Health 深化一致，增量小）。
2. **镜头级地点覆盖（P3）**——多地点场景的单镜头地点指定（`shot_visual_spec.location_id` 已存在，解析优先级 scene → shot）。
3. **契约防回归 CI（P1）**——独立小轮或搭车。
4. **M2 多参考图 role 化（P2）**——若 M1+本轮地点参考在真实使用中反馈成立则升级。
