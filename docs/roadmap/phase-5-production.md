# Phase 5 — Production Readiness

## Goal

让一个没有源码、Python、uv 或开发知识的真实用户能够安全安装、升级、运行、备份、诊断和回滚。Phase 1 已启动最小门禁；本阶段完成发布级证据。

## Release Gate

以下任一 P0 未完成，不能标记 Production：安装包 smoke、旧数据迁移、备份恢复、核心 E2E、真实 Adapter certification、本地安全边界、签名/回滚、错误诊断。

---

## Epic 5.1 — 测试体系与发布证据

### P5-E1-T01 — 完成分层测试金字塔与覆盖门槛

**背景**：测试数量不是目标；需要覆盖 Domain 不变量、Adapter Contract 和用户关键旅程。

**当前问题**：后端 31 项以 happy path 为主；前端无测试；测试使用 `create_all` 绕过迁移；没有覆盖率与 mutation/fault 风险清单。

**目标**：形成快速单元、Service/DB 集成、Contract、前端组件和少量 E2E 的稳定结构。

**修改范围**：frontend、backend、database、tests、infra、docs。

**实现建议**：按风险设置门槛而非全仓统一高百分比；核心状态机/ownership/approval/finalizer 要求高分支覆盖；UI 重点测状态与行为，不测实现细节。

**Acceptance Criteria**：

- [ ] Domain/Service、API/DB、Contract、frontend component、E2E 分层命令清晰。
- [ ] 测试库覆盖空库迁移和至少一个旧版本升级。
- [ ] 核心状态机与安全边界达到约定分支覆盖，覆盖率下降阻断 CI。
- [ ] flaky test 有隔离/修复时限，不允许永久重跑掩盖。
- [ ] 测试总时长分 fast PR 与 nightly/manual profile。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E6-T01、Phase 2 稳定契约  
**Risk**：追求覆盖率数字产生低价值测试；评审以风险场景为准。

### P5-E1-T02 — 建立核心 E2E、故障注入与真实 Adapter Certification

**背景**：生产故障通常发生在跨 Module 边界，而非单个函数。

**当前问题**：没有浏览器/Tauri E2E；Worker、断线、重启、磁盘失败、真实 ComfyUI/OpenAI-compatible 未形成可重复证据。

**目标**：发布候选必须通过核心用户链、恢复链和至少一个真实 LLM/ComfyUI profile 的认证测试。

**修改范围**：frontend、backend、desktop、Provider、tests、infra、docs。

**实现建议**：E2E 覆盖 novel→snapshot→scenes/shots→generation→version→Director→approval；故障注入进程退出/WS 断线/磁盘满/Provider timeout；真实外部服务在受控 nightly/manual 环境运行并脱敏。

**Acceptance Criteria**：

- [ ] 核心 E2E 在安装包环境而非仅 Vite/Uvicorn 开发环境通过。
- [ ] Worker/Agent 重启、cancel、retry、reconcile 场景通过。
- [ ] 一个支持矩阵中的 LLM 与 ComfyUI workflow 通过 certification。
- [ ] 外部服务不可用时测试明确 skip/fail，不能自动换 Mock 后报告成功。
- [ ] 测试产物包含日志、截图/trace 与诊断 ID，不包含 secrets。

**Priority**：P0  
**Complexity**：XL  
**Dependencies**：P5-E2-T01、P2-E4、Phase 3 核心 UX  
**Risk**：真实 Adapter 不稳定；把 Contract fixture 与少量 certification 分层，避免普通 PR 依赖 GPU。

---

## Epic 5.2 — 桌面发行、迁移与恢复

### P5-E2-T01 — 打包受控 Backend Runtime、Workflow 与安装器

**背景**：当前 Tauri 壳依赖源码路径和系统 `uv`，不能分发给真实用户。

**当前问题**：`backend.rs` 从编译期仓库定位 backend 并执行 `uv run uvicorn`；未打包 Python/依赖/workflow；只探测端口，不检查 health；`ensure_backend` 失败处理薄弱；Windows 专用代码与 bundle targets=all 不一致。

**目标**：安装包包含受控 Backend sidecar/runtime 和版本匹配资源，可独立启动、验证、退出。

**修改范围**：desktop、backend packaging、frontend、infra、docs、tests。

**实现建议**：确定首发 Windows；构建 frozen Python executable/sidecar 或等价可复现 runtime；使用动态端口+session handshake；资源 manifest 校验版本；Tauri 负责生命周期与日志路径。

**Acceptance Criteria**：

- [ ] 干净 Windows VM 无 Python/uv/源码也可安装并启动。
- [ ] Backend、frontend、workflow/schema 版本在启动时匹配。
- [ ] 端口冲突、sidecar 崩溃、启动超时有可见错误和重试。
- [ ] 退出应用能优雅停止子进程且不误杀其他进程。
- [ ] bundle targets 与实际支持平台一致。

**Priority**：P0  
**Complexity**：XL  
**Dependencies**：P1-E5-T02、P1-E5-T01  
**Risk**：Python 原生依赖与杀毒误报；尽早制作最小 release spike，不等所有功能完成。

### P5-E2-T02 — 实现启动迁移、备份、恢复与回滚演练

**背景**：用户项目数据比应用二进制更重要，升级失败不能破坏唯一 Project State。

**当前问题**：Tauri 启动不执行 Alembic；没有启动前备份、schema compatibility、完整性检查、恢复 UI/CLI 或失败回滚流程。

**目标**：每次升级先验证并备份，迁移失败保持旧数据可恢复；用户可主动备份/恢复项目。

**修改范围**：desktop、backend、database、storage、frontend、infra、docs、tests。

**实现建议**：使用 SQLite online backup API + manifest/checksum；迁移前检查磁盘与 app/schema version；原库不原地覆盖不可恢复文件；媒体与 DB 用一致 snapshot manifest；演练 current-2→current。

**Acceptance Criteria**：

- [ ] 首次启动和旧库升级自动运行正确迁移。
- [ ] 迁移前自动备份，失败后应用不打开不兼容库并提供恢复。
- [ ] DB+media 备份可验证 checksum 并在干净环境恢复。
- [ ] current-2/current-1→current 与模拟失败回滚测试通过。
- [ ] 恢复操作有明确覆盖确认和审计记录。

**Priority**：P0  
**Complexity**：XL  
**Dependencies**：P5-E2-T01、P1-E1-T02  
**Risk**：DB 与媒体快照时间不一致；用 manifest 和短暂写暂停保证一致窗口。

### P5-E2-T03 — 建立签名 Release Pipeline、更新渠道与回退

**背景**：可重复发布需要从 commit 到签名产物、版本说明和升级验证的完整链路。

**当前问题**：无 GitHub Actions/CI release、签名、SBOM、更新 manifest、稳定/测试渠道或回退策略。

**目标**：tag 触发受控构建与签名，产物可验证；更新失败可回到兼容版本而不降级数据库。

**修改范围**：infra、desktop、docs、tests。

**实现建议**：CI 使用锁定工具链与缓存；生成 checksum/SBOM/provenance；签名 secret 仅在受保护环境；先支持手动检查更新或 beta channel，再决定自动更新。

**Acceptance Criteria**：

- [ ] 同一 tag 在干净 runner 生成可验证安装包。
- [ ] 产物有代码签名、checksum、SBOM 和变更说明。
- [ ] stable/beta 渠道隔离，未签名或版本回退攻击被拒绝。
- [ ] 应用更新失败不破坏旧可执行文件和用户数据。
- [ ] release checklist 与紧急回退演练完成。

**Priority**：P0  
**Complexity**：XL  
**Dependencies**：P5-E2-T01、P5-E2-T02、P5-E3-T01  
**Risk**：签名证书和平台分发流程外部依赖；提前确认 Windows 目标与凭据责任人。

---

## Epic 5.3 — Security、Privacy 与审计

### P5-E3-T01 — 完成威胁模型、Secrets、供应链与安全门禁

**背景**：生产安全需要覆盖本地端口、Tauri WebView、外部 Provider、文件和依赖供应链。

**当前问题**：Phase 1 只建立最小 session/CSP；尚无正式 threat model、OS secure secrets、依赖/SBOM 策略、输入大小限制或渗透验证。

**目标**：识别资产/信任边界和滥用路径，关闭发布范围内高危风险。

**修改范围**：frontend、backend、desktop、infra、docs、tests。

**实现建议**：STRIDE 风格轻量 threat model；secret 进入 OS credential store；CSP/Host/Origin/path/upload 校验；依赖锁定、SCA、secret scan、Rust/Python/npm audit；不提前做完整 RBAC。

**Acceptance Criteria**：

- [ ] Threat model 覆盖本地 API/WS、WebView、Provider、文件、更新和备份。
- [ ] API key 不明文存 DB/配置文件，日志/导出自动脱敏。
- [ ] 请求体、上传、Prompt、并发和磁盘配额有上限。
- [ ] Critical/High 依赖漏洞有阻断和例外时限。
- [ ] 安全测试验证 CSWSH、路径穿越、恶意文件、端口劫持和更新签名。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E5-T02、P2-E4-T01  
**Risk**：本地产品误做企业权限系统；范围聚焦单用户控制面与数据安全。

### P5-E3-T02 — 建立 Audit Log、隐私与数据保留策略

**背景**：用户需要追踪谁/什么 Run 修改了镜头，支持排错与撤销；日志又不能无限保存敏感内容。

**当前问题**：Event 是瞬时的，source 归因不完整；无持久审计、retention、数据导出/清除策略。Prompt/source text 可能含版权或隐私内容。

**目标**：关键业务变更有不可变审计摘要；运行日志、消息、资产和备份有明确保留/清理规则。

**修改范围**：backend、database、frontend、docs、tests。

**实现建议**：Audit Entry 记录 actor/source/session/run、entity、action、revision、request_id 与最小变更摘要；不复制完整敏感正文；按对象类型配置 retention；用户可导出诊断与删除非事实运行数据。

**Acceptance Criteria**：

- [ ] Shot/Character/Version/Generation/Approval/Restore 关键动作有审计项。
- [ ] 审计记录追加式，不随实体编辑覆盖。
- [ ] Secret、完整 Prompt/小说正文默认不进入审计摘要。
- [ ] retention/cleanup 不删除仍被 Project State 引用的资产。
- [ ] 用户可查看相关活动并导出脱敏记录。

**Priority**：P1  
**Complexity**：L  
**Dependencies**：P2-E3-T03、P1-E4-T03  
**Risk**：审计表增长；采用分页/归档策略，不在热查询中加载全文。

### P5-E3-T03 — 建立资源配额与本地防滥用

**背景**：即使无公网用户，错误点击、失控 Agent 或恶意页面也可能耗尽 GPU、磁盘和 Provider 费用。

**当前问题**：缺请求体、任务数、并发、磁盘和费用边界；批量/重试可放大负载。

**目标**：按 session/project/provider 限制危险资源，用户在提交前看到并可调整。

**修改范围**：backend、frontend、Provider runtime、config、tests。

**实现建议**：本地 token bucket 只用于 API 滥用；业务配额使用队列并发、daily budget、storage quota；超限返回可操作错误。云端分布式 rate limit 留到 Phase 6。

**Acceptance Criteria**：

- [ ] 上传/文本/批量任务/并发/重试有可配置硬上限。
- [ ] 磁盘接近阈值时停止新生成并引导清理/迁移。
- [ ] 可得费用在提交前与累计视图显示。
- [ ] Agent 不能绕过与 UI 相同的配额 Service。
- [ ] 限制命中有审计与测试，不影响正常本地交互。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P2-E4-T02、P4 批量/视频范围  
**Risk**：费用数据并非所有 Provider 可得；未知时用任务/并发硬限制。

---

## Epic 5.4 — Observability 与性能

### P5-E4-T01 — 建立结构化日志、Metrics、Error Tracking 与诊断 Health

**背景**：真实用户遇到失败时，团队必须无需访问其项目正文也能定位组件与链路。

**当前问题**：Phase 1 只建立基本关联日志/health；无长期指标、错误聚合、支持包或 SLO。

**目标**：观察 API、Worker、Agent、Provider、SQLite 和桌面启动的成功率/延迟/队列/错误，并默认保护隐私。

**修改范围**：backend、frontend、desktop、infra、docs、tests。

**实现建议**：本地结构化日志+轮转；metrics 可本地查看/用户选择上传；Error Tracking 发送脱敏 fingerprint/context；定义核心 SLI/SLO 与告警阈值。

**Acceptance Criteria**：

- [ ] 可观察请求延迟/错误、队列深度/等待、生成成功率、Agent 工具失败、DB lock。
- [ ] Error 通过 request/run/generation ID 关联前后端与 sidecar。
- [ ] 日志轮转/空间上限/retention 生效。
- [ ] Telemetry 默认值、同意与关闭路径符合隐私策略。
- [ ] health/readiness 与支持诊断不暴露 secrets/绝对敏感路径。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E4-T03、P5-E3-T02  
**Risk**：遥测本身收集敏感数据；采用 allowlist 字段并默认本地。

### P5-E4-T02 — 建立性能预算、规模基准与证据驱动优化

**背景**：索引、缓存和虚拟化应解决已测瓶颈，而不是成为架构装饰。

**当前问题**：无 500 Scene/10,000 Shot/5,000 Asset 基准；worker progress 高频 commit、列表无完整索引策略、媒体 I/O 风险已知；暂无缓存必要性证据。

**目标**：定义启动、查询、编辑、事件和任务吞吐预算，按 profiling 修复瓶颈。

**修改范围**：frontend、backend、database、storage、tests、docs。

**实现建议**：生成合成数据集；记录 SQLite query plan/lock time、React render/内存、磁盘 I/O；先分页/复合索引/节流/virtualization，再评估 cache。Project State 写路径不加不必要缓存。

**Acceptance Criteria**：

- [ ] 目标数据量和硬件档位有可重复 benchmark。
- [ ] 列表/Storyboard/启动/搜索/写入满足定义预算。
- [ ] 新增索引都有查询证据并测量写入代价。
- [ ] progress DB/event 更新有节流且最终值不丢。
- [ ] 未证明收益时不引入 Redis/通用缓存层。

**Priority**：P1  
**Complexity**：L  
**Dependencies**：P2-E2-T03、P3-E4-T02  
**Risk**：合成数据与真实项目不同；用匿名真实分布校准。

### P5-E4-T03 — 提供支持诊断包与事故 Runbook

**背景**：桌面用户环境不可直接登录，支持需要用户可控的脱敏诊断材料和恢复步骤。

**当前问题**：日志散落控制台，无一键导出、环境/版本 manifest、DB integrity 摘要或故障处置手册。

**目标**：用户能预览并导出诊断包；团队对启动、迁移、Provider、队列、数据损坏有明确 Runbook。

**修改范围**：frontend、backend、desktop、docs、tests。

**实现建议**：诊断包包含 app/schema/provider capability、health、最近脱敏错误、日志片段、DB integrity 结果；不含正文、Prompt、媒体或 key，除非用户逐项选择。

**Acceptance Criteria**：

- [ ] 用户可预览诊断包内容并删除敏感项后导出。
- [ ] 默认不包含小说正文、Prompt、媒体、API key 或完整用户路径。
- [ ] 启动失败时也能从 Desktop 壳导出 sidecar 日志。
- [ ] 关键故障有 detect→contain→recover→verify Runbook。
- [ ] 支持包格式版本化并有自动脱敏测试。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P5-E4-T01、P5-E2-T02  
**Risk**：脱敏遗漏；采用字段 allowlist，不直接打包整个日志/数据库。

## Docker 决策

当前桌面交付不依赖 Docker。若 CI 需要可复现外部测试环境，可在本阶段为测试/开发提供可选 Compose；不能用 Docker 代替 Tauri sidecar、安装包、迁移和真实 Windows smoke。
