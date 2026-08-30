# Current Sprint

> **Sprint 01 完成（2026-08-20）**：8 项 P0 任务全部完成（P1-E1-T01/T02、P1-E2-T01/T02、
> P1-E3-T01/T02、P1-E4-T01、P1-E6-T01），见 [Completed](completed.md)。
> **Sprint 02 完成（2026-08-30）**：P1-E2-T03（完成链原子化）+ P1-E4-T02（Event Gateway 加固）完成。
> 剩余 P0 为 P1-E5-T01（Fail-closed 配置）、P1-E5-T02（本地 Session/WS Origin/CSP）；P1 任务
> P1-E4-T03（关联日志）与 P1-E6-T02（文档事实源）待办。

## Sprint 01 — Project State Correctness & Runtime Stabilization

**Sprint Goal**：先保护唯一 Project State，再让 Generation/Agent 的关键运行语义可验证。完成后，小说分析不会静默写错字段，Agent 不会越界或在取消后继续修改，真实 ComfyUI 能进入受控验证，Generation 崩溃恢复有明确实现基础。

**建议节奏**：3 周稳定化 Sprint；按下方 Wave 顺序拉取，不要求团队把 8 项同时置为 In Progress。

## Tasks

| Order | Task ID | Task Name | Priority | Complexity | Dependencies | Status |
|---:|---|---|---|---|---|---|

完整背景、实现建议与验收标准见 [Phase 1](../roadmap/phase-1-foundation.md)。

## Execution Waves

```text
Wave A（可并行）
  P1-E6-T01  CI 骨架与对应回归用例

Wave B
  P1-E3-T02  Agent cancel
  P1-E1-T02  DB 不变量/revision/reorder

Wave C
  P1-E2-T02  Generation claim/recovery/state machine
  P1-E6-T01  收齐本 Sprint 门禁
```

## Dependencies / Scope Notes

- `P1-E1-T01` 已完成（2026-08）：Plan 显式映射、批量写入事务化、幂等/替换策略落库；P1-E1-T02 的事务决策见 [Phase 1 P1-E1-T01 Design Decision](../roadmap/phase-1-foundation.md)。
- `P1-E4-T01` 已完成（2026-08）：generations/recent 路由冲突修复、统一错误 Envelope（422/404/405/409/500 + request_id）、Router 业务 SQL 移入 Service、前端 ApiError 携带 request_id 并支持 timeout/AbortSignal；P1-E4-T02 的 request context 基线见 [P1-E4-T01 Design Decision](../roadmap/phase-1-foundation.md)。
- `P1-E3-T01` 已完成（2026-08）：reference 解析强制 project ownership（跨项目/已删除/伪造 selection 拒绝）、同号歧义澄清、FakeLLM selection run-local 化、ToolExecutor 防御；见 [P1-E3-T01 Design Decision](../roadmap/phase-1-foundation.md)。
- `P1-E2-T01` 已完成（2026-08）：规范 provider id 落库并与实际执行一致、workflow catalog + preflight、未知 provider/type/workflow fail fast 422、httpx/websockets 显式依赖；见 [P1-E2-T01 Design Decision](../roadmap/phase-1-foundation.md)。P1-E5-T01 依赖解锁。
- `P1-E3-T02` 已完成（2026-08）：协作式取消（cancelling → 单次 cancelled 终态）、节点/工具边界取消检查、current_stage 实时报告、工具真实 changed_fields 与 shot.updated source/run_id；见 [P1-E3-T02 Design Decision](../roadmap/phase-1-foundation.md)。
- `P1-E6-T01` 已完成（2026-08）：Alembic-from-zero/round-trip 迁移测试、真实 Worker loop 测试、ruff 门禁、前端 vitest（错误契约/Event reconcile/Store/组件）、GitHub Actions CI、secret 扫描与 docs/testing.md 本地命令；见 [P1-E6-T01 Design Decision](../roadmap/phase-1-foundation.md)。
- `P1-E1-T02` 已完成（2026-08）：部分唯一索引不变量、原子条件更新 revision（Shot/Character）、安全重排（完整集合校验+两阶段编号）、父删子隐规则、迁移重复检测；见 [P1-E1-T02 Design Decision](../roadmap/phase-1-foundation.md)。
- `P1-E2-T02` 已完成（2026-08）：集中状态机（非法迁移 409）、原子认领（条件 UPDATE）、lease 心跳与崩溃恢复、重试退避、单 Worker 校验、/health worker 字段；见 [P1-E2-T02 Design Decision](../roadmap/phase-1-foundation.md)。
- `P1-E6-T01` 不是最后才做；每个 P0 修复必须同 PR/commit 带回归测试，CI 骨架可并行推进。
- `P1-E2-T03`（完成链原子化）与 `P1-E4-T02`（Event Gateway）已完成（2026-08-30，见 [Completed](completed.md)）；下一个 Sprint 首位 P0 为 `P1-E5-T01`（生产配置 Fail-closed）与 `P1-E5-T02`（本地 Session/WS Origin/CSP）。
- 本 Sprint 不开发 Timeline、Continuity、多 Agent、云端、插件或 UI 大改。

## Definition of Done

- [ ] 每项 Task 的 Acceptance Criteria 全部勾选并附验证命令/结果。
- [ ] API/DB/Event/Tool 变化先更新事实源文档。
- [ ] 新增失败路径至少包含一个先失败、修复后通过的回归测试。
- [ ] 后端测试、迁移 smoke、前端 type/build/test、Cargo check 和最小 CI 全部通过。
- [ ] 统一错误不泄露 secrets、绝对敏感路径或原始异常栈。
- [ ] 相关日志包含 request/project/run/generation 等适用关联 ID。
- [ ] 没有修改无关模块，没有引入未请求框架或分布式基础设施。
- [ ] `git diff` 中每一项业务改动都可追溯到本 Sprint Task。
- [ ] 完成后从本文移入 [Completed](completed.md)，记录日期和 Commit/PR。
