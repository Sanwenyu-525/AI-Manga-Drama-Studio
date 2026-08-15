# Phase 6 — Scale & Long-term Architecture

## Goal

只在用户规模、数据规模或扩展团队已经超出模块化单体能力时演进。Phase 6 是触发式路线图，不是必经的“架构升级仪式”。

## Trigger Policy

每个 Task 启动前必须附：现状指标、瓶颈证据、两种以上方案、迁移/回滚计划、单机模式影响。没有触发证据则保持 Future。

---

## Epic 6.1 — 容量与持久化演进

### P6-E1-T01 — 建立容量评审与架构决策门槛

**背景**：规模问题必须先测量，否则会用分布式复杂度替代真实产品工作。

**当前问题**：Phase 5 会建立单机基准，但尚没有决定何时从 SQLite/本地存储演进的正式流程。

**目标**：按 SLO、数据量、并发和运维成本定期评审，并形成 ADR。

**修改范围**：architecture、docs、benchmarks、infra。

**实现建议**：每季度或版本里程碑记录 p95 latency、DB size/lock、queue wait、media storage、active projects/users；只有连续超预算且本地优化无效时启动迁移。

**Acceptance Criteria**：

- [ ] SQLite、DB-poll、filesystem、EventBus 的触发阈值有可测指标。
- [ ] 每次架构迁移有 ADR、成本估计和退出条件。
- [ ] 先验证分页/索引/节流/归档等局部优化。
- [ ] 无触发器时明确记录“不迁移”决定。

**Priority**：P2  
**Complexity**：M  
**Dependencies**：P5-E4-T02  
**Risk**：指标被用来追求架构而非用户价值；必须关联真实受影响用户/任务。

### P6-E1-T02 — 在协作需求成立后迁移 PostgreSQL 与 Multi-tenant Schema

**背景**：多设备/多人并发编辑会超出单机 SQLite 的产品模型，而不只是性能问题。

**当前问题**：当前单用户本地项目不需要 Tenant/User/Role；提前加入会污染所有查询和 UX。

**目标**：当云端协作被验证后，提供 tenant-scoped Project State 与可回滚迁移，同时保留本地单机能力。

**修改范围**：backend、database、API、auth、infra、docs、tests。

**实现建议**：先做 storage/repository compatibility audit；tenant_id 进入所有事实表和唯一约束；PostgreSQL 使用在线迁移/双写仅在必要时；本地模式通过独立 Implementation，不让业务 Service 分支散落。

**Acceptance Criteria**：

- [ ] 有付费/试点用户证明多人/多设备需求。
- [ ] 所有查询和事件通过 tenant isolation 测试。
- [ ] SQLite→PostgreSQL 导入可校验、可重试、可回滚。
- [ ] 本地项目可继续离线使用或有清晰产品决定。
- [ ] 性能/成本优于已测单机方案。

**Priority**：P2  
**Complexity**：XL  
**Dependencies**：P6-E1-T01、P6-E4-T02  
**Risk**：这是产品与运维模式改变，不应伪装成数据库替换。

---

## Epic 6.2 — 分布式任务与事件

### P6-E2-T01 — 在跨机器 Worker 需求出现后外部化 Queue

**背景**：DB-poll 对单机足够；多机器 GPU 或高并发视频才需要外部消息系统。

**当前问题**：SQLite lease 无法协调多主机，长视频任务可能需要独立 Worker；目前尚无此需求证据。

**目标**：保留 Generation Runtime Interface，把 claim/lease/delivery Implementation 替换为受控外部 Queue。

**修改范围**：backend、worker、infra、observability、docs、tests。

**实现建议**：先定义交付语义、幂等 finalizer、dead-letter 与 backpressure；再在 Redis Queue/云队列/Temporal 中选最小满足项。不要同时改业务状态机。

**Acceptance Criteria**：

- [ ] 有跨机器或单机容量超标证据。
- [ ] at-least-once delivery 下不会重复创建 Asset/Version。
- [ ] cancel、priority、retry、dead-letter 与恢复语义有故障测试。
- [ ] 旧 SQLite worker 可在本地模式继续运行。
- [ ] 运维成本、SLO 和回退路径有 ADR。

**Priority**：P2  
**Complexity**：XL  
**Dependencies**：P6-E1-T01、Phase 5 Generation/Observability  
**Risk**：消息系统增加重复交付与运维面；幂等性必须在迁移前完成。

### P6-E2-T02 — 在可靠跨进程消费需求出现后引入 Outbox/Event Replay

**背景**：进程内事件适合 UI 提示；跨服务审计、自动化和第三方消费需要持久交付。

**当前问题**：当前 WS 重连通过 REST 对账即可；没有必要仅为 sequence 持久化所有事件。

**目标**：当存在多个可靠消费者时，以 transactional outbox 保证 commit 后发布和可重放。

**修改范围**：backend、database、events、infra、docs、tests。

**实现建议**：业务事务写 outbox；dispatcher 发布 Studio Event；consumer 保存 offset/idempotency。UI 仍以 Project State 为事实源，不把 event log 变成 Event Sourcing。

**Acceptance Criteria**：

- [ ] 至少两个需要可靠重放的真实 consumer 已确认。
- [ ] DB commit 与 outbox 写入同事务。
- [ ] 重复/乱序/重启消费不会重复副作用。
- [ ] retention、归档与 schema version 策略明确。
- [ ] 明确不将 Project State 改为 Event Sourcing。

**Priority**：P2  
**Complexity**：XL  
**Dependencies**：P6-E2-T01 或其他可靠 consumer 触发、P5 Audit  
**Risk**：双事实源误用；文档和 API 必须继续以数据库实体为唯一可信状态。

---

## Epic 6.3 — 存储、归档与搜索

### P6-E3-T01 — 在媒体容量超限后引入对象存储与冷热归档

**背景**：视频/多版本会让本地磁盘成为瓶颈，但对象存储会改变离线和备份模型。

**当前问题**：本地 filesystem 具有高 Locality；在用户未遇到空间问题前迁移没有收益。

**目标**：当配额/备份成本超限时，通过 Storage Interface 支持本地、对象存储和可恢复归档。

**修改范围**：storage、backend、database、infra、frontend、docs、tests。

**实现建议**：内容寻址/checksum、upload session、signed access、local cache；归档只移动非 active/长期未访问媒体，metadata 留在 Project State；支持回迁和离线提示。

**Acceptance Criteria**：

- [ ] 有真实媒体容量、备份时间或多设备访问触发证据。
- [ ] 上传/下载可恢复，checksum 验证，不产生悬空 DB 引用。
- [ ] archived asset 的 UI、恢复时间与离线行为清楚。
- [ ] 用户可导出完整项目，不被单一云厂商锁定。
- [ ] 本地 Storage Implementation 继续受支持。

**Priority**：P2  
**Complexity**：XL  
**Dependencies**：P6-E1-T01、P5 backup/quotas  
**Risk**：成本、隐私、离线能力和供应商锁定；必须支持可移植 manifest。

### P6-E3-T02 — 在 SQLite 搜索不够用后引入专用索引

**背景**：项目可能需要跨剧集搜索台词、角色、地点、Prompt 和资产 metadata，但 SQLite FTS 可能已足够。

**当前问题**：当前首先缺基础搜索 API，不是搜索引擎性能；不能跳过 Phase 2 直接上 Elasticsearch/向量库。

**目标**：先以 SQLite FTS/结构化索引满足搜索；只有语义搜索或跨租户规模证明后才换专用引擎。

**修改范围**：backend、database/search Adapter、frontend、infra、docs、tests。

**实现建议**：建立 Search Contract 与基准查询集；索引异步可重建，不成为事实源；权限/tenant filter 在查询层强制；语义向量是独立可选能力。

**Acceptance Criteria**：

- [ ] 有真实查询日志证明现有搜索未达 SLO/召回。
- [ ] 新索引可从 Project State 全量重建和校验。
- [ ] 删除/归档/权限变化及时反映，不泄漏跨项目数据。
- [ ] 搜索质量与延迟有评测集。
- [ ] 没有需求时优先 SQLite FTS，不新增服务。

**Priority**：P2  
**Complexity**：L  
**Dependencies**：P2 搜索/分页、P6-E1-T01  
**Risk**：索引陈旧和双写；坚持可重建派生数据模型。

---

## Epic 6.4 — 扩展与协作

### P6-E4-T01 — 在两个以上外部扩展案例后定义 Provider/Workflow SDK

**背景**：稳定 SDK 应从多个真实 Implementation 的共同需求中提炼，而不是提前预测。

**当前问题**：目前只有 Mock/ComfyUI；现有 Provider Interface 已够内部扩展，尚不需要 Marketplace 或通用 Plugin Runtime。

**目标**：当外部团队需要独立发布 Adapter 时，提供版本化 contract、沙箱权限、测试套件和安装生命周期。

**修改范围**：backend、desktop、SDK、security、docs、tests。

**实现建议**：先支持进程外 provider adapter 或受控 package；manifest 声明 capability/permission/version；contract test kit；签名与隔离优先于动态 UI 插件。

**Acceptance Criteria**：

- [ ] 至少两个由独立维护者提出的稳定扩展用例。
- [ ] SDK 不暴露 SQLAlchemy、LangGraph、ComfyUI 内部类型。
- [ ] 版本兼容、签名、权限、资源限制和卸载行为明确。
- [ ] 插件失败不能破坏主进程或 Project State。
- [ ] 内建 Adapter 使用同一 contract test kit。

**Priority**：P2  
**Complexity**：XL  
**Dependencies**：Phase 5 Security/Release、多个真实 Adapter  
**Risk**：长期兼容成本极高；没有外部采用承诺时不发布公共 SDK。

### P6-E4-T02 — 在团队协作被验证后实现身份、RBAC 与同步

**背景**：多人协作需要身份、权限、冲突和审计，是完整产品模式，不是加一张 users 表。

**当前问题**：当前单用户 session boundary 不表达组织/角色；Project State 和事件均为本地模型。

**目标**：为明确的团队用例提供 least-privilege 角色、项目共享与冲突策略。

**修改范围**：auth、backend、database、frontend、events、infra、docs、tests。

**实现建议**：先定义 owner/editor/reviewer 最小角色；所有 Service 入口接受 Actor/Policy Context；同步采用 revision/ChangeSet，实时协作是否需要 CRDT 由冲突数据决定。

**Acceptance Criteria**：

- [ ] 有团队试点和角色权限矩阵。
- [ ] REST/WS/Asset/Event/Agent Tool 均执行相同 tenant/project policy。
- [ ] 越权与横向访问测试覆盖所有资源。
- [ ] 冲突可见可恢复，离线编辑策略明确。
- [ ] Audit 能追踪 actor，隐私/删除策略合规。

**Priority**：P2  
**Complexity**：XL  
**Dependencies**：P6-E1-T02、Phase 5 Audit/Security  
**Risk**：认证厂商、同步和合规大幅增加维护成本；无付费协作需求不启动。

### P6-E4-T03 — 以评测证明多 Agent 的净收益

**背景**：多 Agent 只有在质量/吞吐提升大于协调成本和不可预测性时才值得引入。

**当前问题**：单 Director 的持久化、审批、评测要先稳定；增加 Writer/Director/Continuity Agent 可能重复上下文和冲突修改。

**目标**：通过离线 benchmark 比较单 Agent 与角色化多 Agent，在同等成本下证明质量或吞吐提升后再产品化。

**修改范围**：Agent runtime、evaluation、Workflow、docs、tests。

**实现建议**：先将角色实现为同一 Workflow 中有界步骤，共享 Project State/ChangeSet，不允许 Agent 之间直接把聊天当事实；设置预算、停止条件和冲突仲裁。

**Acceptance Criteria**：

- [ ] 有版本化任务集、质量/成本/延迟指标和单 Agent 基线。
- [ ] 多 Agent 在预设指标上显著优于基线，否则停止。
- [ ] 所有写入仍经过 Service、Approval、ChangeSet 和 ownership policy。
- [ ] 并发冲突、循环委派和预算耗尽有硬停止条件。
- [ ] 用户能理解各 Agent 责任和最终决策来源。

**Priority**：P3  
**Complexity**：XL  
**Dependencies**：P4 Workflow/Review、Phase 5 Observability、P6-E4-T02（若协作）  
**Risk**：演示效果掩盖成本与可靠性；严格以评测和真实生产数据决定。
