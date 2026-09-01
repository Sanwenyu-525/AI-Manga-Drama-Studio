# FULLSTACK_INTEGRATION_REPORT.md — 全栈联调修复与验证报告（2026-08-31）

> 审计输入见 [FULLSTACK_INTEGRATION_AUDIT.md](FULLSTACK_INTEGRATION_AUDIT.md)。
> 本报告记录实际执行的修复、联调验证与遗留事项。

---

# Executive Summary

针对审计发现的 **4 个 P0 + 6 个 P1** 契约断点完成全部修复（零 Breaking Change），并新增 **live HTTP 全链路 smoke（14 步）**：从 health → 建项目 → 剧本分析（快照确认 0.0s）→ AI 分镜 → 图片生成（含双击 409 幂等验证）→ 媒体访问 → 时间线排片 → 配音（audio/wav）→ 渲染成片（2.8MB FINAL_VIDEO）→ 下载 → 契约路由验证，全部真实 HTTP 执行通过。

**验证汇总**：后端 pytest 568 通过 / 1 偶发（隔离复跑通过，与本次改动无关）+ ruff 全绿；前端 vitest 242（含新增 mediaUrl 回归测试）/ tsc / eslint / production build 全绿。

**全栈联调成熟度评价：Good**。主链路（UI → API → Service → DB → Provider → Task → Asset → Preview → Download）已形成真实闭环；扣分项：视频真实链路本次未 live 复验（mock 为 fail-fast 占位）、AI Director 刷新恢复为已知限制。

# Integration Status

| 集成面 | 状态 | 说明 |
|---|---|---|
| REST 契约（163 调用点 × 168 operations） | **对齐** | 4 处不一致已修复；其余方法/路径/参数/DTO/状态码逐条核对 |
| 枚举/状态机 | **对齐** | Generation 9 态、Agent/Proposal/Pipeline/Timeline 全一致；provider status 补 unavailable |
| 时间格式 | 对齐 | ISO 8601 UTC 字符串端到端统一 |
| Null/undefined | 对齐 | DTO Optional ↔ 前端 `\| null` + 兜底 |
| 错误信封 | 对齐 | `{error:{code,message,details,request_id}}` 全端统一；路由级 404（NOT_FOUND）与实体级 404（ENTITY_NOT_FOUND）可区分 |
| 鉴权边界 | **修复后对齐** | REST header / 媒体 `?token=` / WS `?token=` 三通道全部打通 |
| 任务链路（202+轮询+WS） | 对齐 | 幂等门 409 live 验证；轮询补失败上限 |
| 缓存同步（WS invalidate） | 对齐 | commit-then-publish + invalidate，无直写 cache |

# Main Flow Status

| 链路 | 状态 | 验证方式 |
|---|---|---|
| Project（创建/编辑/删除/封面） | **PASS** | live smoke 步骤 4 + pytest test_api / test_project_cover_delete |
| Script（导入/保存/AI 分析） | **PASS** | live smoke 步骤 5（preview→快照 confirm 0.0s，2 scenes） |
| Character（CRUD/版本/关联） | **PASS** | pytest test_characters / test_character_versions / test_agent_ownership（live smoke 未单独走角色 CRUD，后端契约全绿） |
| Scene（创建/编辑/分镜聚合） | **PASS** | live smoke 步骤 5-6 |
| Storyboard（AI 分镜/编辑/绑定） | **PASS** | live smoke 步骤 6（6 shots） |
| Image（生成→资产→版本→激活→缩略图） | **PASS** | live smoke 步骤 7-8（mock provider；真实引擎见 Sprint 04 报告 40 张对跑） |
| Video | **NOT VERIFIED（本次 live）** | video.mock 为 fail-fast 占位（capability=False 设计如此）；真实 agnes 链路有 pytest（test_provider_contract）+ P4-E3-T01 历史验证，未消耗配额复验 |
| Audio（配音→WAV 资产→试听） | **PASS** | live smoke 步骤 10（audio/wav 真实下载） |
| Render/Export（渲染→FINAL_VIDEO→下载） | **PASS** | live smoke 步骤 11（mock 渲染器 2.8MB 可播放 AVI；ffmpeg 真实 MP4 见 P9 live E2E 记录） |
| Download（content/thumbnail） | **PASS** | live smoke 步骤 8/11（字节级下载 + Content-Type 校验） |

# API Issues Fixed

| 问题 | 修复 |
|---|---|
| `POST /agent/continuity/runs` 后端不存在 → AI 修复按钮死路 | [ContinuityWarningList.tsx](../../frontend/src/features/continuity/ContinuityWarningList.tsx) 改调真实契约 `POST /agent/continuity/fix` `{warning_id, patch:{}}`（按行 warning 触发修复 run，WAITING_HUMAN 审批）；补 onError 反馈 |
| 资产筛选 `?type=` vs 后端 `asset_type` | [useProjectAssetLibrary.ts](../../frontend/src/features/assets/useProjectAssetLibrary.ts) 参数名改为 `asset_type` + 契约注释 |
| `mediaUrl` 双 `?` 拼接 | [mediaUrl.ts](../../frontend/src/lib/mediaUrl.ts) 路径已含 query 时用 `&` 追加 token（修复时间线预览壳内 401 + v 参数污染） |
| 项目封面未带 token | [ProjectHome.tsx](../../frontend/src/features/project/ProjectHome.tsx) 封面 src 经 `mediaUrl()` 包裹（修复壳内 401 破图） |

# Request / Response Issues Fixed

| 问题 | 修复 |
|---|---|
| 前端消费 `item.name`/`item.source_type` 但列表 DTO 不返回 | [domain/asset.py](../../backend/app/domain/asset.py) `AssetListItemRead` 增量补 `name`/`source_type` + [api/assets.py](../../backend/app/api/assets.py) 映射（additive，恢复资产浏览器来源分组/MASTER 徽章/真实名称） |

# Enum / Type Issues Fixed

| 问题 | 修复 |
|---|---|
| Provider 状态缺 unavailable 中文标签与状态色 | [SettingsPage.tsx](../../frontend/src/features/settings/SettingsPage.tsx) STATUS_LABELS 补 `unavailable: "不可用"`；[styles.css](../../frontend/src/styles.css) 补 `.provider-dot.unavailable` 红点 |

# Task Integration Fixes

| 问题 | 修复 |
|---|---|
| operation 轮询无限重试（后端重启/断网 → 按钮永久 pending） | [useOperationPolling.ts](../../frontend/src/features/ai/useOperationPolling.ts)：连续失败上限 10 次；404（operation 丢失）3 次后快速失败；放弃时经 onError 回调合成可读错误（`error: string`，与全部调用方消费形态一致），解除按钮卡死 |
| TimelineView 创建时间线/一键排片失败静默 | [TimelineView.tsx](../../frontend/src/features/timeline/TimelineView.tsx) 合并错误面板（createTimeline/sequence/render 任一失败即显示）；顺带移除 `as never` 类型断言 |

# Provider Integration Fixes

- **无假连接**：连接状态全部来源于后端真实 registry/健康检查（live smoke 步骤 2 验证 image.mock=connected、video_mock=unavailable 诚实降级）。
- API Key 安全复核：config 读取只返回 `api_key_set`/`api_key_hint` 掩码；PUT 不回传未改 key；日志无泄漏（沿用既有审计结论，本次未引入新暴露面）。
- Provider 配置链（Settings → 保存 → 测试 → 模型 → 生成）：live smoke 步骤 3 验证 config 读写实配一致。

# File / Download Fixes

- 文件访问策略确认为「API 相对路径 + 统一 `/assets/{id}/content|thumbnail` 出口」，无静态目录挂载、无绝对磁盘路径外泄；FileResponse 原生支持 Range（视频拖动）。
- 本次修复 2 处媒体标签 token 透传断点（封面 + 时间线预览，见 API Issues Fixed）。
- 下载按钮（`<a download>` 同源）经 live 下载验证可用。

# Error Handling Fixes

- Continuity 修复失败、轮询失败、时间线创建/排片失败：从"静默"提升为可见错误（见上各节）。
- 既有优点确认：409 乐观并发在 ShotInspector/EpisodePanel/TimelineView 均有 invalidate + 用户可读提示；统一错误信封携带 request_id 可复制追溯。

# State Synchronization Fixes

- ShotContinuityCard 冗余 `GET /shots/{id}` 请求随 sceneId prop 移除而删除（修复调用语义变化的副产品）。
- 既有优点确认：WS 事件 → query invalidate 映射完整（35+ 事件类型）；断线重连 reconcile 全量失效；序号 gap 检测触发对账。

# Performance Fixes

- 本次无性能型修复（资产列表/导入的流式与原子写已由后端优化轮交付）；删除 1 处冗余请求（见上）。

# Tests Added / Updated

| 测试 | 类型 | 内容 |
|---|---|---|
| `frontend/src/__tests__/mediaUrl.test.ts` | 新增（vitest） | token 附加策略 4 例：无 token 原样 / 无 query 加 `?` / **已有 query 加 `&`（双 `?` 回归）** / assetUrl 组装 |
| `continuityUi.test.tsx` AI 修复用例 | 更新 | 断言改为 `/agent/continuity/fix` + `{warning_id, patch}`（原用例固化了错误契约） |
| `backend/tests/test_asset_browser.py` | 更新 | 列表形状断言补 `name`/`source_type` + imported 来源语义 |
| `backend/scripts/smoke_fullstack.py` | 新增（live smoke） | 14 步全链路（见 Executive Summary）；含幂等 409、legacy `?type=` 参数不生效的对照断言、路由级 vs 实体级 404 区分 |

# Files Changed

前端（11 文件 + 1 新增测试）：
[mediaUrl.ts](../../frontend/src/lib/mediaUrl.ts)、[ProjectHome.tsx](../../frontend/src/features/project/ProjectHome.tsx)、[useProjectAssetLibrary.ts](../../frontend/src/features/assets/useProjectAssetLibrary.ts)、[ContinuityWarningList.tsx](../../frontend/src/features/continuity/ContinuityWarningList.tsx)、[SceneWarningBadge.tsx](../../frontend/src/features/continuity/SceneWarningBadge.tsx)、[ShotContinuityCard.tsx](../../frontend/src/features/continuity/ShotContinuityCard.tsx)、[RailWorkspacePages.tsx](../../frontend/src/features/navigation/RailWorkspacePages.tsx)、[SettingsPage.tsx](../../frontend/src/features/settings/SettingsPage.tsx)、[useOperationPolling.ts](../../frontend/src/features/ai/useOperationPolling.ts)、[TimelineView.tsx](../../frontend/src/features/timeline/TimelineView.tsx)、[styles.css](../../frontend/src/styles.css)、[__tests__/continuityUi.test.tsx](../../frontend/src/__tests__/continuityUi.test.tsx)、`__tests__/mediaUrl.test.ts`（新）

后端（2 文件 + 1 新增 smoke）：
[domain/asset.py](../../backend/app/domain/asset.py)、[api/assets.py](../../backend/app/api/assets.py)、[tests/test_asset_browser.py](../../backend/tests/test_asset_browser.py)、`scripts/smoke_fullstack.py`（新）

# Breaking Changes

**NO**。唯一后端变更为 `AssetListItemRead` **增量**字段（name/source_type）；唯一接口变更（continuity/fix）是把前端从不存在的端点迁回已存在端点；`ContinuityWarningList` 的 `sceneId` prop 为组件内部接口（3 处调用方同仓同步更新，非对外契约）。

# Remaining Issues

- P2 清单（7 项，见审计报告 §Integration Problems P2）：契约文档补 `agent.run.cancelled` 事件、死状态映射清理、手写 queryKey 收敛、`?download=1` 强制下载变体、thumbnail MIME 精确化、check-missing 前端入口。
- `test_generation_atomicity` 全量套件下 1 例 provider_ref 时序偶发（隔离通过；建议后续在测试内对 provider_ref 断言加轮询重试）。

# Known Limitations

1. **AI Director 刷新恢复**：agentStore 纯内存，刷新后对话流/工具进度丢失（提案经 server query 可恢复）；后端无消息持久化端点，完整恢复需新契约，超出本次最小修复范围。
2. **Video live 复验**：mock 为设计内 fail-fast 占位；真实 agnes 视频链路未在本次消耗配额复验（历史验证 + 单测覆盖契约）。
3. **operation store 为内存态**：后端重启后未完成 operation 不可恢复（前端现会诚实报错并提示重新发起，而非无限等待）。
4. ComfyUI/Agnes 真实引擎质量（首可用率、prompt 命中率）属产品运营指标，不在联调审计范围（见 real-chain-validation-report）。

# Recommended Next Steps

1. **契约防回归**：将「前端调用点 → 后端 OpenAPI」比对固化为 CI 检查（可从 OpenAPI 生成前端类型或写脚本断言 163 调用点路径全部存在于 openapi.json）——本次 4 个 P0 中 3 个可被此检查拦截。
2. **Tauri 壳内媒体回归**：smoke 已覆盖 HTTP 层 token；建议补一条壳内（session token 启用）的浏览器级 E2E，把 `<img>/<video>` 401 类问题（本次 P0-3/P0-4）纳入自动防线。
3. agent run 消息持久化 + 刷新恢复（需新端点，建议随多 Agent 阶段一并设计）。
4. P2 清单按需清理（多为文档同步与死代码）。
