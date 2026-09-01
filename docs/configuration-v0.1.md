# 配置矩阵（Configuration Matrix）

> 事实源：`backend/app/core/config.py`（pydantic-settings，env 前缀 `STUDIO_`）。
> P1-E5-T01：**production 环境 fail-closed**——fake/mock 内容提供器在启动时被拒绝（`validate_startup_config`，lifespan 调用），杜绝"看起来成功、其实是假结果"。
> 开发默认（fake/mock）保持不变；`.env.example` 提供无 secret 模板。

## 环境

| 变量 | 默认 | 取值 | 说明 |
|---|---|---|---|
| `STUDIO_APP_ENV` | `development` | `development` / `test` / `production` | production 触发 fail-closed 门禁 |

## 提供器（生产必须为真实实现）

| 变量 | 默认 | 取值 | production 要求 | 重启影响 |
|---|---|---|---|---|
| `STUDIO_LLM_MODE` | `fake` | `fake` / `openai` | 必须 `openai` + 有效 base_url/key | 重启 |
| `STUDIO_IMAGE_PROVIDER` | `mock` | `mock` / `comfyui` / `agnes` | 必须 `comfyui` 或 `agnes` | 重启 |
| `STUDIO_VIDEO_PROVIDER` | `mock` | `mock` / `agnes` | 必须 `agnes` | 重启 |
| `STUDIO_AUDIO_PROVIDER` | `mock` | `mock` / `edge` | 必须 `edge` 或未来真实 TTS | 重启 |
| `STUDIO_RENDER_PROVIDER` | `auto` | `auto` / `mock` / `ffmpeg` | 任意（mock 渲染产出真实可播放成片，非假数据） | 重启 |

## 连接与密钥（SECRET，只走 env / 设置页内存，绝不落库、绝不明文回传）

| 变量 | 默认 | secret | 说明 |
|---|---|---|---|
| `STUDIO_LLM_BASE_URL` | 无 | 否 | OpenAI 兼容端点（DeepSeek / Ollama / vLLM / Agnes） |
| `STUDIO_LLM_API_KEY` | 无 | **是** | env 优先于磁盘明文（llm.json / llm_profiles.json） |
| `STUDIO_LLM_MODEL` | `deepseek-chat` | 否 | 模型名 |
| `STUDIO_COMFYUI_URL` | `http://127.0.0.1:8188` | 否 | 本地 ComfyUI |
| `STUDIO_AGNES_BASE_URL` | `https://api.agnes-ai.cn/v1` | 否 | Agnes 云端 |
| `STUDIO_AGNES_API_KEY` | 无 | **是** | env 优先于磁盘明文（image.json） |
| `STUDIO_VIDEO_MODEL` | `agnes-video-2.5-flash` | 否 | 视频模型 |
| `STUDIO_TTS_DEFAULT_VOICE` | `zh-CN-XiaoxiaoNeural` | 否 | edge 默认音色 |

## 运行时（Generation worker / HTTP）

| 变量 | 默认 | 说明 |
|---|---|---|
| `STUDIO_HOST` | `127.0.0.1` | 仅回环（本地控制面） |
| `STUDIO_PORT` | `17820` | 后端端口 |
| `STUDIO_LOG_LEVEL` | `INFO` | 日志级别 |
| `STUDIO_CORS_ORIGINS` | Vite 17821 + Tauri origins | 逗号分隔允许的浏览器 Origin |
| `STUDIO_GENERATION_CONCURRENCY` | `1` | **必须为 1**（单 worker，>1 启动即拒） |
| `STUDIO_GENERATION_MAX_ATTEMPTS` | `3` | 重试上限 |
| `STUDIO_GENERATION_LEASE_SECONDS` | `120` | 崩溃恢复租约窗口 |
| `STUDIO_GENERATION_RETRY_BACKOFF_BASE` / `_MAX` | `1.0` / `60.0` | 指数退避（秒） |
| `STUDIO_DATA_DIR` | `backend/data` | SQLite + 项目资产目录 |
| `STUDIO_WORKFLOWS_DIR` | 仓库根 `workflows/` | ComfyUI workflow 模板目录 |
| `STUDIO_COMFY_INTROSPECTION` | `native` | `native` / `mcp` | 检查通道 introspection 实现（P2-E4-T02）：native=直连 `/object_info`；mcp=经用户自装 comfy-mcp（失败自动回落 native）。只影响诊断，不影响生产执行通道 | 重启 |
| `STUDIO_COMFY_MCP_COMMAND` | `comfy-mcp` | 任意命令 | mcp 模式下启动的 comfy-mcp console script（用户自装，不随应用分发） | 重启 |

## 运行时落盘配置（设置页写入，非 env）

- `{data_dir}/llm_profiles.json` — LLM 连接 Profile（命名连接/激活/任务绑定），唯一事实源；api_key 仅掩码回传。
- `{data_dir}/image.json` — 图像运行时覆盖层；api_key 明文可存在（env 优先，绝不生效于 env 已设时）。
- `{data_dir}/llm.json` — 仅首次播种「默认连接」，此后不再参与解析。

## 本地安全（P1-E5-T02）

| 变量 | 默认 | secret | 说明 |
|---|---|---|---|
| `STUDIO_SESSION_TOKEN` | 无 | **是** | Tauri 壳 spawn 后端时注入的高熵会话 token；设置后 REST 需 `X-Session-Token`（媒体标签可 `?token=`）、WS 需 `?token=`（`/health`、`/system/info` 豁免）。不设 = 开发/浏览器模式（auth 关闭）。绝不写日志、不落库、不入源码 |

## 重启影响

env 配置全部在**进程启动时**读取（`settings = Settings()`）；改动需重启后端。设置页保存的运行时覆盖（llm_profiles.json / image.json）即时生效、无需重启（Provider 缓存重置）。

## 生产部署检查清单（P1-E5-T01）

1. `STUDIO_APP_ENV=production`
2. `STUDIO_LLM_MODE=openai` + 有效 base_url + key
3. `STUDIO_IMAGE_PROVIDER` ∈ {comfyui, agnes}；`STUDIO_VIDEO_PROVIDER=agnes`；`STUDIO_AUDIO_PROVIDER=edge`（或真实 TTS）
4. 密钥只放 OS 级 env，`backend/.env` 不入库
5. 启动后 `/api/v1/health` 返回 `env: "production"`
