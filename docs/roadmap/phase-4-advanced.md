# Phase 4 — Advanced Capabilities

## Goal

只开发能明显提升“漫剧连续生产质量与吞吐”的差异化能力。每个 Epic 在进入 Sprint 前必须有用户验证、成本边界与停做条件；“看起来很酷”不是立项理由。

## Value Gate

| Epic | 用户价值 | 与核心目标关系 | 成本/风险 | 进入条件 |
|---|---|---|---|---|
| Continuity | 减少角色/服装/场景跨镜漂移与返工 | 直接提升漫剧一致性 | 视觉模型误报、状态建模 L/XL | 至少 20 个真实 Scene 的问题样本与人工基线 |
| Production Workflow | 批量执行但仍可追踪、暂停和恢复 | 提升生产吞吐 | DAG/状态机 XL | Phase 2 Run/Approval/Generation 均稳定 |
| Video + Minimal Timeline | 从图片产出迈向可交付片段 | 产品扩展核心 | Provider 成本、媒体体积 XL | 用户验证图片链成熟后最需要的是成片而非更多图片工具 |
| AI Quality Review | 在生成后自动标记问题 | 减少人工筛选 | 评分可信度/费用 XL | 有标注数据和可接受 precision 指标 |

未通过 Value Gate 的 Epic 保持 Planned，不因为 Phase 4 到期自动开始。

---

## Epic 4.1 — Continuity

### P4-E1-T01 — 建立 Continuity State、Transition 与 Issue Domain

**背景**：漫剧最具重复成本的问题是角色身份、服装、道具、空间与动作在相邻镜头中漂移。

**当前问题**：Character 只有身份与 visual_prompt，Shot 关联不能表达某一时刻的服装、状态、空间位置或允许变化；没有 continuity issue/decision。

**目标**：用结构化状态表达“需要保持”和“明确发生变化”的内容，成为生成 Prompt 与 Review 的共同事实源。

**修改范围**：backend、database、frontend、Agent、docs、tests。

**实现建议**：先覆盖 Character appearance/costume、location/time、key props 三类；Transition 显式记录从 Shot A 到 B 的允许变化；Issue 独立于状态，支持 open/accepted/fixed。不要建立通用知识图谱。

**Acceptance Criteria**：

- [ ] 用户可查看/编辑 Scene/Shot 的 continuity state 与允许 transition。
- [ ] 状态变更有 revision、source 和历史，不从聊天记录推断事实。
- [ ] Prompt builder 只注入相关最小状态，不无限增长上下文。
- [ ] Issue 可定位两个版本/镜头并记录处理决策。
- [ ] 真实样本证明能表达前三类高频问题。

**Priority**：P1  
**Complexity**：L  
**Dependencies**：Phase 2 ChangeSet/Version、Phase 3 UX  
**Risk**：字段无限扩张；只为高频生产判断建模，其余先用 note。

### P4-E1-T02 — 实现视觉 Continuity 检查与人工校准

**背景**：结构化状态只有在能帮助发现生成结果偏差时才形成差异化价值。

**当前问题**：当前生成完成即作为候选版本，没有视觉一致性评分或 issue 建议；直接自动拒绝会产生高误伤。

**目标**：对选定版本执行可解释检查，生成候选 Issue，由用户确认；不自动改 Project State。

**修改范围**：backend、Agent/vision provider、frontend、database、tests。

**实现建议**：建立 Review Adapter；输入目标 continuity state、参考版本和候选图；输出结构化 evidence/confidence；低置信只提示，高置信也需人工确认，保存模型/provenance。

**Acceptance Criteria**：

- [ ] Review 结果列出检查项、证据、置信度和建议，不只给单一分数。
- [ ] 误报/漏报在标注样本集上达到预先定义阈值。
- [ ] Review 失败不影响生成版本可用性。
- [ ] 用户确认后才创建/关闭 Continuity Issue。
- [ ] 成本、耗时与关闭功能的路径清晰。

**Priority**：P1  
**Complexity**：XL  
**Dependencies**：P4-E1-T01、P4-E4-T01 的评测框架  
**Risk**：视觉模型可靠性不足；未达到阈值时停留“实验”而不进入默认流程。

---

## Epic 4.2 — Production Graph 与批量执行

### P4-E2-T01 — 建立版本化 Workflow Definition

**背景**：多个 Shot、Provider、Review 和审批步骤需要可重复流程，但业务 Service 不能依赖具体编排引擎。

**当前问题**：ComfyUI workflow 是单 JSON 模板；Studio 没有领域级 Workflow、step capability、输入输出或版本。Agent 与 Generation 各自编排，无法形成 Production Graph。

**目标**：定义 Studio Workflow Contract，描述业务步骤与依赖；具体执行 Adapter 可替换。

**修改范围**：backend、database、frontend、Workflow Engine、docs、tests。

**实现建议**：首版只支持 generate→review→activate 的有向无环步骤；definition/version 不可变，run 保存 snapshot；ComfyUI workflow 作为某一 step 的 Adapter 配置，不能泄漏 node_id 到业务/API。

**LLM 工作流生成（2026-08-31 拷问会决策并入）**：LLM 可作为版本化 Workflow Definition 的「生成器」入口——LLM 产出 ComfyUI 图 JSON 后，必须经过**生成后校验**（对照 `/object_info` 全节点 schema 校验节点存在性与输入类型）+ **节点白名单**（ComfyUI 存在可读写文件/执行脚本类节点，未校验的 LLM 生成图不得直接入队），通过后注册为版本化模板入库，之后正常走 catalog 执行。禁止每次生成任务临场让 LLM 现产工作流（与 P1-E2-T01 的 fail-closed catalog 决策保持一致：执行路径上只允许已验证模板）。

**Acceptance Criteria**：

- [ ] Workflow Definition 有 version、capability、typed input/output 与校验。
- [ ] Run 引用不可变 definition snapshot，编辑不改变历史。
- [ ] 业务 Service 不导入 LangGraph/ComfyUI 类型。
- [ ] 循环、缺输入和不支持 capability 在运行前失败。
- [ ] 至少一个图片生产 workflow 可重复执行。
- [ ] LLM 生成的工作流经校验+白名单后注册入库，未通过校验的图不进入执行路径。

**Priority**：P1  
**Complexity**：XL  
**Dependencies**：Phase 2 Provider Profile/Approval/Run 持久化  
**Risk**：通用 DAG 容易过度设计；只实现已验证的三个步骤与必要状态。

### P4-E2-T02 — 实现可暂停、恢复的批量 Production Run

**背景**：用户价值来自一次处理一个 Scene/选中 Shots，同时保留逐镜追踪和控制。

**当前问题**：当前每个 Shot 手动创建 Generation；没有批量并发预算、依赖、暂停/恢复或部分失败策略。

**目标**：按 selection/workflow 启动 Production Run，控制并发、费用和失败；单镜结果仍独立可追溯。

**修改范围**：frontend、backend、database、Workflow/Generation、events、tests。

**实现建议**：Run 生成独立 child jobs；复用 Generation lease/idempotency；并发由 Provider capability/profile 限制；失败策略支持 continue/pause，不实现任意脚本。

**Acceptance Criteria**：

- [ ] 提交前显示 Shot 数、步骤、Provider、预计资源和审批点。
- [ ] pause 后不启动新 child job，resume 不重复已完成任务。
- [ ] 单项失败可重试，Run 汇总准确反映 partial success。
- [ ] cancel 的传播规则明确且不删除已有版本。
- [ ] 服务重启后 Run 和 child job 可恢复。

**Priority**：P1  
**Complexity**：XL  
**Dependencies**：P4-E2-T01、P2-E2-T03、P1-E2 runtime  
**Risk**：批量请求放大成本和 SQLite 写负载；必须有预算、限流和故障测试。

### P4-E2-T03 — 提供只读优先的 Director Canvas

**背景**：Production Graph 超过少量步骤后，图形视图能帮助理解依赖与失败位置。

**当前问题**：导航中曾出现未开放 Canvas，但没有领域 Workflow；现在直接做可编辑节点画布会先造编辑器再找用途。

**目标**：先用只读 Canvas 展示 Run/步骤/审批/失败；只有用户证明需要后再开放有限编辑。

**修改范围**：frontend、Workflow API、tests、UX docs。

**实现建议**：自动布局、可缩放、节点详情与跳转；状态来自 Workflow Run Contract；编辑首版只允许启停预定义 optional step，不允许任意连线。

**Acceptance Criteria**：

- [ ] Canvas 能准确展示 definition 与当前 run 状态。
- [ ] 失败节点可跳转 Generation/Approval/Issue。
- [ ] 100+ 节点仍可操作并满足键盘替代路径。
- [ ] 未有需求证据前不开放任意节点脚本/连线。

**Priority**：P2  
**Complexity**：L  
**Dependencies**：P4-E2-T01、P4-E2-T02  
**Risk**：可视化成本抢占执行可靠性；只读价值未验证则停止。

---

## Epic 4.3 — 视频与最小 Timeline

### P4-E3-T01 — 扩展 Video Provider 与不可变视频版本

**背景**：漫剧最终需要动态片段，但必须复用已成熟的 Provider/Generation/Asset/Version 语义。

**当前问题**：Domain 请求虽允许 video 字符串，Worker 实际仅支持图片；没有时长、帧率、参考图、codec、音轨等 Studio Contract。

**目标**：以独立 VideoProvider Interface 生成可追溯视频版本，不让 ShotService 理解具体模型。

**修改范围**：backend、database、storage、Provider、frontend、docs、tests。

**实现建议**：先选一个真实 Provider；输入 active image/reference、motion prompt、duration/fps/profile；复用 Generation Runtime，但 capability 和 finalizer 明确区分媒体。视频采用流式文件与磁盘配额。

**Acceptance Criteria**：

- [ ] 不支持 video 的 Provider 在排队前拒绝。
- [ ] 一个 Shot 可保留多个不可变视频版本并切换 active。
- [ ] provenance 包含参考图片版本、profile、Provider 与参数摘要。
- [ ] cancel/retry/recovery/大文件路径复用生产级状态机。
- [ ] 真实 Adapter smoke 与 Mock 测试通过。

**Priority**：P1  
**Complexity**：XL  
**Dependencies**：Phase 5 前置的存储/配额能力、P4-E2 workflow  
**Risk**：成本、耗时和磁盘增长显著；必须先限制 duration/resolution/concurrency。

### P4-E3-T02 — 建立最小 Timeline 与确定性 Export

**背景**：用户需要把已选版本按 Shot 顺序预览并导出，而不是立即获得完整专业 NLE。

**当前问题**：Shot 有 duration，但没有时间轴编排、转场、音频或 export manifest；直接做复杂编辑器维护成本极高。

**目标**：提供顺序、时长、基础转场和预览，生成可重放的 export manifest 与成片。

**修改范围**：frontend、backend、database、media pipeline、docs、tests。

**实现建议**：Timeline 以 Scene/Shot 顺序派生，用户只调整 duration/trim/基础 transition；export job 版本化输入 manifest，使用 FFmpeg Adapter；专业多轨、关键帧和特效延后。

**Acceptance Criteria**：

- [ ] active image/video 版本按顺序形成可预览 timeline。
- [ ] 调整时长/基础转场有 revision 与 undo。
- [ ] 相同 manifest 重试产生等价输出并可追溯。
- [ ] 缺失媒体、编码失败、磁盘不足有可恢复错误。
- [ ] 导出不覆盖历史成片，支持最小 MP4 profile。

**Priority**：P1  
**Complexity**：XL  
**Dependencies**：P4-E3-T01、P4-E2-T02、Phase 5 storage/recovery  
**Risk**：范围扩张为 NLE；首版明确单主轨、基础转场、无复杂音频编辑。

**状态（2026-08-31 核对）**：P4-E3-T01 **已完成**（VideoProviderProtocol + 真实 AgnesVideoProvider + mock 占位 fail-fast、排队前 type/capability 校验、Shot 多不可变视频版本 + `active_video_asset_id` + video-versions API，cancel/retry/recovery 复用既有 Generation 状态机）。P4-E3-T02 **主体完成**（Timeline 三表 + 四轨 + clip 编辑 + sequence-from-shots + 非渲染预览 + type=render 渲染 mock/ffmpeg → FINAL_VIDEO 不可变版本 + 音频混流/字幕烧录）；**AC-2 缺口已关闭（2026-08-31）**：TimelineClip 新增 `transition`（cut/fade/dissolve，ffmpeg xfade / mock PIL 交叉淡化落地）+ `revision` 乐观并发（原子条件更新 409）+ Timeline 编辑纳入 ChangeSet/Undo 体系（source="timeline"）。

---

## Epic 4.4 — AI 质量评审

### P4-E4-T01 — 建立可评测的生成质量 Review Loop

**背景**：AI 评审只有在能减少人工筛选且不会替用户作错误决定时才有价值。

**当前问题**：Director Review 节点主要汇总执行结果，没有图像质量、构图、Prompt 遵循或可读性评测数据集；盲目自动重生成会增加成本。

**目标**：对选定质量维度输出结构化建议，并以人工标注样本持续评测；默认不自动重生成。

**修改范围**：backend、Agent/vision、database、frontend、tests、evaluation docs。

**实现建议**：先选择 2–3 个可验证维度（主体存在、画幅/黑边、文本/手部明显缺陷）；保存 model/version/evidence；建立 offline eval 和阈值。自动重试需独立批准和预算。

**Acceptance Criteria**：

- [ ] 有版本化标注集、指标与基线，不以主观 demo 代替评测。
- [ ] Review 输出维度、证据、置信度和建议。
- [ ] 低置信结果不会自动拒绝/激活版本。
- [ ] 成本和延迟可测，可按项目关闭。
- [ ] 未达到预设指标时功能保持实验标签。

**Priority**：P1  
**Complexity**：XL  
**Dependencies**：P2-E5-T01、P2-E4-T02  
**Risk**：模型偏差与评测数据不足；以“辅助筛选”定位，禁止伪装为客观质量分。
