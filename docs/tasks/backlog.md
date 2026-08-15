# Backlog

> 任务完整定义位于对应 Phase 文件。表内顺序综合价值、风险、依赖与成本；Priority 相同不代表可以跳过前置阶段。

## P0

| Rank | Task ID | Task Name | Phase | Complexity | Key Dependency |
|---:|---|---|---|---|---|
| 1 | P1-E2-T03 | 原子化生成完成、真实取消与资产补偿 | 1 | XL | P1-E2-T01/T02 |
| 2 | P1-E4-T02 | 修复 Event Gateway 线程、生命周期与恢复语义 | 1 | L | P1-E4-T01 |
| 3 | P1-E5-T01 | 生产配置 Fail-closed 与依赖/环境契约 | 1 | M | P1-E2-T01 |
| 4 | P1-E5-T02 | 建立本地 Session、WS Origin 与 Tauri CSP | 1 | L | P1-E4-T01/T02 |
| 5 | P2-E1-T01 | 提交用户已审阅的 Analysis Snapshot | 2 | L | Phase 1 data/API |
| 6 | P2-E3-T01 | 持久化 Agent Run、Session、Message 与 Checkpoint | 2 | L | Phase 1 Agent/Event |
| 7 | P2-E3-T02 | 实现风险分级、Approval 与 Resume | 2 | XL | P2-E3-T01 |
| 8 | P2-E3-T03 | 实现 ChangeSet、Shot Snapshot 与 Undo | 2 | XL | P2-E3-T02 |
| 9 | P2-E4-T01 | 建立 Provider Settings 与诊断工作区 | 2 | L | Phase 1 Provider/Security |
| 10 | P3-E1-T01 | 建立统一 Async State、Toast、Skeleton 与 Error Boundary | 3 | L | P1-E4-T01 |
| 11 | P3-E1-T02 | 让断线、刷新与后台任务恢复对用户可见 | 3 | M | P1-E4-T02/P2-E3-T01 |
| 12 | P5-E1-T01 | 完成分层测试金字塔与覆盖门槛 | 5 | L | P1-E6-T01/Phase 2 |
| 13 | P5-E1-T02 | 建立核心 E2E、故障注入与真实 Adapter Certification | 5 | XL | Desktop/Provider/UX |
| 14 | P5-E2-T01 | 打包受控 Backend Runtime、Workflow 与安装器 | 5 | XL | Phase 1 Security/Config |
| 15 | P5-E2-T02 | 实现启动迁移、备份、恢复与回滚演练 | 5 | XL | P5-E2-T01 |
| 16 | P5-E2-T03 | 建立签名 Release Pipeline、更新渠道与回退 | 5 | XL | P5-E2-T01/T02 |
| 17 | P5-E3-T01 | 完成威胁模型、Secrets、供应链与安全门禁 | 5 | L | Phase 1/2 Security |
| 18 | P5-E4-T01 | 建立结构化日志、Metrics、Error Tracking 与诊断 Health | 5 | L | P1 observability/P5 audit |

## P1

| Rank | Task ID | Task Name | Phase | Complexity | Key Dependency |
|---:|---|---|---|---|---|
| 1 | P1-E4-T03 | 建立关联日志与深度健康检查 | 1 | M | P1-E4-T01/P1-E2-T02 |
| 2 | P1-E6-T02 | 修正文档事实源与移除误导性遗留入口 | 1 | S | P1-E6-T01 |
| 3 | P2-E1-T02 | 支持长文本分块、进度与明确角色提取 | 2 | L | P2-E1-T01/P2-E4-T02 |
| 4 | P2-E2-T01 | 补齐核心实体归档、恢复与删除语义 | 2 | L | Phase 1 DB/Security |
| 5 | P2-E2-T02 | 建立项目作用域 Asset Library | 2 | L | Generation finalizer/Security |
| 6 | P2-E2-T03 | 项目化任务查询、筛选与受控批量操作 | 2 | M | Generation state/API |
| 7 | P2-E4-T02 | 建立模型/生成 Profile、能力与预算边界 | 2 | M | P2-E4-T01 |
| 8 | P2-E5-T01 | 完成版本比较、批注与决策状态 | 2 | M | Version integrity |
| 9 | P3-E1-T03 | 统一表单冲突、保存、撤销与离开保护 | 3 | M | Revision/feedback primitives |
| 10 | P3-E2-T01 | 对齐导航、页面层级与真实能力 | 3 | M | Assets/Settings |
| 11 | P3-E2-T02 | 重做项目创建与导入的确定性流程 | 3 | M | Snapshot/Settings/feedback |
| 12 | P3-E3-T01 | 实现一致 Selection、多选、键盘与批量动作 | 3 | L | Batch API/forms |
| 13 | P3-E4-T01 | 达到桌面工具可访问性基线 | 3 | M | UI primitives/selection |
| 14 | P3-E4-T02 | 优化查询、轮询、布局持久化与首屏感知 | 3 | M | Event recovery/pagination |
| 15 | P4-E1-T01 | 建立 Continuity State、Transition 与 Issue Domain | 4 | L | ChangeSet/Version/UX |
| 16 | P4-E1-T02 | 实现视觉 Continuity 检查与人工校准 | 4 | XL | P4-E1-T01/evaluation |
| 17 | P4-E2-T01 | 建立版本化 Workflow Definition | 4 | XL | Phase 2 runtime |
| 18 | P4-E2-T02 | 实现可暂停、恢复的批量 Production Run | 4 | XL | P4-E2-T01 |
| 19 | P4-E3-T01 | 扩展 Video Provider 与不可变视频版本 | 4 | XL | Workflow/storage limits |
| 20 | P4-E3-T02 | 建立最小 Timeline 与确定性 Export | 4 | XL | Video/Workflow |
| 21 | P4-E4-T01 | 建立可评测的生成质量 Review Loop | 4 | XL | Version/Profile |
| 22 | P5-E3-T02 | 建立 Audit Log、隐私与数据保留策略 | 5 | L | ChangeSet/logging |
| 23 | P5-E3-T03 | 建立资源配额与本地防滥用 | 5 | M | Profile/batch scope |
| 24 | P5-E4-T02 | 建立性能预算、规模基准与证据驱动优化 | 5 | L | Pagination/UX perf |
| 25 | P5-E4-T03 | 提供支持诊断包与事故 Runbook | 5 | M | Observability/backup |

## P2

| Rank | Task ID | Task Name | Phase | Complexity | Trigger / Dependency |
|---:|---|---|---|---|---|
| 1 | P3-E3-T02 | 增加 Command Palette 与上下文动作 | 3 | M | Selection/action registry |
| 2 | P4-E2-T03 | 提供只读优先的 Director Canvas | 4 | L | Workflow/Production Run |
| 3 | P6-E1-T01 | 建立容量评审与架构决策门槛 | 6 | M | Phase 5 benchmarks |
| 4 | P6-E1-T02 | 在协作需求成立后迁移 PostgreSQL 与 Multi-tenant Schema | 6 | XL | Multi-user trigger |
| 5 | P6-E2-T01 | 在跨机器 Worker 需求出现后外部化 Queue | 6 | XL | Cross-host/GPU trigger |
| 6 | P6-E2-T02 | 在可靠跨进程消费需求出现后引入 Outbox/Event Replay | 6 | XL | Two reliable consumers |
| 7 | P6-E3-T01 | 在媒体容量超限后引入对象存储与冷热归档 | 6 | XL | Storage trigger |
| 8 | P6-E3-T02 | 在 SQLite 搜索不够用后引入专用索引 | 6 | L | Search SLO trigger |
| 9 | P6-E4-T01 | 在两个以上外部扩展案例后定义 Provider/Workflow SDK | 6 | XL | External maintainer trigger |
| 10 | P6-E4-T02 | 在团队协作被验证后实现身份、RBAC 与同步 | 6 | XL | Paid/team pilot trigger |

## P3

| Rank | Task ID | Task Name | Phase | Complexity | Trigger / Dependency |
|---:|---|---|---|---|---|
| 1 | P3-E4-T03 | 主题与视觉一致性收尾 | 3 | S | Core UI primitives complete |
| 2 | P6-E4-T03 | 以评测证明多 Agent 的净收益 | 6 | XL | Workflow/evaluation evidence |

## Backlog Rules

- P0 可能因为前置依赖留在 Backlog；只有依赖满足且团队容量允许时进入 Sprint。
- Phase 4 Task 进入 Sprint 前必须通过该文件的 Value Gate。
- Phase 6 Task 没有 trigger evidence 不得进入 Sprint，即使技术实现看似简单。
- 新任务必须先关联既有 Epic；若无法关联，先说明为什么需要新增 Epic，而不是按代码目录增加清单。
