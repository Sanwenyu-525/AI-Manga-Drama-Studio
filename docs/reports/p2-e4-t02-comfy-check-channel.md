# P2-E4-T02 — ComfyUI 检查通道：workflow live 诊断 + Comfy MCP 双通道

> 日期：2026-09-01 ｜ 类型：新功能（架构演进） ｜ 影响：Protected Core Flow 只读增强，生产执行链零改动

## 1. 需求背景

Post-MVP 用户设想（外部评审输入）：保留 ComfyUI 的确定性执行通道，同时新增检查/理解通道——
让 Studio 与 Agent 能"认识"用户实际安装的 ComfyUI 环境（节点/模型/workflow 兼容性），
官方 `comfy-mcp`（beta）作为可选的 Agent 控制通道，而不是取代现有 HTTP 执行链。

实施范围（用户确认）：**三阶段全做**——live 诊断 + Agent 工具 + MCP Adapter。

## 2. 架构决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 生产执行通道 | **不动**：GenerationService → worker → ImageProvider → ComfyUIClient | 大批量生产不需要 LLM/MCP 的不确定性与延迟（红线 3/8 保持） |
| 检查通道契约 | 查询式 `resolve_choices(class_types)` 而非全量快照式 | comfy-mcp 的节点检索是 query-oriented 的；全量枚举在其 beta 工具面上不保证存在 |
| MCP 依赖边界 | `mcp` sdk 入依赖；**comfy-mcp 不打包不分发**（用户自装） | 官方 AGPL-3.0-or-later OR 商业双许可 + beta； mere-aggregation 规避许可义务 |
| beta 工具面漂移 | 动态工具匹配（名称语义 + inputSchema 推导入参） | 39→40 工具仍在变动；硬编码工具名会脆弱 |
| 降级语义 | MCP/native 任何失败 → 诊断 unreachable，**绝不阻断排队** | 检查通道是增强，不是门槛；worker 运行时诚实失败兜底 |
| fail-fast 同步性 | 守卫走 sync 原生通道（线程池/运行中事件循环内不可 asyncio.run） | 路由是同步 def；Agent ToolExecutor 在 async graph 节点内被同步调用 |

## 3. 交付清单

### 后端
- `providers/workflow/introspection.py`（新）：`WorkflowIntrospector` Protocol + `WorkflowDiagnostics`/`EnvironmentSnapshot`/`NodeDiagnosis` 域契约（四态：ok / invalid / unreachable / static_error）
- `providers/comfyui/introspection.py`（新）：native 实现 + `parse_enum_choices`（双形态枚举 + 类型 token 排除）+ `project_choices`（**节点存在即登记**——缺节点判定依据是键缺失）
- `providers/comfyui/mcp_introspection.py`（新）：MCP 实现（动态工具匹配 + 宽容 JSON walker + 存在性/枚举分离提取）
- `providers/comfyui/client.py`：`get_object_info()`（async）+ `get_object_info_sync()`（sync twin），均 never-raise、`trust_env=False`
- `services/workflow_diagnostics_service.py`（新）：async/sync 双入口 + 60s TTL 缓存 + 单例
- `services/generation_service.py`：`_live_workflow_guard`（排队前 fail-fast 422）
- `agents/tools.py` + `agents/risk.py`：R0 工具 `check_workflow` / `inspect_comfy`
- `api/providers.py`：`GET /providers/comfyui/workflows` + `POST /providers/comfyui/workflows/{id}/validate`
- `core/config.py`：`comfy_introspection`（Literal native|mcp）+ `comfy_mcp_command`
- `pyproject.toml`：`mcp>=1.2.0`

### 前端（子代理交付）
- `api/providers.ts`（新）：`listComfyWorkflows` / `validateComfyWorkflow` + DTO
- `api/queryKeys.ts`：+`comfyuiWorkflows` key
- `features/settings/SettingsPage.tsx`：ComfyUI 卡「工作流检查」面板（模板下拉 + 逐节点 ✅/❌/⚠）
- `styles.css`：`.workflow-check` 布局（无硬编码颜色）

### 测试
- `tests/test_workflow_diagnostics.py`（新，**37 项**）：client twin / 枚举解析 / 投影 / 诊断四态 / fail-fast 守卫 / API 四态与 422 / Agent R0 分类与 ToolExecutor / MCP 动态匹配、能力缺失、连接失败回落
- `__tests__/workflowHealthPanel.test.tsx`（新，**4 项**）：列表加载 / ok 渲染 / invalid 缺节点缺模型 / unreachable 文案

### 文档
- `docs/api-event-contract-v0.1.md`：§48.2b（端点契约 + fail-fast 语义 + 许可说明）+ 端点索引 + R0 工具清单
- `docs/configuration-v0.1.md`：`STUDIO_COMFY_INTROSPECTION` / `STUDIO_COMFY_MCP_COMMAND`
- `backend/.env.example`：新段落
- `AGENTS.md` §5：状态行

## 4. 验证（triple check + 回归）

| 检查 | 结果 |
|---|---|
| pytest 全套 | **617 passed + 1 skip**（新增 37） |
| vitest | **280 passed**（新增 4） |
| tsc -b | 0 错误 |
| eslint src | 0 错误 |
| ruff check | 全绿（顺手修复既有 `test_pipeline.py` 5 处未用 import） |

**已知既有 flaky**：`test_generation_atomicity.py::test_failure_injection_then_retry_leaves_one_valid_version[asset]`
在全量跑中偶发失败，单跑通过——与本次改动无关（守卫对 mock provider 是 no-op；该类时序问题在记忆台账已有记录）。

## 5. 红线自查

- ✅ Agent 不直调 ComfyUI/MCP：工具只经 `WorkflowDiagnosticsService`
- ✅ 检查通道只读：永不下发 queue/interrupt；生产链路（Generation→Provider）零改动
- ✅ 外部实现先转 Studio Domain Contract：native/mcp 双实现可互换（`STUDIO_COMFY_INTROSPECTION` 一刀切换）
- ✅ API 增量变更：两个新端点 + 新 R0 工具，无既有契约破坏
- ✅ 降级不阻断：unreachable/诊断崩溃 → 照常 202

## 6. 后续机会（未做，登记）

- MCP adapter 的 workflow 图编辑/修复能力（comfy-mcp `validate_workflow`/slot 编辑）——等其 beta 稳定后评估，输出仍是"建议不直改"（workflow 模板不在 DB，无 revision/ChangeSet 体系）
- Director 生成失败后的自动自检编排（planner 提示词引导调用 `check_workflow`）
- `inspect_comfy` 补模型目录摘要（现走 sync 通道未拉 `get_catalog`）

## 7. 事故记录：SettingsPage.tsx 工具层陈旧 overlay（已处置）

前端子代理与本轮先后遭遇 `frontend/src/features/settings/SettingsPage.tsx` 的 **Edit 工具静默不落盘**
（报成功且返回"已更新"快照，但磁盘 mtime/size/内容均未变）。复现与定位结论：

- **Read 工具同样不可信**：返回的是缓存合并视图（显示了从未落盘的行），全文 Read 也不回源磁盘。
- 文件本身完全正常：非只读、独占打开成功（无进程持锁）、纯 LF、有效 UTF-8、无 NUL；同会话内
  更大的其他文件（AGENTS.md / 契约文档）Edit 均正常落盘——排除文件锁与体积因素。
- 判定为 IDE 会话内该文件的**粘性陈旧 overlay**（疑似子代理绕过工具层用 node 直写后，工具层
  与磁盘失去同步且不再自愈）；本会话内对外部写入无反应。

**处置（终态已落盘并三重验证）**：
1. 一次性 node 脚本直接写磁盘：移除重复注释行 → Edit 工具重试（仍静默失败，确证粘性）→
   node 固化终态（唯一合并注释行 `// P2-E4-T02: 工作流 live 健康检查面板（WorkflowHealthCheck）：模板下拉 + 逐节点 live 校验。`），
   脚本内自带磁盘回读自证。
2. 完整性验证：`tsc -b` 0 错误、`eslint SettingsPage.tsx` 0 错误、settingsPage + workflowHealthPanel **22 tests passed**。
3. 功能内容本身（WorkflowHealthCheck 面板 / api/providers.ts / queryKeys / styles.css）此前已由
   node 直写落盘并经 ripgrep 验证，未受影响。

**规程（写该文件时执行，直到 IDE 重启后重测）**：
- 对该文件的任何修改走 node/PowerShell 直写 + 脚本回读自证；
- **不要相信 Edit/Read 工具对该文件的输出**（包括"成功"回执与内容快照）；
- IDE/会话重启后先用小 Edit 探针 + 外部 mtime 比对验证工具层是否恢复同步，恢复前沿用外部写入。
