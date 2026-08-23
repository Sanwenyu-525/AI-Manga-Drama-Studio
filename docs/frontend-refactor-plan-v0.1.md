# AI Manga Drama Studio 前端页面审计与重构计划 v0.1

> 状态：**R0 / R1 Done（2026-08-23）**；样式基线恢复（`2cfcb3d`）、Episode-aware canonical 路由与状态单一事实源（`2a6f143`）已落地；R0/R1 收尾（a11y + 响应式布局）随本计划提交。R2 / R3 / R4 未开始。  
> 审计日期：2026-08-21  
> 适用范围：`frontend/`，不修改后端领域语义与 API/Event Contract  
> 主要读者：前端开发者、技术负责人、后续执行重构的 AI Agent

---

## 1. 结论摘要

当前前端已经覆盖项目主页、项目创建、剧本分析、分镜、镜头检查器、AI Director、素材、生成队列、版本审阅、连续性、时间线、工作流与设置等主要能力，产品闭环基本完整；现阶段的首要工作不是重新设计视觉，而是恢复前端基线并消除多套状态源。

本次审计得到四个优先结论：

1. **必须先恢复样式基线。** Phase 9 合并后，`frontend/src/styles.css` 丢失了 663 行规则，并以一个孤立的 `border-radius` 声明结尾。设置、工作流、素材、AI Director、审批、连续性、时间线等页面或组件已出现明显的未样式化状态。
2. **URL 必须成为当前工作区的唯一事实源。** 现在 URL、编辑标签、持久化快照和 Selection Store 都能决定中心工作区，直接打开 Storyboard URL 时已经复现错误内容。
3. **Selection-aware AI 的上下文目前不可靠。** `selection.workspace` 初始化为 `storyboard` 后没有随路由更新；镜头选中又分别保存在 `selectionStore.shotIds` 与 `workspaceStore.activeShotId`，存在漂移风险。
4. **再做组件与数据层拆分。** `TimelineView.tsx`、`ProjectExplorer.tsx`、`ShotInspector.tsx`、`events/socket.ts` 和 `api/types.ts` 已经承担过多职责，但这些结构调整应排在基线恢复与状态收敛之后。

推荐按 R0–R4 五个阶段执行。R0、R1 为阻断项；完成前不建议开展新的大页面功能。

---

## 2. 审计目标与方法

### 2.1 目标

- 检查当前页面是否符合 `docs/frontend-ux-v0.1.md` 的 Project First、Visual First、Selection Driven AI 与 Progressive Disclosure 原则。
- 找出影响主路径的可复现缺陷。
- 识别页面、状态、数据访问、事件与样式层的结构性债务。
- 给出可以分批落地、每批都能验证且不改变业务语义的重构方案。

### 2.2 本次检查范围

- 路由与页面：`frontend/src/app/router.tsx`
- Studio Shell：`StudioPage`、`WorkspaceHost`、`EditorTabsBar`
- 主要工作区：Script、Storyboard、Assets、Timeline、Version Review
- 左右侧栏与底部 Dock：Project Explorer、Shot Inspector、AI Director、Generation Queue
- 状态：Selection、Workspace、Editor Tabs、Agent、Generation 与持久化
- 数据访问：TanStack Query、Query Keys、REST Client、WebSocket Event Router
- 样式：`frontend/src/styles.css`
- 验证：1440×900 浏览器实机浏览、Vitest、TypeScript/Vite 构建

### 2.3 审计基线

遵守以下事实源与红线：

- `docs/frontend-ux-v0.1.md` §2、§76–93
- `docs/api-event-contract-v0.1.md` §74、§78、§97–99、§123–125、§141
- Project State 与 TanStack Query 管理服务端状态；Zustand 只管理 Selection 与本地 UI 状态。
- WebSocket 只触发领域事件适配与 Query Cache 更新，不暴露后端实现细节。
- 本轮不引入新的 UI 框架、全局状态框架或后端契约变更。

---

## 3. 当前页面与信息架构

| 路由 | 当前页面/工作区 | 主要职责 | 审计判断 |
|---|---|---|---|
| `/` | Project Home | 项目选择、重命名、软删除、封面上传 | 主次结构清楚，可保留 |
| `/projects/new` | New Project | 项目参数与启动方式 | 视觉完成度较高，但启动方式语义重复 |
| `/assets` | Global Assets | 跨项目最近生成素材 | 与项目素材库边界不清晰 |
| `/workflows` | Workflows | ComfyUI 模板只读目录 | 功能存在，当前样式严重缺失 |
| `/settings` | Settings | Provider 状态与 ComfyUI 测试 | 功能存在，当前样式严重缺失 |
| `/projects/:projectId/script` | Script Workspace | 小说导入、AI 分析与 Scene 创建 | 主路径成立，标准视口横向溢出 |
| `/projects/:projectId/storyboard/:sceneId` | Storyboard Workspace | 镜头浏览、选择与生成 | 核心页面，但直接访问 URL 会渲染错误工作区 |
| `/projects/:projectId/assets` | Project Asset Workspace | 项目资产、版本与溯源 | 与全局 Assets 存在重复概念 |
| `/projects/:projectId/timeline` | Timeline Workspace | 排片、预览、素材替换与渲染 | 能力集中在单文件，空状态 404 被当异常请求重试 |
| `/projects/:projectId/shots/:shotId/versions` | Version Review | 版本选择、对比、激活与溯源 | 独立路由合理，需恢复丢失样式 |

当前五区 Studio Shell 与 UX 事实源一致：顶部命令栏、Project Explorer、中心工作区、右侧 Inspector/AI Director、底部任务 Dock。问题主要来自每个区域内部的职责增长，以及导航状态没有形成单向数据流。

---

## 4. 已复现问题与优先级

### P0-1：Phase 9 合并导致样式表被截断

**证据**

- 当前 `frontend/src/styles.css` 约 752–777 行，文件末尾为不属于任何选择器的 `border-radius: 999px;`。
- `HEAD^1` 的同一文件约 1385 行；提交 `501b422` 对该文件显示 `1 insertion, 663 deletions`。
- 合并提交 `9fd8fee` 采用了包含截断样式表的第二父分支版本。
- 静态扫描得到 436 个直接写在 TSX 中的 class token，其中 225 个没有匹配到当前样式表选择器；当前样式表本身包含 265 个 class selector（其中包括未被静态字面量引用的选择器）。这三个数字属于不同集合，不能相加或相减为覆盖率。扫描不包含模板字符串中的动态类名，只用于衡量回归规模。
- 实机页面中，Settings 与 Workflows 已退化成近似浏览器默认排版；缺失规则还覆盖 Asset Browser、AI Director、Proposal、Continuity、Project Settings、Version Compare、Timeline 等区域。

**影响**

- 页面视觉层级、布局、交互反馈和可读性大面积退化。
- 现有组件测试仍能通过，说明当前测试不能发现 CSS 资源丢失。
- 在该基线上做组件拆分，会把“恢复旧样式”“新增时间线样式”“重构结构”混入同一 diff。

**处理原则**

先从合并第一父分支恢复被误删的既有规则，再单独补齐 Phase 9 Timeline 样式；不要直接以当前截断文件为基础重写所有页面。

### P0-2：URL、标签页和持久化争夺中心工作区控制权

**复现**

直接访问：

```text
/projects/:projectId/storyboard/:sceneId
```

URL 与顶部导航显示为 Storyboard，但中心区域稳定显示“添加第一个剧集”或 Script 内容。随后从 Project Explorer 再次点击 Scene，Storyboard 才正常出现。

**原因**

- 路由选择 `StoryboardWorkspace`。
- `StoryboardWorkspace` 在 effect 中调用 `openScene()`。
- 父级 `StudioPage` 也在 effect 中执行 `applyWorkspace(hydrateWorkspace())`。
- `WorkspaceHost` 不根据当前子路由渲染，而是再次根据 `editorTabsStore.activeTabId` 决定 Script/Scene/Shot。
- 子级先打开 Scene tab 后，父级持久化恢复可能把 active tab 覆盖回 Script，形成竞态。

**目标**

- URL 决定当前工作区与实体。
- Editor Tabs 只保存“打开过哪些对象、顺序与标题”，不能覆盖路由。
- 点击 Tab 必须导航到对应 URL；刷新或直接访问 URL 必须重建/激活对应 Tab。

### P0-3：AI Director 的 Selection Context 可能错误

**证据**

- `selectionStore` 将 `workspace` 默认设为 `storyboard`。
- 生产代码没有调用 `setWorkspace()`。
- 用户处于 Script、Assets 或 Timeline 时，Director 请求仍可能发送 `workspace: "storyboard"`。
- 直接访问 Storyboard URL 时，路由参数没有同步到 `selection.sceneId`；只有从 Project Explorer 点击 Scene 才会调用 `setScene()`。
- 当前镜头同时保存在 `selectionStore.selection.shotIds[0]` 与 `workspaceStore.activeShotId`。Storyboard 同时写入两者，Inspector 只读取后者，AI Director 读取前者。

**影响**

这违反 Selection Driven AI 的核心原则：UI 看起来在编辑某对象，但 AI 上下文与 Inspector 可能引用另一套状态。

**目标**

- Project/Episode/Scene/Workspace 从路由派生。
- Shot/Asset 的临时选择只保留一个事实源。
- AI Director 在发起 Run 时，由统一的 `useDirectorContext()` 组装路由上下文与临时选择，不长期复制 Project State。

### P0-4：前端构建当前失败

执行结果：

- `npm test`：24 个测试文件、149 项测试全部通过。
- `npm run build`：失败。

失败原因：

```text
src/features/timeline/TimelineView.test.tsx(5,21):
TS6133: 'beforeEach' is declared but its value is never read.
```

这说明测试通过不等于交付可构建。R0 完成标准必须同时包含 test 与 build。

### P1-1：标准桌面视口下 Studio 尺寸预算失衡

在 1440×900 下：

- Shell 默认左栏约 300px、右栏约 380px，加上两个 Resize Handle 后，中心区约 750px。
- `.episode-panel` 设置 `min-width: 920px`，Script Workspace 必然出现横向滚动。
- `@media (max-width: 1220px)` 与 `@media (max-width: 1100px)` 将 `.app-shell` 改为 3 列，但主 Grid Areas 仍按 5 列（含两个 handle）定义，响应式规则与实际 DOM 不一致。
- 时间线可有自己的横向画布，但 Shell、Script、Storyboard、Assets 不应产生页面级横向滚动。

### P2-1：导航激活态与真实页面不一致

`StudioPage` 中 Script 导航使用 `!onStoryboard` 判断激活，因此 Assets 和 Timeline 页面也会激活 Script。顶部的“导演画布”实际只是切换右侧 AI Director 面板，并不是文档中定义的 Director Canvas，命名会误导用户。

### P2-2：新建项目的四种启动方式实际只有两种行为

- “导入小说”与“导入剧本”都只创建 Project + Episode，然后进入同一个 Script 页面。
- “空白项目”与“已有分镜”都只创建 Project，不创建 Episode，也进入同一个 Script 空状态。
- Stepper 展示“项目设置 → 导入 → AI 分析”，但当前页面只实现第一步。

应选择以下之一：

1. 在本轮收敛为“创建首集”和“仅创建项目”两类真实行为；或
2. 后续实现完整向导后再恢复四种入口。

不应继续保留四个看似不同但结果相同的选项。

### P1-2：空状态通过异常请求表达

Timeline 页面在尚未创建时间线或最终视频时，请求返回 404；TanStack Query 默认重试一次，实机看到 3 次 404 控制台错误。这里的 404 是合法空状态，应由查询层显式映射为 `null`，并关闭该状态的重试，而不是让页面把异常转换为空状态。

### P2-3：核心文件职责过重

| 文件 | 当前规模 | 混合职责 |
|---|---:|---|
| `api/types.ts` | 912 行、81 个导出类型 | Project、Agent、Generation、Continuity、Timeline 全部 DTO |
| `TimelineView.tsx` | 716 行 | 查询、编辑状态、拖拽、轨道、Clip Inspector、Preview、Media Library |
| `ProjectExplorer.tsx` | 606 行 | Episode/Scene、Character、Location 的查询、CRUD 与 UI |
| `ShotInspector.tsx` | 445 行 | Shot 编辑、冲突、角色、生成、删除、版本、连续性 |
| `events/socket.ts` | 310 行 | Socket 生命周期、序列校验、事件适配、所有领域缓存失效 |
| `GenerationQueue.tsx` | 283 行 | Generation、Job、Task 三套状态与控制动作 |

文件行数不是验收指标；这里的问题是单文件同时包含多个可独立变化的领域职责。该项属于维护性债务，只有在相关 Feature 即将继续变化、现有结构阻碍测试，或缺陷跨越两个以上职责时才启动拆分，不作为 R0/R1 阻断项。

### P2-4：Query Key 与请求逻辑分散

静态统计：

- 生产代码约 90 处直接 `api.get/post/patch/delete`。
- 22 个 Feature TSX 文件直接拼接 REST URL。
- 约 48 处使用原始数组 Query Key，39 处使用原始数组做 invalidation。
- 项目已有 `queryKeys.ts`，但没有成为唯一入口。

结果是 WebSocket、Mutation 与页面查询对同一实体使用不同粒度的 Key，事件路由只能频繁做宽泛失效。

### P2-5：其他次级一致性问题

- 全局 `/assets` 基于 Recent Generations，项目 `/projects/:id/assets` 基于 Asset Library，名称都叫“素材”，但数据语义不同。
- Storyboard Tab 标题使用 UUID 尾部拼成 `Scene Scene 87`，没有使用实际 `scene_number/name`。
- 全局 `styles.css` 同时承载基础样式、Shell 与所有 Feature，任何合并冲突都可能影响整个应用。
- 当前没有覆盖“直接 URL + 刷新”“路由与 AI Context 同步”“CSS 资源完整性”“标准桌面视口无溢出”的测试。

---

## 5. R1 架构决策门槛

本计划提出“URL 表达当前可导航工作区与实体，Zustand 只保存临时选择和布局”。这与当前 `docs/frontend-ux-v0.1.md` §44–46、§82 中由 Selection/Workspace Store 保存 `projectId/episodeId/sceneId/workspace` 的描述不同。

因此，R1 开工前必须先完成以下文档决策：

1. 技术负责人确认本计划的单向状态模型。
2. 同步修改 `docs/frontend-ux-v0.1.md` 的 Selection Model、Workspace Context、Zustand Store 与 Local UI State 章节。
3. 若 Director Selection DTO 的可选字段语义发生变化，同步澄清 `docs/api-event-contract-v0.1.md` §78–80；本计划不要求改变 DTO 字段或后端接口。

在事实源更新获批前，R1 保持 Proposed，不允许代码先行。R0 只恢复已丢失基线，不依赖该架构决策，可以独立执行。

---

## 6. 目标前端模型

### 6.1 单向状态来源

```text
URL
 ├─ projectId / episodeId / sceneId / workspace / shot detail route
 └─ 决定当前页面与 active editor tab

TanStack Query
 └─ Project / Episode / Scene / Shot / Asset / Generation / Timeline

Selection Store
 └─ 当前临时选择：selectedShotIds / selectedAssetIds

Workspace Store
 └─ 面板尺寸、折叠状态、右侧面板 Tab、底部 Dock、已打开标签清单

Agent / Generation Store
 └─ 运行中的临时进度；最终状态仍来自服务端
```

明确禁止：

- 不在 Workspace Store 再保存 `activeShotId`。
- 不在 Selection Store 长期复制 URL 已经表达的 project/episode/scene/workspace。
- 不允许持久化快照覆盖当前 URL。
- 不允许 Editor Tabs 决定路由外的另一份中心内容。

### 6.2 已选定路由方案

R1 采用 Episode-aware 路由，不再保留“继续使用无 Episode URL”这一实现分支：

```text
/projects/:projectId/episodes/:episodeId/script
/projects/:projectId/episodes/:episodeId/scenes/:sceneId/storyboard
/projects/:projectId/episodes/:episodeId/scenes/:sceneId/shots/:shotId
/projects/:projectId/episodes/:episodeId/timeline
/projects/:projectId/assets
/projects/:projectId/shots/:shotId/versions
```

具体语义：

- `script`、`storyboard`、`shot`、`timeline` 分别对应唯一中心内容。
- Shot Editor Tab 使用 `.../scenes/:sceneId/shots/:shotId`，刷新后在中心区打开 Shot Inspector；右侧面板继续由用户选择 Inspector 或 AI Director。
- 关闭活动 Shot Tab 后导航到所属 Scene 的 Storyboard；关闭活动 Scene Tab 后导航到该 Episode 的 Script；Script 基础 Tab 不可关闭。
- 路由中的 Scene 必须属于 Episode、Shot 必须属于 Scene；不匹配时以服务端实体关系生成 canonical URL 并 `replace`，找不到实体时在 Studio Shell 内显示 404/Error State。
- Workspace 持久化快照增加 `schemaVersion`。R1 首次加载时丢弃旧版本的 active tab，仅保留可安全解析的面板尺寸；打开清单按新 URL 重建。

旧路由兼容规则：

- `/projects/:projectId/script` 与 `/projects/:projectId/timeline`：Route Adapter 加载项目 Episode，确定性选择 `episode_number` 最小的一集，然后 `replace` 到 canonical URL；不读取持久化的“最后访问 Episode”。
- 项目没有 Episode 时，旧 URL 保持不跳转并显示“添加第一个剧集”空状态；创建成功后进入新 URL。
- `/projects/:projectId/storyboard/:sceneId`：Route Adapter 读取 Scene/Storyboard 得到 `episode_id` 后 `replace` 到 canonical URL。
- 旧 Route Adapter 只负责兼容和重定向，不参与新页面的 Selection 状态。
- 旧 Route Adapter 作为兼容路由保留到未来单独声明的弃用版本；不在本轮 R4 删除。
- 迁移不修改后端 API；Loading、404、跨项目实体错误必须显式展示。

### 6.3 Selection 生命周期与 Director Payload

Selection 不持久化；刷新后只从 URL 恢复路由实体。临时 Shot/Asset 选择由用户重新建立，Shot Detail URL 除外。

清理规则：

| 变化 | Shot Selection | Asset Selection |
|---|---|---|
| 切换 Project | 清空 | 清空 |
| 切换 Episode | 清空 | 清空 |
| 切换 Scene | 清空；若进入 Shot Detail，则从 `shotId` 建立单选 | 清空 |
| 进入 Script | 清空 | 清空 |
| 进入 Storyboard | 仅保留属于当前 Scene 的选择，否则清空 | 清空 |
| 进入 Shot Detail | 设为 URL 中的单个 Shot | 清空 |
| 进入 Project Assets | 清空 | 由 Asset Browser 点击写入，可单选起步 |
| 进入 Timeline | 清空 | 清空；Clip 选择仍是 Timeline 本地编辑状态，不伪装成 Asset Selection |
| 实体删除或 404 | 清空对应选择并显示空状态/错误 | 同左 |

Director 请求由 `useDirectorContext()` 在提交瞬间生成：

| Route/Screen | `workspace` | `project_id` | `episode_id` | `scene_id` | `shot_ids` | `asset_ids` |
|---|---|---|---|---|---|---|
| Script | `script` | URL | URL | 省略 | `[]` | `[]` |
| Storyboard | `storyboard` | URL | URL | URL | 当前 Scene 内选择或 `[]` | `[]` |
| Shot Detail | `storyboard` | URL | URL | URL | `[URL shotId]` | `[]` |
| Project Assets | `assets` | URL | 省略 | 省略 | `[]` | 当前素材选择或 `[]` |
| Timeline | `timeline` | URL | URL | 省略 | `[]` | `[]` |

Asset Browser 必须在选中、取消选中、离开页面和资产失效时更新 Selection Store；这是 R1 验收的一部分。后端 Selection DTO 不变。

### 6.4 推荐目录边界

以下仅描述 R3+ 的长期边界，不是一次性搬迁清单。保留现有 Feature-first 方向，不做全仓库搬家式重构：

```text
frontend/src/
├── app/
│   ├── router.tsx
│   └── shells/
│       ├── RootShell.tsx
│       └── StudioShell.tsx
├── api/
│   ├── client.ts
│   ├── queryKeys.ts
│   └── contracts/
│       ├── core.ts
│       ├── production.ts
│       ├── agent.ts
│       └── timeline.ts
├── events/
│   ├── socket.ts
│   ├── eventRouter.ts
│   └── handlers/
├── features/
│   ├── storyboard/
│   │   ├── StoryboardPage.tsx
│   │   ├── ShotInspector.tsx
│   │   ├── components/
│   │   └── queries.ts
│   ├── timeline/
│   │   ├── TimelinePage.tsx
│   │   ├── components/
│   │   ├── useTimelineEditor.ts
│   │   └── queries.ts
│   └── ...
└── styles/
    ├── tokens.css
    ├── base.css
    ├── shell.css
    └── features/
```

边界原则：

- 只为有两个以上调用方或需要独立测试的逻辑创建 hook/helper。
- 不建立万能 `components/common`、万能 `useApi` 或新的全局 Store。
- Feature 内可以直接使用 TanStack Query，但 URL、Key、空状态映射集中到该 Feature 的 `queries.ts`。
- 样式先按文件拆分，暂不要求迁移 CSS Modules 或 CSS-in-JS。

### 6.5 大文件拆分目标

以下是触发 R3 条件后的候选边界，不要求一次全部实施。

#### `ProjectExplorer.tsx`

拆为：

- `ProjectExplorerShell`
- `EpisodeTree` / `EpisodeBranch`
- `CharacterLibrarySection`
- `LocationLibrarySection`
- `useProjectTreeMutations`

Episode/Scene 的导航适配保留在 Tree；Character/Location 不再共享同一组件的本地编辑状态。

#### `TimelineView.tsx`

拆为：

- `TimelinePage`：加载、空状态与命令编排
- `TimelineToolbar`
- `TimelineCanvas` / `TrackLane` / `ClipBlock`
- `ClipInspector`
- `TimelinePreview`
- `MediaLibrary`
- `useTimelineEditor`：本地 override、commit、playhead、zoom

拖拽计算继续复用纯函数 `timelineMath.ts`，不要引入新的拖拽框架。

#### `ShotInspector.tsx`

拆为：

- `ShotInspector`：选择与加载边界
- `ShotForm`
- `ShotActions`
- `ShotVersions`
- 现有 `ShotContinuityCard` 保持独立
- `useShotEditor`：表单初始化、dirty、revision conflict 与保存

#### `events/socket.ts`

拆开 Socket 连接生命周期与 Event→Query 映射。建议建立显式表：

```text
event_type → required payload fields → affected query key factory
```

继续使用现有 `StudioEvent` envelope 校验；不在本轮复制后端 DTO 做全事件运行时验证。所有 key 从 `queryKeys` 生成；只有无法定位实体时才使用前缀失效。

---

## 7. 分阶段实施计划

### R0：恢复可交付基线（P0，1–2 人日）

1. 修复 `TimelineView.test.tsx` 未使用导入，使 build 恢复。
2. 以 Git blob `9fd8fee^1:frontend/src/styles.css` 作为完整的 pre-Phase-9 样式基准，恢复整个文件，不从当前截断文件猜测缺失区间。
3. 当前 Phase 9 历史中没有可恢复的 Timeline CSS。新建 `frontend/src/styles/features/timeline.css`，在 `main.tsx` 中排在基准 `styles.css` 之后导入，不再修改基准文件尾部。
4. Timeline CSS 必须覆盖：loading/error/empty、toolbar/status/actions、ruler/playhead、track/lane、Clip 默认/选中/禁用/拖动/左右裁剪、side tabs、Clip Inspector、Preview/final video、Media Library。
5. 删除当前孤立 CSS 声明，确认 CSS 能被 Vite 正常解析。
6. 增加最小页面 smoke checklist：Home、New Project、Settings、Workflows、Script、Storyboard 空/有数据/选中 Shot、Project Assets、Version Review、Timeline 空/有轨道。
7. 测试数据使用 `STUDIO_LLM_MODE=fake` 与 Mock Image Provider 创建临时项目 `Frontend Refactor Audit`：1 Episode、1 Scene、至少 3 Shots、1 个生成 Asset、1 条已排片 Timeline。Checklist 记录运行时生成的 URL，完成后可软删除临时项目。

**验证**

```text
npm test
npm run build
```

并在 1440×900 下保存 checklist 截图。pre-Phase-9 页面不得出现浏览器默认 button/list 排版；Timeline 必须满足第 4 项全部状态，Shell 级无横向滚动。R0 不改变组件 DOM、路由语义或产品行为。

### R1：收敛路由、标签与 Selection（P0，3–5 人日）

R1 拆成可独立审查和回滚的五步：

1. **R1a — Characterization tests**：先为当前正确行为补充保持绿色的测试与共用 harness；每个当前失败场景的目标断言与 R1b–R1d 对应修复放在同一提交中，不提交红色 CI。
2. **R1b — Facts + canonical routes**：批准并更新 UX 事实源；落地 §6.2 的 Episode-aware 路由和旧路由 Redirect/空状态。
3. **R1c — WorkspaceHost + Tabs**：让子路由直接渲染工作区；Tab 点击改为 navigate；增加持久化 `schemaVersion`，旧快照不得覆盖 URL。
4. **R1d — Selection + Director**：按 §6.3 实现清理矩阵，删除 `workspaceStore.activeShotId`，补上 Asset Selection，用 `useDirectorContext()` 生成 payload。
5. **R1e — Navigation polish**：修正顶部激活态；将当前只切换侧栏的“导演画布”改名为“AI Director”。

**验证**

- 直接打开、刷新、前进/后退 Script、Storyboard、Shot Detail、Assets、Timeline 均显示正确内容。
- 从 Project Explorer、顶部导航与 Editor Tab 进入同一对象，URL 和 UI 一致。
- 在 §6.3 的五种 workspace 中发送 Director 请求，payload 与矩阵一致。
- 删除镜头后 Inspector 和 Director Selection 同时清空。
- 旧 localStorage 快照不能把 canonical Storyboard/Shot URL 覆盖回 Script。

### R2：修复 Shell 与响应式布局（P1，1.5–2 人日）

1. 定义 Studio 的最小可用宽度与三档布局：宽屏、标准桌面、紧凑桌面。
2. 修正 5 列 Grid 与 Resize Handle 在媒体查询下的列定义。
3. 移除 Script 的固定 `min-width: 920px`，让 Analysis Workspace 在标准桌面下改为两列/单列或可控内部滚动。
4. 明确只有 Timeline Canvas 可以横向滚动；其他页面不得产生页面级横向滚动。
5. 为顶部状态区建立优先级：主导航 > 主操作 > 状态文本；宽度不足时先隐藏次要状态。
6. 检查 New Project、Version Review 与 modal 在 1220、1440、1920 宽度下的可用性。

**验证**

- 1440×900：Shell 无页面级横向滚动，Script 主操作完整可见。
- 1220×768：可通过折叠侧栏完成主路径，顶部主操作不被挤出。
- 1920×1080：Storyboard 卡片密度与 Inspector 宽度不过度拉伸。

### R3：按证据拆分数据与组件边界（P2，单独估算）

R3 不纳入 R0/R1 的交付承诺。先做两项已证实有直接收益的工作，每项独立提交：

1. 所有 Query/Mutation/Invalidation Key 改用 `queryKeys`；为 Timeline 预期 404、revision conflict 与常用 invalidation 组合建立 Feature Query helper。
2. 将 Socket 连接生命周期与 Event→Query Key 映射分开；沿用现有 `StudioEvent` 基础校验，不在本轮为每个事件手写一套重复的运行时 DTO validator。

Project Explorer、Shot Inspector、Timeline、Generation Queue 只在满足以下任一条件时单独立项拆分：

- 下一项需求会再次修改该职责；
- 现有结构无法对目标逻辑做独立测试；
- 一个已复现缺陷跨越两个以上职责；
- 已出现第二个真实调用方。

拆分时保持 DOM、className 与行为不变。`api/types.ts` 分包、OpenAPI 类型生成、全量 CSS 目录重组分别立项，不与组件拆分捆绑。

### R4：一致性收尾与回归测试（P1/P2，2–3 人日）

1. 统一 Loading、Empty、Error、Conflict 的页面表现。
2. 明确 Global Assets 与 Project Assets 的命名和入口；若保留全局页面，命名为“跨项目素材”。
3. Tab 标题改用真实 Episode/Scene/Shot 编号与名称。
4. 增加路由刷新、Selection Context、期望 404、事件缓存失效测试。
5. 增加关键页面的视觉 smoke 基线或最小 E2E，不依赖真实 LLM/ComfyUI。
6. 删除只由本次重构产生的废弃 Store 字段、临时迁移分支与孤立 CSS；保留 §6.2 的兼容 Route Adapter。

---

## 8. 建议提交序列

每个提交只表达一个行为变化：

```text
fix: make frontend build pass
fix: restore frontend styles lost in phase 9 merge
feat: add baseline timeline workspace styles
test: characterize existing workspace behavior
docs: align frontend ux state ownership with canonical routes
fix: add episode-aware studio routes and legacy redirects
fix: derive workspace host and tabs from route
fix: version and migrate workspace persistence
fix: unify shot selection source
fix: synchronize director context with route
fix: repair studio responsive grid
refactor: centralize feature query keys and invalidation
refactor: separate event socket lifecycle from query routing
```

大组件拆分不进入固定序列，满足 R3 启动条件后另行立项。构建修复、663 行样式恢复和新 Timeline 样式必须是三个独立提交。

---

## 9. 验收标准

### 9.1 功能

- 用户可从 Project Home 完成：打开项目 → 导入文本 → 进入 Scene → 选择 Shot → 修改/生成 → 查看版本 → 进入 Timeline。
- 所有 Studio 子路由可直接访问与刷新。
- 旧 Studio URL 会按 §6.2 进入 canonical URL 或合法空状态。
- Editor Tab、Project Explorer、顶部导航与浏览器前进/后退保持一致。
- AI Director 收到的 Selection 与当前 UI 一致。
- 旧 workspace localStorage 快照不会覆盖当前 URL。
- Generation/Agent/Timeline 的长任务仍遵守现有 202 + Event 流程。

### 9.2 视觉与布局

- Settings、Workflows、Assets、AI Director、Proposal、Continuity、Timeline、Version Review 均有完整样式。
- 1440×900 不出现 Shell 级横向滚动。
- 侧栏折叠、拖拽尺寸和持久化继续有效。
- Timeline 的横向滚动被限制在时间线画布内。

### 9.3 工程质量

- `npm test` 全部通过。
- `npm run build` 通过。
- 当前 149 项测试不减少；新增测试覆盖路由事实源与 Director Context。
- Query Key 不再在 Feature 组件中使用未经登记的原始数组。
- 不新增万能全局 Store，不将服务端实体复制进 Zustand。
- API/Event DTO 与 `docs/api-event-contract-v0.1.md` 保持一致。

---

## 10. 风险与回滚

| 风险 | 预防措施 | 回滚点 |
|---|---|---|
| 样式恢复与 Phase 9 新样式冲突 | 以第一父分支整个文件为基准，再单独新增 Timeline CSS；页面逐一 smoke | R0 的样式恢复与 Timeline CSS 两个提交 |
| 路由迁移破坏已有链接 | 保留旧路由 Redirect；先加适配测试 | Route Context 提交 |
| Selection 收敛影响 Inspector/Director | 先增加一致性测试，再删除 `activeShotId` | Unified Selection 提交 |
| 事件失效过窄导致 UI 不刷新 | 建立 event→query 矩阵，保留短期前缀失效兜底 | Event Router 提交 |
| 大组件拆分造成无意义 diff | 保持 DOM 与 className 不变，禁止同时视觉改版 | 每个 Feature 独立提交 |

---

## 11. 非目标

本轮明确不做：

- 重做品牌视觉或更换整体设计语言。
- 引入 Redux、MobX、新 UI Kit、CSS-in-JS 或拖拽框架。
- 改变后端 Service、Repository、Agent 或 Generation 生命周期。
- 新增多人协作、云素材库、完整 Director Canvas。
- 为未来需求建立抽象层或插件系统。

---

## 12. 开工顺序

最小正确顺序：

```text
恢复样式与构建
→
URL/Selection 单一事实源
→
Shell 响应式
→
组件与数据层拆分
→
一致性与回归测试
```

如果资源只允许做一轮，至少完成 R0 + R1。它们直接修复当前可见回归，并恢复 AI-native UX 最关键的 Selection 可信度。

---

## 13. 审计复现命令

### 13.1 CSS 合并回归

```powershell
git show --stat --oneline 501b422 -- frontend/src/styles.css
git show HEAD^1:frontend/src/styles.css | Measure-Object -Line -Character
git show HEAD^2:frontend/src/styles.css | Measure-Object -Line -Character
Get-Content frontend/src/styles.css -Tail 12
```

预期可见：Phase 9 提交对样式表为 `1 insertion, 663 deletions`，第一父分支文件明显更长，当前文件尾部存在孤立声明。

### 13.2 静态 class token 扫描

```powershell
$cssSource = Get-Content -Raw frontend/src/styles.css
$selectors = [System.Collections.Generic.HashSet[string]]::new()
[regex]::Matches($cssSource, '\.([A-Za-z_][A-Za-z0-9_-]*)') |
  ForEach-Object { [void]$selectors.Add($_.Groups[1].Value) }

$classTokens = [System.Collections.Generic.HashSet[string]]::new()
Get-ChildItem frontend/src -Recurse -Filter *.tsx | ForEach-Object {
  $tsxSource = Get-Content -Raw $_.FullName
  [regex]::Matches($tsxSource, 'className\s*=\s*["'']([^"'']+)["'']') |
    ForEach-Object {
      $_.Groups[1].Value -split '\s+' | ForEach-Object {
        if ($_ -match '^[A-Za-z_][A-Za-z0-9_-]*$') {
          [void]$classTokens.Add($_)
        }
      }
    }
}

$missing = @($classTokens | Where-Object { -not $selectors.Contains($_) })
"used-static=$($classTokens.Count) css-selectors=$($selectors.Count) missing=$($missing.Count)"
$missing | Sort-Object
```

当前审计结果约为 `used-static=436 css-selectors=265 missing=225`。该正则不解析模板字符串、条件拼接或组合选择器，只用于发现大规模资源丢失；R0 后数值应显著下降，但不设为零值硬门槛。

### 13.3 前端验证

```powershell
Set-Location frontend
npm test
npm run build
```

当前基线为 149 项测试通过、build 因 `TimelineView.test.tsx` 的未使用 `beforeEach` 失败。
