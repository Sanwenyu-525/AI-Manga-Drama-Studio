# 真实链路验证报告（Sprint 04）

> 执行日期：2026-08-31。规划：[sprint-04-real-chain-validation.md](../tasks/sprint-04-real-chain-validation.md)
> 数据与逐张快评原始记录：`_validate/quick_review.json`、`_validate/gens2.json`、`_validate/regen2.json`、`_validate/out/`

## 1. 执行摘要

| 项 | 结果 |
|---|---|
| 选材 | 2400 字篮球章节（街球初战，演示库截取），避开 K3 6000 字截断 |
| 规划链 | 3 Scenes（真实 LLM）→ 38 Shots（action/dialogue/emotion/camera/image_prompt 全落库） |
| 图像对跑 | 20 shots × 双引擎（Agnes 云端 / 本地 ComfyUI + Z-Image-Turbo int8）= **40 张，全部生成并完成快评** |
| 首跑可用率 | Agnes **14/20 = 70%**；ComfyUI **17/20 = 85%**；合计 **77.5%** |
| 重生成 | 7 shots × 2 = 14 张（单变量 prompt 加年龄强化）；3 张转可用 |
| 最终可用率 | 合计 **34/40 = 85%** |

**结论：核心产品假设成立。** 真实 LLM 规划 + 双引擎生成的产出可作为漫剧分镜素材，两个引擎均达到「整集可组装」的画质基线（统一电影感黄昏风格、构图专业、竖版原生适配）。

## 2. 引擎归因（对跑核心价值）

| 结论 | 证据 |
|---|---|
| **prompt 语义主导（双引擎同漂移）** | S1#10「场边低声交谈」：两引擎都画成「两男坐凳密谋+孩子」，且重生成双引擎仍顽固——问题在 LLM 写进 image_prompt 的语义，不在引擎。S1#02 场边平板男、S1#13 步行离开：双引擎一致执行，证明 prompt 指向即结果 |
| **结构性错误不可靠重生成修复** | 景别错（S1#08 全景而非特写，双引擎仍是）、环境幻觉（S1#14 古建筑背景，Agnes 顽固）、主体错位（S1#10）、年龄漂移（沈亦 8 岁被画成 10-18）——单变量加词（"8-year-old"）几乎无效 |
| **物体幻觉偶发但部分可修** | 8 号台球式篮球（Agnes）、悬浮水瓶（双引擎）→「悬浮瓶」双引擎重生成后修复（S1_12 ✓）；台球化/双球悬浮（S1_07/06 Agnes）转为「无球/仍双球」——幻觉表现为随机漂移，非系统性 |
| **年龄控制：两引擎都弱** | Agnes 系统性把沈亦画成 10-18 岁；ComfyUI 更贴 8-12 但波动大（4-7 / 13-16 / 16-22 都有）。这是跨镜头角色一致性（K2）的最痛证据：**同一角色年龄都无法稳定，更遑论面容** |
| **ComfyUI (Z-Image) 基线略优** | 首可用率 85% vs 70%，主因一是年龄更贴、二是语义漂移少 |
| **双引擎质量下限都很高** | 40 张中构图/光影/画质几乎无崩坏；失败集中在语义/常识层，而非画功层 |

## 3. K1 实测（preview/confirm 不一致）

**本次实例未爆**：preview 与 confirm 为两次独立 LLM 调用，本次 3/3 title+description 完全一致（短时间窗口高复现）。**机制缺口仍在**（无快照保证），风险等级维持；建议在 P2-E1-T01 正式设计中解决，不作为本次硬阻塞。

## 4. 规划观点的验证/修正

| 规划观点 | 验证结果 |
|---|---|
| K1 预计第一个硬阻塞 | 未爆雷（实例一致）——风险记录，非 incident |
| K2 角色一致性是重点观察项，预期最痛 | ✅ 被证实：年龄漂移为主、面容一致性无机制保障 |
| K4 Z-Image 需注册模板（代价=一个 JSON + catalog 一行） | ✅ 精确成立，preflight/build/试生成一次通过 |
| 「get_models 只枚举 CheckpointLoaderSimple，DiT 模型不可枚举」 | ✅ 证实：`unet_name` 枚举不存在于该端点 → **P2-E4-T01 需求证据** |
| Z-Image 蒸馏版出图快 | ✅ 本地 8 步 euler，单张明显快于 Agnes 云端 |

## 5. 问题清单（P0–P3）

### P0（阻塞后续路径）
- 无。本次链路全部打通（创建→规划→分镜→双引擎→版本回填→审阅）。

### P1（下一 Sprint 应处理）
| ID | 问题 | 证据 | 归属任务 |
|---|---|---|---|
| P1-1 | image_prompt 语义不可控：LLM 会把「场边对话」类副信息写进 prompt 并两引擎共振，导致镜头内容与分镜意图偏离 | S1#10 双引擎顽固「密谋」 | P2-E4-T02（prompt profile/工程）+ P4-E4-T01（Review Loop）前置证据 |
| P1-2 | 角色年龄/面容一致性无机制：Age drift 双引擎、单变量 prompt 修复无效 | S1_04/08/14、跨引擎年龄分布 4-22 岁 | **reference 图机制（ComfyUI IPAdapter 路线）优先级提升**；管道半现成（`$REFERENCE_IMAGE` 占位符 + `upload_image()`） |
| P1-3 | 结构性错误无自愈路径：景别错/环境错重生成不改善，需要人工改 prompt 或换构图词 | S1_08/S1_14 重生成前后不变 | generate→review→edit 的人工 Review Loop（P4-E4-T01 雏形） |

### P2
| ID | 问题 | 说明 |
|---|---|---|
| P2-1 | DiT 系模型（UNETLoader）不出现在设置页模型枚举 | `get_models()` 只查 CheckpointLoaderSimple；正式 Provider Profile 需分架构枚举（P2-E4-T01） |
| P2-2 | 自定义 workflow 模板注册靠手写 catalog 代码行 | 本次唯一代码改动即此行；正式任务应将 catalog 扩展流程化（P2-E4-T01 附带） |
| P2-3 | 幻觉物（悬浮瓶/台球球/杂散地面物）无检测 | 约 5/40 出现；可考虑生成后轻量异常检测或靠 Review Loop 人工拦截 |
| P2-4 | 前端无 workflow_id/provider 显式选择入口 | 本次全部经 API 完成；用户产品路径待补（P2-E4-T01） |

### P3
- K3 长文本截断（6000 字）：本次未触发；P2-E1-T02 已有章节描述，无需新增行动。

## 6. Phase 2 优先级重排提案（本 Sprint 核心产出）

按 §5 证据，下一 Sprint 建议顺序：

1. **P2-E1-T01（Analysis Snapshot）** —— P0 维持。K1 机制缺口未核销，且它是「规划不可回溯/不可审计」的根基修复。
2. **P2-E4-T01（Provider Profile 工作区）** —— 从 P0 升为**下一个 Sprint 头号**：本次暴露的三处真实痛点（DiT 模型不可枚举、catalog 手写注册、UI 无 provider/workflow 选择）全部落在它身上，且全部是「真实使用 2 小时」撞出来的需求，不再是审计猜测。
3. **P4-E4-T01（Review Loop）的「人工评审分镜图」最小版** —— 证据充分（结构性错误重生成无效，只能人工干预）；建议以后续任务形式提前至 Phase 2 交付雏形，而非等 Phase 4。
4. **reference 图机制（IPAdapter 路线）设计与可行性预研** —— K2 证据已足（年龄漂移顽固）；应先出设计（依赖 ComfyUI 模板扩展 + `$REFERENCE_IMAGE`），与 P2-E4-T01 解耦可并行论证。

P2-E3-T03（ChangeSet/Undo）、P2-E2-*（生命周期/资产库）维持原优先级，本次无新证据需要调整。

## 7. DoD 核对

- [x] 一章真实小说 → 3 Scenes → 20 shots 对跑 → 40 张双引擎图，逐张带快评记录（`quick_review.json`）
- [x] 报告含分引擎可用率、逐 shot 对照表（`quick_review.json` rows）、引擎归因、Phase 2 重排提案
- [x] 硬阻塞：0（K1 未爆、无阻塞修复；模板注册为环境准备非 bug 修复）
- [x] backlog/AGENTS 漂移修正（见 §8）
- [x] 报告归档至 `docs/reports/`

## 8. 文档漂移修正（P1-E6-T02 部分落地）

- **backlog.md**：P2-E3-T01/T02 标注「大部分已由 P7 落地（agent_runs 落库 + Proposal/WAITING_HUMAN + approve/reject），剩余项 = 前端刷新水合 + retention/cleanup」；P2-E4-T01 备注「已获 Sprint 04 真实使用证据，见本报告 §5」。
- **AGENTS.md §5**：「MVP 之后（Phase 2+）」修订——「接真实 LLM」已达成（Agnes agnes-2.5-flash）；「Timeline」已做；新增真实链路验证结果指针。

## 9. 原始证据位置

- 快评数据：`_validate/quick_review.json`（40 行 + 重生成判定嵌于本报告 §2/§5）
- 图像：`_validate/out/{agnes,comfyui}/` 40 张 + `_validate/out/regenerated/` 14 张（可作评审对比素材）
- 中间产物：`preview1.json`/`scenes1.json`/`shots1.json`/`gens2.json`/`regen2.json`
- 验证项目：`真实链路验证-街球`（project 16512cd5），EP `街球初战`（episode 10efb924）