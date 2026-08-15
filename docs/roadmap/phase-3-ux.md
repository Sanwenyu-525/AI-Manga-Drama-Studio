# Phase 3 — UX & Product Polish

## Goal

把“开发者知道如何操作”提升为“普通创作者能理解状态、恢复错误并高效完成工作”。本阶段以核心路径可用性为准，不追求营销页面、移动端适配或无依据的视觉重做。

## Entry / Exit

**Entry**：Phase 2 的 API、生命周期、审批和 Provider Settings 已稳定。  
**Exit**：小说导入→规划→分镜→生成→版本评审→Director 修改在 Loading/Empty/Error/Offline/Conflict 场景均可完成；键盘、焦点和桌面布局达到生产工具基线。

---

## Epic 3.1 — 一致反馈与恢复

### P3-E1-T01 — 建立统一 Async State、Toast、Skeleton 与 Error Boundary

**背景**：用户需要区分“尚未加载、空数据、正在执行、失败、可重试”，不能把所有情况显示为 spinner 或空白。

**当前问题**：多个 Query/Mutation 没有错误 UI；不同组件自行写 loading 文案；无全局 Error Boundary、Toast、Skeleton 或一致确认 Modal。`ProjectHome` 有较完整状态，但 StudioPage、Storyboard、VersionReview 等不一致。

**目标**：形成少量可复用的深层 UI Module，所有核心页面使用一致状态和错误动作。

**修改范围**：frontend、design docs、tests。

**实现建议**：建立 QueryState/MutationFeedback/ErrorPanel/ConfirmDialog/Toast/Skeleton primitives；错误展示使用统一 ApiError 与 request_id；只迁移核心路径，不一次重写全部 CSS。

**Acceptance Criteria**：

- [ ] 核心页面均区分 loading/empty/error/success。
- [ ] mutation 成功/失败有一致 Toast，危险操作使用可访问确认框。
- [ ] 页面级异常被 Error Boundary 捕获并提供恢复/诊断 ID。
- [ ] Skeleton 保持布局稳定，不使用无限全屏 spinner。
- [ ] 组件测试覆盖错误、重试与无数据状态。

**Priority**：P0  
**Complexity**：L  
**Dependencies**：P1-E4-T01  
**Risk**：过度抽象导致组件 API 膨胀；只抽取三处以上重复模式。

### P3-E1-T02 — 让断线、刷新与后台任务恢复对用户可见

**背景**：WS 是提示通道，用户刷新或短暂断网后仍应知道任务真实状态。

**当前问题**：Queue/Agent Zustand store 不从持久数据水合；事件 gap 仅更新 sequence；EventSocket 后台永久重连。网络错误时 Operation 每 500ms 无限轮询，用户不知道是离线还是任务仍运行。

**目标**：客户端启动、重连和回到前台时以 bootstrap/任务查询恢复；离线/降级状态有明确提示。

**修改范围**：frontend、events、API、tests。

**实现建议**：统一 ConnectionState；指数退避+抖动+可取消轮询；重连/gap/visibility change 触发 scoped reconcile；live store 只保存 UI 临时信息，持久状态来自 Query。

**Acceptance Criteria**：

- [ ] 刷新时 queued/running Generation 与 Agent Run 自动恢复显示。
- [ ] 断线、重连、对账中、失败分别有可理解状态。
- [ ] 网络失败不会 500ms 无限请求，支持用户手动重试/取消。
- [ ] 离开 Studio 后无幽灵 socket/interval 持续运行。
- [ ] 断线期间完成任务后，重连能显示正确终态。

**Priority**：P0  
**Complexity**：M  
**Dependencies**：P1-E4-T02、P2-E3-T01  
**Risk**：重复 reconcile 产生请求风暴；按 project/query key 去重并设置 stale policy。

### P3-E1-T03 — 统一表单冲突、保存、撤销与离开保护

**背景**：创作表单字段多，revision 冲突和误清空会直接损失工作。

**当前问题**：Character 编辑器在 mutation 完成前清空表单，conflict state 未连接；ShotInspector 只有部分 409 处理且无显式 discard；Project/Episode/Scene 表单反馈不一致。

**目标**：所有 revision 实体共享可理解的 dirty/saving/saved/conflict 状态，用户能比较并决定 reload/overwrite/copy。

**修改范围**：frontend、API usage、tests。

**实现建议**：抽取 revision form hook 但保留领域字段组件；mutation 成功后再 reset；缓存本地 draft；离开 dirty 页面提示；Phase 2 ChangeSet 用于 Agent，普通表单仍用轻量 undo/discard。

**Acceptance Criteria**：

- [ ] 保存失败不清空输入，用户可重试或复制内容。
- [ ] 409 显示本地值与服务器最新值，并提供 reload/merge 路径。
- [ ] saving 时防重复提交，成功后 revision 更新准确。
- [ ] dirty 离开有提示，discard 能恢复服务器状态。
- [ ] Character、Shot 与至少一个层级实体有组件测试。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P1-E1-T02、P3-E1-T01  
**Risk**：通用字段级 merge 成本高；首版允许 reload/copy/manual merge，不做 CRDT。

---

## Epic 3.2 — 信息架构与核心旅程

### P3-E2-T01 — 对齐导航、页面层级与真实能力

**背景**：导航应回答用户当前处于项目、分镜、资产、任务还是设置，不应展示无行为入口。

**当前问题**：顶部“素材/工作流/设置”部分为静态文本；Storyboard grid/list toggle 无行为；Canvas 提示文案与完成阶段冲突；真实 Asset/Provider 页面未成为稳定导航节点。

**目标**：所有可见入口要么可用，要么明确 disabled+reason；核心页面层级和返回路径一致。

**修改范围**：frontend、routes、design docs、tests。

**实现建议**：以用户任务而非后端模块重排：Home/Studio/Assets/Activity/Settings；Studio 内保留 Explorer/Storyboard/Inspector/Director/Queue；功能开关统一来源。

**Acceptance Criteria**：

- [ ] 可点击导航均有真实目标、active state 和返回路径。
- [ ] 未开发入口隐藏或带明确原因，不能伪装成可用按钮。
- [ ] 页面标题、面包屑/上下文和 selected project 一致。
- [ ] Assets/Activity/Settings 与 Phase 2 功能可达。
- [ ] 路由刷新和 deep link 不丢项目上下文。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P2-E2-T02、P2-E4-T01  
**Risk**：导航重排会影响已有肌肉记忆；保持 Studio 五区主布局不做无必要重设计。

### P3-E2-T02 — 重做项目创建与导入的确定性流程

**背景**：新建项目是首个信任时刻，不能用示例默认名或把不同起始模式做成同一行为。

**当前问题**：`NewProjectPage.tsx` 默认名为示例项目；blank/storyboard/script/novel 最终都只创建 project+episode。Episode 创建失败会留下孤立 project；Provider 文案指向不存在的切换入口。

**目标**：每种起始方式有明确下一步；跨多 API 创建可恢复，不让用户重复项目。

**修改范围**：frontend、backend（必要 orchestration API）、API、docs、tests。

**实现建议**：使用短向导：项目元数据→起始资产→Provider 检查→创建；后端提供 bootstrap transaction 或前端保存 created project 并进入可恢复状态，不把多个写请求伪装为一个原子操作。

**Acceptance Criteria**：

- [ ] 空白/脚本导入/继续现有项目的行为和文案真实不同。
- [ ] 不再默认提交示例项目名。
- [ ] Episode/导入失败后用户能继续或清理，不重复创建 project。
- [ ] Provider 未配置时可先进入 Studio，并显示明确下一步。
- [ ] 首次创建 E2E 覆盖成功、失败、返回与刷新。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P2-E1-T01、P2-E4-T01、P3-E1-T01  
**Risk**：一步式 transaction 涵盖 LLM 会变成长 HTTP；创建与异步分析必须分离。

---

## Epic 3.3 — 桌面生产效率

### P3-E3-T01 — 实现一致 Selection、多选、键盘与批量动作

**背景**：分镜生产需要高频连续操作，鼠标逐卡片处理会成为主要成本。

**当前问题**：Selection Store 名义支持数组但实际只单选；与 `workspaceStore.activeShotId` 重复。无 Shift/Ctrl 多选、方向键、快捷保存、批量生成/修改入口。

**目标**：形成单一 Selection UI 事实源；高频动作可键盘完成；批量操作复用 Phase 2 的逐项结果契约。

**修改范围**：frontend、state、tests、UX docs。

**实现建议**：先定义 selection reducer（anchor/focus/selected IDs）；删除重复 active shot state 或单向派生；快捷键仅在正确 scope 生效；批量操作先覆盖生成、取消和可逆字段更新。

**Acceptance Criteria**：

- [ ] 单击、Ctrl/Cmd、Shift 范围选择行为一致。
- [ ] Inspector/Director/批量工具读取同一 selection source。
- [ ] 方向键导航、Enter 打开、Cmd/Ctrl+S 保存、Esc 取消有冲突测试。
- [ ] 输入框聚焦时不会误触全局快捷键。
- [ ] 批量结果显示逐项失败且可重试。

**Priority**：P1  
**Complexity**：L  
**Dependencies**：P2-E2-T03、P3-E1-T03  
**Risk**：快捷键与系统/Tauri 冲突；维护一份可发现的 command registry。

### P3-E3-T02 — 增加 Command Palette 与上下文动作

**背景**：随着页面和动作增长，专业用户需要不依赖固定按钮层级的可发现入口。

**当前问题**：上下文菜单、命令面板和统一 action registry 均未实现；相同动作在卡片、Inspector、Queue 中容易重复绑定。

**目标**：常用命令由同一 action definition 驱动按钮、右键菜单和命令面板，并依据 selection/capability 启停。

**修改范围**：frontend、state、tests、UX docs。

**实现建议**：建立轻量 action registry（id/label/shortcut/canExecute/execute），先纳入导航、保存、生成、取消、版本评审，不做插件式命令系统。

**Acceptance Criteria**：

- [ ] Command Palette 可搜索并执行首批高频命令。
- [ ] disabled action 显示原因，不静默无响应。
- [ ] 按钮/菜单/快捷键共享执行与权限判断。
- [ ] selection 改变后命令状态即时更新。
- [ ] 键盘与 screen reader 基础测试通过。

**Priority**：P2  
**Complexity**：M  
**Dependencies**：P3-E3-T01  
**Risk**：过早变成扩展框架；本阶段 registry 只服务内建命令。

---

## Epic 3.4 — 可访问性、布局与感知性能

### P3-E4-T01 — 达到桌面工具可访问性基线

**背景**：键盘和焦点不仅服务无障碍用户，也是高效桌面创作工具的基础。

**当前问题**：部分 icon-only 按钮缺 accessible name；焦点顺序、Dialog focus trap、状态 announcement、reduced-motion 与色彩对比没有系统检查。

**目标**：核心路径满足 WCAG 2.2 AA 的适用条目，完整键盘可操作。

**修改范围**：frontend、styles、tests、design docs。

**实现建议**：采用语义 HTML/ARIA 最小补充；自动 axe + 人工键盘清单；尊重 `prefers-reduced-motion`；不把拖拽作为唯一操作方式。

**Acceptance Criteria**：

- [ ] 所有交互控件有可访问名称和可见 focus。
- [ ] Modal/Palette 焦点进入、循环、关闭和返回正确。
- [ ] 异步成功/失败/进度有合适 live announcement。
- [ ] 关键颜色对比达到 AA；状态不只靠颜色表达。
- [ ] 自动扫描无 critical/serious，核心旅程人工键盘通过。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P3-E1-T01、P3-E3-T01  
**Risk**：第三方组件限制；优先修核心路径并登记剩余例外。

### P3-E4-T02 — 优化查询、轮询、布局持久化与首屏感知

**背景**：性能优化应来自可测瓶颈和用户等待感，而不是提前重写状态栈。

**当前问题**：ShotInspector/VersionReview/Queue 在有 WS 时仍频繁 polling；Query invalidation 过宽；StudioPage 未使用 bootstrap；固定布局在 1024–1100 宽度拥挤，面板尺寸不持久。单 bundle 尚可但会随功能增长。

**目标**：减少无效请求，首屏先显示项目骨架/摘要，面板布局可恢复；建立感知性能预算。

**修改范围**：frontend、backend（bootstrap/查询只做必要调整）、tests、docs。

**实现建议**：使用 bootstrap hydrate；WS 驱动活跃任务、低频 reconciliation 兜底；集中 query key；保存 panel sizes/density；在 profiler 证明收益后做 route lazy loading/virtualization。

**Acceptance Criteria**：

- [ ] Studio 首屏使用 bootstrap，避免同一摘要的多次瀑布请求。
- [ ] 无活跃任务时不进行 0.8–5s 高频轮询。
- [ ] Event 只 invalidate 相关 project/entity query。
- [ ] 面板大小、折叠与密度在重启后恢复，最小 1024 宽可操作。
- [ ] 首屏、交互响应和大 Storyboard 有记录的性能预算与基准。

**Priority**：P1  
**Complexity**：M  
**Dependencies**：P3-E1-T02、P2-E2-T03  
**Risk**：过度缓存导致陈旧状态；Project State 仍以服务器查询为准。

### P3-E4-T03 — 主题与视觉一致性收尾

**背景**：当前 dark-first 符合产品定位，视觉工作应集中在一致性而非为了清单强做 Light Mode。

**当前问题**：局部 spacing、状态色、空态与表单结构随功能追加可能漂移；尚无 visual regression。Light Mode 没有用户证据。

**目标**：核心组件遵守现有 Design Token；建立视觉回归基线。主题扩展仅在需求明确时启动。

**修改范围**：frontend、styles、design docs、tests。

**实现建议**：审计 token 使用和重复样式；Storybook/组件截图只覆盖稳定 primitives；Light Mode 留作 P3 候选，不作为 Phase exit gate。

**Acceptance Criteria**：

- [ ] 核心表单、按钮、卡片、状态、Dialog 使用统一 token/组件。
- [ ] 关键页面在目标窗口尺寸有视觉回归快照。
- [ ] Dark Mode 对比、hover/focus/disabled 状态完整。
- [ ] 没有证据时不新增 Light Mode 维护面。

**Priority**：P3  
**Complexity**：S  
**Dependencies**：P3-E1-T01、P3-E4-T01  
**Risk**：像素级快照脆弱；只覆盖稳定区域和关键状态。
