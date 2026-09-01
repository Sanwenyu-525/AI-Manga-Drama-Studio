# FEATURE_MAP.md — 产品能力地图

> 自主产品迭代 Agent 的功能事实源：什么已完成、什么只是骨架、什么是 Mock。
> 每轮迭代完成后更新，防止重复开发。状态图例：
> ✅ 完成（端到端可用） · 🔶 部分完成 · 🧪 Mock/实验 · ⬜ 未开始 · 🗑 已废弃

## 核心生产链（Project → Script → Character → Scene → Storyboard → Image → Video → Audio → Asset → Export）

| 模块 | 能力 | 状态 | 备注 |
|---|---|---|---|
| Project | 项目 CRUD / bootstrap / 软删除 | ✅ | |
| Script | 小说导入 / AI 分析（ScenePlan） / 分析快照（preview→confirm 零二次 LLM） | ✅ | 快照幂等 + 过期机制 |
| Script | 设定文档库（source_documents） / Tauri 本地导入 | ✅ | Agent 上下文注入设定文档 |
| Character | CRUD / revision 并发 / 软删除 / 出场关联 | ✅ | |
| Character | 参考图版本链（上传→版本→MASTER） | ✅ | EntityVersionBlock |
| Character | **生成参考图：预览 / 手动覆盖 / 无模式 / 溯源展示 / 能力警告** | ✅ | **2026-08-31 M1 前端闭环** |
| Location | **地点生产库（创建/编辑/删除 + 视觉版本链 MASTER + 关联设定文档）** | ✅ | **2026-09-01 自主迭代 03**（后端早已落地，本轮补前端入口） |
| Location | **场景一致性：场景绑定地点 + 生成自动注入地点 MASTER 参考图（角色优先·地点兜底）+ 预览/溯源区分** | ✅ | **2026-09-01 自主迭代 03**；活动栏「地点」模块 |
| Scene / Shot | CRUD / 排序 / revision / 软删除 | ✅ | |
| Storyboard | 聚合端点 / ShotCard / 面包屑导航 / 虚拟化网格 | ✅ | |
| Storyboard | 批量生成（当前/待生成/失败重生成/整场景） | ✅ | 场景粒度 |
| Storyboard | **镜头多选 + 批量操作**（Ctrl 切换 / Shift 范围选 / checkbox；批量生成·改景别·前移后移·删除；409 计入「进行中」聚合） | ✅ | **2026-09-01 自主迭代 02**；batch-update/batch-delete 端点 |
| Image | Generation 队列（DB-poll / claim+lease / 重试 / 崩溃恢复 / 幂等 409 门） | ✅ | max_attempts 默认 3 |
| Image | Provider：mock / agnes / comfyui（Z-Image-Turbo + 参考图模板） | ✅ | 参考图注入走 $REFERENCE_IMAGE_1..3 |
| Image | 版本不可变（V1/V2 共存 / active 切换 / 版本条 / 全屏审片 / 对比） | ✅ | |
| Video | Agnes 文生视频（4-12s） / 不可变视频版本 / active 切换 | ✅ | mock 为 fail-fast 占位 |
| Audio | 配音（mock WAV / edge-tts） / 整轨批量配音 / 试听 | ✅ | |
| Audio | 渲染混流（ffmpeg 混音+烧字幕 / mock AVI 有声有字幕） | ✅ | |
| Timeline | 四轨 / clip 编辑（拖拽/裁剪/转场） / revision 并发 / 撤销 / 排片 / 渲染导出 | ✅ | |
| Export | FINAL_VIDEO 不可变版本注册 / 下载 | ✅ | |
| Export | **产物下载 + 全屏预览**（DownloadButton ×5 处 / FINAL_VIDEO 下载成片 / 文件名自动推导 / 统一 Lightbox） | ✅ | **2026-08-31 前端优化轮** |
| Pipeline | 一键成片（analyze→shots→images→timeline→render 断点续跑） | ✅ | |

## Agent / AI 层

| 能力 | 状态 | 备注 |
|---|---|---|
| AI Director（LangGraph 五节点 / Structured Planner + Deterministic Executor） | ✅ | |
| 三工具（get_shot / update_shot / generate_image） | ✅ | |
| Proposal 审批流（R0-R3 风险分级 / TTL 过期 / approve+conflict） | ✅ | R1 自动执行+ChangeSet |
| ChangeSet / Undo（补偿变更链 / 批量撤销 / 409 恢复） | ✅ | |
| Agent Run 持久化 + SQLite Checkpointer + resume | ✅ | |
| AI Director 刷新恢复（对话流/工具进度） | 🔶 | agentStore 内存态，刷新丢失；提案可经 server query 恢复（候选池：消息持久化） |
| Continuity 引擎（两表 + 8 规则 + 警告 + Agent check/fix + 前端） | 🔶 | 部分规则为 placeholder 语义（P8-E2 未全落地） |
| 一致性相似度评分（M3） | ⬜ | 依赖样本基线（Value Gate） |
| 多 Agent | ⬜ | Post-MVP 远期 |

## 基础设施 / DX

| 能力 | 状态 | 备注 |
|---|---|---|
| 事件总线 + WS 网关（envelope+sequence） | ✅ | |
| 本地会话 token / Origin 白名单 / CSP | ✅ | REST header / 媒体 `?token=` / WS `?token=` 三通道打通（mediaUrl.ts 单一事实源） |
| 启动配置校验（production 拒 fake/mock） | ✅ | fail-closed |
| correlation_id 日志链路 | ✅ | request/gen 级（contextvar + 中间件 + worker） |
| 生成重试预算接通（STUDIO_GENERATION_MAX_ATTEMPTS） + 幂等 409 门（in-flight 查重） | ✅ | 后端优化轮；pipeline resume 容忍 409 |
| 生成队列状态表达（queued/running/…五态可区分 + 错误中文映射） | ✅ | friendlyGenerationError，原文保留 tooltip |
| mutation 错误反馈全覆盖（~15 处 ApiErrorPanel） | ✅ | 前端优化轮；含 operation 轮询失败上限（10 次 / 404 快速失败） |
| LLM Profiles / 图像引擎配置 / ComfyUI 模型目录 | ✅ | |
| live 全链路 smoke（14 步：建项目→分析→分镜→生成→配音→渲染→下载） | ✅ | backend/scripts/smoke_fullstack.py |
| 测试基线 | ✅ | pytest 623（1 skip，1 例既有 flaky 单跑通过）/ vitest 285 |

## 已知未闭环（详见 PRODUCT_OPPORTUNITY_BACKLOG）

- recent/change-sets 分页（⬜） · M2 多参考图 role 化（⬜）
- OperationStore 持久化（⬜） · 项目资产 GC（⬜）
- 契约防回归 CI（⬜，P1） · Tauri 壳内媒体 E2E（⬜） · AI Director 刷新恢复（🔶） · SettingsPage 拆分（⬜）
