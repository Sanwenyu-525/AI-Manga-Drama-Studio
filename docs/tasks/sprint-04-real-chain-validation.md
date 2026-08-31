# Sprint 04 — 真实链路验证（Real Chain Validation）

> 状态：**规划定稿（2026-08-31），未开始执行**。本文档是执行前的完整规划；执行期间按 §5 阻塞规则与 §7 步骤推进，完成后产出验证报告并重排 backlog。
>
> 决策背景：Phase 1 全部 P0 已关闭（2026-08-30），路线图默认下一步为 Phase 2。经拷问会决策（2026-08-31）：**先用真实数据校准路线图，再进 Phase 2**。理由：路线图基准是 2026-08-15 代码审计，从未被真实使用验证；且已核实 backlog 存在漂移（P2-E3-T01/T02 大半已由 P7 落地、P2-E4-T01 设置 UI 已存在）；真实 LLM（Agnes）已接通但「真实规划 → 真实图像 → 版本回填」从未端到端跑过任何一集。
>
> **修订（2026-08-31，拷问会第二问）**：图像链由「仅 Agnes」升级为**双引擎对跑（Agnes + 本地 ComfyUI）**。理由：a) `generation.provider` 是逐次生成级字段，双引擎无需切 env；b) 同一批 prompt 双引擎各生一遍，可把「prompt 质量问题」与「引擎/模型质量问题」分开归因——单跑 Agnes 做不到；c) K2（角色一致性）在本地 ComfyUI 生态（IPAdapter/LoRA/ControlNet）有后续演进路径，云端 Agnes 没有，验证需采集本地基线证据。

## 1. 本 Sprint 要回答的三个问题

1. **产品核心假设是否成立**：真实 LLM 规划 + 双引擎图像生成的产出，能否作为漫剧生产素材？
2. **引擎归因**：质量问题主要出在 prompt（Studio 可控）还是引擎/模型（需换 provider 或上参考图机制）？
3. **Phase 2 优先级长什么样**：按真实痛点（而非代码审计推断）重排后，下一个 Phase 2 Sprint 应该做什么？

## 2. 已核实的活性缺陷（验证前已知，非验证目标）

| # | 事实 | 代码位置 | 对本 Sprint 的影响 |
|---|---|---|---|
| K1 | 预览与确认是两次独立 LLM 调用；真实 LLM 下「确认写入的内容 ≠ 用户预览的内容」 | `frontend/src/features/script/EpisodePanel.tsx` L158/L182 | 预计第一个硬阻塞，见 §6 预修清单 |
| K2 | AgnesImageProvider 不接收参考图；跨镜头角色一致性仅靠 prompt 文字，无机制保障 | `backend/app/providers/image/agnes.py` | **重点观察项，预期最痛**；本地 ComfyUI 香草模板同样无参考图输入（`workflows/default_image_api.json` 仅 EmptyLatentImage） |
| K3 | 分析链对 >6000 字原文静默截断，UI 无提示 | `backend/app/services/script_service.py` L63/L164 | 选材 ≤3000 字避开；作为 P2-E1-T02 证据记录 |
| K4 | ComfyUI workflow catalog 仅注册一个香草 SD txt2img 模板；**已确认本地模型为 Z-Image-Turbo int8（智谱开源，DiT 架构）**，与香草模板结构性不兼容（非 `CheckpointLoaderSimple` 可加载，走独立加载器节点） | `backend/app/providers/comfyui/workflow_mapper.py` L48 + `workflows/default_image_api.json` | 需注册 Z-Image 模板（§6-3 预修项；代价已核实 = 一个 JSON 文件 + catalog 一行代码） |

## 3. 范围（已确认：核心段 · 双引擎）

**做**：导入小说 → analyze preview → 确认创建 Scenes → AI 生成分镜（ShotPlans）→ **双引擎图像生成（同一批 shots：Agnes 云端 vs 本地 ComfyUI + Z-Image-Turbo int8 各生一遍）** → 版本审阅（V1/V2 共存 + Set Active）。

**不做**：Timeline 排片 / edge-tts 配音 / ffmpeg 渲染（P9/P10 已有 live E2E 证据）；ComfyUI 参考图/LoRA 工作流改造（本 Sprint 只采集基线证据，机制落地归后续任务）；UI 改版；多 Agent；任何新架构。

## 4. 度量体系（已确认：结构化快评）

### 4.1 图像快评表（每张生成图像一条记录）

| 维度 | 判定方式 |
|---|---|
| 引擎 | agnes / comfyui（每条记录必填） |
| 景别符合度 | 1–5 分：prompt 中 shot_type 是否在图中成立 |
| 角色一致性 | 1–5 分：同一角色跨镜头外观是否稳定（仅多镜出场角色计分） |
| 整体可用性 | 1–5 分：作为该镜头成片素材是否可用 |
| 判定 | 可用 / 需重生成 / 废弃 |
| 失败模式 | 枚举标签：构图错 / 景别错 / 角色崩 / 肢体崩 / 风格漂 / 其他 |

### 4.2 汇总指标

**按引擎分组统计**（agnes / comfyui 各一列）：

- **首次可用率** = 首次生成即「可用」的张数 / 该引擎总首次生成张数
- **重生成改善率** = 重生成后转「可用」的张数 / 该引擎重生成总张数
- 平均生成耗时；失败率（API/网络错误与质量不合格分开统计）
- 规划质量定性记录（不打分，进报告文字）：Scene 划分合理性、Shot 景别多样性、对白/动作分配、image_prompt 英文质量

**跨引擎归因**（对跑的核心价值）：

- **逐 shot 对照表**：同一 prompt 两引擎的三维度评分与判定并排呈现
- **归因规则**：两引擎同崩 → prompt 问题（Studio 可控）；一崩一好 → 引擎/模型问题（换 provider 或上参考图机制）；两引擎同好 → 核心假设成立
- 角色一致性按引擎分开看：若本地基线显著更好，IPAdapter/LoRA 机制提级的证据即成立

### 4.3 结论阈值（建议值，出报告时可调整）

按「双引擎中较好者的首次可用率」判定：

| 最佳引擎首次可用率 | 解读 | 对 Phase 2 的影响 |
|---|---|---|
| ≥ 50% | 核心假设成立 | 按重排后的 Phase 2 执行，报告给出引擎选型建议 |
| 30–50% | 需看归因：prompt 双崩为主 → prompt 工程（P2-E4-T02 及 image_prompt 迭代链）提级；引擎分化为主 → 弱引擎出局，强引擎生态深耕（ComfyUI 则含参考图机制） | 对应方向提级 |
| < 30% | 图像质量是产品级风险 | provider/工作流全面重估（含 ComfyUI 自定义工作流与 reference 图机制） |

## 5. 阻塞处理规则（已确认：只修硬阻塞）

- **硬阻塞** = 不修就无法继续核心段流程的 bug。仅此类当场修。
- 其余一切问题（质量、UX、非致命错误）只记录编号 + 截图/日志，不修。
- 每次硬阻塞修复：最小修法 + 先失败后通过的回归测试 + 在报告中注明与正式任务的归属关系。
- 防失控约束：禁止「顺手优化」；禁止把非阻塞问题当阻塞处理。

## 6. 预修/预判清单

| 顺序 | 项 | 最小修法 | 与正式任务的关系 |
|---|---|---|---|
| 1 | K1 preview/confirm 不一致 | confirm 复用 preview 的 ScenePlan（前端携带 plan payload，或后端按 operation 缓存），不重新调 LLM | P2-E1-T01 的最小版；正式的持久化 snapshot 设计仍归 P2-E1-T01 本体 |
| 2 | Agnes 图像 key 未配置 | `backend/.env` 设 `STUDIO_AGNES_API_KEY` 后重启 | 环境准备，非代码 |
| 3 | ComfyUI + Z-Image 模板就绪（K4，已确认场景） | ① 前提：本机 ComfyUI 已能跑 Z-Image-Turbo 出图（未跑通则先在 ComfyUI 内跑通一次）；② 从 ComfyUI 导出实际可用的 Z-Image 工作流 **API 格式 JSON**；③ 模板改造：prompt/negative_prompt/seed/width/height 的值替换为 `$PROMPT`/`$NEGATIVE_PROMPT`/`$SEED`/`$WIDTH`/`$HEIGHT`，模型文件名（unet/clip/vae）与采样参数（turbo 为蒸馏模型：低步数低 CFG）写死为字面量；④ 注册：JSON 放入 `workflows/` + `WORKFLOW_CATALOG` 加一行——**唯一代码改动**（已核实：required 占位符仅 `$PROMPT/$SEED/$WIDTH/$HEIGHT`，模板不含 `$CHECKPOINT` 也能过 preflight）；⑤ `POST /providers/comfyui/test` preflight 通过 + 试生成一张 | ComfyUI 链路首次真实接入，属环境准备不计入正式任务。附带 P2-E4-T01 需求证据：`get_models()` 只枚举 `CheckpointLoaderSimple`（models/checkpoints/），Z-Image 类 DiT 模型放 diffusion_models/ **不会出现在设置页下拉**，模型名只能模板写死——「非 SD 架构模型不可枚举/不可配置」。Z-Image-Turbo 蒸馏版出图快，本地对跑时间成本低 |

## 7. 执行步骤

### Step 0 — 准备
- 确认 Agnes 图像计费方式与余额；设 `STUDIO_AGNES_API_KEY`；确认 `STUDIO_LLM_MODE=openai` 指向 Agnes（agnes-2.5-flash）。
- ComfyUI：本机启动 server，跑通 §6-3 就绪清单。
- 选材：一章 1500–3000 字（建议用自己小说的一章——内容熟悉，便于判定规划质量；同时自然避开 K3 截断）。
- 建快评表（§4.1 模板，表格文件随报告存放）。

### Step 1 — 规划链
- 导入 → preview → **记录 preview 全文** → confirm → diff「确认写入 vs 预览」（预计撞 K1 → 按 §6 最小修法处理）。
- generate-shots → 检查 ShotPlans：image_prompt 英文质量、景别分布、对白/动作分配，定性记录。

### Step 2 — 图像链（双引擎对跑）
- 预算内逐 shot 双引擎生成（同一 prompt，先 Agnes 后 ComfyUI，或交替）；生成一张、快评一张。
- 「需重生成」的 shot：修改 prompt 后**双引擎各重生成一次**（形成 V2），再次快评——重生成也要保持对跑，否则归因失效。
- 多镜出场角色：横向对比记录角色一致性，按引擎分开记（K2 证据）。
- 注意：ComfyUI 生成走本地 GPU，与 Agnes 云端耗时量级不同，分别记录耗时。

### Step 3 — 汇总
- 写验证报告：`docs/reports/real-chain-validation-report.md`（§4 全部数据 + 问题按 P0–P3 分级 + Phase 2 优先级重排提案）。
- 修正文档漂移：backlog 中 P2-E3-T01/T02 标注已落地部分；AGENTS.md §5「MVP 之后」列表更新（Timeline 已做、真实 LLM 已接等过时条目）。

## 8. 预算边界

- 图像生成：**每引擎**首 pass ≤ 40 张 + 重生成 ≤ 20 张（即双引擎合计 ≤ 120 张；Agnes 部分按实际计费可在执行前调整，ComfyUI 部分仅耗本地 GPU 时间，实际花费/耗时记入报告）。
- LLM：分析与分镜规划调用量为个位数，预计可忽略。

## 9. 产出物与验收标准（Sprint DoD）

- [ ] 一章真实小说 → ≥3 Scenes → ≥10 Shots → ≥20 张 Agnes + ≥20 张 ComfyUI 图像（同一批 shots 对跑），全部有快评记录
- [ ] 报告含：分引擎首次可用率 / 重生成改善率 / 失败模式分布 + 逐 shot 双引擎对照表 + 引擎归因结论 + 按真实痛点重排的 Phase 2 优先级提案
- [ ] 硬阻塞修复全部带先失败后通过的回归测试
- [ ] backlog.md / AGENTS.md §5 漂移修正完成
- [ ] 报告归档至 `docs/reports/`，问题 P0–P3 分级

## 10. 风险与应对

| 风险 | 应对 |
|---|---|
| Agnes 图像质量不达预期 | 这本身就是本 Sprint 最重要的验证结论，不是失败；对跑设计保证 ComfyUI 侧仍产出可比数据 |
| 本地 ComfyUI 不可用（server 起不来 / checkpoint 不匹配 / 模板不兼容） | §6-3 就绪清单先行排除；若最终不可用，降级为 Agnes 单引擎 + 报告如实记录 ComfyUI 接入障碍（这本身是 P2-E4-T01 的证据） |
| 角色一致性双引擎都崩 | 预期内（K2 + 双引擎均无参考图输入）；证据将直接决定 reference 图机制（ComfyUI 侧 IPAdapter/LoRA 路线）的优先级。利好：`$REFERENCE_IMAGE` 占位符已在 WorkflowSchema 声明、`upload_image()` 上传通道已在 ComfyUIClient 存在——后续落地成本低于从零 |
| 费用/耗时超预期 | §8 预算按引擎分别封顶，超限即停该引擎并如实记录 |
| 边测边修失控 | §5 规则硬约束：只修硬阻塞 |

## 11. 与既有任务的关系

| 任务 | 本 Sprint 承担的部分 |
|---|---|
| P2-E1-T01（Analysis Snapshot） | 仅最小修法（§6-1）；正式持久化设计仍为 P0 |
| P2-E1-T02（长文本分块） | 仅收集截断/长文本证据，不做实现 |
| P2-E4-T01（Provider 设置与诊断） | §6-3 ComfyUI 首次真实接入与 catalog 扩展是其最小预演；接入障碍（若有）即其需求证据 |
| P2-E4-T02（Profile 与预算边界） | §8 分引擎预算是其最小预演 |
| P1-E6-T02（文档事实源修正） | §7 Step 3 的漂移修正是该任务的部分落地 |
