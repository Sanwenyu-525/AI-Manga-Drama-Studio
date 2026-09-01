# Autonomous Iteration Report 06 — 场景信息编辑（Scene Properties）

> 自主产品迭代第六轮（Post-MVP） · 2026-09-01
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`
> 上一轮：`docs/reports/autonomous-iteration-2026-09-01-agent-refresh-recovery.md`

---

## Current Product Status

Post-MVP 自主迭代第 6 轮。一致性（角色/场景）、就绪度（缺口可见）、Agent 上下文恢复已闭环；
本轮补上「人机协同」的场景侧闭环——AI 拆解后的场景环境可人工细化，改时段/光照即触发连续性
重算与陈旧标记，引导重生成。

## Opportunities Found（Top 6）

| Opportunity | Problem | Value | Cost | Priority |
|---|---|---|---|---|
| **场景信息编辑（Scene Properties）** | 场景环境（时段/光照/天气/氛围/描述）只读；多个 UI 提示「缺环境」却无修复入口 | 高（可控性） | 低（后端已就绪） | **P1 本轮选** |
| AI Director update_scene 工具 | 用户想「把这场戏改成夜晚」Agent 无法提案 | 中-高 | 中 | P2（新进候选，依赖场景编辑） |
| 契约防回归 CI | 契约断点无自动防线 | 中（DX） | 低 | P1（未选） |
| 产出覆盖纳入就绪度（视频/音频） | 就绪度不含视频/配音缺口 | 中 | 低 | P2（未选） |
| 场景批量环境应用 | 多场景统一改时段需逐场景编辑 | 中 | 低 | P3（新进候选） |
| 镜头级地点覆盖 | 多地点场景单镜头指定 | 中 | 低 | P3（未选） |

## Selected Opportunity

**场景信息编辑（Scene Properties）：让 AI 拆解后的场景环境可人工细化**。

### Why This
- **来源 1（功能存在但未形成完整体验）+ 操作断点**：`PATCH /scenes/{id}` 早已支持
  time_of_day/lighting/weather/mood/description，且 `update_scene` 内置 **P8-T017 hook**
  （场景基准变更 → 连续性重算 + 活跃资产 stale 标记）。但前端无编辑入口——AI 拆解后场景环境
  不可改。更讽刺的是：多个 UI 已提示「场景缺环境信息」（ShotInspector `sceneOk`、就绪度缺口），
  却无修复路径。这是教科书级的「报问题但没给修法」断点。
- 对齐 **Controllability / 人机协同**：AI Generate → Human Edit → AI Regenerate 循环的场景侧。
  改时段/光照 → 连续性重算 → 活跃资产 stale → 引导重生成 → 更一致的画面。

### Why Now
- 后端 100% 就绪（零后端改动）；迭代 03 的地点绑定已在场景头建好 PATCH + invalidate 交互模式，
  本轮补齐其余字段，增量最小、风险最低。
- 迭代 05 刚证明「Agent 上下文可恢复」，本轮把「人类可细化场景」补上——人机两侧闭环。

### Why Not Others
- **AI Director update_scene 工具**：价值真实但依赖场景编辑 UI 的语义稳定后设计（已入候选）。
- **契约防回归 CI**：工具链防线，独立小轮。
- **产出覆盖纳入就绪度**：对已交付 readiness 的增量，价值有限。
- **M2 多参考图**：需 M1 真实使用反馈（Value Gate）+ 高成本。

## What Was Built

### 前端（纯前端，零后端改动）
| 变更 | 位置 |
|---|---|
| `ScenePropertiesEditor`——时段/光照/天气/氛围/描述表单（从 scene 预填、脏检查、`PATCH /scenes/{id}` {revision, patch}、空字符串=清空、**409 乐观并发冲突提示**、ApiErrorPanel 复用） | [ScenePropertiesEditor.tsx](../../frontend/src/features/storyboard/ScenePropertiesEditor.tsx)（新） |
| StoryboardView 场景头「编辑场景」按钮 + 内联面板（与迭代 03 地点绑定同区同模式）；保存后 invalidate scene/storyboard/scenes/sceneContinuity/continuityWarnings | [StoryboardView.tsx](../../frontend/src/features/storyboard/StoryboardView.tsx) |
| CSS（scene-props-editor/grid/actions，全 token 复用） | [styles.css](../../frontend/src/styles.css) |

### 数据流闭环
UI Entry（场景头「编辑场景」→ 表单）→ User Operation（改时段/光照… → 保存）→ Frontend State（ScenePropertiesEditor 脏检查 + 409 冲突态）→ API（PATCH /scenes/{id} {revision, patch}）→ Backend（SceneService.update_scene 既有 + P8-T017 连续性重算 + 活跃资产 stale 标记）→ Persistence（revision+1 / scene_continuity_states 环境基准更新）→ Result（SceneRead）→ Frontend Feedback（invalidate 各级查询 + 关闭面板）→ Reuse（api.patch / ApiErrorPanel / queryKeys / 场景头既有模式全复用）。

## Validation

- 前端：vitest 全量 **298 passed**（新增 4：从场景预填 / 脏检查 + PATCH 负载 / 409 冲突提示 / 保存成功 onClose）。
- 后端：**零改动**；`test_continuity` + `test_episode_scene_crud` 29 项通过（PATCH 场景 + P8-T017 链路的既有覆盖）。
- tsc -b 0 错 · eslint 0 错 · ruff（本轮无后端改动）· vite build ✅
- **live HTTP smoke**（`scripts/smoke_scene_edit.py` 5 步）：PATCH 场景时段/光照/氛围/描述 → revision 1→2 → `GET /scenes/{id}/continuity` 验证 **P8-T017 重算已把新环境基准传播**到 scene_continuity_states（time_of_day=夜晚/lighting=月光/mood=紧张）。

## Core Flow Regression

改动面 = Storyboard 场景头（Storyboard→Image 一环）。后端零改动（无 Schema/契约变更）；前端仅在场景头新增一个按钮 + 内联编辑器，既有地点绑定/生成菜单/工具栏零改动；PATCH 走既有 `update_scene` 全不变量（revision 乐观并发 / P8-T017 hook / scene.updated 事件）。全量 vitest + 场景/连续性后端测试通过即证。

## Remaining Risks

1. 409 冲突提示「关闭重开」是轻量处理（编辑器以最新 scene 重新挂载）；同屏内自动刷新表单留待后续。
2. 场景环境编辑目前不影响生成 prompt 直接拼装（prompt 拼装归 P2-E4-T02 prompt profile，是独立后续）——本轮价值在连续性准确性与陈旧标记引导。
3. 编辑器保存后自动关闭（无「保存并继续编辑」）——够用，符合最小可行。

## Backlog Changes

- **Done**：场景信息编辑（→ FEATURE_MAP Scene 行）。
- **新进 Candidate**：AI Director update_scene 工具（P2，依赖场景编辑语义）；场景批量环境应用（P3）。
- 维持：产出覆盖纳入就绪度（P2）、契约防回归 CI（P1）、镜头级地点覆盖（P3）、M2 多参考图（P2）。

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **契约防回归 CI（P1）**——多轮迭代后端点持续增多（OpenAPI 170+ operations），自动防线价值上升；独立小轮。
2. **AI Director update_scene 工具（P2）**——场景编辑 UI 语义已稳，Agent 提案场景级修改（走既有 Proposal/风险分级/ChangeSet 流）直接增强差异化 Agent 能力。
3. **产出覆盖纳入就绪度（P2）**——视频/配音缺口并入 readiness。
4. **M2 多参考图 role 化（P2）**——若 M1+场景参考真实使用反馈成立则升级。
