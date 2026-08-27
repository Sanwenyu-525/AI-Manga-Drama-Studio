# P12 — 最终模式切换、Design System 与跨页面集成验收

## 页面定位

P12 不是再做一个新业务页面，而是最后用 Stitch 把 P0-P11 统一成一套产品：确认模式切换、组件规范、状态规范、导航、字体、颜色、跨页跳转、中文化都一致。

它是最终“可开发原型规范页”。

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
Using the approved P0-P11 screens, create the FINAL INTEGRATION and DESIGN SYSTEM reference for DeepSeek Harness Manga Drama Studio.

Do NOT invent a new visual direction.

1. MODE STATES
Show:
Harness
and
漫剧智能体

Harness state:
文件树 / 编辑器 / 终端 / Git / AI助手.

Manga Agent state:
fixed activity rail + AI导演 + domain workspaces.

Inside Manga Agent:
智能体工作区 / 漫剧工作区.

Clearly demonstrate:
Same application shell.
Different professional mode.
No separate app.

2. FIXED NAVIGATION
Freeze the exact activity rail order:
项目
工作区
AI导演
故事
角色
分镜
工作流
资产
镜头
提示词历史
知识库
连续性检查
时间线
生产日志
设置

3. DESIGN TOKENS
Document visually:
background hierarchy
panel hierarchy
border
spacing scale
typography hierarchy
Chinese sans-serif
monospace technical text
icon sizing
selected state
hover
focus
disabled

4. COLOR SEMANTICS
Blue = selected / primary system action
Orange = AI suggestion / attention
Green = completed / healthy / connected
Red = error / high-risk
Gray = neutral / disabled / secondary

Avoid neon glow and excessive cyberpunk style.

5. COMPONENT LIBRARY
Show production-ready examples:
Top application bar
Mode switch
Workspace switch
Activity rail
File tree
Tabs
Panel header
Button
Icon button
Status badge
Progress
Agent message
Agent action proposal
Shot card
Asset card
Inspector section
Prompt diff
Generation manifest
Workflow node
Condition node
Human approval node
Timeline clip
Issue card
Version graph
Production event
Modal / drawer / tooltip / search

6. GLOBAL STATUS LANGUAGE
统一：
等待
排队中
运行中
已完成
失败
需要审核
已忽略
已锁定
已保存
有未保存修改

Never rely only on color.

7. CROSS-PAGE ROUTING EXAMPLES
Demonstrate:
P1 Chapter12 → P3 affected shots
P3 Shot012 → P6 Shot Inspector
P6 current prompt → P7 Prompt History
P6 continuity warning → P9 Continuity Checker
P5 asset usage → affected shots
P8 knowledge rule → affected prompts
P9 fix → P6 new version
P10 clip → P6 Shot
P11 event → P7 Manifest

8. CHINESE LOCALIZATION
All generic UI Chinese.
Only technical/proper names may remain English.

9. DEMO DATA
Use only 《篮球少年》 / 沈亦 / basketball environments.

10. FINAL REFERENCE SCREEN
Create a design-system/reference page plus representative mode-switch states.
The result should be suitable for developers to implement directly.

The product message:
“DeepSeek Harness is the core environment; 漫剧智能体 is a professional domain extension with source-aware, traceable AI production.”
```

---

## 本页专用页面标准

### P12 必须冻结的东西
- 一级/二级导航层级
- 左 Rail 顺序
- 颜色语义
- 字体语义
- 状态枚举
- Agent 消息样式
- Shot/Asset/Prompt/Workflow/Timeline 等核心组件
- 跨页跳转语义

### 最终交付目标
Codex 可以根据 P12 + 各 P 页面，直接建立前端 Design Tokens、组件库、路由和页面骨架。

---

## 验收清单

- [ ] P0-P11 看起来像同一个产品。
- [ ] Harness 与漫剧智能体切换清楚。
- [ ] 二级工作区不与模式混淆。
- [ ] 导航顺序所有页面一致。
- [ ] 中文字体与等宽字体使用正确。
- [ ] 颜色状态一致。
- [ ] 所有常见状态不只靠颜色。
- [ ] 跨页面跳转链路明确。
- [ ] 不再出现 Cyberpunk/无关 Demo 内容。
- [ ] 能作为开发团队的最终 UI 规范页。

---

## Codex + StitchMCP 制作注意事项

P12 最后做。不要在 P0-P11 未验收前提前让 Stitch“统一风格”，否则会把错误一起固化。
