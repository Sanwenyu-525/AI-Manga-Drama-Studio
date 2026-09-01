# Autonomous Iteration Report 09 — 契约防回归 CI（前端调用点 ↔ OpenAPI 全量比对）

> 自主产品迭代第九轮（Post-MVP） · 2026-09-01
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`
> 上一轮：`docs/reports/autonomous-iteration-2026-09-01-stale-shot-loop.md`

---

## Current Product Status

Post-MVP 自主迭代第 9 轮。产品功能面已相当厚（一致性 / 就绪度 / Agent / 过期闭环），
本轮转向**工程质量防线**：全栈联调曾一次抓到 4 P0 + 6 P1 契约断点，全部靠人工联调发现；
OpenAPI 已膨胀到 175 operations、前端 175 个调用点，没有任何机器防线——改错一个路径
或 method 就是运行时 404/405。本轮把这个 P1（连续 3 轮被挤出的头号候选）落地成 CI 门。

## Opportunities Found（Top 6）

| Opportunity | Problem | Value | Cost | Priority |
|---|---|---|---|---|
| **契约防回归 CI（调用点↔OpenAPI 比对）** | 契约断点（改路由/换 method/删端点）无自动防线，靠人工联调发现 | 高（DX + 防 P0 回归） | 低 | **P1 本轮选** |
| DTO 字段级契约检查 | 路径/method 有防线，手写 types.ts 与后端 DTO 字段漂移仍无检测 | 中高 | 中 | P1（新进候选） |
| 视频/音频 stale 纳入过期闭环 | 过期徽标只覆盖图片资产 | 中 | 低 | P2（维持候选） |
| 产出覆盖纳入就绪度 | 就绪度不含视频/配音缺口 | 中 | 低 | P2（维持候选） |
| 未使用后端路由报告 | 175 ops 里哪些只给 Agent/脚本/调试用，无人知道 | 低（DX） | 低 | P3（新进候选） |
| M2 多参考图 role 化 | 单 MASTER 覆盖不了多角度 | 高 | 高 | P2（未选，需 M1 反馈） |

## Selected Opportunity

**契约防回归 CI：脚本断言前端全部调用点存在于后端 OpenAPI，纳入 CI。**

### Why This
- **来源 5（Developer Friction）+ Class 4**：全栈联调审计发现 4 P0 + 6 P1 契约断点，
  全部是「前端调了后端不存在/不匹配的路由」。每次改后端路由都可能悄悄打断前端，靠人工 smoke 兜底。
- 这属于**技术债防回归**：不补，后续每轮迭代（新增/改名路由）都在累积运行时炸点。

### Why Now
- OpenAPI operations 与前端调用点双双到 **175**，规模达到必须机器化的拐点。
- 该候选已连续 3 轮被产品功能挤出；本轮是**纯工具链小轮**，不干扰产品迭代节奏，且零新 CI 基建。

### Why Not Others
- **DTO 字段级检查**：价值高但需要 types.ts ↔ components 字段级对齐（更大工程），
  先立住路径/method 防线，字段级作为下一步候选（已在候选池标注依赖）。
- **视频/音频 stale**：功能面继续扩有边际收益，但工程防线是本轮更该补的短板。
- **M2 多参考图**：需 M1 真实使用反馈 + 高成本。

## What Was Built

### 后端（纯工具链，零 Schema、零运行时改动）
| 变更 | 位置 |
|---|---|
| `check_frontend_contract.py`——扫描 `frontend/src/**/*.{ts,tsx}` 全部 `api.<method>(path)` 调用点 → 与 FastAPI **`app.openapi()` 同进程实时生成**的 spec 逐段比对（零快照过期风险）；CLI 支持 `--app`（进程内 spec）/ `--openapi-url`（连运行中的后端） | [check_frontend_contract.py](../../backend/scripts/check_frontend_contract.py) |
| **segment-wise 通配匹配**统一处理：模板字符串 `${expr}`→`*`、`"a"+x+"b"` 拼接、三元段（`${cond?"approve":"reject"}`→`*`）、query 丢弃（含 query 值段）、动态前缀（EntityVersionBlock `${base}${entityId}/versions`→`* */versions`）；`api.upload`→POST、`{param}`→`*` | 同上 |
| **CI 门** `test_frontend_contract.py`（8 项）：全量比对 + spec 规模守卫（>150 ops）+ 6 个归一化单元用例，随既有 pytest 跑 | [test_frontend_contract.py](../../backend/tests/test_frontend_contract.py) |
| 契约 §141 新增规则 11：契约有机器防线 | [api-event-contract-v0.1.md](../../docs/api-event-contract-v0.1.md) |

### 匹配算法要点
```
api.get(`/scenes/${sceneId}/storyboard`)  → segments ["scenes","*","storyboard"]
"/projects/" + pid + "/characters"        → ["projects","*","characters"]
`/agent/proposals/${id}/${cond?"approve":"reject"}` → ["agent","proposals","*","*"]
"/agent/change-sets?entity_id=" + id      → ["agent","change-sets"]   （query 丢弃）
`${base}${entityId}/versions`             → ["*","*","versions"]       （动态前缀）
匹配：段数相同 && 每段相等或任一侧为 `*`（`*` 匹配字面段，覆盖三元/动态前缀）
```

## Validation

- 后端：pytest 全量 **649 passed, 1 skipped**（新增 8；反回归实证：删 `/providers` +
  `/generations/recent` 两条路由 → 精确报出 4 处断点，含 `file:line` 与归一化路径）。
- 前端：vitest **299 passed**（本轮零前端改动，无回归）。
- ruff `scripts/` + `tests/` All checks passed · tsc -b 0 错 · eslint 0 错。
- 基线：**175 前端调用点 ↔ 175 backend operations 全匹配**（无历史断点残留）。

## Core Flow Regression

零运行时改动：本轮仅新增 `scripts/check_frontend_contract.py` + `tests/test_frontend_contract.py`，
不触碰 app 代码、前端代码、DB。全量 pytest 通过即证无回归；前端无改动。

## Remaining Risks

1. **路径级防线 ≠ 字段级防线**：`types.ts` 手写 DTO 与后端字段仍可能漂移（改字段名/删字段
   运行时才炸）。下一步候选：字段级比对或 openapi-typescript 生成类型。
2. **匹配算法的宽容度**：`*` 匹配字面段——前端写成过于泛化的路径（如 `/shots/*/x` 命中
   `/shots/{id}/x`）不会报错，但这类泛化写法在本仓不出现；若未来出现，可收紧为
   「前端 `*` 只匹配后端 `{param}`」。
3. **反向方向（未使用路由）不门禁**：175 ops 含 Agent/脚本/调试专用路由，unused 只提示不拦截
   （已入候选，避免误报噪音）。

## Backlog Changes

- **Done**：契约防回归 CI（→ FEATURE_MAP DevEx 行；契约 §141 规则 11）。
- **新进 Candidate**：DTO 字段级契约检查（P1，依赖路径级已落地）；未使用后端路由报告（P3）；
  契约检查接入 pre-commit / npm script（P3）。
- 维持：视频/音频 stale（P2）、产出覆盖纳入就绪度（P2）、M2 多参考图（P2）等。

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **DTO 字段级契约检查（P1）**——路径/method 防线已立，字段漂移成为剩余最大契约风险；
   可从 `types.ts` 接口字段集 ↔ OpenAPI components 比对起步。
2. **视频/音频 stale 纳入过期闭环（P2）**——图片闭环立住后扩到视频/配音。
3. **产出覆盖纳入就绪度（P2）**——视频/配音缺口并入 readiness。
4. **M2 多参考图 role 化（P2）**——若 M1+场景参考真实使用反馈成立则升级。
