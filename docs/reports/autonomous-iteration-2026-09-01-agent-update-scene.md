# Autonomous Iteration Report 07 — AI Director update_scene 工具

> 自主产品迭代第七轮（Post-MVP） · 2026-09-01
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`
> 上一轮：`docs/reports/autonomous-iteration-2026-09-01-scene-properties-edit.md`

---

## Current Product Status

Post-MVP 自主迭代第 7 轮。一致性（角色/场景）、就绪度、Agent 刷新恢复、场景编辑已闭环；
本轮把「AI Director 只能改镜头」的能力缺口补上——**Agent 现在能提案场景级修改**，
「把这场戏改成夜晚」从不可能变成一条完整可撤销链路。

## Opportunities Found（Top 6）

| Opportunity | Problem | Value | Cost | Priority |
|---|---|---|---|---|
| **AI Director update_scene 工具** | Agent 只能改镜头；「把这场戏改成夜晚」无法达成 | 高（差异化 Agent 能力） | 中 | **P1 本轮选** |
| 契约防回归 CI | 契约断点无自动防线 | 中（DX） | 低 | P1（未选） |
| 产出覆盖纳入就绪度 | 就绪度不含视频/配音缺口 | 中 | 低 | P2（未选） |
| 场景批量环境应用 | 多场景统一改时段需逐场景编辑 | 中 | 低 | P3（未选） |
| 镜头级地点覆盖 | 多地点场景单镜头指定 | 中 | 低 | P3（未选） |
| M2 多参考图 role 化 | 单 MASTER 覆盖不了多角度 | 高 | 高 | P2（未选，需 M1 反馈） |

## Selected Opportunity

**AI Director update_scene 工具：场景级 Agent 能力**。

### Why This
- **来源 6（AI Agent 化）+ 第七类（差异化）**：AI Director 是产品差异化核心，但工具面只能改镜头。
  用户说「把这场戏改成夜晚」——真实 LLM planner 只有 update_shot 可选 → 找不到镜头目标 → 澄清。
  这是 Agent 能力面的真实缺口。
- 迭代 06 刚把场景编辑 UI + PATCH 语义 + P8-T017 连续性 hook 打通——`update_scene` 工具是这套
  语义的 Agent 侧复用，**零 Schema、走既有 P7 流（风险分级/ChangeSet/撤销）**。

### Why Now
- 场景编辑 UI（迭代 06）已确立场景字段语义；Agent 侧补上同一语义，形成「人类手动 / Agent 自动」
  双通道，正是 MVP 三原则「Make AI operate it」的延伸。
- 风险框架（risk.py R1）、ChangeSet（entity_type 分发）、工具注册（TOOL_SCHEMAS）全部可增量扩展。

### Why Not Others
- **契约防回归 CI**：DX 防线，独立小轮（已连续两轮被挤出，下轮重估）。
- **产出覆盖纳入就绪度**：对已交付 readiness 的增量。
- **M2 多参考图**：需 M1 真实使用反馈（Value Gate）+ 高成本。
- **场景批量环境应用**：低频。

## What Was Built

### 后端（纯增量，零 Schema 变更）
| 变更 | 位置 |
|---|---|
| `UpdateSceneArgs`（scene_id + patch 白名单：name/time_of_day/lighting/weather/mood/description）+ `TOOL_SCHEMAS` 注册 | [tools.py](../../backend/app/agents/tools.py) |
| `_update_scene` 处理器——**R1 自动应用**：ownership 复核 → SceneService.update_scene（触发 P8-T017 连续性重算 + stale）→ **scene ChangeSet 记录** + resume 幂等（相同 (run, scene, tool) 已应用则跳过）；风险升级兜底拒绝不猜测 | 同上 |
| `ToolOperation.tool` Literal 增 `update_scene` | [domain/agent.py](../../backend/app/domain/agent.py) |
| risk.py：`update_scene` → R1（可逆编辑，自动执行） | [risk.py](../../backend/app/agents/risk.py) |
| **ChangeSetService `record_scene_patch` + `_undo_scene_patch` + undo 分发**（entity_type="scene"，撤销走 SceneService 重触发 P8-T017） | [change_set_service.py](../../backend/app/services/change_set_service.py) |
| fake_planner 场景意图识别（目标词「场景/这场戏/这场」+ 环境值词 时段/光照/天气/氛围 → update_scene；无值 / 无选中场景 → 澄清）+ `parse_production_intent` 场景 target_type | [fake_planner.py](../../backend/app/agents/fake_planner.py) |
| fake.py `scene_id_from_prompt`（从 understand prompt 提取 scene_id） | [fake.py](../../backend/app/llm/fake.py) |
| graph `execute_node` 放宽 shot 强制：场景工具（update_scene 等）免 resolved_shot_id | [graph.py](../../backend/app/agents/director/graph.py) |
| 契约 §26 风险分级注释 | [api-event-contract-v0.1.md](../../docs/api-event-contract-v0.1.md) |

### 前端（标签层，零逻辑改动）
| 变更 | 位置 |
|---|---|
| `changeSetToolLabel` 增「修改场景」；`SHOT_FIELD_LABELS` 补场景字段（时段/光照/天气/氛围/描述）——ChangeSet 面板 diff 表可读 | [agentProposals.ts](../../frontend/src/lib/agentProposals.ts) |

### 数据流闭环
UI（导演面板输入「把这场戏改成夜晚」，选中场景）→ Agent understand（fake/真实 planner → update_scene op）→ load_context（场景归属）→ execute（ToolExecutor `_update_scene`）→ SceneService.update_scene（P8-T017 连续性重算 + stale）→ ChangeSetService.record_scene_patch（scene ChangeSet）→ run completed → 前端 ChangeSetPanel 展示「修改场景」diff → 撤销 → `_undo_scene_patch` 补偿（恢复 before + revision+1）。

## Validation

- 后端：pytest 全量 **638 passed, 1 skipped**（新增 5：应用+ChangeSet 记录 / 撤销恢复 / R1 无审批 / P8-T017 传播 / planner 意图边界——无值澄清、无选中场景澄清）。既有 agent 全套（test_agent/proposals/context/ownership/change_sets/refresh）51 项通过，零回归。
- 前端：vitest 全量 **298 passed**（本轮仅标签层，无新增测试；既有 changeSetPanel/agentProposals 测试通过）。
- tsc -b 0 错 · eslint 0 错 · ruff `app` All checks passed · vite build ✅
- **live HTTP smoke**（`scripts/smoke_agent_scene.py` 7 步）：白天基线 → 导演「把这场戏改成夜晚」→ update_scene 应用（revision 3）→ scene ChangeSet before={白天}/after={夜晚} → P8-T017 连续性基准传播（time_of_day=夜晚）→ 撤销恢复白天。

## Core Flow Regression

改动面 = AI Director 工具面 + ChangeSet。既有 update_shot/generate_image/continuity_fix 行为零改动（`ToolOperation` Literal 只新增值、不改变现有值）；`execute_node` 仅在**无 shot 工具**的 plan 下放宽 shot 强制（原有 shot 工具路径不变）；ChangeSet undo 分发新增 scene 分支、shot/timeline 分支不变；fake_planner 场景意图在镜头意图之前判断（消息含「场景/这场戏」才会进场景分支，既有镜头指令不受影响）。全量 pytest/vitest 通过即证。

## Remaining Risks

1. **fake 场景意图是关键词规则**（时段/光照/天气/氛围固定词）——生产走真实 LLM（Structured Planner 经 `TOOL_SCHEMAS` 会输出 update_scene）；fake 路径只覆盖固定词（已入候选「场景理解增强」）。
2. `update_scene` 恒 R1 自动应用，无 proposal 兜底分支（若未来风险策略升级需 `create_scene_proposal`——已入候选）。
3. 撤销「清空字段到 None」沿用 SceneUpdate None=unchanged 语义（与 shot 一致）——撤销目标是已设置字段（测试按此设计）。

## Backlog Changes

- **Done**：AI Director update_scene 工具（→ FEATURE_MAP 工具面；候选池标「已交付」）。
- **新进 Candidate**：AI Director 场景理解增强（P3，真实 LLM 验证）；update_scene proposal 兜底（P3）。
- 维持：契约防回归 CI（P1）、产出覆盖纳入就绪度（P2）、场景批量环境应用（P3）等。

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **契约防回归 CI（P1）**——连续两轮被挤出；7 轮迭代后 OpenAPI 170+ operations，前端调用点持续增长，自动防线价值达到峰值；独立小轮成本最低。
2. **产出覆盖纳入就绪度（P2）**——视频/配音缺口并入 readiness。
3. **场景批量环境应用（P3）**——多场景统一改环境。
4. **M2 多参考图 role 化（P2）**——若 M1+场景参考真实使用反馈成立则升级。
