# Completed Tasks

> Post-MVP Roadmap 的完成记录。Task 只有在 Acceptance Criteria 与验证全部通过后，才从 Current Sprint 移到这里。

## Post-MVP

当前没有已完成的 Post-MVP Task。

| Task ID | Task Name | 完成日期 | Commit / PR | 简要修改说明 |
|---|---|---|---|---|
| P1-E1-T01 | 修复 AI 计划映射与批量写入事务 | 2026-08-20 | 07eff18 |
| P1-E4-T01 | 修复路由冲突并统一错误/请求契约 | 2026-08-20 | 待提交 | 显式映射 Scene/Shot Plan（location_id 落库）；批量写入事务化（all-or-nothing + 失败注入测试）；analysis_key/storyboard_key 幂等 no-op 与显式 replace 策略；Scene DTO 新增 location_id；文档与迁移 e1f2a3b4c5d6 同步 |

## 历史 MVP 里程碑（基线，不占用 Post-MVP Task ID）

| Task ID | Task Name | 完成日期 | Commit / PR | 简要修改说明 |
|---|---|---|---|---|
| MVP-A | Core Studio | 2026-08 | — | Project/Episode/Scene/Shot、Storyboard、Tauri Shell 与基础测试 |
| MVP-B | AI Planning | 2026-08 | — | Fake/OpenAI-compatible LLM Gateway、小说分析、Scene/Shot Plan 与 Operation |
| MVP-C | Production | 2026-08 | — | Generation、Mock/ComfyUI Adapter、Asset/MediaVersion、WS 与 Queue UI |
| MVP-D | AI Director | 2026-08 | — | LangGraph Director、三工具、Selection-aware 场景 A/B/C |
| MVP-P1 | Character & Bootstrap | 2026-08 | — | Character CRUD/Shot 关联与 Project Bootstrap |

历史行来自仓库 `AGENTS.md` 的里程碑记录；未找到对应 Commit/PR 时保持 `—`，不推测提交号。

## Completion Template

完成任务时追加一行：

```text
| P1-E1-T01 | 修复 AI 计划映射与批量写入事务 | YYYY-MM-DD | <commit/PR> | 显式映射 Scene/Shot Plan，批量写入事务化并补充失败注入测试 |
```

同时执行：

1. 从 `current-sprint.md` 移除该任务；
2. 更新后续任务 Dependencies/Status；
3. 若阶段 Exit Criteria 达成，更新 `docs/roadmap/README.md` 的 Phase Status；
4. API/DB/Event/Tool 有变化时确认事实源文档已同步。
