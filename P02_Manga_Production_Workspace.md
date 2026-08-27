# P2 — 漫剧工作区 — 生产控制中心

## 页面定位

这是进入漫剧工作区后的默认首页。它回答“现在做到哪里、AI 正在做什么、哪里有风险、来源是否变化、Prompt/资产/生成是否可追溯”。

它不是商业 BI Dashboard，也不是大预览页。

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
Continue the exact same P0 shell.

Mode:
漫剧智能体

Workspace:
漫剧工作区

Page role:
AI manga production command center for 《篮球少年》AI漫剧 · Season 1.

TOP CONTEXT:
Show source binding without breadcrumb:
智能体工作区：D:\Novel\BasketballLegend
↔ 已绑定
漫剧项目：《篮球少年》AI漫剧 · Season 1

MAIN OVERVIEW:
High information density, panel-based production overview.

Show:
- Episode 01 制作中
- 总进度 78%
- Episode list and stage status
- current AI agent activity
- generation queue
- assets health
- continuity risks
- prompt trace health
- recent source changes
- recent output
- pending human approvals

EPISODE ROWS OR COMPACT CARDS:
Episode 01
48 镜头
图片 42/48
视频 31/48
音频 20/48
提示词：完整
当前版本：V18
状态：制作中

PRODUCTION PIPELINE:
小说分析 ✓
剧本 ✓
资产 ✓
分镜 ●
图片生成 ●
视频生成 等待
配音 等待
时间线 等待
审核 等待
导出 等待

RECENT OUTPUT:
Do not use a giant promotional concept image.
Use a real basketball shot preview:
Shot 042 · 沈亦篮下扣篮
图生视频 · MiniMax H3 · V3
Actions:
播放 / 打开镜头 / 查看提示词

ATTENTION:
3 个连续性风险
1 个 Prompt 缺失
2 个资产待补充
Buttons:
查看问题 / 生成修复方案

SOURCE CHANGE:
Chapter 12 已修改
影响 Episode 03 · 8 个镜头
Actions:
分析影响 / 查看变化

RIGHT AI DIRECTOR:
“Episode 01 当前完成 78%。视频生成是主要瓶颈，同时检测到 3 个连续性风险。”
Actions:
优化生产顺序 / 查看风险 / 生成报告

Use Chinese UI. No oversized preview. No SaaS KPI dashboard feeling.
```

---

## 本页专用页面标准

### 信息优先级
1. 当前 Episode / 总体进度
2. Agent/生成队列
3. 待处理风险与人工审核
4. 来源变化
5. 最近输出
6. Prompt / Asset / Version 健康度

### 首页预览
- 最近输出预览最多占主区约 1/3～1/2。
- 不显示软件宣传图或概念海报。
- 必须是当前项目真实镜头语义。

### 快捷入口
建议：创建 Episode / 生成分镜 / 批量生成 / 连续性检查 / 提示词历史 / 打开工作流。

---

## 验收清单

- [ ] 没有巨大营销式预览图。
- [ ] Episode、Queue、Agent、风险、来源变化都一屏可见。
- [ ] 显示智能体工作区 ↔ 漫剧项目绑定，而不是父子路径。
- [ ] 最近输出能跳 Shot Inspector / Prompt History。
- [ ] AI导演给的是生产建议，不只是聊天。
- [ ] 页面不像企业 BI 仪表盘。

---

## Codex + StitchMCP 制作注意事项

P2 是漫剧工作区默认首页。后续 P3-P11 都应能从 P2 一跳进入，也应能返回 P2。
