# Autonomous Iteration Report 04 — 生产就绪度（Production Readiness）

> 自主产品迭代第四轮（Post-MVP） · 2026-09-01
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`
> 上一轮：`docs/reports/autonomous-iteration-2026-09-01-location-consistency.md`

---

## Current Product Status

Post-MVP 自主迭代第 4 轮。角色一致性（M1 参考图）、场景一致性（迭代 03 地点参考图）已闭环；
本轮把「这部作品还差什么」显性化——工作区新增前瞻式生产就绪度，补齐反应式「需要处理」的盲区。

## Opportunities Found（Top 6）

| Opportunity | Problem | Value | Cost | Priority |
|---|---|---|---|---|
| **生产就绪度（Project Health 深化）** | 概览只报错不报缺口；角色无 MASTER / 场景未绑定地点时生成仍会继续（K2 痛点） | 很高 | 低-中 | **P1 本轮选** |
| AI Director 刷新恢复 | 刷新丢失对话流/工具进度 | 中 | 中 | P2（未选） |
| 镜头级地点覆盖（多地点场景） | 一场多地点无法单镜头指定 | 中 | 低 | P3（未选） |
| 产出覆盖纳入就绪度（视频/音频） | 就绪度暂不含视频/配音缺口 | 中 | 低 | P2（新进候选） |
| 契约防回归 CI | 契约断点无自动防线 | 中（DX） | 低 | P1（未选） |
| M2 多参考图 role 化 | 单 MASTER 覆盖不了多角度 | 高 | 高 | P2（未选，需 M1 反馈） |

## Selected Opportunity

**生产就绪度（Production Readiness）：让一致性缺口在生成前可见**。

### Why This
- **来源 2（核心流程）+ 来源 25（Project Health）**：工作区概览是「反应式」的（只列失败/运行中），
  不回答「这部作品还差什么」。角色无 MASTER / 场景未绑定地点或地点无 MASTER 时，生成**无法注入
  一致性参考图**——这正是 Sprint 04 实证的头号痛点 K2。用户会在不一致资产上浪费大量生成。
- 直接承接迭代 03：地点绑定刚成为真实能力 → 用户立刻需要知道「哪些场景还没绑定」。
- 确定性规则聚合（无 LLM、只读），符合「Deterministic First」红线，零 AI 风险。

### Why Now
- 迭代 03 交付后产生新需求（绑定覆盖率可见性），本轮闭环；三个数据源（characters.master_version_id /
  scenes.location_id / continuity_warnings）全部就绪，增量成本最低。
- 三轮自主迭代后基线稳定，适合纯增量。

### Why Not Others
- **AI Director 刷新恢复**：mid-run 水合复杂且有风险；run 本身可经 server query 恢复；适合独立轮。
- **镜头级地点覆盖**：多地点场景是低频场景。
- **M2 多参考图**：需 M1 真实使用反馈（Value Gate）+ 高成本。
- **契约防回归 CI**：工具链，独立小轮。

## What Was Built

### 后端（纯增量，零 Schema 变更）
| 变更 | 位置 |
|---|---|
| `ReadinessRead` / `ReadinessMetric` / `SceneBindingReadiness` DTO | [readiness.py](../../backend/app/domain/readiness.py)（新） |
| `ProjectReadinessService.readiness()`——确定性聚合：characters {total/ready/missing}（ready=有 MASTER）· scene_binding {scenes_total/bound/bound_with_master/unbound}（bound_with_master=绑定且有 MASTER）· continuity_open（status=open 计数）；场景地点用一次 dict 查避免 N+1 | [readiness_service.py](../../backend/app/services/readiness_service.py)（新） |
| `GET /projects/{id}/readiness`（Router 薄委派；契约 §103.1） | [projects.py](../../backend/app/api/projects.py) |
| 契约 §103.1 生产就绪度文档 | [api-event-contract-v0.1.md](../../docs/api-event-contract-v0.1.md) |

### 前端（复用优先，零新依赖）
| 变更 | 位置 |
|---|---|
| `ProjectReadiness` / `ReadinessMetric` / `SceneBindingReadiness` 类型 + `queryKeys.readiness` | [types.ts](../../frontend/src/api/types.ts) · [queryKeys.ts](../../frontend/src/api/queryKeys.ts) |
| 工作区「生产就绪度」面板：三指标缺口卡片（角色 MASTER 覆盖 / 场景地点绑定 / 连续性警告）→ 点击跳转角色·分镜·连续性；全就绪 = 干净态「一致性资产就绪」 | [WorkspaceOverviewPage.tsx](../../frontend/src/features/workspace/WorkspaceOverviewPage.tsx) |
| CSS（ws-ready-card / ws-ready-row / bad·ok 语义色，全 token 复用） | [styles.css](../../frontend/src/styles.css) |

### 数据流闭环
UI Entry（工作区「生产就绪度」面板）→ User Operation（查看缺口 → 点击跳转）→ Frontend State（readiness query + staleTime）→ API（GET /projects/{id}/readiness）→ Backend（ProjectReadinessService 确定性聚合）→ Persistence（读 Project State，只读不写）→ Result（三指标）→ Frontend Feedback（缺口卡片/干净态）→ Reuse（queryKeys/mediaUrl/ApiErrorPanel/现有 ws 面板样式全复用）。

## Validation

- 后端：pytest 全量 **629 passed, 1 skipped**（新增 5：空项目全零 / 角色 MASTER 覆盖 / 场景绑定三态 / 连续性计数 / 项目 404）。既有 flaky `test_generation_atomicity` 本次通过。
- 前端：vitest 全量 **289 passed**（新增 4：全就绪干净态 / 角色缺口跳转 / 场景缺口跳转 / 连续性计数跳转）。
- tsc -b 0 错 · eslint 0 错 · ruff `app` All checks passed · vite build ✅
- **live HTTP smoke**（`scripts/smoke_location_ref.py` 扩至 8 步）：step 8 验证 readiness 聚合与前述状态一致（1 场景已绑定且有 MASTER → bound_with_master=1，角色 0，连续性 0）。

## Core Flow Regression

改动面 = 工作区概览 + 新只读端点。后端零 Schema / 零破坏性契约变更（新端点纯 additive）；前端只在概览新增面板，既有状态区/管线/剧集卡/最近生成/需要处理零改动；全量 pytest/vitest 通过即证。

## Remaining Risks

1. 就绪度卡片跳转落点在模块首页（角色/分镜/连续性）而非具体缺口（未绑定场景列表）——够用但不精确；已入候选「就绪度缺口一键跳转细化」。
2. 只覆盖一致性缺口（角色/场景/连续性），不含视频/音频产出覆盖——已入候选「产出覆盖纳入就绪度」。
3. continuity_open 聚合未按严重度区分（info/warning/error）——首版统一计数，够用于提示。

## Backlog Changes

- **Done**：生产就绪度（含原「地点覆盖健康度」候选 → 交付并移除该候选行）。
- **新进 Candidate**：产出覆盖纳入就绪度（P2）；就绪度缺口一键跳转细化（P3）。
- 维持：AI Director 刷新恢复（P2）、镜头级地点覆盖（P3）、契约防回归 CI（P1）等。

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **AI Director 刷新恢复（P2）**——后端 run 已持久化，缺口是消息端点 + 前端水合；多轮一致性/就绪度迭代后，把「Agent 上下文可恢复」补上，形成完整人机协同体验。
2. **产出覆盖纳入就绪度（P2）**——把视频/配音产出缺口并入就绪度（复用 workspaceMetrics 思路）。
3. **契约防回归 CI（P1）**——独立小轮。
4. **镜头级地点覆盖（P3）**——多地点场景。
