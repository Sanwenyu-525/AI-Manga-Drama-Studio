# Autonomous Iteration Report 08 — 过期镜头闭环（Stale 可见 + 批量重生成）

> 自主产品迭代第八轮（Post-MVP） · 2026-09-01
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`
> 上一轮：`docs/reports/autonomous-iteration-2026-09-01-agent-update-scene.md`

***

## Current Product Status

Post-MVP 自主迭代第 8 轮。一致性、就绪度、Agent 恢复/场景工具已闭环；本轮把
「编辑→过期→重生成」的循环断点补上——场景环境变更（手动或 Agent）把镜头标 stale 后，
前端现在能看见「过期」并一键批量重生成。

## Opportunities Found（Top 6）

| Opportunity                  | Problem                                           | Value                        | Cost | Priority         |
| ---------------------------- | ------------------------------------------------- | ---------------------------- | ---- | ---------------- |
| **过期镜头闭环（stale 可见 + 批量重生成）** | 场景编辑/Agent update\_scene 把镜头标 stale，但前端看不见也无批量重生成 | 高（Class 4 修改成本 + Class 2 高频） | 低    | **P1 本轮选**       |
| 契约防回归 CI                     | 契约断点无自动防线                                         | 中（DX）                        | 低    | P1（未选，连续 3 轮被挤出） |
| 视频/音频 stale 纳入过期闭环           | 过期徽标只覆盖图片                                         | 中                            | 低    | P2（新进候选）         |
| 产出覆盖纳入就绪度                    | 就绪度不含视频/配音缺口                                      | 中                            | 低    | P2（未选）           |
| 就绪度纳入过期镜头计数                  | readiness 不显示过期待重生成                               | 中                            | 低    | P3（新进候选）         |
| M2 多参考图 role 化               | 单 MASTER 覆盖不了多角度                                  | 高                            | 高    | P2（未选，需 M1 反馈）   |

## Selected Opportunity

**过期镜头闭环：连续性 stale 可见 + 批量重生成**。

### Why This

- **来源 2（核心流程）+ 来源 3（MVP 缺口）+ Class 4/2**：迭代 06（场景编辑）与迭代 07
  （Agent update\_scene）都会触发 P8-T017 把镜头活跃图片资产标 stale，但前端**不展示**（ShotCard
  只有「需重生成」dirty 徽标，不认资产级 stale）**也无批量重生成入口**——用户改了场景时段后
  不知道哪些镜头过期、要逐个重生成。

- 这是「编辑→过期→重生成」生产循环的**断点**：系统标记了过期，却不告诉用户、不给一键修复。

### Why Now

- 迭代 06/07 刚让「标 stale」成为高频路径（场景编辑 + Agent 都触发）；闭环只差「可见 + 批量」。

- 后端 P8-T017 stale 机制已成熟；`ShotSummary` 聚合端点一次批量查询即可暴露，零 Schema。

### Why Not Others

- **契约防回归 CI**：DX 防线，已连续 3 轮被挤出——下轮必须重估（OpenAPI 180+ operations）。

- **视频/音频 stale**：图片闭环先立住，再扩维度。

- **M2 多参考图**：需 M1 真实使用反馈（Value Gate）+ 高成本。

## What Was Built

### 后端（纯增量，零 Schema 变更）

| 变更                                                                                                  | 位置                                                                                                                  |
| --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `ShotSummary.image_stale: bool = False`——`get_storyboard` 一次批量查询活跃图片资产 `status="stale"`（P8-T017 标记） | [domain/shot.py](../../backend/app/domain/shot.py) · [shot\_service.py](../../backend/app/services/shot_service.py) |
| 契约 §100 ShotSummary DTO 注释                                                                          | [api-event-contract-v0.1.md](../../docs/api-event-contract-v0.1.md)                                                 |

### 前端（复用优先）

| 变更                                                                                                 | 位置                                                                                                                                                                                    |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ShotSummary.image_stale` 类型 + ShotCard「过期」徽标（`.badge.stale` 红，区别于 dirty 的「需重生成」）                  | [types.ts](../../frontend/src/api/types.ts) · [VirtualizedShotGrid.tsx](../../frontend/src/features/storyboard/VirtualizedShotGrid.tsx) · [styles.css](../../frontend/src/styles.css) |
| 生成菜单「重新生成过期镜头」（`staleShots = image_stale && 无进行中`，走 `batchSubmit` allSettled 聚合——409 幂等门计「进行中」非失败） | [StoryboardView.tsx](../../frontend/src/features/storyboard/StoryboardView.tsx)                                                                                                       |

### 数据流闭环

UI（分镜板看到「过期」徽标 → 生成菜单「重新生成过期镜头」）→ Frontend（staleShots 过滤 + batchSubmit）→ API（批量 POST generations）→ Backend（Generation 队列 → 新资产 active）→ Persistence（资产 stale→active，shot active\_image\_asset\_id 指向新资产）→ Frontend Feedback（WS invalidate → image\_stale 回落 false）。

## Validation

- 后端：pytest 全量 **641 passed, 1 skipped**（新增 3：生成后 image\_stale=false / 场景编辑→true（含资产层确证 asset.status=stale）/ 重生成→false）。

- 前端：vitest 全量 **299 passed**（新增 1：image\_stale 镜头显示「过期」徽标）。

- tsc -b 0 错 · eslint 0 错 · ruff `app` All checks passed · vite build ✅

- **live HTTP smoke**（`scripts/smoke_stale_loop.py` 5 步）：生成 → image\_stale=false → 场景编辑（P8-T017）→ image\_stale=true（前端「过期」数据源）→ 重生成 → 回落 false。

## Core Flow Regression

改动面 = Storyboard 聚合 + 生成菜单。后端：`get_storyboard` 仅新增一个批量查询字段（`image_stale` 默认 false，旧 DTO 兼容）；`_to_summary` 增可选参数（既有调用不变）。前端：ShotCard 新增条件徽标（无 image\_stale 时零变化）、生成菜单新增一项（既有菜单项不变）。全量 pytest/vitest 通过即证。

## Remaining Risks

1. **仅覆盖图片资产**：视频/配音的 stale 未暴露（已入候选「视频/音频 stale 纳入过期闭环」）。
2. `image_stale` 与 `dirty_state="dirty_image"` 是两个信号（资产级 stale vs 镜头级 dirty）——徽标并存不冲突，但用户可能困惑「需重生成」vs「过期」；首版语义：过期=连续性环境变更导致，需重生成=镜头字段编辑导致。
3. 批量重生成走既有 409 幂等门（同镜头进行中计「进行中」非失败）——与迭代 02 一致。

## Backlog Changes

- **Done**：过期镜头闭环（→ FEATURE\_MAP Storyboard 行）。

- **新进 Candidate**：视频/音频 stale 纳入过期闭环（P2）；就绪度纳入过期镜头计数（P3）。

- 维持：契约防回归 CI（P1）、产出覆盖纳入就绪度（P2）、M2 多参考图（P2）等。

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **契约防回归 CI（P1）**——已连续 3 轮被挤出；8 轮迭代后 OpenAPI 180+ operations、前端调用点持续增长，自动防线价值达到峰值，下轮强烈建议做（独立小轮、纯工具链不干扰产品迭代）。
2. **视频/音频 stale 纳入过期闭环（P2）**——图片闭环立住后扩到视频/配音。
3. **产出覆盖纳入就绪度（P2）**——视频/配音缺口并入 readiness。
4. **M2 多参考图 role 化（P2）**——若 M1+场景参考真实使用反馈成立则升级。

