# AI Manga Drama Studio

AI 原生漫剧制作 Studio —— 以 AI Agent 为核心交互方式，以结构化项目系统（Project State）为记忆，以 Workflow Engine 为执行系统，以 ComfyUI 和生成模型为渲染后端的 AI 原生漫剧生产平台。

> 当前阶段：**MVP Stage A（Core Studio）** —— 先让软件本身会管理漫剧，再让 AI 学会操作这个软件。

---

## 快速启动

根目录提供了管理脚本，一条命令即可管理前后端（支持交互菜单）：

```bat
studio.bat                 # 双击 / 交互菜单：启动 / 停止 / 重启 / 状态 / 日志 / 退出
studio.bat start           # 启动前后端（自动执行数据库迁移）
studio.bat stop            # 停止前后端
studio.bat restart         # 重启前后端
studio.bat status          # 查看运行状态
studio.bat logs            # 查看前后端日志
```

PowerShell 下等价用法（`studio.bat` 内部即调用此脚本）：

```powershell
.\studio.ps1               # 交互菜单（同上）
.\studio.ps1 start         # 或 stop / restart / status / logs
```

> `studio.bat` 与 `studio.ps1` 需放在一起使用（bat 是入口，ps1 是管理逻辑）；bat 已内置 `-ExecutionPolicy Bypass`，不受执行策略限制。

首次安装依赖：

```bash
cd backend && uv sync && uv run alembic upgrade head   # 后端依赖 + 数据库
cd frontend && npm install                             # 前端依赖
```

- 前端：http://127.0.0.1:17821（`/api` 自动代理到 17820）
- API 文档：http://127.0.0.1:17820/docs
- 健康检查：http://127.0.0.1:17820/api/v1/health
- 后端日志与 PID 记录在 `.studio/` 目录（已 gitignore）；端口被手动启动的旧进程占用时脚本会提示

### 手动启动

```bash
# 后端（FastAPI + SQLite）
cd backend
uv sync            # 安装依赖（uv 0.11+）
uv run alembic upgrade head   # 初始化数据库（backend/data/studio.db）
uv run uvicorn app.main:app --host 127.0.0.1 --port 17820 --reload

# 前端（React + Vite），另开终端
cd frontend
npm install
npm run dev        # 5173 在 Windows 保留端口区间内，故固定 17821
```

### 桌面壳（Tauri，可选）

```bash
cd apps/desktop
npm install
npm run tauri dev  # 需要 Rust 工具链；首次编译较慢
```

### 测试

```bash
cd backend
uv run pytest tests -q
```

---

## 当前功能（Stage A）

- ✅ 项目 / 剧集 / 场景 / 镜头 完整 CRUD（REST，含乐观并发 revision + 409）
- ✅ Storyboard 卡片网格：选择镜头 → Inspector 编辑 → PATCH 保存 → 自动刷新
- ✅ 软删除（`deleted_at`），镜头/场景删除后可恢复（恢复 API 后续）
- ✅ `/scenes/{id}/storyboard` 聚合端点（避免 N+1）
- ✅ 事件总线（commit 后 publish；WebSocket 网关后续阶段接入）
- ⬜ AI 分析（Stage B）、ComfyUI 生成（Stage C）、AI Director（Stage D）

## 架构

完整设计链（9 份事实源文档）见 [docs/](./docs)，Agent 协作入口见 [AGENTS.md](./AGENTS.md)。

```
backend/app/
├── api/          # REST 路由（无业务逻辑）
├── domain/       # Pydantic DTO（LLM 与 Domain 的数据契约）
├── db/models/    # SQLAlchemy 模型（SQLite, WAL, 软删除）
├── repositories/ # 数据访问层
├── services/     # 业务层（UI 与 AI Director 共用）
├── events/       # 事件总线（先 commit 再 publish）
└── core/         # 配置 / 日志 / 错误契约

frontend/src/
├── app/          # 路由 + 五区布局（TopBar/Explorer/Workspace/RightPanel/Dock）
├── features/     # project / studio / storyboard
├── stores/       # Zustand（selection / workspace 本地 UI 状态）
└── api/          # fetch client + DTO 类型 + Query keys
```

## 目录结构

```
├── AGENTS.md          # Agent 入口文档（红线、契约速查、开发约定）
├── docs/              # 9 份事实源文档（PRD → MVP Spec）
├── backend/           # FastAPI + SQLAlchemy + SQLite
├── frontend/          # React + TypeScript + Vite
├── apps/desktop/      # Tauri 壳
└── workflows/         # ComfyUI workflow 模板（Stage C 使用）
```
