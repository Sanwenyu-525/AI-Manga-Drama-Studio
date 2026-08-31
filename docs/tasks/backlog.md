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

## 状态注记（2026-08-31，Sprint 04 真实链路验证会后）

- **P2-E1-T01**：**已完成（2026-08-31）**。preview 落库不可变 `analysis_snapshots`（source_hash + episode_revision + plan_json + model/prompt/schema provenance）；confirm 提交 snapshot_id 零 LLM 写入（写入=预览逐项一致）；幂等重放；原文/revision 变更 → 快照过期（409 语义经 operation failed 呈现）；`GET /episodes/{id}/analysis-snapshots/latest` 支持刷新水合；legacy 无 snapshot_id 路径向后兼容。契约 §14.1。P2-E1-T02（长文本分块）的前置「明确角色提取/替换原文控件」未动——T02 仍按原表。
- **P2-E3-T01**：大部分已由 P7 落地（`agent_runs` 落库 + SQLite Checkpointer + run summary/messages/plan）；剩余缺口 = 前端刷新水合 + running 态对账 + retention/cleanup 配置。
- **P2-E3-T02**：**已完成（2026-08-31）**。R0–R3 风险分级落地（`app/agents/risk.py` 确定性分类 + 策略）：R1 update_shot 自动执行+ChangeSet（不把每次近景修改升级为确认）；R2 generate_image 审批前零 Generation 创建（`STUDIO_AGENT_AUTO_APPROVE_R2` 可放开）；R3 未知工具一律审批。Proposal 携带结构化 risk 元数据（level/reason/tasks/cost=null 诚实未知/irreversible）+ `expires_at`（默认 24h）：过期=终态（approve/reject 409）、读路径懒扫描、全部过期 run→failed 不悬挂；interrupt→restart→resume 自动测试通过。AC 全项满足。
- **P2-E3-T03**：**已完成（2026-08-31）**。`agent_change_sets` 表记录每次已应用 Agent mutation 的最小 before/after patch（含 worker active-version 切换，`generations.run_id` 溯源）；Undo=新补偿变更（revision+1、链回原记录、历史不改写、媒体只切 active）；同字段被覆盖→409+recovery（force=true 恢复路径）；批量 undo 逐项结果（undone|conflict|skipped）；前端 ChangeSetPanel 执行前(proposal)/后(change set)审阅+跳转受影响实体。首版范围=Director Shot patch + active-version 切换（按任务 Risk 注记收窄）。
- **P2-E4-T01**：已获 Sprint 04 真实使用证据（DiT 模型不出现于模型枚举、catalog 需手写注册、前端无 provider/workflow 选择入口），见 `docs/reports/real-chain-validation-report.md` §5。**Sprint 05 已交付**：P2-1 分架构模型枚举（`GET /providers/comfyui/models` 返回 `catalog`，UNETLoader/CLIPLoader/VAELoader 槽位）+ P2-2 运行时 workflow catalog 自动发现（workflows/ 目录 drop-in 即注册，无需改 `workflow_mapper.py`）+ P2-4 前端单镜头生成引擎选择（GenerationEnginePicker，provider + workflow 显式指定）。**剩余**：图像 Provider Profile（镜像 LLM 侧 `/llm/profiles` 模式：多命名配置 + 任务绑定 + secret masked，`/image/profiles`）——在 LLM Profile 后再做，避免并行双 Role 模型。
- **P4-E1-T01**：**Continuity State Domain 已由 P8 并行交付（2026-08）**：`scene_continuity_states`/`shot_continuity_states` 两表（迁移 `a0b1c2d3e4f7`/`a8b9c0d1e2f3`）+ 8 条确定性规则 + `continuity_warnings` + Agent continuity check/fix（复用 Proposal 审批流）+ 前端 `features/continuity/`。**剩余**：本任务范围收敛为字段治理与边角；视觉检查归 P4-E1-T02，不再按「未开始」排期。
- **P4-E3-T01**：**已完成（2026-08-31 代码核对）**。VideoProviderProtocol（`providers/video/base.py`）+ 真实 AgnesVideoProvider（agnes-video-2.5-flash，text-to-video：任务创建/轮询/下载）+ mock 占位 VideoProviderUnavailable（fail-fast）；registry `video.mock`（`video_generation: False`）/`video.agnes`（`True`）；排队前 type ∈ image/video 校验 + 未知 provider 422 + capability 区分（generation_service）；Shot 可保留多个不可变视频版本并切换 active（`active_video_asset_id` + `GET/POST /shots/{id}/video-versions`、activate 端点）；cancel/retry/recovery 复用既有 Generation 状态机；前端 ShotInspector 视频入口 + SettingsPage 视频 provider 配置；test_config / test_image_settings 覆盖。AC 全项满足。
- **P4-E3-T02**：**已完成（2026-08-31，AC-2 缺口已关闭）**。Timeline 三表 + 默认四轨（VIDEO/VOICE/MUSIC/SUBTITLE）+ clip 编辑（drag/trim/re-track/enable/text）+ `sequence-from-shots` + 非渲染预览 + `type=render` 渲染（mock MJPEG AVI / ffmpeg H.264 MP4）→ `FINAL_VIDEO` 不可变版本 + 音频混流/字幕烧录（P10）+ AC-2（`TimelineClip.transition` cut/fade/dissolve 转场、clip `revision` 乐观并发 409、Timeline 编辑纳入 ChangeSet/Undo）均已落地；缺失媒体/编码失败/磁盘不足走 generation fail + RENDER_FAILED 可恢复路径。
- **P2-E3-T03 / P2-E2-\***：本次验证无新证据，优先级维持原表。

## 当前工作区：一致性参考图管道（M1-M4）

> 事实源：`docs/reports/p3-consistency-engine-preresearch.md`（Sprint 04 §6 第 4 条预研授权交付物，2026-08-31）。结论：角色一致性失败=机制缺失（无参考图输入）而非引擎问题；管道骨架半现成（协议/占位符/上传/溯源已存在），断在 7 处接线；主路线=Z-Image Omni 原生 3 参考图（`TextEncodeZImageOmni`），IPAdapter 系仅覆盖 SD1.5/SDXL、与 DiT 栈不兼容，弃用。

- **M1 参考图管道接线（进行中，2026-08-31 开工）**：关断点 1/2/3/6——worker 读 CHARACTER_REFERENCE 溯源行构建 `ImageRequest.reference_images` / comfyui provider `upload_image()` 接入生产流 / 新模板 `workflows/zimage_turbo_ref.json`（LoadImage×3 + Omni image1/2/3，drop-in 注册）/ WorkflowSchema `$REFERENCE_IMAGE_1..3`；`GenerationCreate.reference_asset_ids` 显式覆盖 + `INPUT_ROLES` 常量修正 + mock E2E。验收：mock 请求携带 reference_images；comfyui upload→mapper 注入单测；pytest 全绿 + 真实 ComfyUI 冒烟 1 张带参考图。
- **M2 多参考图数据模型**：`character_version_assets` 表（role: FACE/BODY/FRONT/SIDE/EXPRESSION/STYLE，Alpha 设计 §30-31）+ 迁移 + ReferenceResolver role 优先级（缺 face 回退版本代表图，上限 3 张=Omni 限制）+ EntityVersionBlock 多图管理 UI。验收：角色版本挂多图标 role；生成自动按优先级取 ≤3 张；pytest + vitest 全绿。
- **M3 相似度评分 harness**：DINOv2 为主（风格化角色，无许可坑）、ArcFace 为辅（仅写实角色）；离线 harness（`backend/scripts/consistency_eval.py`，不入生成主路径）+ 阈值校准报告 + feature flag 提示 UI。**Value Gate**：≥20 真实 Scene 问题样本 + 人工基线；产品内只提示不拦截（与 P4-E4-T01「默认不自动重生成」红线一致）。验收：Value Gate 达标；harness 在人工基线上区分度达预设阈值。
- **M4 引擎扩展与 Review Loop（Phase 2）**：Z-Image-Edit / Omni-Base 模板 A/B（Turbo 蒸馏版参考图遵循度不达标时的备选）、LoRA 试点（主力角色长期复用）、ReActor 兜底评估（关键特写）、Review Loop 集成（P4-E4-T01）、prompt 拼装（P2-E4-T02）、云端参考图 provider。验收：按 backlog Value Gate 逐项立项。

依赖：M1 无前置（纯接线）；M2 ← M1；M3 与 M1/M2 并行（产品化依赖 M1 产出）；M4 ← M1-M3 结论。
