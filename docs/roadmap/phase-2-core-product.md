# Phase 2 — Core Product Completion

## Goal

补齐 MVP 主链路中“看似存在但用户无法可靠控制”的核心能力：用户提交的是自己审阅过的计划；项目/资产/任务生命周期完整；AI Director 的高风险修改可审批、恢复和撤销；真实 Provider 可在产品内配置与诊断。

## Entry / Exit

**Entry**：Phase 1 P0 数据、异步状态机、错误契约和安全边界关闭。  
**Exit**：核心对象的创建/编辑/归档/恢复可完成；规划/Agent Run 可恢复；R2/R3 操作有审批和 ChangeSet；资产/版本/Provider 有可用管理面。

---

## Epic 2.1 — 可信规划与导入

### P2-E1-T01 — 提交用户已审阅的 Analysis Snapshot

**背景**：Preview 的产品意义是让用户确认将写入 Project State 的确切内容。

**当前问题**：`EpisodePanel.tsx` 预览后，确认操作重新调用 analyze；真实 LLM 可能产生不同 ScenePlan。Operation 状态又只在内存中，刷新后无法解释此前提交。

**目标**：Preview 生成不可变、可校验的 Analysis Snapshot；Confirm 只提交该 snapshot，不重新生成。

**修改范围**：frontend、backend、database、API、docs、tests。

**实现建议**：持久化 snapshot ID、source hash、model/provenance、structured plan 与过期状态；Confirm 接受 snapshot ID + expected episode revision；源文本变化后明确失效并要求重新预览。

**Acceptance Criteria**：

- [ ] Confirm 写入内容与用户看到的 snapshot 字段逐项一致。
- [ ] 源文本/episode revision 改变后旧 snapshot 返回 409/expired。
- [ ] 重复 Confirm 幂等，不重复创建 Scene/Shot。
- [ ] 刷新后能读取 preview/operation 状态与失败原因。
- [ ] 模型、prompt/schema version 与 source hash 可追溯。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E1-T01、P1-E4-T01  
**Risk**：保存原文/Prompt 涉及隐私与空间；只存必要 provenance 并定义保留策略。

### P2-E1-T02 — 支持长文本分块、进度与明确角色提取

**背景**：普通用户会导入超过 1000–3000 字的章节，系统不能静默截断或承诺不存在的角色生成。

**当前问题**：`script_service.py` 构造 Prompt 时截取 `source_text[:6000]`；UI 未告知截断。EpisodePanel 文案暗示自动创建角色，但当前流程没有稳定实现；“替换原文”控件无行为。

**目标**：长文本按可解释策略处理并显示进度；角色提取是显式预览/确认步骤，或移除承诺。

**修改范围**：frontend、backend、database、LLM、docs、tests。

**实现建议**：先设支持上限与 token estimation；分块后汇总为 Episode Outline/ScenePlan，保留 chunk provenance；角色候选与现有 Character 做人工确认合并，不自动覆盖身份资产。

**Acceptance Criteria**：

- [ ] 超过阈值时不静默截断，UI 显示范围、预计成本与进度。
- [ ] 分块失败可重试单块且最终 snapshot 一致。
- [ ] 角色候选在创建/合并前可审阅，重名冲突有明确选择。
- [ ] “替换原文”有真实、可恢复行为或被移除。
- [ ] 典型长章节与边界长度有测试。

**Priority**：P1  
**Complexity**：L  
**Dependencies**：P2-E1-T01、P2-E4-T02  
**Risk**：分块汇总可能损失跨段连续性；先限制规模并以样本文本评测，不建立通用 RAG。

---

## Epic 2.2 — 生命周期、资产与查询

### P2-E2-T01 — 补齐核心实体归档、恢复与删除语义

**背景**：软删除只有在用户能看到、恢复并理解级联影响时才是完整产品能力。

**当前问题**：Project/Episode/Scene/Shot/Character 的 delete/restore 覆盖不一致；父实体删除后子实体的直接访问规则不统一；前端缺归档入口与冲突说明。

**目标**：为核心实体定义统一但符合领域的 active→archived/deleted→restored 生命周期。

**修改范围**：frontend、backend、database、API、docs、tests。

**实现建议**：先写生命周期矩阵；默认归档可恢复，物理删除只用于明确清理流程；父级可见性在 Repository scope 中统一；restore 检查编号和名称冲突。

**Acceptance Criteria**：

- [ ] 每类实体的可归档/恢复/永久删除权限与级联规则已记录。
- [ ] 删除父实体后子实体不能通过直接 ID 绕过可见性规则。
- [ ] 恢复冲突返回可操作错误，不覆盖现有实体。
- [ ] UI 提供归档视图、恢复反馈与危险操作确认。
- [ ] CRUD/restore API 与自动测试完整。

**Priority**：P1  
**Complexity**：L  
**Dependencies**：P1-E1-T02、P1-E5-T02  
**Risk**：历史软删除数据可能不符合新规则；迁移前需审计并提供修复报告。

### P2-E2-T02 — 建立项目作用域 Asset Library

**背景**：生成资产已经存在于文件系统和数据库，但用户没有统一入口检索、导入、复用和清理。

**当前问题**：只有按 ID 读取内容/缩略图，没有 project asset list/import/archive、筛选或分页；文件 metadata、ownership 与 media type 校验有限。

**目标**：用户能在项目内管理图片/后续视频资产，并追溯其 Shot、Generation、Version 来源。

**修改范围**：frontend、backend、database、storage、API、docs、tests。

**实现建议**：cursor pagination；按 media_type/source/scene/shot/created_at 筛选；导入先校验 MIME/size/checksum，再注册项目相对路径；删除默认归档并保护被 active version 引用的资产。

**Acceptance Criteria**：

- [ ] Asset list 仅返回当前 project，支持 cursor、类型与来源筛选。
- [ ] 导入拒绝超限、伪装 MIME、越界路径和跨项目 Shot。
- [ ] 资产详情能追溯 Generation、Version、Shot 与文件完整性。
- [ ] 被引用资产不能无提示物理删除。
- [ ] Empty/Loading/Error/分页状态有前端测试。

**Priority**：P1  
**Complexity**：L  
**Dependencies**：P1-E2-T03、P1-E5-T02  
**Risk**：视频资产体积大；本任务只定义存储 Interface，不提前引入对象存储。

### P2-E2-T03 — 项目化任务查询、筛选与受控批量操作

**背景**：队列、版本与活动记录随项目增长后必须可定位，且不能跨项目混在一起。

**当前问题**：Generation recent 是全局 limit 查询且当前路由冲突；多个列表无分页。缺按 status/type/shot/provider 的筛选，批量重试/取消没有部分失败语义。

**目标**：高频任务列表按 project 分页筛选；仅为明确用例增加批量取消/重试。

**修改范围**：frontend、backend、database、API、docs、tests。

**实现建议**：项目作用域 cursor API；索引由查询计划/基准驱动；批量请求返回每项结果，不做全局“万能 batch”。

**Acceptance Criteria**：

- [ ] Generation/Version/Activity 列表不跨 project 泄漏。
- [ ] cursor 分页在新增数据时无明显重复/漏项。
- [ ] status/type/provider/scene/shot 筛选有契约测试。
- [ ] 批量 cancel/retry 显示逐项成功/失败并保持幂等。
- [ ] 10,000 Shot/5,000 Asset 基准下查询满足已定义预算。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P1-E2-T02、P1-E4-T01  
**Risk**：过多筛选导致索引膨胀；先采集查询模式再加索引。

---

## Epic 2.3 — 可恢复、可审批、可撤销的 Director

### P2-E3-T01 — 持久化 Agent Run、Session、Message 与 Checkpoint

**背景**：Agent 是生产流程的一部分，重启/刷新后必须能恢复历史和当前状态。

**当前问题**：Director Run 与 Operation 均为进程内字典，resume 是占位；前端只保留单次 live store，刷新即丢失。

**目标**：Run/Session/Message/Plan/Tool Step 有持久状态；LangGraph checkpoint 只服务编排，不替代 Project State。

**修改范围**：frontend、backend、database、Agent、API、docs、tests。

**实现建议**：以 Studio Domain 表持久化 run summary/step/output；checkpoint 通过 Adapter 关联 run_id；设置 retention/cleanup；启动时恢复 running/cancelling 状态并与事实源对账。

**Acceptance Criteria**：

- [ ] 服务重启后能读取 Run、Plan、步骤、终态和安全摘要。
- [ ] running Run 按策略恢复、失败或等待用户，不永久悬挂。
- [ ] 前端刷新后水合当前 Run 与最近历史。
- [ ] Checkpoint 数据不能被当作 Scene/Shot 事实源。
- [ ] Retention/cleanup 有配置和测试。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：Phase 1 Agent/Event/DB tasks  
**Risk**：直接持久化 LangChain Message 会泄漏实现与敏感内容；必须先映射 Studio Contract。

### P2-E3-T02 — 实现风险分级、Approval 与 Resume

**背景**：高风险批量修改、替换 active version 或外部生成不能只靠自然语言确认。

**当前问题**：现有 Planner→Executor 直接执行；`agent.approval.required` 契约存在但 Runtime 没有真实 interrupt/resume，R0–R3 设计未落地。

**目标**：R0/R1 可按策略自动执行，R2/R3 在持久 ApprovalRequest 上暂停；批准、拒绝、修改计划后确定性恢复。

**修改范围**：frontend、backend、database、Agent、events、API、docs、tests。

**实现建议**：风险评估输出结构化 reason/scope/cost；审批绑定 plan_hash 与 revision；resume 必须验证未过期、未被二次处理；Executor 不重新让 LLM 决定已批准步骤。

**Acceptance Criteria**：

- [ ] R2/R3 未批准前无写操作或 Generation 创建。
- [ ] Approval 显示影响实体、字段、费用/任务数与不可逆风险。
- [ ] approve/reject/expire 具有幂等终态和权限/会话校验。
- [ ] 目标 revision 改变时旧审批失效并重新规划。
- [ ] interrupt→restart→resume 场景自动测试通过。

**Priority**：P0  
**Complexity**：XL  
**Dependencies**：P2-E3-T01  
**Risk**：审批粒度过细会打断创作；先覆盖 R2/R3，不把每次近景修改都升级为确认。

### P2-E3-T03 — 实现 ChangeSet、Shot Snapshot 与 Undo

**背景**：AI 批量修改只有在可审阅、可撤销时才能成为生产工具。

**当前问题**：当前只保留实体最新字段和媒体版本；没有修改前 snapshot、ChangeSet 或撤销。Agent cancel 也无法撤回已经完成的步骤。

**目标**：每次 Agent mutation 产生可读 ChangeSet；用户可按 revision 安全撤销尚未被后续修改覆盖的变更。

**修改范围**：frontend、backend、database、Agent、events、API、docs、tests。

**实现建议**：保存最小 before/after patch 与 expected revisions，不复制整个数据库；Undo 作为新的补偿变更而非改历史；媒体不可变版本只切换 active，不删除。

**Acceptance Criteria**：

- [ ] ChangeSet 列出实体、字段、before/after、run/tool/source。
- [ ] Undo 生成新 revision/event，历史不被覆盖。
- [ ] 后续 revision 已改变时 Undo 返回冲突与可选恢复路径。
- [ ] 批量 ChangeSet 支持全撤销或逐项结果，不形成半静默状态。
- [ ] UI 能在执行前/后审阅并跳转受影响实体。

**Priority**：P0  
**Complexity**：XL  
**Dependencies**：P2-E3-T02、P1-E1-T02  
**Risk**：任意字段的通用 Undo 容易过度设计；首版只覆盖 Director 的 Shot patch 与 active-version 切换。

---

## Epic 2.4 — Provider 与生成配置产品化

### P2-E4-T01 — 建立 Provider Settings 与诊断工作区

**背景**：真实用户需要在产品内知道“连接到哪里、用什么 workflow、为什么失败”，而不是编辑环境变量后重启猜测。

**当前问题**：只有 providers list/test API，无安全配置 UI；NewProject 文案承诺可切换 Mock 但没有入口；checkpoint、workflow、输出节点和能力无法预检。

**目标**：用户可配置、测试并选择 LLM/Image Provider profile，秘密安全保存，项目引用稳定 profile ID。

**修改范围**：frontend、backend、database、desktop、config、API、docs、tests。

**实现建议**：普通配置存数据库/项目设置，secret 通过 OS secure storage Adapter；test connection 返回分阶段诊断；项目保存 profile reference，不复制 key。

**Acceptance Criteria**：

- [ ] 设置页可创建/测试/启用/禁用 Provider profile。
- [ ] API key 不经普通 GET 返回、不写日志/数据库明文。
- [ ] ComfyUI workflow/checkpoint/output capability 在保存前校验。
- [ ] 项目切换 profile 不改变历史 Generation provenance。
- [ ] 失败诊断区分连接、认证、模型/workflow 和输出错误。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E2-T01、P1-E5-T02；OS secure store 可与 P5 打包任务协作  
**Risk**：跨平台 secret store 差异；先支持当前 Windows 交付目标，Interface 保持可替换。

### P2-E4-T02 — 建立模型/生成 Profile、能力与预算边界

**背景**：不同模型、分辨率和 workflow 需要显式能力，不能让业务 Service 猜 Provider 细节。

**当前问题**：LLM model/temperature、图片尺寸与默认 workflow 分散在 config/请求/模板；缺 token、并发、超时、费用或任务数预估。

**目标**：用户选择 Studio Profile；系统在提交前校验 capability 并显示可理解的资源边界。

**修改范围**：frontend、backend、database、Provider/LLM、docs、tests。

**实现建议**：Profile 保存 Studio Domain 参数，再由 Adapter 映射；能力返回 image/video/reference/size limits；本地模型无法提供费用时显示未知而不是伪造。

**Acceptance Criteria**：

- [ ] Profile 版本化，历史任务保留当时配置摘要。
- [ ] 不支持的 media type/reference/size 在排队前失败。
- [ ] LLM 有 token/input limit、timeout、retry 与结构化输出失败策略。
- [ ] 批量操作提交前显示任务数和可得的成本/时间估计。
- [ ] Profile 变化不要求修改 ShotService/剧情逻辑。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P2-E4-T01  
**Risk**：Provider 参数过多会泄漏实现；只暴露对创作有意义的 Studio Contract。

---

## Epic 2.5 — 版本评审闭环

### P2-E5-T01 — 完成版本比较、批注与决策状态

**背景**：V1/V2 共存解决了历史保留，但用户仍缺选择理由与比较工具。

**当前问题**：VersionReviewPage 主要是缩略图和 Set Active；无并排/放大比较、备注、采用/拒绝状态、Prompt/provenance 摘要或错误反馈。

**目标**：用户能比较版本、记录决策并安全激活，AI Director 也能引用明确版本。

**修改范围**：frontend、backend、database、API、docs、tests。

**实现建议**：媒体文件继续不可变；在 MediaVersion 上增加可变 review metadata 或独立 Review 记录；active 切换使用 revision/transaction；支持 before/after 与关键参数对照。

**Acceptance Criteria**：

- [ ] 两个版本可并排/放大比较并显示来源、尺寸、时间、Provider/Profile。
- [ ] 用户可记录 note 与 accepted/rejected/undecided，不修改媒体文件。
- [ ] Set Active 有冲突处理、成功/失败反馈和正确 project event。
- [ ] Agent/Generation 创建的版本都可追溯到 run/generation。
- [ ] 键盘切换与基本可访问性测试通过。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P1-E2-T03、P1-E1-T02  
**Risk**：评审状态与 active 状态不是同一概念；契约中必须分开。
