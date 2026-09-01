# Autonomous Iteration Report 02 — 镜头多选批量操作

> 自主产品迭代第二轮（Post-MVP） · 2026-09-01
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`
> 上一轮：`docs/reports/autonomous-iteration-2026-08-31-refimages.md`

---

## Selected Opportunity

**镜头多选批量操作：ShotGrid 多选态 + 批量操作栏**（Backlog Candidate，P1，UV=4）。

### Why This
- 全仓无任何 multiSelect 机制（上轮代码扫描实证）；批量改景别/删除/重排/生图只能逐个点，是生图高频路径上最明显的效率断点。
- UV=4 为候选池最高且**零依赖**（M2 依赖 M1 用户验证、契约 CI 属 DX 防线）。

### Why Now
迭代 01 报告 Next #1；M1 参考图闭环后单镜头体验完整，批量入口成为下一个显性缺口；三轮审计修复后基线稳定，适合纯增量功能。

### Why Not Others
契约防回归 CI（P1）价值真实但属防线型 DX，适合独立小轮或搭车；recent/change-sets 分页太小不成主题；M2 需 M1 真实使用反馈，不抢跑。

## What Was Built

### 后端（纯增量，零 Schema 变更，复用 `update_shot`/`delete_shot` 全部不变量）
| 变更 | 位置 |
|---|---|
| `POST /scenes/{scene_id}/shots/batch-update`——`{shot_ids, patch}`，**批量覆盖语义**：服务端取每镜头当前 revision 应用（客户端无需 per-shot revision），逐镜头走 `update_shot`（revision+1 / dirty_state / PromptVersion / `shot.updated` 事件 / continuity 重算与单镜头编辑完全一致） | [api/shots.py](../../backend/app/api/shots.py) · [shot_service.py](../../backend/app/services/shot_service.py) `batch_update_shots` |
| `POST /scenes/{scene_id}/shots/batch-delete`——逐镜头软删除 + `shot.deleted` 事件 | 同上 `batch_delete_shots` |
| **逐项结果**（对齐 ChangeSet undo 模式）：`{requested, succeeded, failed, results[{shot_id, status: updated\|deleted\|failed, error_code?, message?}]}`——部分失败仍 200，一个坏 id 不阻塞其余；重复 id / 空 patch → 422，场景不存在 → 404，跨场景/未知 id 计入该项 failed | [domain/shot.py](../../backend/app/domain/shot.py) `ShotBatchResult` |
| 契约文档 §19 批量操作段 | [api-event-contract-v0.1.md](../api-event-contract-v0.1.md) |

### 前端（复用优先，零新依赖）
| 变更 | 位置 |
|---|---|
| `selectionStore` 多选能力：`toggleShot`（additive 切换）/ `setShotIds`（Shift 范围选）；`selectShot` 单选替换语义不变 | [selectionStore.ts](../../frontend/src/stores/selectionStore.ts) |
| 网格多选交互：Ctrl/Cmd+点击切换、Shift+点击范围选（锚点=最近单击）、卡片悬停 checkbox（`pointer-events: auto` 覆盖缩略图 none，stopPropagation 防误触单击/双击）；列表视图同款修饰键 | [VirtualizedShotGrid.tsx](../../frontend/src/features/storyboard/VirtualizedShotGrid.tsx) |
| **BatchActionBar**（选中 >1 浮出）：计数 + 批量生成 / 改景别（六值下拉）/ 前移 / 后移 / 删除（confirm）/ 清除选择；重排复用既有 `PATCH /scenes/{id}/shots/reorder`（`moveBlock` 整块位移 + 全序重算，边界 no-op 提示，零后端改动） | [BatchActionBar.tsx](../../frontend/src/features/storyboard/BatchActionBar.tsx)（新） |
| **批量生成去掉 fail-fast**：`Promise.all` → `Promise.allSettled` + 逐项聚合——409 幂等门计为「已在进行中」而非失败（诚实计数，含首个真实错误原因）；既有菜单批量（待生成/失败/整场景）同路径受益 | [batchSubmit.ts](../../frontend/src/features/generation/batchSubmit.ts)（新）· [StoryboardView.tsx](../../frontend/src/features/storyboard/StoryboardView.tsx) |
| 错误反馈：mutation error 走既有 `ApiErrorPanel`；部分结果进 `generationNotice`（如「已更新 1/2 个镜头，1 个失败」）；WS invalidate 复用既有 `shot.updated/deleted` 映射 | 同上 |
| CSS（全 token 复用：--accent/--hairline/--radius/--red） | [styles.css](../../frontend/src/styles.css) |

### 数据流闭环
UI Entry（卡片 checkbox / Ctrl+点击 → BatchActionBar）→ User Operation（选操作）→ Frontend State（selection.shotIds 多选 / moveBlock 全序）→ API（batch-update/batch-delete/batch 提交/reorder）→ Backend（Service 逐项复用单镜头不变量）→ Persistence（revision+1 / 软删除 / 事件）→ Result（逐项 results）→ Frontend Feedback（ApiErrorPanel + 聚合 notice + WS invalidate）→ Reuse（reorder 契约 / update_shot / delete_shot / ApiErrorPanel 全复用）。

## Validation

- 后端：pytest 全量 **617 passed, 1 skipped**（新增 5 项：batch-update 全量/部分失败/422+404 校验、batch-delete 软删除/部分失败）
- 前端：vitest 全量 **276 passed**（新增 selectionStore 4 项、batchSubmit 聚合 3 项、BatchActionBar+moveBlock 10 项、网格多选 3 项）
- tsc -b 0 错 · eslint 0 错 · ruff `app` All checks passed · vite build ✅

## Core Flow Regression

改动面 = Storyboard 选择与镜头 mutation（核心链路 Storyboard→Image 一环）。单镜头 PATCH/DELETE/生成行为零变更（batch-update 内部逐镜头调用 `update_shot` 原实现；单选语义、Inspector、既有批量菜单入口保留）；后端端点纯 additive、无 DB Schema/破坏性契约变更；全量 pytest/vitest 通过即证。

## Remaining Risks

1. **批量生图并发无上限**：选中 N 镜即提交 N 个任务（409 门挡同镜头重复，但不同镜头全放行）——大量选中时依赖队列自身吞吐；观察后再考虑前端分批提交。
2. 批量改景别走 `update_shot` 会把触及镜头全部置 `dirty_image`（与单改语义一致，但用户可能低估「重生成标记」的扩散面）；提示文案未做特殊说明。
3. Shift 范围选/前移后移仅在**当前场景网格序**内有效（设计如此；跨场景批量不在本轮范围）。
4. checkbox 悬停显隐在触屏设备无 hover 态（桌面 Tauri 场景无碍）。

## Backlog Changes

- **Done**：镜头多选批量操作（→ FEATURE_MAP Storyboard 行）
- **顺手收口**：后端报告建议 #2（分页）之外的批量域无新增候选；契约防回归 CI 维持 P1 候选

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **契约防回归 CI**（P1，小成本高杠杆）——本轮联调报告建议 #1，拦截 3/4 类 P0 契约断点。
2. **M2 多参考图 role 化**（P2）——若 M1 实际使用反馈成立则升级。
3. **recent/change-sets 分页**（P1，小）——可搭车。
