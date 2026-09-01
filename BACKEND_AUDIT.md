# BACKEND_AUDIT.md — AI Manga Drama Studio 后端全面审计（2026-08-31）

> 审计范围：`backend/app` 全量（35 Service / 27 API 模块 / Provider 体系 / 任务系统 / 存储 / 安全）。
> 方法：4 路并行深扫（Provider / Task / API / Storage-Security）+ 关键文件人工核对。
> 原则：只找真问题；不盲目重构；不破坏 API Contract 与 DB Schema。

---

# Architecture

```
UI → FastAPI Router (api/) → Service (services/) → Repository/Domain → SQLite (WAL)
                                  ↑
        Agent (agents/, LangGraph) ┘ 只调 Service
        GenerationService → Provider Interface → ComfyUI / Agnes / Mock
        Worker (generations/worker.py) DB-poll 轮询，generations 表即队列
        Scheduler (jobs/scheduler.py) 多步 Job DAG
```

- 分层红线整体执行良好：Router 薄、SQL 不在 Agent、事件 commit-then-publish、版本不可变。
- Provider 走 `typing.Protocol` + registry 惰性单例 + 运行时配置解析，业务层无 provider 硬编码分支（1 处例外，见 P1-8）。

# Current Modules

| 模块 | 目录 | 评价 |
|---|---|---|
| API | `app/api/`（27 文件） | 20+ 文件薄委派合规；个别违规（见 P1-4/5） |
| Domain/DTO | `app/domain/` | 全 Pydantic，无 ORM 直返 |
| Service | `app/services/`（35 个） | 边界清晰，无 God Service；最大 worker.py ~1500 行但职责单一 |
| Provider | `app/providers/`（image/video/audio/render/workflow/comfyui）+ `app/llm/` | 抽象统一度高 |
| Task | `app/generations/` + `app/jobs/` + `app/operations/` | 状态机强制、lease 崩溃恢复完整 |
| Storage | `app/services/asset_service.py` | 项目相对路径 + 唯一 data_dir 入口 |
| Config | `app/core/config.py` | env 优先于磁盘明文，fail-closed 校验 |
| Event | `app/events/` | WS 网关 per-connection sequence，有界队列 |

# Request Flow

HTTP → session token 中间件 → CORS → request_logging（X-Request-ID）→ Router → Service → DB commit → EventBus → WS fan-out。
长任务：POST 202 + operation_id / DB 队列 → worker 串行执行 → 事件驱动前端。
错误：`StudioError` 家族 → 统一 envelope `{error:{code,message,details,request_id}}`；httpx 异常全部在 provider 边界包装，不会裸漏 500。

# AI Provider Architecture

- 五类 capability（image/video/audio/render/workflow）均为 Protocol + 归一化 Request/Result dataclass + `on_progress(percent, stage)` + 永不抛错的 `cancel`。
- registry：canonical id 元组 + 惰性缓存 + `reset_*` 失效；未知 id 一律 422 fail-fast（无静默回落）。
- capability：媒体侧静态 `_CAPABILITIES` 表；LLM 侧运行时启发式（模型名正则 + override）。
- Agnes video 已是 submit/poll/download 三阶段；ComfyUI 走 WS 进度 + history 兜底轮询。
- Provider/Model 分离已达标：`provider` 与 `model` 是独立字段，workflow 模板独立目录自动发现。

# Task Architecture

- DB 即队列：原子条件 UPDATE claim（`queued/retrying` + backoff 门 + lease 过期重认领）→ running → CAS 终态。
- 状态机 `generations/state.py` 唯一事实源，非法转换 409。
- 取消：排队取消（立即终态）/ 运行中取消（durable `cancelling` + 内存 hint + provider 中断 + CAS 竞态防护 + staged 文件补偿）。
- 崩溃恢复：lease 过期扫描（running→re-queue/interrupted；cancelling→cancelled）——**机制完整但被默认参数废掉**（见 P1-1）。
- 事务边界：外部 AI 调用严格在事务外；完成链单事务 + 文件补偿。

# Storage

- DB 存项目相对路径，`settings.data_dir` 唯一根；provider 输出目录统一在 data_dir 下。
- `register_asset` 流式拷贝（1MB chunk）+ 流式 SHA-256 + 原子 `os.replace` + staged 文件补偿。
- 读取侧 `_safe_path` 防穿越；`check_missing_assets` 主动对账 ready→missing。
- 缺口：导入链路（见 P1-7）、项目软删后资产文件无 GC。

# Database

- SQLite WAL + FK ON + 每请求 session；乐观并发 = 原子条件 UPDATE（9 个实体一致）。
- 大字段：episodes.source_text、agent_runs.*_json、generations.parameters 等（Text，无 BLOB）——可接受。
- N+1 点：render/worker/pipeline 逐 clip `session.get(Asset)`（≤200 clip，SQLite 单机影响有限，P2 记录）。
- `GET /generations/recent`、`GET /agent/change-sets` 无分页上限（P2 记录）。

# Security

- 会话 token：REST 头 + WS query，/health、/system/info 豁免；env 优先密钥策略；读取侧 mask `••••{key[-4:]}`；无 print；日志无 key/Authorization。
- 已知取舍：`llm_profiles.json`/`image.json` 明文存 key（本地桌面场景，代码自述）。
- 缺口：token 比较用 `!=`（时序侧信道，本地风险极低）；写入侧 asset name 无分隔符防御。

---

# Problems

## P0

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| P0-1 | **ComfyUI 主链路 6 处 httpx 客户端跟随系统代理**（`trust_env` 默认 True）——queue_prompt / get_history / download_output / upload_image / cancel / health_check 在系统代理开启时会把回环 127.0.0.1:8188 劫持成 502（与 llm 探测同类已证 bug；同文件 get_catalog 已修，其余 6 处漏网） | `providers/comfyui/client.py:32,119,131,159,178,194` | 系统代理开启 = 图像生成全链路不可用 |
| P0-2 | **continuity 路由重复注册**：`include_router(continuity.router)` 连续两次 → OpenAPI 重复 operation、路由表膨胀 | `api/router.py:40,43` | API 契约污染 |

## P1

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| P1-1 | **自动重试与崩溃恢复实际失效**：`settings.generation_max_attempts=3` 是死配置（无消费方），`create_generation` 硬编码 `max_attempts=1` → 首次可重试失败即终态 failed；崩溃后 lease 过期直接 interrupted 不再 re-queue | `services/generation_service.py:128`、`core/config.py:73` | 任务可靠性：瞬时网络错误不重试；重启后 running 任务直接判死 |
| P1-2 | **生成任务无幂等防重**：同一 shot 双击生成按钮 = 两条昂贵任务全部执行（浪费生成成本/时间） | `services/generation_service.py:38` | 成本浪费 + 队列拥塞 |
| P1-3 | **correlation_id 是死脚手架**：日志格式带 `[%(correlation_id)s]` 但无任何 Filter/contextvar 注入，永远输出 `[ - ]`；日志与 request_id 不可互查 | `core/logging.py:19`、`main.py:108` | 可观测性违约（AGENTS §9） |
| P1-4 | **Router 内裸 SQL**（红线 §3.6 违规）：`_merge_shadow_warnings` 直接 `db.execute(text(...))` 查 continuity_warnings | `api/continuity.py:85-97` | 分层破坏 |
| P1-5 | **Router 跨模块引用私有符号 + 直连 DB**：`continuity_fix` import `director.runner._session/_to_read` 并在路由内 `session.get(AgentRun)`；同文件已有公开 `get_run()` 不用 | `api/agents.py:146-152` | 分层破坏 + 脆弱耦合 |
| P1-6 | **导入资产序号用 COUNT+1**：软删/并发导入时序号回退或冲突，`dest.write_bytes` 直接覆盖旧文件且非原子 → 同名旧文件被静默覆盖、checksum 失配 | `services/asset_service.py:219-227,323-332` | 数据损坏风险 |
| P1-7 | **worker 感知具体 encoder**：`provider.name == "ffmpeg"` 决定输出扩展名——唯一渗入业务层的能力分支 | `generations/worker.py:977` | Provider 红线边缘 |
| P1-8 | **HTTP 上传整体读入内存**：`tmp.write(file.file.read())` 在 service 校验 50MB 之前已全量进 RAM | `api/assets.py:162` | 内存放大（恶意/误传大文件） |

## P2（记录，本次不强行处理）

| # | 问题 | 位置 |
|---|---|---|
| P2-1 | 响应格式三种风格并存（裸实体 / 裸 dict / FileResponse）——前端依赖现状，统一属 breaking change，仅记录 | 全局 |
| P2-2 | 列表端点多数无分页（`/generations/recent`、`/agent/change-sets` 无界增长最重） | api/* |
| P2-3 | `db/models/generation.py` 的 `GENERATION_STATUSES` 与 `generations/state.py` 漂移（含未实现的 waiting_provider/processing_output、缺 interrupted/cancelling），死常量 | models/generation.py:15 |
| P2-4 | OperationStore 纯内存，重启后 202 operation 404（analyze/pipeline 有 DB 兜底，shot-planning/model_import 丢工作） | operations/store.py |
| P2-5 | 两套 capability 机制并存（静态 dict vs LLM 启发式）；新 provider 漏登记静默降级 | registry.py:253 |
| P2-6 | N+1：render/timeline/worker 逐 clip `session.get(Asset)`（≤200，SQLite 影响有限） | render_service、worker |
| P2-7 | 项目软删不级联资产文件/记录，磁盘无 GC | project_service.py:255 |
| P2-8 | Agnes 下载 `resp.content` 整载内存（视频数十 MB），无大小上限 | providers/*/agnes.py |
| P2-9 | prompts.py 列表循环内逐条查 version（N+1） | api/prompts.py:56 |
| P2-10 | `.env.example` 缺 `STUDIO_LLM_STRUCTURED_METHOD` 等 3 项 | .env.example |
| P2-11 | pipeline `failed` 状态枚举无写入路径；resume 不等图片就绪即可 finalize（render 对缺图 clip 跳过） | pipeline_service |
| P2-12 | worker `_paused`/`_cancelled` 内存 hint 重启丢失（暂停态静默解除） | worker.py:69 |

# Proposed Changes（本次执行）

1. **P0-1**：comfyui client 全部 6 处补 `trust_env=False`（与 get_catalog、llm、agnes 决策一致——base_url 是用户显式本机端点，绝不跟系统代理）。
2. **P0-2**：删除重复 `include_router`。
3. **P1-1**：`GenerationCreate.max_attempts` 默认改 `None`；service 落库时 `data.max_attempts or settings.generation_max_attempts`——接通死配置；显式传值行为不变（向后兼容）。
4. **P1-2**：`create_generation` 增加 in-flight 查重（同 shot+type 存在 queued/running/retrying/cancelling → 409 CONFLICT）；pipeline `_ensure_images` 容忍 409（视为已在飞行中，跳过）。
5. **P1-3**：`core/logging.py` 实现 contextvar correlation_id + Filter；`main.py` 中间件绑定 request_id；worker 执行期绑定 `gen:{id}`。
6. **P1-4/5**：裸 SQL 迁入 `ContinuityService`（ORM 查询，保留 schema drift 降级）；`continuity_fix` 改用公开 `get_run()`。
7. **P1-6**：导入序号改 MAX(suffix)+1 解析；落盘改 tmp+`os.replace` 原子写 + 已存在拒绝；流式拷贝（去 read_bytes）。
8. **P1-7**：RenderProvider 声明 `output_extension` 属性（ffmpeg=.mp4 / mock=.avi），worker 用 `getattr`，删除 name 分支。
9. **P1-8**：上传落盘改 1MB 分块流式写。
10. **P2-3**：同步死常量 `GENERATION_STATUSES`。
11. 加固：session token 比较改 `secrets.compare_digest`（REST + WS）。

# Risks

- max_attempts 默认 1→3 改变瞬时失败的行为（failed→retrying，约 1s+2s backoff 后 failed）：相关测试已显式 monkeypatch/传参，兼容。
- 生成 409 防重是新约束：前端双击会收到 409（正确语义）；pipeline resume 路径已做容错。
- 其余修改均为内部实现替换，无 API Contract / DB Schema 变更。
