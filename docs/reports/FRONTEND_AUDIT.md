# FRONTEND_AUDIT.md — 前端系统性审计（2026-08-31）

> 审计范围：`frontend/src` 全部生产代码（~80 文件，忽略 `__tests__`）。
> 方法：3 路并行扫描（UI 一致性 / 生成链路 / 架构与代码质量）+ 核心文件人工复核。
> 原则：只报实证问题（文件:行号），不打分颜值；不提议推翻现有架构。

---

## Current Architecture

- **技术栈**：React 18 + TypeScript + Vite + Zustand（UI State）+ TanStack Query v5（Server State）+ React Router v6 + Phosphor Icons + Geist Variable。无组件库，手写 CSS（`styles.css` ~8000 行，DeepSeek Harness 暗色四层 token）。
- **壳层**（router.tsx `AppFrame`）：AppHeader + ProjectContextBar（面包屑）+ ActivityRail + 路由页 + SystemStatusBar，全屏冻结壳，结构清晰。
- **路由**：`/projects/:id` 下 15+ 子工作区（workspace/source/director/characters/storyboard/shots/knowledge/continuity/script/storyboard/shots/timeline/assets/prompts/production-log），全部**静态 import，无 React.lazy**。
- **API 层**：`api/client.ts` 统一封装（base URL / session token / 30s 超时 / ApiError{code,requestId}），**零绕过**（features 下无直接 fetch）；`queryKeys.ts` 单一事实源。
- **事件层**：`events/socket.ts` WS + 指数退避重连 + sequence 去重/缺口 reconcile，实现健壮。
- **状态**：6 个 Zustand store 全部为 UI/瞬时状态，`stores/persistence.ts` 唯一持久化 owner（debounce + sanitize），**无 Server State 重复存储**。

**总体评价：纪律性极强的代码库**——0 个 `any`、0 个 `console.log`、0 个 TODO、0 个空 catch、0 处组件硬编码颜色、按钮 primary 密度克制。主要债务集中在**错误反馈的最后一公里、生成链路状态表达、产物导出能力**三处，均为可控局部修复。

---

## Current UI System

- **Token**（styles.css:48-73）：`--abyss/--workbench/--panel/--elevated/--overlay` 五层底色、`--ink/--muted/--faint` 三级文字、`--accent/--orange/--green/--red` 语义色 + 各自 `-dim`、`--radius:8px`/`--radius-sm:6px`。组件层 **0 硬编码颜色**（14 处内联 style 全部无颜色）。
- **按钮**：无 Button 组件，统一 class 约定 `.btn`（styles.css:491）+ `.primary/.secondary/.compact/.tiny/.danger` 变体 + `.icon-button`。主按钮密度优秀（SettingsPage 30+ 按钮仅 1 个 primary）。
- **Loading**：9 种方案并存（按钮文案替换为主流、btn-spinner、两套重复 shimmer keyframes、orbit spinner、5 个命名各异的 `*-loading` class、进度条）。
- **Modal/Lightbox**：无统一原语，3 套各自实现 overlay（ProjectSettingsModal、DirectoryBrowserModal、AssetsPage lightbox），backdrop/ESC 逻辑重复 3 次。
- **字体排版**：body 13px + tabular-nums，层级靠 muted/faint + 字重，未见字号混乱问题。

---

## Problems（按严重度）

### P0 — 破坏核心工作流的缺陷

| # | 问题 | 证据 |
|---|---|---|
| P0-1 | **批量生成提交失败完全静默**：StoryboardView 的 `generateImages`（批量出图主入口）无 onError/isError，点「生成待生成镜头」失败后无任何反馈——直接违反「点击生成后页面无反馈」红线 | StoryboardView.tsx:113-122 |
| P0-2 | **约 12 个核心 mutation 静默失败**：GenerationQueue 的 retry/cancel + JobRow 的 pause/resume/cancel/retry（GenerationQueue.tsx:105-112, 312-315）；ProjectHome 的 rename/deleteProject/uploadCover（ProjectHome.tsx:144-173）；ShotInspector 的 activate 设当前版本（ShotInspector.tsx:523-529）；VersionReviewPage activate（:55-61）；EntityVersionBlock 设 MASTER（:69-74）；EpisodePanel createEpisode（:126-135）；StoryboardView createShot（:82-89）。已有好模式（ApiErrorPanel）但接入不全 |
| P0-3 | **审片页不支持视频版本**：VersionReviewPage 主画布/对比板用 `<img>` 渲染所有 media_type，视频版本无法播放且无 onError 提示；而 ShotInspector 是有 video 分支的，行为不一致 | VersionReviewPage.tsx:171-175, 352 |
| P0-4 | **空态「AI 生成 Storyboard」无防重复提交**：`onClick={() => generateShotPlan.mutate()}` 无 disabled，可连点重复提交分析任务（同文件 :169/:238 的同类按钮均有守卫） | StoryboardView.tsx:277 |

### P1 — 显著损害体验/工程质量

| # | 问题 | 证据 |
|---|---|---|
| P1-1 | **任务状态表达缺陷**：队列行 className 硬编码 `running`（GenerationQueue.tsx:154），queued 与 running 无视觉区分；**cancelled 显示绿色成功 CheckCircle**（图标逻辑反了，:186-190）；错误信息后端原文直出无友好化（:198-200）；无已耗时显示 | GenerationQueue.tsx |
| P1-2 | **产物零下载能力**：图片/音频/视频版本无任何下载按钮；FINAL_VIDEO 仅 `<a target="_blank">` 打开而非下载（TimelineView.tsx:920-923）。生产工具核心产物无法导出 |
| P1-3 | **图片 lazy 覆盖率低**：全站仅 4 处 `loading="lazy"`；热点缺失——VersionStrip 版本条、VersionReviewPage 侧栏、EntityVersionBlock、TimelineView MediaLibrary（一次最多 100 张，:967-995）、时间线 clip 缩略图。ShotInspector 版本预览直接加载 `/content` 原图而非 `/thumbnail` |
| P1-4 | **formatDate 7 处重复实现**：7 个组件各自私有 `Intl.DateTimeFormat` 同构代码，而 `lib/format.ts` 只有 6 行 formatBytes | AssetsPage:152、EntityVersionBlock:156、PromptsHistoryPage:122、ProvenancePanel:211、ProductionLogPage:157、ProjectHome:463+477、VersionReviewPage:384 |
| P1-5 | **视频预览未控 preload**：ShotInspector `<video>` 无 preload，版本轮询期间（800ms~3s refetch）反复自动拉流 | ShotInspector.tsx:555 |
| P1-6 | **7 处列表行内图标按钮无 aria-label**（仅有 title，不构成可靠 accessible name） | GenerationQueue:166-172、CharactersSection:100-108、DocumentsSection:352、ProjectHome:291-305、TimelineView:895-903 |
| P1-7 | **TimelineView 多处吞错**：replaceAsset `.catch(() => onChanged())` 完全吞、删除片段吞错、updateClip/saveText 非 409 吞 | TimelineView.tsx:652-700, 853-862 |
| P1-8 | **SettingsPage 巨石文件 1927 行**：25 useState + 16 useMutation + 9 个内联组件，三张 ConfigCard 各自重复 saved/touched/error 表单状态机 | SettingsPage.tsx |
| P1-9 | **TimelineView 片段配音按钮无 pending 守卫**：仅校验 text 非空，可连点 | TimelineView.tsx:818 |
| P1-10 | **PipelineBar 双 primary 同屏**：「一键成片」与「确认」两个 primary 并存，违反一屏一个主 CTA | PipelineBar.tsx:131,136 |

### P2 — 一致性/优化项（低风险顺手处理）

| # | 问题 | 证据 |
|---|---|---|
| P2-1 | border-radius 裸值 ~47 处游离 token 外：6px/8px 裸值 10 处与 token 同值；`999px`(24 处) 与 `99px`(4 处) 两套 pill 写法并存；3px/4px/5px/7px/10px 孤立值 | styles.css |
| P2-2 | 两套重复 shimmer keyframes（`skeleton-shimmer` 1.4s 与 `sk-shimmer` 1.6s 功能相同） | styles.css:4795-4825, 7882-7921 |
| P2-3 | 无 React.lazy：SettingsPage(1927 行)/TimelineView/VersionReviewPage 等低频重路由全部进首屏 chunk（桌面 Tauri 影响小，非紧急） | router.tsx |
| P2-4 | `useOperationPolling` 轮询失败无退避/上限，cleanup 后 catch 分支新设 timer 不会被清理 | useOperationPolling.ts:37-45 |
| P2-5 | 弱空状态：GenerationQueue/CharactersSection/DocumentsSection 仅一行文案无 CTA；EpisodePanel 无剧集时无空态引导；AssetBrowserView/Timeline MediaLibrary 空态纯文案 | 各文件 |
| P2-6 | ShotInspector 单列长滚动：生成参数与版本结果混排，点生成后需滚动看结果（结构性问题，暂不动） | ShotInspector.tsx |
| P2-7 | 5 处版本/素材选择 UI 重复实现 + 2 套版本徽章推导（versioning/deriveVersionBadges vs libraries/deriveEntityVersionBadges），无统一 AssetPicker/VersionPicker | VersionStrip、TimelineView:781-804、VersionReviewPage:130-155、EntityVersionBlock:86-124、AssetBrowserView |
| P2-8 | 3 套 Modal overlay 自实现，无统一 Modal 原语 | ProjectSettingsModal、DirectoryBrowserModal、AssetsPage lightbox |
| P2-9 | `error instanceof Error ? ... : String(error)` 样板手写 10+ 处，缺 `useApiMutation` 封装或全局 MutationCache onError | EpisodePanel:202-242、PipelineBar:72-102 等 |
| P2-10 | Lightbox 仅 AssetsPage 有，ShotInspector 版本预览无点击放大 | AssetsPage:119-143、ShotInspector:553-562 |

---

## Proposed Changes（修复计划）

### Wave 1（P0，立即）
1. **静默 mutation 全面接入错误反馈**：StoryboardView（generateImages/createShot）、GenerationQueue（retry/cancel + Job 四控制）、ShotInspector activate、VersionReviewPage activate、ProjectHome 三 mutation、EpisodePanel createEpisode、EntityVersionBlock activate——统一复用既有 `ApiErrorPanel`。
2. StoryboardView 空态 AI 生成按钮补 disabled 守卫（对齐同文件 :238 模式）。
3. VersionReviewPage 按 `media_type` 分支渲染 `<video>`（主画布 + 对比板），img 加 onError 降级提示。

### Wave 2（P1）
4. GenerationQueue 状态表达：live 行按 `status` 渲染（queued→Hourglass、running→ spinner 语义 class）；状态图标映射修正（completed→Check、cancelled/failed→XCircle/Warning、其余→Hourglass）；错误信息友好化映射（保留原文 title）。
5. **下载能力**：新增 `lib/download.ts`（a[download] + `/assets/{id}/content`）+ `components/DownloadButton.tsx`；接入 ShotInspector 版本预览、VersionReviewPage、AssetBrowserView、AssetsPage lightbox、TimelineView FINAL_VIDEO（保留「打开」+ 新增「下载」）。
6. 图片 lazy 补齐 5 处 + ShotInspector 版本条改用 `/thumbnail`、video 加 `preload="metadata"`。
7. `lib/format.ts` 增加 formatDate/formatDateTime/formatClockTime，替换 7 处私有实现。
8. 7 处图标按钮补 aria-label。
9. TimelineView 吞错修复（保留 409 冲突 UI 分支，仅对真实错误加反馈）+ 配音按钮 pending 守卫。
10. PipelineBar「一键成片」降级 secondary。
11. Lightbox 抽共享组件，ShotInspector 版本预览接入点击放大。

### Wave 3（P2 低风险顺手）
12. styles.css：6px/8px 裸值 → token（同值替换零视觉变化）；`99px` → `999px` 统一 pill。
13. 合并两套 shimmer keyframes。

### 暂不处理（记录原因）
- **SettingsPage 拆分**（P1-8）：纯机械拆分但 diff ~2000 行且 settingsPage.test.tsx 依赖内联结构，与「不为漂亮而重构正常代码」冲突，列为下一 Sprint 首项（拆分边界已在 P1-8 给出：SettingsChrome / LlmConfigCard / LlmProfileRegistry / ImageConfigCard / ComfyUiEngineCard / VideoConfigCard / TestResultView / useProviderForm）。
- **AssetPicker 统一抽象**（P2-7）：跨 5 处业务语义不同（版本激活 vs 素材替换 vs MASTER 设定），需先统一徽章推导再谈组件抽象，属 Phase 2。
- **React.lazy**（P2-3）：桌面端本地资源加载，收益小；涉及 Suspense fallback 视觉变化。
- **StoryboardView 列表视图虚拟化**（P2-6 邻接）：网格视图已有 VirtualizedShotGrid，列表场景量级小。

---

## Risks

- 修改 GenerationQueue/StoryboardView/ShotInspector 有对应测试文件（generationQueueJobs.test.tsx / panels.test.ts / versionStrip.test.tsx），改动需保持既有 DOM 结构与文案（「取消任务」title、「已提交 N 个生成任务」notice 等）。
- VersionReviewPage video 分支需验证 `media_type` 取值（image/video）与后端一致（types.ts:473 `media_type: string`）。
- lib/format.ts 新增函数为纯增量，替换私有实现需逐处核对格式参数（7 处格式不完全一致：有的含年份有的不含）。

---

## Next Step

按 Wave 1 → Wave 2 → Wave 3 顺序修复，完成后运行 `tsc -b`、`eslint`、`vitest run`、`vite build` 四重验证，输出 `FRONTEND_OPTIMIZATION_REPORT.md`。
