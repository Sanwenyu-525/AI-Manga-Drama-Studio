# P1 — 智能体工作区（源文件 / Harness 增强工作区）

## 页面定位

P1 解决“用户已经把小说、剧本、人物设定、资料放在一个目录中，Agent 如何直接工作”的问题。

它应该继承 Harness 的文件操作能力，而不是做成一个独立小说编辑器。同时增加漫剧领域能力：源内容理解、结构提取、源到生产映射、修改影响分析。

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
Continue the exact P0 DeepSeek Harness Manga Drama Studio shell. Do not redesign the shell.

Mode:
漫剧智能体

Workspace:
智能体工作区

Purpose:
Open and work directly with an existing user folder such as:
D:\Novel\BasketballLegend

This workspace must still feel like DeepSeek Harness:
- left file explorer
- center editor/document viewer
- optional terminal/editor tabs
- right AI agent
- Git/file status
but with manga-domain intelligence added.

LEFT:
Show a VS Code / Harness-like file tree:
《篮球少年》
├─ chapters
│  ├─ Chapter_10.md
│  ├─ Chapter_11.md
│  └─ Chapter_12.md
├─ characters
│  ├─ 沈亦.md
│  └─ 教练.md
├─ outlines
├─ world
├─ research
├─ project_meta.json
└─ notes.txt

CENTER:
Open Chapter_12.md in a comfortable prose editor.
Support tabs, search, Markdown, version state, AI-modified indicator.
Allow contextual actions on selected text:
解释 / 提取角色 / 提取场景 / 加入知识库 / 创建分镜候选 / 询问AI.

SECONDARY INTELLIGENCE PANEL:
Tabs:
故事结构 / 角色 / 场景 / 时间线 / 来源映射 / AI分析

SOURCE-TO-PRODUCTION MAPPING:
For Chapter 12 show:
关联：Episode 03 / Scene 04 / Shot 021-034
Buttons:
打开漫剧 / 查看映射 / 分析影响

CHANGE IMPACT:
When Chapter 12 changes, show:
可能影响 8 个镜头、2 个角色动作、1 段对白.
Require user review before applying downstream changes.
Do not auto-sync destructive changes.

RIGHT:
Agent title “AI导演” or “源内容分析”.
Show a message:
“检测到 Chapter 12 已修改，可能影响 Episode 03 的 8 个镜头。”
Actions:
分析影响 / 查看文件 / 生成更新方案 / 稍后处理

SOURCE INTELLIGENCE:
small developer-style metrics, not dashboard cards:
文件 126 / 已索引 126 / 角色 38 / 场景 74 / 剧情事件 218.

SEMANTIC SEARCH:
Example query:
“沈亦第一次受伤是什么时候？”
Answer must show source file references.

All visible generic UI text must be Simplified Chinese.
Keep the same demo project and design system.
```

---

## 本页专用页面标准

### 核心结构
- 左：真实文件树。
- 中：文档编辑器，可保留终端/编辑器 Tab。
- 右：AI导演。
- 辅助：故事结构/映射/影响分析。

### 必须保留的 Harness 能力
- 文件访问
- 编辑器
- Terminal
- Git 状态
- 搜索
- 插件入口
- AI 对话

### 漫剧增强能力
- 源文件索引
- 语义检索
- 知识提取
- 源→Episode/Scene/Shot 映射
- 修改影响分析
- AI 修改 Diff 与回滚

---

## 验收清单

- [ ] 页面看起来仍像 Harness，而不是小说 SaaS。
- [ ] 可以直接看见真实目录路径和文件树。
- [ ] Chapter 12 能映射到 Episode/Scene/Shot。
- [ ] 修改源文件后先“分析影响”，不是直接同步覆盖。
- [ ] AI 修改文件有 Agent / 原因 / Prompt / Diff / 接受 / 撤销。
- [ ] 有语义搜索且回答显示来源。
- [ ] 仍能访问 Terminal/Git/编辑器。

---

## Codex + StitchMCP 制作注意事项

P1 以后是源内容的唯一主入口。不要在 P2/P3 重复做完整文件编辑器，只提供“打开源文件/查看来源”的跳转。
