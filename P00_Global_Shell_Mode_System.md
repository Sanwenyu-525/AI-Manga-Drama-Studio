# P0 — DeepSeek Harness 全局 Shell 与模式系统

## 页面定位

这是所有后续页面的母版。目的不是展示某个业务功能，而是一次性定死：
1. `Harness / 漫剧智能体` 一级模式；
2. 漫剧智能体内部 `智能体工作区 / 漫剧工作区` 二级工作区；
3. 固定 Activity Rail、右侧 Agent、底部状态栏、中文字体与颜色规则；
4. 源工作区和漫剧项目是“绑定关系”，而不是文件夹父子关系。

P0 一旦验收，后续 P1-P11 不允许重新设计 Shell。

## 全局页面标准（所有页面必须继承）

### A. 产品层级
- 一级模式固定为：`Harness | 漫剧智能体`。
- 只有进入“漫剧智能体”后，才出现二级工作区：`智能体工作区 | 漫剧工作区`。
- `智能体工作区`代表用户已有目录，可包含小说、剧本、Markdown、TXT、PDF、图片、设定、资料、已有分镜文本等。
- `漫剧工作区`代表从源内容派生出的独立生产工程。两者**逻辑绑定但不能表现成父子目录**。
- 禁止使用类似 `D:\Novel\BasketballLegend > Season 1` 的面包屑来暗示二者是文件夹父子关系。应使用“源工作区 ↔ 漫剧项目”的绑定关系组件。

### B. DeepSeek Harness 身份
- 漫剧智能体是 DeepSeek Harness 的领域增强模式，不是独立 SaaS、不是新窗口、不是另一个应用。
- 切换到漫剧智能体后仍应保留 Harness 核心能力：文件、编辑器、终端、Git、插件、AI 对话。
- Harness 模式右侧 Agent 称为“AI助手”；漫剧智能体模式根据页面使用“AI导演 / 镜头导演 / 工作流导演 / AI剪辑导演”等领域角色。

### C. 视觉与布局
- 桌面优先，目标画布：`1920 × 1080`，最低设计验证尺寸建议 `1600 × 900`。
- 专业暗色、高信息密度、IDE/创作软件感。
- 参考气质：Cursor / VS Code / Figma / DaVinci Resolve / Unreal Editor；只参考信息架构和专业感，不直接复制。
- 主色：克制蓝色；橙色只用于 AI 建议/注意；绿色用于完成/健康；红色用于错误/高风险。
- 减少 Cyberpunk、霓虹、黑客终端感、过度 ALL CAPS、过度橙色、过度等宽字体。
- 中文正文、导航、按钮使用现代中文无衬线；等宽字体只用于代码、路径、Prompt、Seed、模型 ID、日志等技术内容。
- 不使用巨大 SaaS 卡片；优先 panel / list / inspector / canvas / timeline 等桌面生产软件结构。

### D. 中文化
- 所有可见 UI 默认简体中文。
- 允许英文：DeepSeek Harness、Harness、模型名、API 名、Git 分支、文件名、路径、真实英文 Prompt、Shot ID。
- 禁止残留：`ACTIVE / Production Overview / Recommended Actions / Inspector / Connected / Director Mode / Draft Quality` 等通用英文 UI，应翻译成中文。

### E. 演示项目一致性
所有页面统一使用：
- 项目：《篮球少年》
- 主角：沈亦
- 源工作区示例：`D:\Novel\BasketballLegend`
- 漫剧项目：《篮球少年》AI漫剧 · Season 1
- 示例场景：高中球馆、NCAA 球馆、NBA 球馆、训练馆
- 示例模型：DeepSeek / GPT Image / MiniMax H3 / ComfyUI
- 禁止赛博朋克、武士刀、机械眼、科幻武器、无关奇幻角色等漂移内容。

### F. 跨页追溯
所有生成型页面必须支持尽可能多的以下关联：
`Source → Story/Script → Episode/Scene/Shot → Asset → Prompt → Model → Workflow → Agent → Generation → Version → Output → Review/Fix`

尤其禁止只有“结果图片/视频”而没有来源、Prompt 或版本信息。

---

## StitchMCP 主提示词

> 建议 Codex 将下面整段作为 StitchMCP 的页面生成/修改指令。若已经生成 P0，请同时要求 Stitch **continue the exact same product and design system**，不要重建 Shell。

```text
Design / repair the global application shell for “DeepSeek Harness Manga Drama Studio”.

This is NOT a standalone application. It is a domain-specific professional mode inside DeepSeek Harness.

CRITICAL NAVIGATION HIERARCHY:

Level 1 — global application mode in the top application header:
[ Harness ] [ 漫剧智能体 ]

Level 2 — visible ONLY when 漫剧智能体 is active, inside the project/workspace context area:
[ 智能体工作区 ] [ 漫剧工作区 ]

Never merge these two navigation levels.

HARNESS STATE:
- Left: file explorer / search / Git / plugins.
- Center: editor, document, terminal.
- Right: “AI助手”.
- Bottom: system/runtime status.
- Keep the product recognizable as DeepSeek Harness.

MANGA AGENT STATE:
- Keep the same shell.
- Keep access to files, editor, terminal, Git, plugins and AI conversation.
- Add domain modules: 项目、工作区、AI导演、故事、角色、分镜、工作流、资产、镜头、提示词历史、知识库、连续性检查、时间线、生产日志、设置.
- Right agent becomes “AI导演”.

WORKSPACE RELATIONSHIP:
Do NOT show `D:\Novel\BasketballLegend > Season 1`.
Instead show a binding component:

智能体工作区
D:\Novel\BasketballLegend
《篮球少年》
        ↕ 已绑定
漫剧项目
《篮球少年》AI漫剧 · Season 1

Show status: 已连接 / 最近分析 / 待分析变化.

Create a fixed left activity rail order and never change it across later screens.

Visual direction:
professional dark desktop software, restrained blue primary accent, orange only for AI attention, green for healthy/completed, red for errors.
Reduce cyberpunk/neon/brutalist styling.
Chinese sans-serif for UI; monospace only for paths/code/prompts/technical values.

All visible generic UI labels must be Simplified Chinese.

Final composition should show the Manga Agent state as the main screen and also clearly define the Harness alternate state.
Use the same demo project 《篮球少年》 everywhere.
```

---

## 本页专用页面标准

### 布局
- 顶部第一层必须能一眼识别 `Harness | 漫剧智能体`。
- 二级工作区切换位置低于一级模式，建议位于项目上下文栏。
- 左侧 Activity Rail 固定宽度、固定顺序。
- 中央内容区随模块变化。
- 右侧 Agent 固定为同一个容器体系，角色随模式变化。
- 底部统一系统状态栏。

### 绑定关系组件
必须同时显示：
- 智能体工作区路径；
- 漫剧项目名称；
- 绑定状态；
- 最近分析/同步时间；
- 待分析的源文件变化；
- `查看关联 / 分析变化` 等操作。

### 非目标
- 不做 Landing Page。
- 不做 SaaS Dashboard。
- 不把漫剧智能体画成另一个独立软件。

---

## 验收清单

- [ ] 顶部确实存在 `Harness / 漫剧智能体`。
- [ ] 漫剧智能体内部才出现 `智能体工作区 / 漫剧工作区`。
- [ ] 未出现“小说工作区”作为固定名称。
- [ ] 源目录与 Season 1 没有被画成 breadcrumb 父子路径。
- [ ] Harness 状态仍有文件树、编辑器、终端、Git、AI助手。
- [ ] 漫剧模式仍保留 Harness 基础能力。
- [ ] Activity Rail 顺序已固定。
- [ ] 中文正文不是全等宽字体。
- [ ] 演示内容完全是《篮球少年》。
- [ ] 没有残留通用英文 UI。

---

## Codex + StitchMCP 制作注意事项

1. **先单独生成 P0 并冻结 Shell。**
2. 如果 Stitch 输出仍有错误层级，不要继续 P1，先迭代 P0。
3. Codex 后续调用 StitchMCP 时，把 P0 的 screen/design reference 作为所有页面参考。
4. 后续提示词统一追加：`Do not redesign the application shell.`。
