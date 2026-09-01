# Autonomous Iteration Report 05 — AI Director 刷新恢复（会话水合）

> 自主产品迭代第五轮（Post-MVP） · 2026-09-01
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`
> 上一轮：`docs/reports/autonomous-iteration-2026-09-01-production-readiness.md`

---

## Current Product Status

Post-MVP 自主迭代第 5 轮。一致性（角色/场景）与就绪度（生产缺口可见）已闭环；
本轮把产品差异化核心能力 AI Director 的「刷新即丢上下文」缺口补成闭环——
Agent 上下文可恢复，人机协同体验完整。

## Opportunities Found（Top 6）

| Opportunity | Problem | Value | Cost | Priority |
|---|---|---|---|---|
| **AI Director 刷新恢复** | agentStore 纯内存，刷新即丢对话流/计划/结果（Feature Map 🔶） | 高（差异化核心体验） | 中 | **P1 本轮选** |
| 产出覆盖纳入就绪度（视频/音频） | 就绪度不含视频/配音缺口 | 中 | 低 | P2（未选） |
| 契约防回归 CI | 契约断点无自动防线 | 中（DX） | 低 | P1（未选） |
| 镜头级地点覆盖（多地点场景） | 一场多地点无法单镜头指定 | 中 | 低 | P3（未选） |
| M2 多参考图 role 化 | 单 MASTER 覆盖不了多角度 | 高 | 高 | P2（未选，需 M1 反馈） |
| recent/change-sets 分页 | 长历史静默截断 | 中 | 低 | P1（未选，小） |

## Selected Opportunity

**AI Director 刷新恢复：会话在刷新/重开后可水合**。

### Why This
- **来源 1（🔶 部分完成）+ 来源 4（失败恢复成本）**：AI Director 是产品差异化核心（Agent 生产）。
  后端 `agent_runs` 已持久化 input/plan/result（甚至 `messages_json` 列早已存在但从未写入），
  但前端 agentStore 纯内存 → 刷新即丢全部上下文。这是「功能存在但未形成完整体验」的直接缺口。
- 对齐核心评价标准：Human-AI Collaboration / Recoverability。

### Why Now
- 多轮一致性/就绪度迭代后基线稳定；后端持久化管道已就绪，缺口收敛为「转录计算 + 列表端点 + 前端水合」三件套，增量小、零 Schema。
- 刷新恢复是所有长时间工作流的通用痛点——越早闭环越好。

### Why Not Others
- **产出覆盖纳入就绪度**：对刚交付的 readiness 的增量，价值低于「Agent 上下文可恢复」。
- **契约防回归 CI**：工具链，独立小轮。
- **镜头级地点覆盖**：低频场景。
- **M2 多参考图**：需 M1 真实使用反馈（Value Gate）+ 高成本。

## What Was Built

### 后端（纯增量，零 Schema 变更）
| 变更 | 位置 |
|---|---|
| `AgentRunRead.messages`——`_transcript(run)` 从 input（user 指令）+ result（assistant 摘要/澄清）+ status（waiting_human 审批提示 / failed 错误）**确定性计算**，零新增写入（`messages_json` 列保留给未来逐事件捕获） | [runner.py](../../backend/app/agents/director/runner.py) · [domain/agent.py](../../backend/app/domain/agent.py) |
| `list_runs(project_id, limit)`（最近会话倒序）+ gateway 薄委派 + `GET /agent/runs?project_id=&limit=`（契约 §25.1） | [runner.py](../../backend/app/agents/director/runner.py) · [gateway.py](../../backend/app/agents/gateway.py) · [agents.py](../../backend/app/api/agents.py) |

### 前端（复用优先，零新依赖）
| 变更 | 位置 |
|---|---|
| `agentStore.hydrate(run)`——水合 runId/status/messages/plan/result；后端状态归一（running→executing、waiting_approval/WAITING_HUMAN→waiting_human）；API `AgentPlanStep.arguments` → store `args` 映射 | [agentStore.ts](../../frontend/src/stores/agentStore.ts) |
| `AgentRunRead.messages` 类型 + `queryKeys.agentRuns` | [types.ts](../../frontend/src/api/types.ts) · [queryKeys.ts](../../frontend/src/api/queryKeys.ts) |
| **AIDirectorPanel 挂载自动水合**：空闲且无 run 时取 `limit=1` 上次会话 → hydrate；水合后 runId 置位 → 查询自动停用（不循环） | [AIDirectorPanel.tsx](../../frontend/src/features/director/AIDirectorPanel.tsx) |
| 契约 §25/§25.1 文档 | [api-event-contract-v0.1.md](../../docs/api-event-contract-v0.1.md) |

### 数据流闭环
UI Entry（导演面板挂载，store idle）→ Frontend State（agentStore.hydrate）→ API（GET /agent/runs?project_id=&limit=1）→ Backend（runner.list_runs → `_to_read` 计算 messages）→ Persistence（读 agent_runs 持久化的 input/plan/result，只读）→ Result（最近会话 + 消息转录）→ Frontend Feedback（对话流/计划/结果恢复）→ Reuse（agentStore 既有消息渲染 + queryKeys + api client 全复用）。

## Validation

- 后端：pytest 全量 **633 passed, 1 skipped**（新增 4：completed 转录 / 列表新在前 / WAITING_HUMAN 转录含审批提示 / `_transcript` failed+clarification 边界）。既有 flaky `test_generation_atomicity` 本轮通过。
- 前端：vitest 全量 **294 passed**（新增 5：agentStore hydrate 3 态 + 面板水合/无历史不水合 2）。
- tsc -b 0 错 · eslint 0 错 · ruff `app` All checks passed · vite build ✅
- **live HTTP smoke**（`scripts/smoke_agent_refresh.py` 5 步）：跑 director 会话（"改成近景"→ completed）→ run 明细 messages 转录 `[user, assistant("已修改镜头…")]` → `GET /agent/runs` 返回最近会话（新在前，带 messages）。

## Core Flow Regression

改动面 = AI Director（Agent 链路）。后端纯 additive：DTO 加 messages 字段（默认 []）、新列表端点；`_to_read` 仅多算一个字段，create/start/resume/cancel/approve/reject 路径零改动。前端 agentStore 新增 hydrate action（既有 action 不动）；AIDirectorPanel 仅在水合 idle 态新增一个查询 + effect，既有交互/渲染零改动。全量 pytest/vitest 通过即证。

## Remaining Risks

1. **运行中 run 的水合有限**：刷新时若 run 仍 running，水合只恢复 user 消息 + 状态（无中间工具进度），且面板不自动追踪该 run 的后续 WS 事件——需在下次进入时手动刷新/等待终态。常见终态/待审批场景已完整恢复。
2. 转录为「确定性计算」而非逐事件捕获：不包含 resume 时的「已继续执行…」等瞬时 UI 态（这些本就不该持久化）；`messages_json` 列保留，未来如需完整逐事件转录可迁移。
3. 水合仅取最新一条；「历史会话浏览/切换」未做（超出本轮「刷新恢复」范围）。

## Backlog Changes

- **Done**：AI Director 刷新恢复（→ FEATURE_MAP Agent 层 🔶 → ✅；候选池移除该行）。
- 维持：产出覆盖纳入就绪度（P2）、契约防回归 CI（P1）、镜头级地点覆盖（P3）、M2 多参考图（P2）等。

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **产出覆盖纳入就绪度（P2）**——把视频/配音产出缺口并入 readiness（复用 workspaceMetrics 思路），让「还差什么」覆盖完整生产链。
2. **契约防回归 CI（P1）**——多轮迭代后端点持续增多，自动防线价值上升；独立小轮。
3. **M2 多参考图 role 化（P2）**——若 M1+场景地点参考真实使用反馈成立则升级。
4. **镜头级地点覆盖（P3）**——多地点场景。
