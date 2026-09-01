# Autonomous Iteration Report 01 — M1 参考图前端闭环

> 自主产品迭代 Agent 首轮（Post-MVP） · 2026-08-31
> 机会台账：`PRODUCT_OPPORTUNITY_BACKLOG.md` · 能力地图：`FEATURE_MAP.md`

---

## Current Product Status

MVP 闭环 + P1/P7-P10 + 风险分级/ChangeSet + 一键成片 + Continuity 引擎 + 真实双引擎（Agnes/ComfyUI Z-Image-Turbo）全部落地；后端刚完成 P0×2+P1×8 定点优化（无重构需求，分层红线执行良好）。产品处于 **Post-MVP 迭代期**：核心链路完整，进入「补完体验断点 → 深化一致性 → 提效」阶段。测试基线：pytest 575+ / vitest 258+。

## Opportunities Found（本轮 Top 8）

| # | 机会 | Problem | Value | Cost | Priority |
|---|---|---|---|---|---|
| 1 | **M1 参考图前端闭环** | 后端参考图管道全链路就绪，前端零入口——一致性核心机制不可见不可控 | 5 | 2 | **P0（本轮）** |
| 2 | 镜头多选批量操作 | 全仓无 multiSelect；批量改/删/排只能逐个点 | 4 | 3 | P1 |
| 3 | recent/change-sets 分页 | 20/100 条静默截断，长项目历史丢失 | 3 | 1 | P1 |
| 4 | 生成 409 误报 | 幂等门的 409 被显示为「生成失败」 | 3 | 1 | P1（**并入本轮**） |
| 5 | M2 多参考图 role 化 | 单张 MASTER 覆盖不了多角度/服装 | 5 | 4 | P2（依赖 M1 验证） |
| 6 | M3 相似度评分 | 一致性回归无法量化 | 4 | 4 | P2（依赖样本基线） |
| 7 | locations 结构化 | location_id 自由文本，无一致性引用 | 3 | 3 | P2 |
| 8 | OperationStore 持久化 | 重启丢 analyze/导入进度句柄 | 2 | 2 | P3 |

## Selected Opportunity

**M1 前端闭环：参考图可见、可控、可追溯**（含并入的 409 反馈修复）。

### Why This
- Sprint 04 K2 实证角色一致性是第一痛点（双引擎同漂移 = 机制问题）；M1 管道正是为此而建。
- 「功能存在，但没有形成完整体验」——后端 2026-08-31 刚交付 `reference_asset_ids` → worker 注入 → 3 槽位模板，但用户完全看不见，投资价值为零。属最高优先级类别（核心流程断点 + AI 结果不可控）。
- P3 预研报告 §5.2 本就将 ShotInspector 参考图 UI 列为 M1 范围（断点 4 的前端侧）。

### Why Now
M1 后端是最新落地资产，接续成本最低；M2（多参考图数据模型）的正确形态依赖 M1 被真实使用后的反馈。

### Why Not Others
批量多选（P1）价值高但场景级批量已覆盖主干，非断点；分页（P1）是小优化不成主题；M2/M3 有明确前置依赖。409 修复与参考图同属生成入口体验，成本≈10 行，并入。

## What Was Built

### 后端（纯增量，零破坏）
| 变更 | 位置 |
|---|---|
| `GET /shots/{id}/reference-images` 预览端点（与 create 自动解析同源 + character_name；无 MASTER/无角色→[]；404 语义） | [api/generations.py](backend/app/api/generations.py) · [generation_service.py](backend/app/services/generation_service.py) `preview_references` |
| `GET /generations/{id}` 明细新增 `references` 溯源（auto/explicit + 角色名 + version_id；列表端点保持 `null` 防 N+1） | 同上 `generation_references` · [domain/generation.py](backend/app/domain/generation.py) `ShotReferenceRead`/`GenerationReferenceRead` |
| 契约文档同步（§35 Request reference_asset_ids 语义 / §38 预览端点 / §39 references 字段） | [api-event-contract-v0.1.md](docs/api-event-contract-v0.1.md) |

### 前端
| 变更 | 位置 |
|---|---|
| **ReferenceImagePicker**：自动/手动/无三模式——自动=MASTER 解析缩略图预览（空态区分「未关联角色」vs「无 MASTER 版本」并给引导）+ >3 张上限提示；手动=项目图片资产多选 ≤3 张（编号=注入顺序，满额禁用+可取消）；无=显式空数组。**Provider 能力感知**：当前引擎（显式或默认）无 `reference_image` 能力且将有参考图时警告「生成时将忽略，可切换 ComfyUI」 | [ReferenceImagePicker.tsx](frontend/src/features/storyboard/ReferenceImagePicker.tsx)（新） |
| ShotInspector 接线：生成请求按模式携带 `reference_asset_ids`；保存镜头后失效参考图预览查询 | [ShotInspector.tsx](frontend/src/features/storyboard/ShotInspector.tsx) |
| **生成溯源**：版本区展示当前生效版本生成时实际注入的参考图（缩略图条 + auto/手动标注，staleTime 5min——溯源行不可变） | 同上 `GenerationReferenceStrip` |
| **409 友好文案**：`generationSubmitErrorText`——CONFLICT 显示「任务进行中，请查看进度」而非「生成失败」 | 同上（后端优化报告建议 #1 收口） |
| CSS（复用 Design Token：--accent/--hairline/--orange 警示）+ 类型 + queryKeys | [styles.css](frontend/src/styles.css) · [types.ts](frontend/src/api/types.ts) · [queryKeys.ts](frontend/src/api/queryKeys.ts) |

### 数据流闭环
UI Entry（Inspector 参考图区）→ User Operation（选模式/挑资产）→ Frontend State（ReferenceChoice）→ API（reference_asset_ids / preview 端点）→ Backend（Service 校验+解析）→ Persistence（generation_inputs 溯源行）→ Result（worker 注入 3 槽位）→ Frontend Feedback（版本区溯源条 + 队列进度）→ Reuse（缩略图/资产/版本条既有设施全复用）。

## Validation

- 后端：pytest 全量 **575 passed, 1 skipped**（新增 6 项：预览同源/双空态/404/明细溯源 auto+explicit/列表防 N+1）
- 前端：vitest 全量 **258 passed**（新增 12 项：三模式交互/点击顺序上报/满额禁用与恢复/能力警告双引擎/显式 provider/409 文案）；tsc -b 0 错；eslint 0 错
- ruff `app`：All checks passed；cargo check：Finished（三重验证零错误）
- 真实冒烟：uvicorn 启动 → OpenAPI 端点已注册（128 paths）→ 未知 shot/generation 正确 404 → /health 200

## Core Flow Regression

改动面 = 图片生成入口（核心链路一环）：生成创建路径仅**新增可选字段**（缺省 `null` = 自动解析，行为与 M1 后端交付时完全一致，全量 pytest 中既有 19 项 reference pipeline 测试 + 生成链测试全部通过即可证）；ShotInspector 既有交互（保存/版本/引擎选择）未动签名。无 DB Schema、无事件、无破坏性 API 变更。

## Remaining Risks

1. **手动模式资产池偏大**：项目全部图片资产进入选择网格（含历史生成图）——数量大时需筛选/分组（候选优化，非阻断）。
2. **默认引擎多为 Agnes/Mock（无参考图能力）**：真实一致性收益需用户切 ComfyUI + `zimage_turbo_ref` 模板；UI 已警告引导，但默认路径无一致性增益。
3. 预览端点返回全部解析结果（>3 张仅提示）——极端多角色镜头的注入取舍留给用户手动模式，未自动截断（诚实优先）。
4. M1 真实 ComfyUI 带参考图的生成效果（Turbo 蒸馏版遵循度）仍待实拍验证（P3 报告§7 风险，属 M1 冒烟既有事项，非本轮引入）。

## Backlog Changes

- **Done**：M1 前端闭环（→ FEATURE_MAP「生成参考图」行 ✅）
- **Candidate 新增**：生成队列策略可配置（SettingsPage 遗留）、locations 结构化、P8-E2 规则补全（源自代码扫描）
- **Rejected 维持**：IPAdapter 系（不兼容 DiT）、Agent 工具暴露 reference_asset_ids（Service 自动已覆盖）
- 常设文档建立：`PRODUCT_OPPORTUNITY_BACKLOG.md`（唯一机会台账）+ `FEATURE_MAP.md`（能力地图）

## Next Likely Opportunities（下一轮候选，仍需重新评估）

1. **镜头多选批量操作**（P1）——参考图闭环后，批量生图 + 批量改参的效率缺口更显性；与现有场景级批量模式可复用。
2. **M2 多参考图 role 化**（P2）——若 M1 实际使用反馈为「单 MASTER 不够用」则升级。
3. **recent/change-sets 分页**（P1，小）——可与任一轮搭车。

下一轮将重新执行 Discover → Prioritize（本轮交付可能已改变优先级，不机械沿用本排名）。
