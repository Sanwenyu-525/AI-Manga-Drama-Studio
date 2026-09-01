# PRODUCT_OPPORTUNITY_BACKLOG.md — 产品机会统一台账

> 自主产品迭代 Agent 的唯一机会登记处（Post-MVP）。每轮 Discovery 后更新；
> 开发完成后 Doing → Done，新发现进 Candidate，不做功能垃圾场——
> 每轮只选 1 个主题，且必须记录 Why This / Why Now / Why Not Others。
>
> 评分 1-5（越高越好）；Dev Cost / Technical Risk 越低越好。Priority：
> P0 = 核心流程断点 / P1 = 高频重复与高价值 / P2 = 战略增强 / P3 = 打磨。

## 本轮进行中

（无——自主迭代 02 已收口至 Done；下一轮 Discover → Prioritize 后在此登记）

## Candidate（候选池）

| Opportunity | Source | User Problem | Proposed Solution | UV | Freq | Diff | Cost | Risk | Dep | Priority | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| recent / change-sets 分页 | 后端报告建议 #2 + 代码扫描（20/100 条静默截断） | 长项目生成历史与变更记录丢失 | 两端点补 limit/offset + 前端加载更多 | 3 | 3 | 2 | 1 | 1 | 无 | P1 | Candidate |
| M2 多参考图数据模型 | P3 预研 §6 | 单张 MASTER 代表图覆盖不了多角度/服装/表情 | `character_version_assets`（role: FACE/BODY/SIDE/EXPRESSION/STYLE）+ ReferenceResolver 优先级 | 5 | 4 | 4 | 4 | 2 | M1 用户验证 | P2 | Candidate |
| M3 相似度评分 harness | P3 预研 §6 | 生成后无法量化角色一致性回归 | 离线 DINOv2 harness + 人工基线校准 + 提示型 UI（只提示不拦截） | 4 | 2 | 4 | 4 | 3 | ≥20 问题样本 | P2 | Candidate |
| 生成队列策略可配置 | SettingsPage.tsx:455（超时/重试暂未开放配置） | max_attempts/backoff 无法按项目调整 | 设置页生成策略区 + env 覆盖 | 2 | 2 | 1 | 2 | 1 | 无 | P3 | Candidate |
| OperationStore 最小持久化 | 后端报告建议 #3 | 重启丢 analyze/导入进度句柄 | shot-planning/model_import 两类 operation 落库 | 2 | 1 | 1 | 2 | 2 | 无 | P3 | Candidate |
| 项目软删资产 GC | 后端报告建议 #4 | 删项目后媒体文件残留磁盘 | 显式「删除项目文件」入口 + 确认 | 2 | 1 | 1 | 2 | 2 | 无 | P3 | Candidate |
| Agnes 下载流式化 | 后端报告 P2-8 | 大文件下载整载内存 | `client.stream` + 大小上限 | 2 | 2 | 1 | 1 | 1 | 无 | P3 | Candidate |
| P8-E2 连续性规则补全 | 代码扫描（placeholder 语义） | 部分规则未真实生效 | 按规则逐条落地 + 测试 | 3 | 2 | 2 | 3 | 2 | 无 | P2 | Candidate |
| SettingsPage 1927 行拆分 | 前端优化报告 P1-8（拆分边界已定） | 设置页巨石文件 + 三卡重复 saved/touched/error 状态机，维护与测试成本高 | 按 SettingsChrome / 五卡 / TestResultView / useProviderForm 边界拆分，同步迁移 2 个测试文件 | 2 | 2 | 2 | 2 | 1 | 无 | P2 | Candidate |
| 契约防回归 CI（调用点→OpenAPI 比对） | 全栈联调报告建议 #1 | 契约断点类 P0（本轮 3/4 个）无自动防线，靠人工联调发现 | 脚本断言前端 163 调用点全部存在于 openapi.json（或 OpenAPI 生成前端类型），纳入 CI | 3 | 3 | 2 | 2 | 1 | 无 | P1 | Candidate |
| Tauri 壳内媒体 E2E | 全栈联调报告建议 #2 | `<img>/<video>` token 401 类问题只在壳内出现，HTTP smoke 无法覆盖 | session token 启用下的壳内浏览器级 E2E 主链路一条 | 3 | 2 | 3 | 3 | 2 | 无 | P2 | Candidate |
| 镜头级地点覆盖（多地点场景） | 自主迭代 03 复盘（shot_visual_spec.location_id 已存在） | 一场多地点时无法为单镜头指定不同地点 | ReferenceResolver 支持 shot 级 location 覆盖（shot_visual_spec.location_id 优先于 scene） | 3 | 2 | 2 | 2 | 1 | 无 | P3 | Candidate |
| 就绪度缺口一键跳转细化 | 自主迭代 04 复盘 | 就绪度卡片跳转落点在模块首页而非具体缺口（未绑定场景列表） | readiness 返回缺口 scene_id 列表 + 前端直达分镜；或「未绑定场景」列表页 | 2 | 2 | 1 | 2 | 1 | 无 | P3 | Candidate |
| 产出覆盖纳入就绪度（视频/音频） | 自主迭代 04 复盘 | 就绪度只覆盖一致性（角色/场景/连续性），不含视频/音频产出缺口 | 扩 ReadinessRead：per-episode 视频/配音覆盖（复用 workspaceMetrics 的 imageReady 思路） | 3 | 2 | 2 | 2 | 1 | 无 | P2 | Candidate |
| AI Director update_scene 工具 | 自主迭代 06 复盘 | 用户想「把这场戏改成夜晚」只能手动编辑，Agent 无法提案场景级修改 | Agent 新增 update_scene 工具（走既有 Proposal/风险分级/ChangeSet 流，场景字段白名单） | 3 | 2 | 3 | 3 | 2 | 场景编辑 UI | P2 | Candidate |
| 场景批量环境应用 | 自主迭代 06 复盘 | 多场景统一改时段/光照需逐场景编辑 | 批量选择场景 → 统一 PATCH 环境字段（复用 batch 逐项结果模式） | 2 | 2 | 1 | 2 | 1 | 无 | P3 | Candidate |

## Done（已完成轮次）

| Opportunity | 轮次 | 交付物 |
|---|---|---|
| **场景信息编辑（Scene Properties：时段/光照/天气/氛围/描述 → 连续性重算/stale）** | **2026-09-01（自主迭代 06）** | **见 `docs/reports/autonomous-iteration-2026-09-01-scene-properties-edit.md`** |
| **AI Director 刷新恢复（消息转录 + 最近会话列表 + 前端水合）** | **2026-09-01（自主迭代 05）** | **见 `docs/reports/autonomous-iteration-2026-09-01-agent-refresh-recovery.md`** |
| **生产就绪度（角色 MASTER / 场景地点绑定 / 连续性警告缺口，生成前可见；含原「地点覆盖健康度」候选）** | **2026-09-01（自主迭代 04）** | **见 `docs/reports/autonomous-iteration-2026-09-01-production-readiness.md`** |
| **场景一致性闭环（地点库 + 场景绑定 + 生成注入地点参考图）** | **2026-09-01（自主迭代 03）** | **见 `docs/reports/autonomous-iteration-2026-09-01-location-consistency.md`** |
| 镜头多选批量操作（多选态 + BatchActionBar + 批量端点 + allSettled 聚合） | 2026-09-01（自主迭代 02） | 见 `docs/reports/autonomous-iteration-2026-09-01-batch-shot-operations.md` |
| （M1 前端闭环） | 2026-08-31 | 见 `docs/reports/autonomous-iteration-2026-08-31-refimages.md` |
| 后端定点优化（P0×2 + P1×8，审计轮） | 2026-08-31 | 见 `BACKEND_OPTIMIZATION_REPORT.md`（建议 #1 已并入 M1 轮；#2/#3/#4 见候选池） |
| 前端定点优化（P0×5 + P1×9，含 Tauri 媒体 401 修复；审计轮） | 2026-08-31 | 见 `docs/reports/FRONTEND_OPTIMIZATION_REPORT.md` |
| 全栈联调修复（4 P0 + 6 P1 + live smoke 14 步；审计轮） | 2026-08-31 | 见 `docs/reports/FULLSTACK_INTEGRATION_REPORT.md` |

## Rejected（明确不做 / 降级理由）

| Opportunity | 理由 |
|---|---|
| 社区 / Feed / IM / 插件市场 / 模板商城 / 大型协作 | 与「个人创作者低成本完成质量稳定的 AI 漫剧」核心目标无关（Feature Creep 警戒清单） |
| IPAdapter / InstantID / PuLID-Flux 路线 | 与本项目 DiT 栈不兼容（P3 预研 §4.1 已论证） |
| Agent 工具暴露 reference_asset_ids 参数 | Service 自动解析已覆盖；显式覆盖留 API 层调试用（P3 预研 §7 开放问题 2） |
| AssetPicker/VersionPicker 统一抽象 | 五处业务语义不同（版本激活/素材替换/MASTER 设定），需先收敛 `deriveVersionBadges` 到单一出处再谈抽象（前端优化报告 P2，Phase 2 前置调研项） |
