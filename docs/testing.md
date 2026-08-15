# 测试与 CI 门禁（P1-E6-T01）

本文件列出每个 CI 门禁的本地等价命令。PR 合并前必须全部通过；
CI 与本地使用同一套命令，避免"本地能过、CI 挂"。

## 统一命令

### 1. 后端（Python 3.13 + uv）

```powershell
cd backend
uv sync --locked          # 安装锁定依赖（uv.lock）
uv run ruff check app tests   # Lint（E/F/W/B/S/UP/ASYNC 子集）
uv run pytest -q          # 全量测试（含 Alembic-from-zero、Worker loop、并发/取消/ownership 风险套件）
uv run pytest tests/test_migrations.py -q   # 仅迁移冒烟（fresh DB upgrade + downgrade round trip）
```

> 说明：`tests/conftest.py` 的 `session_factory` fixture 使用 `create_all`
> 仅为单元测试速度；迁移路径（应用实际使用的建表方式）由
> `tests/test_migrations.py` 通过 Alembic 从零构建验证。

### 2. 前端（Node 20 + npm）

```powershell
cd frontend
npm ci                    # 安装锁定依赖
npm run build             # tsc -b + vite build（类型检查 + 产物构建）
npm test                  # vitest：API 错误契约 / Event reconcile / 关键 Store / 组件 smoke
```

### 3. 桌面壳（Rust）

```powershell
cd apps/desktop
cargo check               # Tauri 壳编译检查（无需 WebView2 运行时）
```

### 4. Secret / 依赖扫描

```powershell
python scripts/scan-secrets.py   # 扫描 git-tracked 文件中的常见 secret 模式
```

允许清单：行内含 `SECRET-SCAN` 标记（如测试夹具中的模拟 secret）。
二进制产物（图片/DB/字体）自动跳过。

## 风险覆盖清单（当前自动测试）

| 风险 | 测试文件 |
|---|---|
| Alembic 从零迁移 + downgrade round trip | `tests/test_migrations.py` |
| 真实 Worker DB-poll loop | `tests/test_worker_loop.py` |
| 路由冲突（/generations/recent）与统一错误 Envelope | `tests/test_errors.py`、`test_generation.py` |
| AI 计划映射 / 批量写入事务 / 幂等 / replace | `test_plan_mapper.py`、`test_script_transactions.py`、`test_script_planning.py` |
| Agent ownership / 并发 / 协作式取消 | `test_agent.py`、`test_agent_ownership.py` |
| Provider/Workflow 契约（无需 GPU） | `test_provider_contract.py` |
| 前端 API 错误 / CONFLICT / Event reconcile / Store | `frontend/src/__tests__/*` |

## 可选（不阻塞普通 PR）

- 真实 LLM（`STUDIO_LLM_MODE=openai`）与真实 ComfyUI（`STUDIO_IMAGE_PROVIDER=comfyui`）
  的 smoke 属 nightly/manual profile，需要 GPU/外部服务，不进入 CI。
