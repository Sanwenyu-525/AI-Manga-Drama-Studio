# Current Sprint

## Sprint 01 — Project State Correctness & Runtime Stabilization

**Sprint Goal**：先保护唯一 Project State，再让 Generation/Agent 的关键运行语义可验证。完成后，小说分析不会静默写错字段，Agent 不会越界或在取消后继续修改，真实 ComfyUI 能进入受控验证，Generation 崩溃恢复有明确实现基础。

**建议节奏**：3 周稳定化 Sprint；按下方 Wave 顺序拉取，不要求团队把 8 项同时置为 In Progress。

## Tasks

| Order | Task ID | Task Name | Priority | Complexity | Dependencies | Status |
|---:|---|---|---|---|---|---|
| 1 | P1-E3-T02 | 实现协作式 Agent Cancel 与真实执行报告 | P0 | M | P1-E3-T01（已完成） | Ready |
| 2 | P1-E2-T01 | 修复真实 ComfyUI workflow 与 Provider 选择 | P0 | M | 无 | Ready |
| 3 | P1-E1-T02 | 建立数据库不变量、原子 revision 与安全重排 | P0 | L | P1-E1-T01 事务决策（已定：见 roadmap §P1-E1-T01 Design Decision） | Blocked by dependency |
| 4 | P1-E2-T02 | 实现 Generation 状态机、原子认领与崩溃恢复 | P0 | L | P1-E1-T02 | Blocked by dependency |
| 5 | P1-E6-T01 | 建立风险驱动测试基线与最小 CI | P0 | L | 测试框架可先行；风险用例随任务落地 | Ready |

完整背景、实现建议与验收标准见 [Phase 1](../roadmap/phase-1-foundation.md)。

## Execution Waves

```text
Wave A（可并行）
  P1-E2-T01  ComfyUI/provider
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
- `P1-E6-T01` 不是最后才做；每个 P0 修复必须同 PR/commit 带回归测试，CI 骨架可并行推进。
- `P1-E2-T03`（完成链原子化）和 `P1-E4-T02`（Event Gateway）仍是 P0，但因复杂度和依赖未塞入本 Sprint，排在下一个 Stabilization Sprint 首位。
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
