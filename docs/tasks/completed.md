# Completed Tasks

> Post-MVP Roadmap 的完成记录。Task 只有在 Acceptance Criteria 与验证全部通过后，才从 Current Sprint 移到这里。

## Post-MVP

| Task ID | Task Name | 完成日期 | Commit / PR | 简要修改说明 |
|---|---|---|---|---|
| P1-E2-T03 | 原子化生成完成链、真实取消与资产补偿 | 2026-08-30 | （见 git log） | CAS 终态（取消赢得竞争）、流式原子复制 + staged 文件补偿、provider 临时输出清理、provider_ref 运行期落库、cancel 按 provider id/type 正确路由、meta_json/MIME 来自真实文件；test_generation_atomicity.py 新增 8 项 |
| P1-E4-T02 | 修复 Event Gateway 线程、生命周期与恢复语义 | 2026-08-30 | （见 git log） | EventGateway 重写：线程安全 publish（call_soon_threadsafe）、每连接有界队列 drop-oldest、每连接独立 sequence、显式生命周期（start/stop 幂等 + unsubscribe）、按项目 subscribe 控制帧、防御入站帧；前端 classifySequence（dupe/route/gap）+ reconnect/gap 全量 reconcile；契约 §49.1/49.2/§52 + frontend-ux §83.1；test_event_gateway.py 新增 7 项 |
| P1-E5-T01 | 生产配置 Fail-closed 与依赖/环境契约 | 2026-08-30 | （见 git log） | `validate_startup_config`（lifespan 调用）：production 拒 fake/mock 提供器；llm_mode/video_provider/app_env 转 Literal（启动即拒非法值）；保存时 provider 422（不再静默回落）；新增 `.env.example`（无真实 secret）与 `docs/configuration-v0.1.md` 配置矩阵；test_config.py 新增 12 项 |
| P1-E5-T02 | 建立本地 Session、WS Origin 与 Tauri CSP | 2026-08-30 | （见 git log） | 本地会话 token（`STUDIO_SESSION_TOKEN`）：REST `X-Session-Token` + WS `?token=`（/health、/system/info 豁免）；WS Origin 白名单校验；Tauri 壳 uuid v4 生成 token 注入 spawn + `get_session_token` 命令 + `/health` 握手区分「本应用已运行 / 端口被其他进程占用 / 空闲」；Tauri `csp` 收紧（devCsp null 保开发流）；前端 lib/session.ts 传递 token；test_local_session.py 新增 11 项 + client token header 测试 |
| P1-E1-T01 | 修复 AI 计划映射与批量写入事务 | 2026-08-20 | 07eff18 |
| P1-E4-T01 | 修复路由冲突并统一错误/请求契约 | 2026-08-20 | 3ab41c8 |
| P1-E3-T01 | 强制 Agent Project Ownership 与 Run-local Context | 2026-08-20 | a1f7155 |
| P1-E2-T01 | 修复真实 ComfyUI workflow 与 Provider 选择 | 2026-08-20 | e4b435a |
| P1-E3-T02 | 实现协作式 Agent Cancel 与真实执行报告 | 2026-08-20 | 8736fe2 |
| P1-E6-T01 | 建立风险驱动测试基线与最小 CI | 2026-08-20 | c75615a |
| P1-E1-T02 | 建立数据库不变量、原子 revision 与安全重排 | 2026-08-20 | 3cbca1e |
| P1-E2-T02 | 实现 Generation 状态机、原子认领与崩溃恢复 | 2026-08-20 | ff04349 | 显式映射 Scene/Shot Plan（location_id 落库）；批量写入事务化（all-or-nothing + 失败注入测试）；analysis_key/storyboard_key 幂等 no-op 与显式 replace 策略；Scene DTO 新增 location_id；文档与迁移 e1f2a3b4c5d6 同步 |

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
