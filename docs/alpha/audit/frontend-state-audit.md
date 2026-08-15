# 前端状态管理审查报告（P0-T005）

**审查人观点：** 这是一份**只读分析**，未修改任何代码。审查范围覆盖 `frontend/src` 全部 32 个文件、`package.json`、两份 Alpha 目标文档（`frontend-component-store-api-design-v0.1.md`、`frontend-ux-design-v0.1.md`）与 `docs/AGENTS.md`。

---

## 1. 现状总览：状态管理全貌图

项目技术栈（`package.json`）：React 18 + TypeScript + Vite + **Zustand 5（UI 状态）** + **TanStack Query 5（Server 状态）** + **React Router DOM 6** + **Tauri v2 API** + @phosphor-icons。**无**独立的 WS/SSE 库（用的是原生 `WebSocket`），**无**虚拟列表库，**无** localStorage 持久化。

目前只有 **4 个 Zustand store**（文件 `frontend/src/stores/` 下仅此 4 个）：

| Store | 管理内容 | 数据来源 | 如何更新 |
|---|---|---|---|
| **selectionStore** | 单一选择上下文：`projectId/episodeId/sceneId/shotIds[]/assetIds[]/workspace` | 由组件派生（URL + 点击） | `setProject/setEpisode/setScene/selectShot/...`；StudioPage 从 URL 同步 projectId/sceneId；ProjectExplorer/StoryboardView 点击时同步 |
| **workspaceStore** | 纯 UI 布局：`activeShotId`、右面板 tab（inspector/director）、底部 dock tab（queue/history）+ 展开、explorer/right 折叠 | 组件输入 | 各 `set*` action |
| **generationStore** | **仅** transient 实时生成状态：`live: {id → progress/stage/status}` | `socket.ts` WS 事件 | `upsert/remove/clear`（由 EventRouter.handle 调用） |
| **agentStore** | AI Director 会话 UI 态：`runId/status/objective/steps/tools/messages/result` | `socket.ts` WS 事件 + 提交时的 `startRun` | `startRun/setPlan/toolStarted/toolCompleted/runCompleted/runFailed/reset`（由 EventRouter.handle 调用） |

**Server 状态全部走 TanStack Query**，不存在真正的 Domain Store。所有业务实体（Project/Episode/Scene/Shot/Character/Generation/Version/Provider）都通过 `useQuery`/`useMutation` 直接挂在组件内部，store 层不持有这些数据。

**主入口**（`main.tsx`）：`QueryClient`（staleTime 5s，retry 1）→ `QueryClientProvider` → `RouterProvider`。无 QueryClient 之外的全局 Provider，无 React Query Devtools，无 ErrorBoundary。

**事件层**（`events/socket.ts`）：全局**唯一** `WebSocket` 连接到 `/api/v1/events`，指数退避重连（1s→30s）。WS 消息 → `shouldRouteEvent`（sequence 去重）→ 单例 `EventRouter`（class，由 StudioPage 的 `useEffect` 在挂载时 `setEventRouter(new EventRouter(queryClient))` 注入，卸载时销毁）。Router 内 `switch(event.event_type)`：agent 事件写 `agentStore`，generation 高频率事件写 `generationStore`，其余资源事件（shot.updated/character.*/scene.created/asset.created）**直接 `queryClient.invalidateQueries()`** 触发重拉取。

---

## 2. 数据流审计

### 2.1 API 调用点分布（组件直接调用 `api.*`，全在组件/useMutation 内，无 Store/Service 中间层）

共 **54** 处直接 `api.get/post/patch/delete` 调用（含 hook）。按组件：

- **StudioPage**（Layout）：`GET /projects/{id}`、`GET /projects/{id}/episodes`、`GET /providers`；mutation `POST /shots/{id}/generations`（顶部"生成图片"按钮）。
- **ProjectExplorer**：`GET /projects/{id}/episodes`、`POST /episodes`、`PATCH /episodes/{id}`、`DELETE /episodes/{id}`、`GET /projects/{id}/characters`、`POST /characters`、`PATCH /characters/{id}`、`DELETE /characters/{id}`、`GET /episodes/{id}/scenes`、`PATCH /scenes/{id}`、`DELETE /scenes/{id}`。
- **StoryboardView**：`GET /scenes/{sceneId}/storyboard`、`POST /scenes/{id}/shots`、`POST /scenes/{id}/generate-shots`、`useOperationPolling → GET /operations/{id}`。
- **ShotInspector**：`GET /shots/{id}`、`GET /projects/{id}/characters`、`POST /shots/{id}/generations`、`DELETE /shots/{id}`、`PATCH /shots/{id}`（带 revision）；`ShotVersions` 子组件 `GET /shots/{id}/generations`、`GET /shots/{id}/versions`、`POST /media-versions/{id}/activate`。
- **AIDirectorPanel**：`POST /agent/director/runs`（携带 selection）。
- **EpisodePanel**：`PATCH /episodes/{id}`、`POST /episodes/{id}/analyze/preview`、`POST /episodes/{id}/analyze`、`useOperationPolling`。
- **GenerationQueue**：`GET /generations/recent`（轮询 5s）、`POST /generations/{id}/retry|cancel`。
- **AssetsPage**：`GET /generations/recent`（轮询 15s）、`GET /projects`。
- **SettingsPage**：`GET /providers`（轮询 10s）、`POST /providers/comfyui/test`。
- **WorkflowsPage**：`GET /workflows`。
- **ProjectHome**：`GET /projects`、`POST /projects/{id}/cover`、`PATCH /projects/{id}`、`DELETE /projects/{id}`。
- **NewProjectPage**：`POST /projects` + `POST /projects/{id}/episodes`。
- **VersionReviewPage**：`GET /projects/{id}`、`GET /shots/{id}`、`GET /shots/{id}/versions`、`POST /media-versions/{id}/activate`。

**结论：原则六"Workspace 组件不直接操作 API"未落地** —— 组件全部直连 `api`，无 `*.api.ts` Domain API、无作用域 Hook/Command Service。

### 2.2 Socket 订阅分布

- `startEventSocket()` 只在 **StudioPage**（`/projects/:projectId` 布局）调用一次；`setEventRouter` 也只在 StudioPage。
- **没有任何组件直接 `new WebSocket`**（`grep` 证实只有 socket.ts 一处）。
- 组件通过 `useGenerationStore` / `useAgentStore` 间接消费 WS 派发的状态。

**结论：原则五"SSE 不直达组件"是**符合**的**（比 MVP 阶段明显推进），但有缺陷（见 §3）。

### 2.3 其他轮询（未走 WS）

多个组件用 `refetchInterval` 兜底轮询，与 WS 并存：
- GenerationQueue `/generations/recent`（5s）、AssetsPage（15s）、SettingsPage `/providers`（10s）、**ShotInspector 版本（800ms/3s）+ 生成（2s）**、VersionReviewPage（无轮询，靠 invalidate）。

这是"WS + 轮询双通道"，说明 WS 失效回流还不完整（见 §3 Read Model 缓存）。

---

## 3. 与目标架构逐项对照

| 目标项 | 判定 | 证据 |
|---|---|---|
| **Selection Store** | ✅ 符合（MVP 之上） | `selectionStore.ts`，统一 `StudioSelection`（project/episode/scene/shotIds/assetIds/workspace），Inspector/AI Director 均按它驱动；有 `selectionStore.test.ts` 覆盖派生逻辑 |
| **Workspace Store** | ⚠️ 部分 | 有 `workspaceStore.ts`，但仅 `activeShotId`+面板 tab/折叠，**无** editor tabs、panel 尺寸、bottomPanelTab 完整模型（目标 §36 的 `bottomPanelTab: GENERATION\|AGENT\|CONTINUITY\|CONSOLE` 只实现 queue/history 两档） |
| **实体 Normalize（shotsById 等）** | ❌ 缺失 | 目标要求 `projectsById/episodesById/scenesById/shotsById/assetsById`；现状 server 实体全部在 TanStack Query 缓存里，没有前缀索引（`idsByScene` 等），没有 normalize 层 |
| **Server State vs UI State 分离** | ⚠️ 部分 | 大体方向对（Query=server，Zustand=UI transient），但 `agentStore.messages` 缓存了对话历史（语义上偏 session/UI 状态，勉强可接受）；`activeShotId` 放 workspaceStore 与 `selection.shotIds` 重复（双源） |
| **SSE 经 Dispatcher** | ⚠️ 部分 | 有单例 `EventRouter` 统一分派（原则五符合），但**不是分模块 Reducer**（目标 §54），全部 `switch` 塞在一个类；且资源事件只做 `invalidate`，不做精确 store reducer 更新，导致大量回调光 invalidate→refetch |
| **Read Model 缓存与失效** | ❌ 缺失 | 目标 §58-61 要求 `data/loadedAt/stale` CachedView + 精确 `invalidateShotInspector`。现状 read model 就是 Query，靠 `queryKey` invalidate；没有 loadedAt/stale 概念，shot.updated 事件只会无差别 invalidate `["storyboard"]`/`["shots"]` |
| **乐观更新与 revision 冲突处理** | ⚠️ 部分 | PATCH 带 `revision`，409 被识别为 `CONFLICT` → 提示"刷新后重试"+ invalidate（目标 §48 符合）；**但没有真正"乐观"更新**（目标 §49/§104）—— 所有写入都等服务器返回后才 invalidate，无前端先行占位。字符冲突错误码误用为 `"CONFLICT"`（后端应区分 `CHARACTER_*_CONFLICT`，是后端契约偏差，非前端） |
| **编辑器 Tabs（Editor Tabs）** | ❌ 缺失 | 目标 §94-96 的 `EditorTab[]/activeTabId/WorkspaceHost/WorkspaceRegistry` 均未实现；当前中心工作区是**单一 URL 驱动**（`/script` 或 `/storyboard/:sceneId`），不能同时打开多资源 |
| **工作区持久化（localStorage）** | ❌ 缺失 | `grep localStorage` 为 0；面板尺寸/折叠/tab 全部内存态，重启丢失，违背目标 §92-93 的 `workspace_layout` 持久化 |
| **DesktopAdapter 抽象** | ⚠️ 部分（方向对） | `TitleBar.tsx` 用 `__TAURI_INTERNALS__` 探测，Tauri 下渲染、浏览器返回 null，隔离探测逻辑在一个组件里；但**无独立 adapter 层**，Tauri window API 直接 `import` 在组件顶部（浏览器 bundle 若不 tree-shake 会引入），未按目标"Render/运行时经独立 Adapter 隔离"分层 |
| **Error Boundary** | ❌ 缺失 | `grep ErrorBoundary` 为 0。组件渲染错误无兜底；只有 `ApiErrorPanel`（API 错误横幅）+ `NotFoundPage`（路由兜底）。目标全局/Feature/Field 三层错误处理只实现了 Error banner + request_id |
| **虚拟列表** | ❌ 缺失 | `grep virtualiz`/`react-window` 为 0；Storyboard `shot-grid`/`shot-list`、资源网格全部一次渲染全量 map，目标 §169 要求 500+ 镜头虚拟化 |

**补充判定：目标 §84 的"Active 与 Latest 区分 / MASTER/STALE UI"** —— ⚠️ 部分。`ShotInspector` 的版本区有 `Active` badge + 切换，但**无 Latest/STALE/MASTER/REVOKED** 标签（目标 §35-39）；`shot.active_version` 由后端返回 `is_active`（符合"后端才是 active 事实源"，未在取 max）；STALE（dirty_state / reference outdated）只以 `status="image_ready"` + `dirty_state!=="clean"` 近似表达，无"此版本引用已过期"的展开 UI。

---

## 4. 现有 store 与目标 store 清单差距

目标清单（component-store-api §36 等）：`project / episode / scene / shot / character / asset / generation / job / agent / continuity / timeline / selection / workspace`（13 个）。

| 目标 Store | 现状 | 差距说明 |
|---|---|---|
| project | ❌ 无（Query `["project",id]`） | 无独立 project store；currentProjectId 存在 selection |
| episode | ❌ 无（Query `["episodes",projectId]`） | 无 `episodesById` |
| scene | ❌ 无（Query `["scenes",episodeId]`、`["storyboard",sceneId]`） | 无 scenes 缓存/normalize |
| shot | ❌ 无（Query shot/storyboard/shots） | 无 `shotsById/idsByScene`，ShotInspector read model 不单独缓存 |
| character | ❌ 无（Query characters） | 无 versionsByCharacter/master 管理 |
| asset | ❌ 无 | 素材页直接 `GET /generations/recent` 推断 asset 摘要，无 `assetsById/browser/provenance` store，无 cursor 分页（目标 §27-28） |
| generation | ⚠️ 有一个 mutationStore | 只有 transient `live` map（合理）；无 `historyByTarget/activeGenerationIds`，历史靠 Query 轮询 |
| job | ❌ 无 | 后端 generation≈single task，Queue 是 `GenerationRead` 列表，**无 Job/Task 二级模型**（目标 §30 的 `jobsById/tasksById/taskIdsByJob` 不存在） |
| agent | ⚠️ 有 agentStore | 仅会话 UI；无 `runsById/proposals/reviewQueue`（目标 §33），无 proposal review/approve/reject（Stage D 未做审批流，合理 MVP，但与 Alpha 清单有距） |
| continuity | ❌ 无 | 完全缺失（后端也未提供 MVP 外能力，属正常未实现） |
| timeline | ❌ 无 | 完全缺失（MVP 外） |
| selection | ✅ 有 | 但缺多选语义：`shotIds: string[]` 只存"当前"，`selectShot` 是覆盖式单选（`[shotId]`），无 `toggleShot/selectShotRange/selectedShotIds`（目标 §20-21） |
| workspace | ⚠️ 有（精简） | 无 tabs / panel 尺寸 / persistence / bottomPanelTab 完整枚举 |

总体：**13 个目标 store，现有仅 4 个，且其中 selection/workspace 最接近目标，generation/agent 为会话态，其余 9 个（project/episode/scene/shot/character/asset/job/continuity/timeline）全部缺席**。但这**不代表错误**——MVP 用 TanStack Query 管理 server 状态是完全合理且符合 AGENTS.md 技术栈的选择；差距在于**没有 Read Model 缓存层与失效策略**，以及**缺少 Job/Editor Tabs/持久化等 Alpha 特有场景**。

---

## 5. 技术债与建议清单（按影响排序）

### 🔴 高影响（架构结构性，建议 Alpha 优先）

1. **无 Read Model 缓存与精确失效（目标 §58-61）。** 现在 `shot.updated/character.updated` 事件只会无差别 `invalidateQueries(["storyboard"])/(["shots"])`，导致切 Storyboard 重拉全列表；ShotInspector 依赖 800ms/3s 轮询兜底。建议引入 `CachedView{data,loadedAt,stale}` 与分实体失效键，把 WS reducer 拆成**分模块 Reducer**（`shotReducer/characterReducer/assetReducer/agentReducer`），align 目标 §54-58，减少无谓 refetch。

2. **无 Job/Task 二级模型 + WS 事件缺口。** 前端只有"单个 generation"概念。Alpha 的 Job 分组、（Scene 批量）进度组合、`BLOCKED/PAUSED/RESUMED` 状态无从表达（UX §63-66）。这需要后端先行提供 `job` API + `JOB_*`/`TASK_*` 事件，前端再加 jobStore。当前是**交叉依赖**——应同步排期。

3. **无 Editor Tabs 与 Workspace 路由模型（目标 §94-96、§162-163）。** 中心区是单 URL view，无法多开。引入 `EditorTab[]/activeTabId/WorkspaceRegistry` 并对齐 `URL = Project/Workspace`、`Tabs = 打开资源` 的分工。这是"Premiere+Cursor"体验的承重墙，宜尽早。

4. **无工作区持久化（localStorage / workspace:projectId，UX §92-93）。** 面板宽度/折叠/tab/selection 全丢。目标明示"布局属 User Workspace State，不写 Project DB"，用 `zustand/persist` 或手动 localStorage 每 project 独立键即可低成本补齐，影响面广但收益明显。

### 🟠 中影响

5. **重复轮询 vs WS 双通道。** `refetchInterval` 5 个点（GenerationQueue 5s、Assets 15s、Settings 10s、ShotInspector 800ms/2s/3s）。ShotInspector 高频轮询在生成期间压力最大。建议统一由 WS 事件驱动 + 仅失败/离线时降级轮询。
6. **`assetStore` 缺失 / 素材来源别扭。** AssetsPage 是 `GET /generations/recent` 里挑 `output_asset_id` 去重，非真正 asset/provenance 查询（目标 §27-28、§164 需要 `AssetBrowserView`）。属后端无 `GET /assets` 的连带缺口，需后端补清单端点后前端建 store。
7. **字符错误码契约偏差。** 前端把字符 409 当作 `error.code === "CONFLICT"` 判断（`ShotInspector` saveShot），而测试 `client.test` 断言 `code:"CONFLICT"`。目标 §47-48 期望 `SHOT_REVISION_CONFLICT`/`CHARACTER_*_CONFLICT` 类细分码。这是**后端错误码命名**问题，前端已做了对的分支策略（invalidate+提示），只需后端对齐。
8. **无虚拟列表。** 500+ 镜头会卡。建议 Storyboard grid/list 与未来 asset browser 引 `react-virtuoso`/`@tanstack/react-virtual`（现阶段 Shot 规模小，属前瞻性债）。

### 🟡 低影响（规范/健壮性）

9. **`dirty_state`/STALE 语义只做了表层。** `shot-card` 用 `dirty_state!=="clean"`→"需重生成"，无 ALPHA 的 STALE/MASTER/LATEST 标签区分。MVP 足够，Alpha 需按 UX §35-39 补版本条状态，且必须坚持"STALE 由后端算、前端不推导"（AGENTS 红线 #11）。
10. **「生成」成功后不自动切 Active（原则七）已正确实现** —— 前端不在 generation.completed 时假定 active 变化，只 `invalidateQueries`。这是符合架构的正确做法，值得保留并作为后续版本 UI 的基础。**无债**。
11. **ErrorBoundary 缺失。** 加一个布局级 React Error Boundary（保 UI 不白屏），配合现有 ApiErrorPanel/NotFoundPage。
12. **主题/布局一致性与最小窗口**（UX §148-157）目前未实现，属产品化妆期，不影响架构。

---

**总结一句话：** 现状在「**Server State 用 TanStack Query、WS 全局 EventRouter 不直达组件、Selection 驱动 Inspector、版本活性由后端判定、revision 409 合理处理**」这几条架构红线上做得扎实且正确；主要 gap 集中在 **Read Model 缓存/失效、Job 模型、Editor Tabs、工作区持久化、虚拟列表** 这些 **Alpha 新增场景**，而非 MVP 缺陷。建议以「Job 事件契约 + read model 缓存 + 工作区持久化」三件套为 Alpha 第一批改造，均属于可以在后端契约对齐后增量推进、不破坏现有功能的重构。
