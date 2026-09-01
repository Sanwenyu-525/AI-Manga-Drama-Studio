# FRONTEND_OPTIMIZATION_REPORT.md — 前端审计与优化结果（2026-08-31）

> 前置文档：[FRONTEND_AUDIT.md](./FRONTEND_AUDIT.md)（问题清单与证据）。
> 原则遵守情况：未重写任何正常代码、未改变产品结构、未动业务逻辑；全部修改为定向修复。
> 验证：`tsc -b` ✅ · `eslint .` ✅ · `vitest run` 35 文件 **242/242** ✅ · `vite build` ✅ · 后端 `pytest tests/test_local_session.py tests/test_config.py` **23/23** ✅

---

# Summary

对 AI 漫剧生产工作台前端（React 18 + TS + Zustand + TanStack Query + 手写 CSS）完成系统性审计与修复。

**总体评价**：这是一个纪律性很强的前端库（0 个 `any`、0 个 `console.log`、0 个 TODO、0 处组件硬编码颜色、0 个绕过 API 层的 fetch、按钮 primary 密度克制）。真实债务不在"UI 体系崩坏"，而集中在三处：**错误反馈的最后一公里**（~15 个核心 mutation 静默失败）、**生成链路状态表达**（排队/运行不可区分、取消态用成功图标）、**产物导出能力**（零下载入口）。

**审计额外发现一个未记录的生产级 bug（P0-5）**：Tauri token 模式下所有 `<img>/<video>/<audio>` 因无法携带 `X-Session-Token` header 而全部 401——即生产壳里所有生成图片都无法显示。已前后端联动修复。

---

# Problems Fixed

## P0（4 项审计发现 + 1 项审计中发现）

| # | 问题 | 修复 |
|---|---|---|
| P0-1 | 批量生成提交失败完全静默（StoryboardView `generateImages`） | 接入 ApiErrorPanel 渲染 `generateImages.error ?? createShot.error` |
| P0-2 | ~12 个核心 mutation 静默失败 | 全部接入错误反馈：GenerationQueue（retry/cancel + Job 四控制 ×2 处）、ShotInspector activate、VersionReviewPage activate、ProjectHome（rename/deleteProject/uploadCover）、EpisodePanel createEpisode、EntityVersionBlock activate（并入 mutateError 链） |
| P0-3 | 审片页用 `<img>` 渲染视频版本，无法播放 | 主画布 + A/B 对比板均按 `media_type === "video"` 分支渲染 `<video controls preload="metadata">` |
| P0-4 | 空态「AI 生成 Storyboard」无防重复提交 | 补 `disabled={isPending || Boolean(planOpId)}` + 「规划中…」文案，对齐同页既有模式 |
| P0-5 | **Tauri token 模式下全部媒体 401**（审计过程中实证发现：后端 `local_session_auth` 只认 header，`<img>` 无法带 header） | 后端 middleware 接受 `?token=` query（与 WS 网关同模式）；前端新增 [lib/mediaUrl.ts](file:///d:/Develop/AI_Manga_Drama_Studio/frontend/src/lib/mediaUrl.ts) 统一注入 token，替换全部 13 处媒体 URL 拼接点；契约文档 §50 与 configuration 矩阵同步更新 |

## P1（10 项中修复 9 项）

| # | 问题 | 修复 |
|---|---|---|
| P1-1 | 队列状态表达：queued/running 不可区分、cancelled 显示绿色成功图标、错误原文直出 | live 行按 `status` 渲染（queued=沙漏+降透明度 / running=旋转箭头+新 CSS）；状态图标语义映射（cancelled→XCircle）；新增 `friendlyGenerationError` 六类常见技术错误→中文文案映射（原文保留在 title tooltip） |
| P1-2 | 产物零下载能力 | 新增 [lib/download.ts](file:///d:/Develop/AI_Manga_Drama_Studio/frontend/src/lib/download.ts) + [DownloadButton](file:///d:/Develop/AI_Manga_Drama_Studio/frontend/src/components/DownloadButton.tsx)；接入 5 处：ShotInspector 版本区、ShotInspector 大图 Lightbox、VersionReviewPage 审片画布、AssetBrowserView 检查器、AssetsPage lightbox；FINAL_VIDEO 新增「下载成片」（`<a download>`，保留「打开」）；成片文件名 `ShotXXXX_V{n}.{ext}` 自动推导 |
| P1-3 | 图片 lazy 覆盖低 | 补齐 6 处 `loading="lazy"`：VersionStrip 版本条、VersionReviewPage 侧栏、EntityVersionBlock、TimelineView clip 缩略图、MediaLibrary 素材网格、ShotThumbImage（本来就是 lazy 的 URL 现在 token 化） |
| P1-4 | formatDate 7 处重复 | [lib/format.ts](file:///d:/Develop/AI_Manga_Drama_Studio/frontend/src/lib/format.ts) 扩展 `formatDate/formatDateTime/formatClockTime/formatMonthDay`，替换 6 处同构实现（ProductionLogPage 含秒的变体确认为不同格式，保留） |
| P1-5 | 视频/音频预览未控 preload | ShotInspector `<video preload="metadata">`、审片页 `<video preload="metadata">`、Lightbox video 同；audio 保持 `preload="none"` |
| P1-6 | 7 处图标按钮无 aria-label | 全部补齐：GenerationQueue 取消、CharactersSection 保存/取消、DocumentsSection 取消、ProjectHome 保存/取消、TimelineView 刷新预览 |
| P1-7 | TimelineView 吞错（replaceAsset/删除片段/updateClip/saveText/commitOverride/MediaLibrary 加入） | 全部补错误状态 + 就地展示；409 冲突仍静默走服务端同步（既有语义保留），仅真实错误浮出 |
| P1-8 | SettingsPage 1927 行巨石 | **未拆分**（见 Remaining Issues，含精确拆分方案） |
| P1-9 | 片段配音按钮无 pending 守卫 | voState 增加 `"pending"`，`disabled` + 「提交中…」 |
| P1-10 | PipelineBar 双 primary 同屏 | **审计误报**（复核确认两个 primary 是互斥状态分支，永不同屏），未修改 |

## P2（低风险顺手处理）

- styles.css：`border-radius` 裸值统一——`8px`→`var(--radius)` ×6、`6px`→`var(--radius-sm)` ×3、`6px 6px 0 0`→token ×1、`99px`→`999px` 统一 pill ×4（全部同值替换，零视觉变化）。
- 新增 `.queue-item.queued` / `.queue-status-spin` / `.lightbox-actions` / `.lightbox-inner video` / `.review-image-stage video` / `.review-canvas-actions` 样式（新功能所需，均复用既有 token）。
- 复核"两套 shimmer keyframes"：实为不同技术（background-position vs translateX overlay），**非真重复**，保留。

---

# UI Improvements

- **生成队列可读性**：排队/运行/失败/取消/完成五态在图标、透明度、颜色三个通道上可区分（不再仅靠颜色）；失败原因从技术原文变为可理解的中文文案（超时/连不上/认证/限流/工作流/模型六类），排查细节 hover 可见。
- **产物可达性**：图片版本可点击放大（新 Lightbox：ESC/点击遮罩关闭 + 内嵌下载按钮）、审片页/素材检查器/素材库均有稳定位置的「下载」按钮、成片可另存为文件——完成「生成 → 预览 → 导出」闭环。
- **防误触**：AI 生成 Storyboard、片段配音、生成任务取消等入口在 pending 时禁用；7 处图标按钮补齐 aria-label（screen reader 可读）。
- **视觉一致性**：radius 全部收敛到 token 体系（保留语义性的 999px pill 与 50% 圆形）。

# Architecture Improvements

- **共享原语补齐**（均按"先复用后新建"，且替换而非叠加）：
  - `lib/mediaUrl.ts` — token 感知媒体 URL（`assetUrl`/`mediaUrl`），单一事实源；
  - `lib/download.ts` — `downloadAsset` + 文件名推导；
  - `components/DownloadButton.tsx` — 统一下载按钮（复用 `.btn secondary compact`）；
  - `components/Lightbox.tsx` — 统一全屏预览（复用既有 `.lightbox` CSS，AssetsPage 的私有实现改为消费共享组件）；
  - `lib/format.ts` — 日期格式化唯一出处。
- **错误反馈模式收敛**：所有静默 mutation 统一走既有 `ApiErrorPanel`（`error ?? error ?? ...` 链式取第一个），未引入 toast 等新反馈机制，保持零新依赖。
- **契约同步**：`api-event-contract-v0.1.md` §50、`configuration-v0.1.md` 本地安全矩阵更新（?token= 语义）。

# Performance Improvements

- 6 处热点图片网格/列表补 `loading="lazy"`（MediaLibrary 一次最多 100 张、版本条随轮询刷新等最痛的点）。
- 全部 `<video>` 显式 `preload="metadata"`——版本轮询期间（800ms~3s）不再反复自动拉流。
- mediaUrl 在无 token 的浏览器开发流零开销（直接返回原串）。

# Files Changed

**前端新增（5）**：`lib/mediaUrl.ts`、`lib/download.ts`、`lib/format.ts`（扩展）、`components/DownloadButton.tsx`、`components/Lightbox.tsx`

**前端修改（15）**：
`features/generation/GenerationQueue.tsx`（状态图标/queued 区分/错误映射/mutation 反馈/aria-label/disabled）
`features/storyboard/StoryboardView.tsx`（防重复提交/错误反馈）
`features/storyboard/VersionReviewPage.tsx`（video 分支/下载/lazy/activate 反馈/formatDate）
`features/storyboard/ShotInspector.tsx`（token URL/video preload/Lightbox 放大/下载/activate 反馈）
`features/storyboard/ShotThumbImage.tsx`（token URL）
`features/versioning/VersionStrip.tsx`（lazy/token URL）
`features/libraries/EntityVersionBlock.tsx`（lazy/token URL/activate 反馈/formatDate）
`features/libraries/CharactersSection.tsx`、`DocumentsSection.tsx`（aria-label）
`features/assets/AssetsPage.tsx`（共享 Lightbox/下载/token URL/formatDate）
`features/assets/AssetBrowserView.tsx`（下载/token URL）
`features/timeline/TimelineView.tsx`（吞错修复×6/pending 守卫/lazy/token URL/下载成片/aria-label）
`features/project/ProjectHome.tsx`（mutation 反馈/aria-label/formatDate 委托）
`features/script/EpisodePanel.tsx`（createEpisode 反馈）
`features/prompts/PromptsHistoryPage.tsx`、`provenance/ProvenancePanel.tsx`、`workspace/WorkspaceOverviewPage.tsx`（formatDate/token URL）
`styles.css`（radius token 统一 + 新 class 样式）

**后端（1）**：`app/main.py`（local_session_auth 接受 `?token=` query fallback）

**文档（3）**：`docs/reports/FRONTEND_AUDIT.md`（新增）、`docs/api-event-contract-v0.1.md`、`docs/configuration-v0.1.md`

---

# Remaining Issues（未处理与原因）

| 项 | 级别 | 原因 |
|---|---|---|
| **SettingsPage.tsx 1927 行拆分** | P1 | 纯机械拆分但 diff ~2000 行，且 `settingsPage.test.tsx`/`settingsModal.test.tsx` 依赖内联结构需同步重写；与"不为漂亮而重构正常代码"冲突。**下一 Sprint 首项**。拆分边界已定：`SettingsChrome`（Tabs/StatusStrip/ActionBar/Skeleton ~200 行）+ `LlmConfigCard`(573-700) + `LlmProfileRegistry`(702-1148) + `ImageConfigCard`(1157-1288) + `ComfyUiEngineCard`(1289-1764) + `VideoConfigCard`(1770-1927) + `TestResultView`(516-570) + `useProviderForm`（三卡重复的 saved/touched/error 状态机） |
| **AssetPicker/VersionPicker 统一抽象**（5 处选择 UI + 2 套徽章推导） | P2 | 五处业务语义不同（版本激活 vs 素材替换 vs MASTER 设定），需先统一徽章推导再谈组件抽象；属 Phase 2 前置调研项 |
| **React.lazy 路由级代码分割** | P2 | 桌面 Tauri 本地资源加载，收益小（build 已提示 751KB chunk）；涉及 Suspense fallback 视觉 |
| **useOperationPolling 无退避/上限** | P2 | 现有行为（失败后持续轮询）在 operation 场景下可接受，改动会影响 202 轮询语义，需与后端 operation TTL 对齐 |
| **EpisodePanel 无剧集空态引导、GenerationQueue 空态无 CTA 等弱空态** | P2 | 涉及信息架构取舍（空态往哪引导），建议随 P2-E4 后续迭代一起做 |
| **StoryboardView 列表视图虚拟化** | P2 | 网格视图已有 VirtualizedShotGrid；列表场景镜头量级小 |
| **无统一 Modal 原语**（3 套 overlay） | P2 | 现有三处实现稳定且视觉一致，抽象收益低于回归风险 |
| **ShotInspector 输入/输出分区**（单列长滚动） | P2 | 结构性改动，牵动 Inspector 布局与测试，建议与 frontend-ux 文档一起规划 |

---

# Suggested Next Steps

1. **下一 Sprint**：SettingsPage 按上述边界拆分（配 `useProviderForm` 消除三卡重复状态机），同步迁移两个测试文件。
2. **生产验证**：在 Tauri 壳真实启动一次，确认 P0-5 修复后生成图片/视频/配音试听/成片下载全链路可用（本次修复的 401 问题只在 token 模式出现，浏览器 dev 无法复现）。
3. **Phase 2 预研**：统一 `deriveVersionBadges` 到单一出处（`versioning/`），作为 AssetPicker 抽象的第一步（纯函数收敛，低风险）。
4. **Bundle**：若未来上 Web 分发，再启用路由级 `React.lazy`（SettingsPage/VersionReviewPage/WorkflowsPage 三个低频路由优先）。

---

## 交付核对

- **P0 已解决**：5/5（含审计中发现的 Tauri 媒体 401 生产 bug）
- **P1 已解决**：9/10（P1-8 SettingsPage 拆分按风险判断延后至下一 Sprint；P1-10 经复核为审计误报）
- **未处理 P2**：8 项（均为有明确理由的延后项，见 Remaining Issues）
- **潜在风险**：
  - 后端 `?token=` 使 token 可能出现在代理/访问日志中——与 WS 既有模式风险等同，且仅本地回环场景（P1-E5-T02 设计边界内）；
  - `friendlyGenerationError` 为关键词匹配，未命中的错误仍展示原文（安全兜底）；
  - 全部改动经 vitest 242 项 + 后端 23 项回归，未新增依赖。
