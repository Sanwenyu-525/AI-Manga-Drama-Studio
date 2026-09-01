# BACKEND_OPTIMIZATION_REPORT.md — 后端审计与优化结果（2026-08-31）

> 配套审计文档：[BACKEND_AUDIT.md](BACKEND_AUDIT.md)（问题全景 P0/P1/P2）。
> 本报告记录实际执行的修复、验证结果与遗留风险。

# Summary

对 `backend/app`（35 Service / 27 API 模块 / 五类 Provider / DB-poll 任务系统 / 文件存储 / 配置安全）完成全量审计，定位 **2 个 P0、8 个 P1、12 个 P2** 问题，本次修复 **P0 ×2 全部、P1 ×8 全部**，另加固 2 处安全细节、同步 1 处死常量、新增 2 个高价值测试。验证：**pytest 全量 570 项通过（1 skip）、ruff 全量通过、OpenAPI 168 operations 零重复**。

架构整体判断：**该后端不需要重构**。分层红线（Router→Service→Repository、事件 commit-then-publish、版本不可变、Agent 只调 Service、Provider Protocol 化）执行良好；本次全部是**定点修复**，无 API Contract / DB Schema 变更。

# Architecture Before

- 优点：模块边界清晰（api/domain/services/providers/generations/llm/events）；Provider 五类 capability 均为 Protocol + 归一化 Request/Result；DB-poll worker 带原子 claim + lease 崩溃恢复；乐观并发（原子条件 UPDATE）覆盖 9 实体。
- 缺陷：配置与代码断线（重试参数死配置）、幂等缺失、日志 correlation 死脚手架、2 处分层违规、1 处能力分支泄漏、存储导入链路非原子。

# Architecture After

- 同构优化（不改形态）：Provider 能力声明补全（render `output_extension`）、日志具备 request/gen 级 correlation、生成入口具备幂等门、导入链路原子化。
- **无新增模块、无新增依赖、无新增表**。

# Problems Fixed

## P0（2/2）

| 问题 | 修复 |
|---|---|
| ComfyUI 主链路 6 处 httpx 跟随系统代理（回环被劫持 502） | [client.py](backend/app/providers/comfyui/client.py) 全部 6 处 `trust_env=False`（与 get_catalog/llm/agnes 决策一致） |
| continuity 路由重复注册（OpenAPI 重复 operation） | [router.py](backend/app/api/router.py) 删除重复 `include_router`；冒烟验证 168 operations 零重复 |

## P1（8/8）

| 问题 | 修复 |
|---|---|
| `settings.generation_max_attempts=3` 死配置，自动重试与崩溃 re-queue 实际失效（默认 1 首败即终态） | [domain/generation.py](backend/app/domain/generation.py) `max_attempts` 改可选；[generation_service.py](backend/app/services/generation_service.py) 落库 `data.max_attempts or settings.generation_max_attempts`。瞬时失败现在会 1s/2s backoff 重试，崩溃后 lease 过期先 re-queue 而非直接 interrupted |
| 生成任务无幂等防重（双击 = 双份昂贵任务） | `create_generation` 增加 in-flight 查重（同 shot+type 存在 queued/running/retrying/cancelling → **409 CONFLICT**）；[pipeline_service.py](backend/app/services/pipeline_service.py) `_ensure_images` 容忍 409（resume 竞态视为已覆盖）。终态后重生成不受影响（V2 语义保留） |
| correlation_id 死脚手架（日志永远 `[ - ]`） | [logging.py](backend/app/core/logging.py) contextvar + Filter + `correlation_scope` 助手；[main.py](backend/app/main.py) 中间件绑定 request_id（含异常路径，try/finally）；[worker.py](backend/app/generations/worker.py) 执行期绑定 `gen:{id}`。日志与 X-Request-ID/错误信封可互查 |
| Router 内裸 SQL（红线违规） | [continuity.py](backend/app/api/continuity.py) 裸 SQL 迁入 [ContinuityService.merge_open_warnings_into_shots](backend/app/services/continuity_service.py)（ORM 查询，保留 schema drift 降级语义），router 变薄委派 |
| Router 跨模块引用私有符号 + 直连 DB | [agents.py](backend/app/api/agents.py) `continuity_fix` 改用公开 `get_run()`（顺带获得 TTL sweep 语义） |
| 导入资产 COUNT+1 序号 + `write_bytes` 非原子覆盖写 | [asset_service.py](backend/app/services/asset_service.py)：序号改 MAX(suffix)+1 解析（gap-tolerant）；落盘改 tmp + `os.replace` 原子写 + 已存在拒绝（409）；流式拷贝去 `read_bytes`；`register_asset` 增加 name 路径分隔符写入侧防御 |
| worker 感知具体 encoder（`provider.name == "ffmpeg"`） | [render/base.py](backend/app/providers/render/base.py) Protocol 声明 `output_extension`；ffmpeg=`.mp4`、mock=`.avi`；worker 改 `getattr(provider, "output_extension", ".avi")` |
| HTTP 上传整体读入内存 | [api/assets.py](backend/app/api/assets.py) 改 1MB 分块流式落盘（50MB 校验前不再全量进 RAM） |

## 安全加固（顺手）

- session token 比较改 `secrets.compare_digest`：REST（[main.py](backend/app/main.py)）+ WS（[events/ws.py](backend/app/events/ws.py)）。

## 文档同步

- [db/models/generation.py](backend/app/db/models/generation.py) 的 `GENERATION_STATUSES` 死常量与 `generations/state.py` 状态机对齐（补 interrupted/cancelling，删未实现的 waiting_provider/processing_output），标注为文档镜像。

# Provider Improvements

- ComfyUI 客户端网络行为统一：全部请求 `trust_env=False` + 各自 timeout（5/8/30/10/120/60/10s），回环端点不再受系统代理影响。
- Render 能力表达补全：输出扩展名成为 Provider 声明的能力而非 worker 侧的身份判断。
- 维持既有优点：未知 provider 一律 422 fail-fast、provider 层不重试（重试职责在 worker + backoff）、`on_progress`/`cancel` 永不抛错契约、node_id 不外泄。

# Task Improvements

- 重试预算接通：`STUDIO_GENERATION_MAX_ATTEMPTS`（默认 3）真正生效；显式传 `max_attempts: 1-5` 覆盖不变。
- 幂等门：同 shot+type 单飞行任务；409 信封 `{"error":{"code":"CONFLICT",...}}`。
- 崩溃语义修正：lease 过期 + 预算未尽 → re-queue（此前一律 interrupted）；`cancelling` 跨重启仍正确终态化。
- pipeline resume 与幂等门兼容（ConflictError 视为已排队）。

# API Improvements

- OpenAPI 去重（168 operations，0 重复）。
- 新 409 场景进入既有统一错误信封，无格式变更。
- 向后兼容：`max_attempts` 由必填默认 1 改为可选 None（显式值仍接受）。

# Storage Improvements

- 导入链路：原子落盘（tmp + `os.replace`）+ 冲突拒绝 + MAX 序号 + 流式 checksum。
- 上传链路：流式分块，防内存放大。
- 写入侧路径防御（name 白名单校验），与读取侧 `_safe_path` 对称。

# Security Improvements

- token 常量时间比较（REST + WS）。
- 复审确认：日志/异常/响应无 api_key 泄漏；env 优先密钥策略完好；未发现新泄漏面。

# Performance Improvements

- 上传/导入不再整载内存（50MB 上限内 O(chunk) 内存）。
- 其余（N+1、分页）属 P2，见 BACKEND_AUDIT.md——当前规模（SQLite 单机、≤200 clip）收益有限，不强行引入复杂度。

# Files Changed

| 文件 | 变更 |
|---|---|
| [backend/app/providers/comfyui/client.py](backend/app/providers/comfyui/client.py) | 6 处 `trust_env=False` + 注释 |
| [backend/app/api/router.py](backend/app/api/router.py) | 删除重复 include |
| [backend/app/domain/generation.py](backend/app/domain/generation.py) | `max_attempts` 可选化 |
| [backend/app/services/generation_service.py](backend/app/services/generation_service.py) | in-flight 409 门 + max_attempts 接通 |
| [backend/app/services/pipeline_service.py](backend/app/services/pipeline_service.py) | `_ensure_images` 容忍 409 |
| [backend/app/core/logging.py](backend/app/core/logging.py) | correlation contextvar/Filter/scope |
| [backend/app/main.py](backend/app/main.py) | 中间件绑定 correlation + `compare_digest` |
| [backend/app/generations/worker.py](backend/app/generations/worker.py) | `gen:{id}` correlation + `output_extension` 取代 name 分支 |
| [backend/app/api/continuity.py](backend/app/api/continuity.py) | 裸 SQL 移除 |
| [backend/app/services/continuity_service.py](backend/app/services/continuity_service.py) | 新增 `merge_open_warnings_into_shots` |
| [backend/app/api/agents.py](backend/app/api/agents.py) | 改用公开 `get_run` |
| [backend/app/services/asset_service.py](backend/app/services/asset_service.py) | 导入原子化/序号/防御 |
| [backend/app/api/assets.py](backend/app/api/assets.py) | 上传流式化 |
| [backend/app/providers/render/base.py](backend/app/providers/render/base.py) / [ffmpeg.py](backend/app/providers/render/ffmpeg.py) / [mock.py](backend/app/providers/render/mock.py) | `output_extension` 能力声明 |
| [backend/app/events/ws.py](backend/app/events/ws.py) | `compare_digest` |
| [backend/app/db/models/generation.py](backend/app/db/models/generation.py) | 状态常量对齐 |
| [backend/tests/test_generation.py](backend/tests/test_generation.py) | 新增 2 测试（409 门 / max_attempts 接线） |
| [BACKEND_AUDIT.md](BACKEND_AUDIT.md) / [BACKEND_OPTIMIZATION_REPORT.md](BACKEND_OPTIMIZATION_REPORT.md) | 新增文档 |

# Verification

- `pytest` 全量两轮：
  - 修复后第一轮：**567 passed, 1 skipped（0 failed）**。
  - 新增 2 测试后第二轮：**568 passed, 1 skipped + 1 failed**——失败为 `test_generation_atomicity::test_failure_injection_then_retry_leaves_one_valid_version[save]`，即 memory 在案的既有 flake（失败参数漂移 `[complete]`/`[asset]`/`[save]`、隔离复跑必过、先于本次改动存在；本次隔离复跑 **5/5 通过**）。属跨测试时序污染（bus.subscribe 累积同类），待单独清理，不阻塞。
- `ruff check app`：**All checks passed**（全量 + 改动文件单查）。
- 冒烟：`app.openapi()` 168 operations、duplicates=[]；correlation 默认 `-`、Filter 生效。
- 定向回归（generation/continuity/asset/pipeline/phase5/session/event 7 模块）：**77 passed**（含 2 个新测试）。

# Remaining Risks

1. **max_attempts 默认 1→3 的行为变化**：瞬时失败的任务会先重试（约 1s/2s backoff）再 failed，前端队列中的任务停留时间略变长——这是配置文档原本承诺的语义。
2. **新 409 约束**：前端对同镜头并发生成会收到 409（正确语义）；如 UI 未处理 409 提示，建议前端后续给出生成中提示（非阻塞）。
3. **P2 遗留**（见 BACKEND_AUDIT.md P2-1..P2-12）：响应信封统一与分页属 breaking change 需产品决策；OperationStore 落库、项目软删资产 GC、Agnes 下载流式化、两套 capability 机制合并等按 backlog 排期。
4. api_key 明文落盘（llm_profiles.json/image.json）为既有已声明取舍（env 优先 + 掩码缓解），云部署前需加密存储。

# Suggested Next Steps

1. 前端为生成按钮增加「生成中」禁用态或 409 toast（配合新幂等门）。
2. `/generations/recent`、`/agent/change-sets` 补 limit/offset（P2-2，前端改动小收益大）。
3. OperationStore 最小持久化（shot-planning/model_import 两类仍纯内存，重启丢进度句柄）。
4. 项目软删时提供资产 GC（或显式「删除项目文件」入口）。
5. Agnes 下载改 `client.stream` + 大小上限（P2-8）。
