# 目标架构状态

> 目标不是立即云原生化，而是在保持本地桌面优先与单体可维护性的前提下，逐阶段形成可恢复、可验证、可发布的 Studio。

## 1. 目标原则

1. SQLite Project State 继续作为唯一业务事实源。
2. 保持模块化单体；在出现真实规模触发器之前不拆微服务、不引入 Redis/Celery/Kafka。
3. 所有长任务都有持久状态、幂等边界、取消语义、崩溃恢复和前端对账。
4. 外部实现只通过 Studio Domain Contract 暴露能力。
5. 默认配置可开发，生产配置必须 fail closed，不能静默回落到 Fake/Mock。
6. UI 必须能解释系统状态：正在做什么、是否保存、失败原因、如何恢复。

## 2. 目标结构

```text
Desktop UI
  ├── Generated REST Client
  ├── Validated Event Client + Reconcile
  └── Query State / Local UI State
             │
             ▼
Application API
  ├── Local Session Boundary
  ├── Error / Request Context
  └── Router（仅协议适配）
             │
             ▼
Deep Application Modules
  ├── Project / Planning / Storyboard
  ├── Director + Approval + ChangeSet
  ├── Generation Runtime + Finalizer
  ├── Asset / Version
  └── Provider Runtime
             │
     Repository / Unit of Work
             │
          SQLite WAL

Adapters: OpenAI-compatible · ComfyUI · Filesystem
Observability: structured logs · metrics · audit trail · health diagnostics
```

## 3. 阶段目标

### Phase 1 结束

- 所有 P0 数据正确性与跨项目边界问题有回归测试。
- Generation 与 Agent 的取消、恢复、归属检查语义可信。
- 统一错误 Envelope、request/correlation context 与可诊断 health 生效。
- ComfyUI 真实 Adapter 可通过 preflight 和受控 smoke test。
- 最小 CI 阻止测试、构建、迁移和契约回归。

### Phase 2 结束

- 用户可完整管理项目、资产、版本与任务生命周期。
- “预览—确认”提交同一份已审阅计划。
- Director Run 可恢复，R2/R3 修改有审批，ChangeSet 可审阅/撤销。
- 搜索、筛选、分页、批量操作只覆盖已证实的高频对象。

### Phase 3 结束

- 核心路径具备一致的 Empty/Loading/Error/Success 状态。
- 键盘、多选、批量、焦点、可访问性和布局持久化达到桌面工具标准。
- 断线、重启、后台任务和版本冲突对用户可见且可恢复。

### Phase 5 发布门槛

- 安装包内含受控 Runtime、迁移与资源，不依赖源码目录或系统 `uv`。
- 有单元/集成/E2E/Adapter smoke 的分层测试，具备发布、升级、备份、恢复和回滚演练。
- 本地 API/WS 有会话边界，Secrets 进入 OS 安全存储，日志与审计不泄露敏感 Prompt/Key。

## 4. 有意保留的架构选择

- **保留模块化单体**：当前团队与负载没有证明微服务收益。
- **保留 SQLite + DB-poll**：单用户桌面场景下可提供最高 Locality；先补 lease/recovery/index，再评估外部队列。
- **不做通用插件平台**：至少出现两个稳定的第三方扩展需求后再抽象 Extension SDK。
- **不做 RBAC/多租户**：本地单用户先使用 session boundary；协作/云端模式经产品验证后进入 Phase 6。
- **不为 light mode 延迟核心 UX**：当前设计系统明确 dark-first；主题扩展属于 P3。

## 5. 关键 Seam

| Seam | Interface 责任 | Implementation | 不应泄露 |
|---|---|---|---|
| Provider Runtime | 能力、健康、提交、进度、取消、结果 provenance | Mock / ComfyUI / future API | node_id、workflow 内部结构 |
| Generation Runtime | 幂等创建、lease、恢复、状态机、finalize | SQLite worker；规模触发后可换外部 queue | provider 特有状态 |
| Director Runtime | run、checkpoint、approval、resume、cancel | LangGraph Adapter | ToolMessage/checkpoint 结构 |
| Contract | REST DTO、Event schema、错误码 | Pydantic/OpenAPI + generated TS | SQLAlchemy/LangChain 类型 |
| Storage | 项目相对路径、流式写入、校验、归档 | Local filesystem；规模触发后对象存储 | 绝对路径与厂商 API |

## 6. Phase 6 触发器

仅在满足以下至少一项时启动对应扩展：

- 单项目达到约 500 Scenes / 10,000 Shots，SQLite 查询或启动时间超出已定义 SLO。
- 需要多设备或多人同时编辑，单机 Project State 不再满足产品模型。
- 需要跨机器 Worker、任务高可用或同时运行大量视频生成。
- 本地媒体达到存储/备份瓶颈，需要对象存储与冷热归档。
- 已有至少两个真实外部 Provider/扩展由独立团队维护，需要稳定 SDK。

触发器未出现时，优先优化现有 Module，而不是引入分布式复杂度。
