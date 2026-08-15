# Design QA — AI Manga Drama Studio

## Comparison target

- Source visual truth:
  - `stitch_ai_manga_drama_studio/project_home_director_s_console/screen.png`
  - `stitch_ai_manga_drama_studio/new_project_import_director_s_console/screen.png`
  - `stitch_ai_manga_drama_studio/novel_analysis_preview_director_s_console/screen.png`
  - `stitch_ai_manga_drama_studio/screen.png`（Storyboard）
- Rendered implementation: `http://localhost:4173/`
- Browser-rendered evidence:
  - `.design-qa/preview-home.png`
  - `.design-qa/new-project-implementation.png`
  - `.design-qa/analysis-implementation.png`
  - `.design-qa/storyboard-implementation.png`
  - `.design-qa/inspector-implementation.png`
  - `.design-qa/director-implementation.png`
  - `.design-qa/version-review-implementation.png`

## Viewport and normalization

- Source pixels: 1600 × 1280, desktop dark theme.
- Browser CSS viewport: 1600 × 1280; browser-reported device pixel ratio: 1.25.
- Full-page captures: 1600 × 1280. Home and New Project were compared at full size.
- Studio viewport captures: 1600 × 1065 because the desktop app browser reserves host chrome vertically. The matching source was cropped to the same 1600 × 1065 top viewport before comparison; no scaling was applied.
- Narrow desktop check: 1100 × 900 CSS pixels, no horizontal document overflow (`scrollWidth === innerWidth`).
- State: real local Project State, Stage B fake LLM preview, Stage C Mock Image Provider, Stage D not connected.

## Full-view comparison evidence

- `.design-qa/home-comparison-final.png`
- `.design-qa/new-project-comparison-final.png`
- `.design-qa/storyboard-comparison-final.png`
- `.design-qa/analysis-comparison-final.png`

The implementation preserves the source composition: near-black multi-panel canvas, amber navigation and primary actions, compact technical typography, thin dividers, vertical manga imagery, five-region Studio shell, storyboard card grid, tri-column analysis review, right inspector, and bottom generation dock.

## Focused region comparison

- New Project: header, settings controls, start-mode cards, vertical cover preview, project specs, and workflow ribbon were checked in the full-size 1600 × 1280 comparison.
- Storyboard: project tree, scene header, shot-card density, selected state, Inspector state, and bottom queue were checked in the 1600 × 1065 comparison and separate Inspector capture.
- Analysis: source editor, scene list, selected scene details, analysis stepper, and confirm action were checked in the analysis comparison.
- Version review and AI Director were checked as implementation-only states because their Stitch references contain known visual/content conflicts (white rendering artifacts, unrelated photography, and Stage D behavior not yet backed by API).

## Required fidelity surfaces

- Fonts and typography: Geist Variable is bundled locally; Chinese uses the system CJK fallback. Weight, uppercase technical labels, numeric alignment, compact small text, and hierarchy are consistent with the references.
- Spacing and layout rhythm: 55–58 px persistent bars, 300/920/380 Studio tracks at 1600 px, thin panel separators, compact 4–7 px radii, and dense shot cards match the desktop production-console intent.
- Colors and tokens: `#0D0F13`, `#14171D`, `#1B1F27`, `#E8A33D`, muted steel text, green success, and red failure states are consistently tokenized.
- Image quality: the supplied 768 × 1376 manga asset is used directly and cropped with `object-fit: cover`; no CSS art, emoji, handcrafted SVG, or placeholder glyph replaces visible artwork. Existing Mock Provider assets remain visible when they are the server truth.
- Copy and content: UI copy is unified to Chinese while preserving stable production terms such as Shot, Storyboard, Project State, ComfyUI, V1/V2, and AI Director.
- Icons: all UI icons come from Phosphor Icons with a consistent optical weight; no inline SVG is used.
- Accessibility: semantic buttons/links/labels, focus-visible outlines, disabled states, alt text, and color-plus-text status indicators are present.

## Primary interactions tested

- Project selection and opening the Studio.
- New Project form: aspect ratio, FPS, and start mode controls.
- Episode source editor and non-writing AI analysis preview.
- Scene selection → Storyboard loading.
- Shot selection → Inspector loading and revision-aware fields.
- Top-bar generation action remains disabled without a selected Shot and becomes enabled after Shot selection.
- AI Director tab and honest Stage D locked state.
- Generation queue expand/collapse and history tab.
- Version review selection and active-version state.
- Production preview console: no warnings or errors in a fresh browser tab.
- `npm run build`: passed.

## Comparison history

### Pass 1

- [P2] Home cover and feature card were too short relative to the source, weakening the vertical editorial composition.
- [P2] Home content margins and recent-project column were narrower than the 1600 px reference.
- [P2] New Project wordmark auto-placed into the wrong header column.

Fixes:

- Made the cover fill the project feature card with a 720 px minimum and removed the 680 px cap.
- Aligned the Home canvas to a 1440 px content frame with a 400 px recent-project column at the reference viewport.
- Assigned the New Project wordmark and back button to explicit header grid positions.

### Pass 2

- Post-fix evidence: `.design-qa/home-comparison-final.png` and `.design-qa/new-project-comparison-final.png`.
- No actionable P0/P1/P2 visual or interaction findings remain.

## Accepted constraints / P3 follow-up

- Home metrics in the Stitch mock are not displayed because the current API has no project aggregate endpoint; the implementation shows only server-backed project fields.
- The Stitch visual-style picker is omitted because MVP Project State has no corresponding persisted field. Adding a cosmetic-only selector would misrepresent saved behavior.
- Mock Image Provider output is intentionally shown as returned by Stage C; production ComfyUI imagery will replace it without a UI change.
- AI Director shows a truthful Stage D readiness state instead of fabricating approval or completed runs.

final result: passed

## UI 修复 Pass 3 (2026-08)

针对桌面端界面问题的检查与修复（/ui-ux-pro-max 审查），构建与 12 项前端测试通过，无 console 错误：

- [P1] 角色选择 chip 内 checkbox 受全局 `input` 规则污染（100% 宽 + 边框 + 9px 内边距）→ 显式重置为 14px 无边框控件，与文字垂直居中。
- [P1] `.icon-button.ok`（角色创建确认按钮）样式缺失 → 补绿色成功态（含 hover/disabled）。
- [P2] `--faint` 对比度 2.9:1 → 提亮至 `#7b8494`（对面板背景 ≥4.5:1），改善 10–12px 次级小字可读性。
- [P2] Storyboard 工具栏进度条标签硬编码 `left:232px` 绝对定位 → 改 flex 布局（`.continuity-track` + 标签），窄屏不再错位。
- [P2] `.episode-panel` `min-width:920px` 导致 ≤1100px 窗口横向溢出 → media query 压缩至 0，三列预览同步收缩。
- [P2] `.btn.danger` 使用未定义 `--danger` 令牌 → 统一到 `--red`。
- [P3] 补 hover 反馈：分段控件 / 视图切换 / 队列 tab / 角色 chip；补 disabled 态：输入控件 / 视图切换 / 文本操作。
- [P3] AI Director 计划步骤 `✓✗●○` 字符图标 → Phosphor SVG（Check/X/Circle），与全站图标体系一致。
- [P3] 版本审片页候选版本状态卡 → `candidate` 类琥珀色语义（当前版本保持绿色）。
- [P3] Shot 卡片缩略图 `loading="lazy"`；新建项目页按钮补 `type="button"`。

Playwright 数值验证：1600px 下进度条标签位于轨道右侧同行、工具栏与文档无横向溢出；1024px 下 episode-panel 内部无横向溢出；审片页选中非 active 版本时 `candidate` 类生效；checkbox 计算样式为 13×14px 无边框无内边距。

## UI 修复 Pass 4 (2026-08) — 顶部导航栏

ProjectHome 顶部导航栏（标题栏下方 56px）结构与设计一致：logo + 标题在左（x=18），四 tab 精确居中（导航中心 == 顶栏中心），「新建项目」按钮在右，1600px 下无重叠。发现并修复两个 UX 缺陷：

- 四个 tab 原为 `<span>` 纯文本（不可点击、无 hover、无说明）→ 语义化为 `<button>`：「项目」active（`aria-current="page"` + hover 高亮），「素材 / 工作流 / 设置」disabled + tooltip（后续接入），诚实锁定。
- 窄窗口（≤1220px）固定 260px 列挤压导航 → 压缩为 200px 列 + 缩小 tab 间距。

Playwright 验证：1600px 与 1100px 下均无重叠、无文档横向溢出；disabled tab hover 不变色、active tab hover 变琥珀亮色；无 console 错误。

## UI 改造 Pass 5 (2026-08) — 原型占位 → 功能化改造

按真实后端能力把页面原型占位改造为可用功能（无后端支撑的保持诚实锁定）：

- **顶部导航真实化**：抽共享 `ConsoleTopbar`（ProjectHome/Assets/Settings 三页共用）；「素材」→ `/assets`、「设置」→ `/settings` 可点击，「工作流」无后端 API 保持锁定 + tooltip。
- **素材页 `/assets`**（新）：真实数据 = `GET /generations/recent` 过滤 `output_asset_id`（按资产去重）；网格缩略图 + lightbox 大图预览（`/assets/{id}/content`）+ 项目/镜头/Provider/时间归属。
- **设置页 `/settings`**（新）：真实数据 = `GET /providers`（mock/comfyui_local 状态、能力徽标、base_url）；「测试连接」→ `POST /providers/comfyui/test`，展示 connected/latency/workflow preflight 真实结果（ComfyUI 未运行时如实显示失败）。
- **Storyboard 列表视图**：view-toggle 双按钮真实切换（网格/列表）；列表行 = 缩略图 + 编号 + 景别 + 角色 + 时长 + 状态徽标 + 选中态。
- **ShotInspector 更多操作菜单**：DotsThree 弹出菜单（全屏审片跳转 / 删除镜头 → `DELETE /shots/{id}` + confirm + 清空选择与 invalidate）；点击外部/ESC 关闭。
- **Studio 导航**：「素材」跳全局素材库；「导演画布」切换右面板 AI Director（active 态联动）；「时间线」无后端保持锁定。

验证：build + 12 项测试通过；Playwright 无 console 错误；素材网格 6 项 + lightbox、列表视图 6 行切换、菜单 2 项 + ESC、导演画布切换、设置页测试连接真实结果（3.8s 超时后显示无法连接）全部通过。

## UI 改造 Pass 6 (2026-08) — 导航重组

- 顶部导航栏（console-topbar）只保留四个 tab（项目 / 素材 / 工作流 / 设置），删除 wordmark 链接与「新建项目」按钮，nav 精确居中（实测中心 800px == 顶栏中心 800px）。
- 「新建项目」按钮移入桌面窗口标题栏（TitleBar），位于拖拽区右侧、窗口控制按钮左侧（36px 全高，hover 反馈）；为此把窗口框架改为 router 布局路由（AppFrame = TitleBar + Outlet），TitleBar 获得路由上下文后可 SPA 跳转 /projects/new。
- 浏览器构建中 TitleBar 仍不渲染（保持纯 web 结构）；首页「新建另一个项目」入口保留。

验证：build + 12 项测试通过；Playwright 浏览器端 topbar 仅含 nav、无 wordmark/按钮、三页一致；模拟 Tauri（注入 `__TAURI_INTERNALS__`）标题栏渲染 drag + 新建按钮 + 窗口控制三段，点击跳转 /projects/new 成功；无 console/pageerror。

## UI 改造 Pass 7 (2026-08) — 四 tab 移入标题栏

- 顶部导航栏（console-topbar）整体移除；四个 tab（项目 / 素材 / 工作流 / 设置）移入桌面窗口标题栏，与「新建项目」按钮、窗口控制按钮构成一体化导航条：drag 区（logo+标题）→ nav（四 tab）→ spacer 拖拽区 → 新建项目 → 最小化/最大化/关闭。
- tab 使用 `useLocation` 驱动 active 状态（项目=/、素材=/assets、设置=/settings），工作流保持锁定；36px 标题栏内 11px 紧凑样式，hover 反馈，active 琥珀色。
- `ConsoleTopbar` 组件删除，三页（项目/素材/设置）直接渲染内容；`.project-home-main` 高度计算去除 56px topbar 偏移（Tauri 下仅剩 36px 标题栏）。
- 浏览器构建中 TitleBar 不渲染 → 浏览器无导航条（纯 web 结构）；桌面端为完整导航。

验证：build + 12 项测试通过；Playwright（模拟 Tauri）：标题栏五段结构、四 tab 跳转与 active 联动、新建按钮跳转、1600px/1100px 均无溢出与顺序错误、无 console/pageerror；浏览器三页渲染正常。

## UI 改造 Pass 8 (2026-08) — 首页桌面化（消除页面级滚动）

选择项目页原为固定最小高度内容（封面 `min-height:720px`、网格 `min-height:660px`），矮窗口下整页滚动，观感像网站。改为桌面应用模式：

- `.project-home-main` 改为 `height:100%` flex 列布局，页面占满视口、永不页面滚动。
- 概览网格 `flex:1; min-height:0` 填满剩余空间；封面 `height:100%; max-height:780px` 自适应窗口高度（矮窗收缩、高窗封顶居中）。
- 侧栏最近项目列表 `overflow-y:auto` 内部滚动（17 个项目时面板内滚动），行高 86→72px 更紧凑；`.project-console` 保留 overflow:auto 作安全兜底。

验证（Playwright + Tauri 模拟）：1600×900 / 1280×800 / 1280×720 / 1920×1080 四种窗口页面滚动均为 0px，封面 542–780px 自适应，侧栏内部滚动 414–730px，主区底部与视口精确对齐，无 console/pageerror；build + 12 项测试通过。

## UI 改造 Pass 9 (2026-08) — 工作流 tab 解锁（真实只读目录）

- 后端新增只读端点 `GET /api/v1/workflows`（backend/app/api/workflows.py）：遍历 WORKFLOW_CATALOG，返回模板 id/文件/默认标记/输出节点/preflight 必需占位符/节点清单/占位符令牌（真实读取 workflows/*.json）。
- 前端新页 `/workflows`（WorkflowsPage.tsx）：模板卡片列表（id、默认徽标、节点数）+ 详情面板（节点类型 chips、占位符令牌、preflight 必需项），只读展示，无编辑。
- 标题栏「工作流」tab 从锁定 span 改为可点击 Link（active 联动）；router 注册 /workflows。
- 契约文档 api-event-contract-v0.1.md 新增 §48.1 Workflow Catalog API 并在 §142 清单登记 /workflows；后端新增 test_workflows_api.py。

验证：后端 97 项 pytest 全过（含新增）；前端 build + 12 项测试通过；Playwright（模拟 Tauri）：工作流 tab 点击跳转 /workflows 且 active、卡片与详情渲染真实数据（7 节点 / 6 节点类型 / 5 占位符）、无 console 错误。

## UI 改造 Pass 10 (2026-08) — 项目页桌面化（全宽布局 + 封面 + 删改）

- **布局**：`.project-home-main` 移除 `max-width:1440px` 居中限制，内容区填满窗口（实测 1600px 下 feature-card 右缘距屏幕仅 28px，原 188px）。
- **封面上传**：后端 Project 加 `cover_path`（alembic 迁移 5f1c9a2b7d40）+ `POST/GET /projects/{id}/cover`（multipart，覆盖式存储，校验扩展名/大小）；DTO 加 `cover_url`；前端封面卡右上「更换封面」按钮（file input → 上传 → invalidate），显示真实封面。
- **重命名**：最近项目行 hover 显示铅笔 → 内联输入框（Enter 保存 / ESC 取消）。
- **删除**：后端 `DELETE /projects/{id}` 软删除并级联 Episode/Scene/Shot/Character（`EVENT_PROJECT_DELETED`）；前端行内垃圾桶按钮 + confirm 对话框，删除后自动落到第一个项目。
- api client 支持 FormData（封面 multipart 上传）。
- 契约文档 §9/§12.1/§12.2 + §142 更新；后端新增 test_project_cover_delete.py。

验证：后端 101 项 pytest 全过（含新增 4 项）；前端 build + 12 项测试；Playwright 全流程：上传封面（img src 切换真实 URL）→ hover 重命名改名成功 → confirm 删除行消失且后端 404，无 console 错误。

## UI 改造 Pass 11 (2026-08) — 首页筛选器（page-heading 占位图标修复）

`/main/div[1]/svg`（SlidersHorizontal）原为纯装饰图标，点击无效果。改为真实的项目状态筛选器：

- 点击弹出下拉菜单：全部项目 / 制作中 / 准备中 / 已完成 / 已归档，每项带真实计数（源自 projects 列表）。
- 选择后项目列表按 status 过滤，标题计数与描述联动（如"0 个项目（已完成）"）；筛选生效时图标琥珀高亮 + tooltip 说明当前筛选。
- 菜单支持点击外部 / ESC 关闭；空筛选结果显示提示行。
- aria-expanded / role=menu 语义完整。

验证：Playwright 实测 17 个项目全为准备中：全部 17 → 已完成 0（列表清空+标题联动+图标高亮）→ 切回全部恢复 17；无 console 错误；build 通过。

## UI 修复 Pass 12 (2026-08) — 剧集树展开/收起修复

资源树剧集行展开状态原由 `selection.episodeId === episode.id` 驱动：再次点击已展开剧集时 setEpisode 同 id 不改变选择，永远无法收起。修复：

- 展开/收起改为独立 UI 状态 `expandedEpisodeId`（toggle）：点击已展开 → 收起（保持选中，工作区不变）；点击未展开 → 展开并选中。
- 剧集行补 `aria-expanded` 语义。

验证：Playwright 2 剧集项目：展开 → 收起 → 连续 3 轮循环 aria-expanded true/false 稳定，children 显隐正确；无 console 错误；build + 12 项测试通过。

## UI 修复 Pass 13 (2026-08) — 行操作按钮与封面滤镜

- **行操作按钮**：原绝对定位右侧常显（active 行）会遮住「准备中」状态字 → 改为行内 flex 布局（status 与 actions 并排），闲置 opacity 0、hover 淡入（opacity 1），focus-within 保持键盘可达；实测 status 右缘 351 < actions 左缘 367，无重叠。
- **按钮边框**：重命名/删除按钮去边框（border:0、透明背景、hover 才出现图标色/底色）。
- **封面黑白**：`.project-cover` 的 `grayscale(1)` 滤镜只作用于默认占位图（新增 `cover-default` 类）；上传封面不套滤镜，彩色原样显示。
- 修复 button 嵌套 button（validateDOMNesting 警告）：actions 移出行按钮，改为 wrap 内 flex item。

验证：Playwright 实测 idle opacity 0 / hover 1、无重叠、边框 0px、上传封面 filter none、默认封面 grayscale(1)；无 console 警告；build 通过。

注：验证期间发现项目库仅剩 1 个（其余被用户侧删除操作移除），属正常数据状态。

## UI 改造 Pass 14 (2026-08) — 素材/工作流/设置页返回按钮

素材页、工作流页、设置页此前没有返回入口（Studio 内跳转后回不去）。修复：

- 三页 page-heading 右上角新增返回按钮：从 Studio 导航进入（`navigate(..., { state: { fromProject } })`）显示「返回工作台」→ `/projects/{id}`（自动重定向当前 workspace）；从标题栏 tab 进入显示「返回项目」→ `/`。
- StudioPage「素材」跳转携带 `fromProject` 来源。

验证：Playwright：Studio → 素材 → 返回工作台（href 指向来源项目，点击回 Studio 且 app-shell 正常渲染）✅；标题栏 → 素材/工作流/设置 → 返回项目 ✅；无 console 错误；build 通过。注：Studio 路由现为 URL 驱动（/projects/:id → /script），返回后 URL 带 /script 属预期行为。

## UI 改造 Pass 15 (2026-08) — 工作区左右面板可收起

工作区（Studio）左侧资源树（explorer）与右侧检查器（right-panel）新增收起/展开：

- **收起按钮**：资源树标题栏右侧（CaretLineLeft，aria-label「收起资源树」）；右面板 tab 栏右侧（CaretLineRight，aria-label「收起右侧面板」），hover 有反馈。
- **收起态**：面板列宽 300/380 → 30px，内容卸载，保留 1px 分隔线；窄条上 sticky「展开」按钮（CaretLineLeft/Right 反向），点击恢复。
- **动画**：grid-template-columns 180ms ease 过渡；双面板可同时收起（30 / 1fr / 30），工作区获得最大空间。
- 状态存 workspaceStore（explorerCollapsed / rightPanelCollapsed），会话内保持。

验证：Playwright 收起/展开全流程：300/920/380 → 30/1190/380 → 300/920/380；右面板 300/1270/30 → 恢复后 tabs 与 inspector（选中镜头态）完整还原；双收起 30/1540/30；无 console 错误；build + 12 项测试通过。

## UI 改造 Pass 16 (2026-08) — 剧集/场景基础 CRUD

此前剧集与场景仅有创建/浏览，补齐重命名与删除：

- **后端**：`DELETE /api/v1/episodes/{id}`（软删除并级联场景/镜头）；补事件 `episode.created/updated/deleted`、`scene.deleted`（create/update 时补发）；`delete_scene` 补发 `scene.deleted` 事件（project_id 经 episode 关联解析）。
- **前端**（ProjectExplorer）：剧集行与场景行 hover 显示操作（铅笔重命名 / 垃圾桶删除，无边框小图标、focus-within 可达）；重命名内联输入（Enter 保存 / ESC 取消）；删除带确认框。
  - 删除当前打开的 Storyboard 场景 → 自动跳回剧本视图；删除选中剧集 → 落到第一个剩余剧集；删除展开中的剧集 → 同步收起。
- 后端新增 test_episode_scene_crud.py（4 项：剧集改名/删除级联、场景改名/删除）。
- 契约文档 §143 事件清单补 episode/scene 事件。

验证：后端 105 项 pytest 全过；前端 build + 12 项测试；Playwright 全流程：剧集重命名、场景重命名、删除场景（含当前打开场景自动跳回剧本）、删除剧集，均无 console 错误。
