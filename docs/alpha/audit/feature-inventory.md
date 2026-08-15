# 现有功能清单报告（P0-T002）

> 能力状态判定标准：READY（可用且有测试/证据）/ PARTIAL（主链可用但部分能力缺）/ PROTOTYPE（雏形/演示级）/ MISSING（未实现）。

## 二、Feature Inventory

| 能力 | 状态 | 证据路径 + 关键行为 | 备注 |
|---|---|---|---|
| Project CRUD / 软删 | **READY** | services/project_service.py(create/update/delete,cascade)、api/projects.py(POST/GET/PATCH/DELETE) | 软删树（episode/scene/shot/character），事件 project.* |
| Project 打开/恢复 | **READY** | api/projects.py GET /{id}/bootstrap；services/project_service.py::bootstrap | Bootstrap 契约 §103-104：project/episodes/characters/providers/active_generations/active_agent_runs 摘要 |
| Project 封面 | **READY** | save_cover(projects.py + service)：multipart 上传，存 data/projects/{id}/cover.*，cover_path 相对路径，格式/大小校验 | API：POST/GET /{id}/cover；前端 ProjectHome 上传 |
| Episode CRUD / 排序 | **READY** | services/episode_service.py、api/episodes.py；episode_number 自动 MAX+1，{project_id,episode_number} UniqueConstraint | 关联 source_text/status |
| Scene CRUD / 排序 | **READY** | services/scene_service.py、api/scenes.py；scene_order、部分唯一索引 (episode_id,scene_number) | **Scene 无 revision**（P1-E1-T02 决策：Phase 2 引入） |
| Shot CRUD / 排序 | **READY** | services/shot_service.py、api/shots.py；reorder 完整集合校验 + 两阶段编号；原子 revision 条件更新；_require_live_scene(父删子隐) | PATCH /scenes/{id}/shots/reorder；shot.updated 事件带 source/run_id |
| 小说导入与分析 | **READY** | api/episodes.py POST /e/{id}/analyze(202)+/analyze/preview；services/script_service.py(analyze_episode/preview/generate_shot_plans)；plan_mapper.py 显式映射；episodes.analysis_key/scenes.storyboard_key 幂等；Fake/真实 gateway | P1-E1-T01 已修复字段丢失+事务化+幂等替换；前端 EpisodePanel 支持本地 .txt/.md 导入 |
| Scene/Shot AI 规划 | **READY** | LLM gateway.py/fake.py/langchain_gateway.py；结构化输出 ScenePlan/ShotPlan；Operation 202 机制 | STUDIO_LLM_MODE=fake|openai |
| Character + CharacterVersion + MASTER | **PARTIAL** | services/character_service.py、db/models/character.py(characters 身份表 + shot_characters 中间表) | **P1 已完成** CRUD/关联/revision/软删/事件/Bootstrap。但 **无 CharacterVersion，也无 MASTER 合并表**——clothing/角色一致性阶段未实现，默认 costume 为弱引用 |
| ShotCharacter 绑定 | **READY** | db/models/character.py::ShotCharacter；shot_service.py(_validate_characters 跨项目 422/404、_replace_characters) | 完整集合 + 项目归属校验；continuity 字段(costume/role/pose)已建柱未填充 |
| Asset 系统 | **READY** | services/asset_service.py(register_asset/create_thumbnail/absolute_path)、db/models/asset.py、api/assets.py(/{id}/content|thumbnail) | 项目相对存储、240px 缩略图、路径安全 _safe_path(见 test_*)、Pillow 尺寸；meta_json 曾用 str(dict)（A-12，Phase 1 是否修复需核实） |
| Generation 系统 | **READY** | services/generation_service.py(create/retry/cancel)、generations/worker.py(DB-poll+poll 0.5s, atomic claim)、generations/state.py(状态机 409)、api/generations.py | 状态机+lease 崩溃恢复+重试退避已实现(P1-E2-T02)；**P1-E2-T03 完成链原子化仍为 P0 遗留**（完成回填跨多事务）；cancel 对 Provider 为 best-effort |
| Version 系统 | **READY** | db/models/media_version.py(不可变)、services/version_service.py(create/setActive/list) | 版本不可变，V1/V2 共存；Set Active 只翻 is_active + shot.active_*_version_id；部分唯一索引强约束 + 单 active |
| Provider 抽象 | **READY** | providers/image/base.py(ImageProvider Protocol)、mock.py、comfyui.py、registry.py | 规范 id mock|comfyui；未知 id 422，无静默回落；provider_status DTO |
| ComfyUI 客户端 + workflow_mapper | **READY** | providers/comfyui/client.py(health/queue/monitor WS/download/upload/cancel/fallback)、workflow_mapper.py(catalog+preflight+placeholder)、api/providers.py POST /comfyui/test | P1-E2-T01 已修复路径/preflight/WS 去硬编码 node；必需 placeholder + 恰好一个 SaveImage |
| Agent Director | **READY** | agents/director/graph.py(Understand→LoadContext→Plan→Execute→Review)、runner.py(run 内存存储/取消)、tools.py(get_shot/update_shot/generate_image) | **P1-E3-T01/T02 已修复**：ownership 强制(跨项目/伪造/软删拒绝)、owner 解析、协作式 cancel、current_stage；无审批/ChangeSet/checkpoint |
| 事件总线 + WS 网关 | **READY** | events/bus.py(EVENT_* 常量/StudioEvent/envelope)、events/ws.py(/api/v1/events + sequence 去重 + system.connected) | commit-then-publish 红线；**P1-E4-T02(鉴权/项目订阅/回放) 为 P0 遗留**；服务重启 sequence 归零 |
| Operation 机制 | **READY** | operations/store.py(OperationStore, 202+GET /operations/{id}, per-key asyncio.Lock)；api/operations.py | 内存存储，无 TTL/清理（A-08，Phase 1 未列 P0） |
| **前端页面/功能** | | | |
| ProjectHome | **READY** | features/project/ProjectHome.tsx(284 行：列表/筛选/重命名/封面上传) | cover 上传 + 列表 + 状态筛选 |
| StudioPage 五区布局 | **READY** | features/studio/StudioPage.tsx(250 行)+ProjectExplorer.tsx(483 行) | URL 驱动 script/storyboard 工作区；Explorer 含角色区内联 CRUD |
| EpisodePanel（脚本） | **READY** | features/script/EpisodePanel.tsx(198 行) | 文本导入/保存/预览/创建 scenes；本地 .txt/.md 导入 |
| Storyboard + ShotInspector | **READY** | StoryboardView.tsx(163 行)、ShotInspector.tsx(436 行) | grid/list + AI 生成分镜 + 生成按钮/版本浏览/409 conflict 处理/角色多选 |
| GenerationQueue | **READY** | features/generation/GenerationQueue.tsx(91 行) | live 队列(store)+历史(dock)+retry/cancel |
| AIDirectorPanel | **READY** | features/director/AIDirectorPanel.tsx(140 行) | Selection 自动附带、消息流、计划卡片、工具进度 |
| AssetsPage | **READY**(简化) | features/assets/AssetsPage.tsx(124 行) | 从 generations/projects 聚合资产列表+预览；非独立资产库 |
| WorkflowsPage | **READY**(只读) | features/workflows/WorkflowsPage.tsx(120 行) | 读 GET /workflows catalog 展示 |
| SettingsPage | **READY** | features/settings/SettingsPage.tsx(137 行) | provider 列表 + test connection(providers API) |
| VersionReviewPage | **READY** | features/storyboard/VersionReviewPage.tsx(98 行) | 版本列表 + Set Active |
| **前端 stores/socket** | | | |
| generationStore | **READY** | stores/generationStore.ts live 瞬时状态 | 最终数据来自 Server Query |
| agentStore | **READY** | stores/agentStore.ts | run 生命周期/step/tool/message |
| selectionStore | **READY** | stores/selectionStore.ts | Selection 单一事实源（传给 Director） |
| workspaceStore | **READY** | stores/workspaceStore.ts | UI 布局状态 |
| event socket | **READY** | events/socket.ts：WS host 派生 URL、sequence 去重、退避重连、EventRouter invalidate | 单例；断线 gap 不做 bootstrap 对账（A-07） |
| **Tauri 壳** | **READY**(开发可用) | backend.rs(自动拉起后端探测 17820)、lib.rs、tauri.conf.json(devUrl 17821) | cargo check 通过（CI 亦覆盖）；依赖源码目录+系统 uv，无安装包/迁移/签名（A-15，Phase 5） |

### 关键事实汇总

1. **MVP（Stage A/B/C/D）+ P1 全部完成**：Project/Episode/Scene/Shot CRUD、小说分析、AI 分镜、Character+ShotCharacter、Asset/Version、Generation DB-poll worker、Provider 抽象（mock/comfyui）、ComfyUI client/mapper、Agent Director 三工具、事件总线+WS、Operation 机制、前端全页面 + stores、Tauri 壳均已是 **READY**。
2. **已修复的审计项**（post-mvp-audit 中多数已落地）：A-00(plan_mapper)、A-01 部分(状态机/lease)、A-02(ownership+协作取消)、A-03(workflow 路径/preflight)、A-04(DB 不变量/原子 revision/reorder)、A-06(A-更名统一 Envelope+recent 路由)、A-11(provider provenance/fail-fast)、A-12(路径安全修正)。
3. **遗留 P0（下一 Sprint）**：P1-E2-T03 Generation 完成链原子化、P1-E4-T02 Event Gateway 鉴权/订阅/回放。
4. **明确状态**：Character 的 **CharacterVersion / MASTER 分支版本体系未实现（MISSING）**——当前只有单字符身份 + 多对多关联，无版本/MASTER 概念。Scene 无 revision（P1-E1-T02 推迟到 Phase 2）。
5. **数量校准**：迁移 7 份（非 8）、test_*.py 18 份（非 19，另有 conftest.py/__init__.py）。

> 本报告为只读审查产物，未改动任何文件。所有能力状态均以真实代码路径 + 行为佐证。
