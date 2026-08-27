# P11 — 生产日志 / 全链路追溯

## 页面定位

P11 负责把 Agent、Prompt、模型、资产、生成、审核、修复串成时间线。面向创作者默认展示“生产事件”，而不是 HTTP/Stack Trace；技术日志可折叠。

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
Continue the same shell.

Active module:
生产日志

LEFT:
Chronological production event timeline.

Example:
10:20 AI导演 — 分析 Chapter 12
10:28 分镜 Agent — 创建 Shot 012
10:31 提示词编译器 — 创建 PV11
10:34 GPT Image — 生成 image V4
10:37 连续性检查 — 发现持球手问题
10:39 AI导演 — 创建 PV12
10:42 GPT Image — 生成 image V5
10:48 MiniMax H3 — 生成 video V1
10:55 用户 — 选择 video V1 进入 Timeline

Event filters:
Episode / Scene / Shot / Agent / Model / Asset / Prompt / Error / Human Action / date.

CENTER:
Selected event detail.

Sections:
任务
Agent
模型
开始/结束/耗时
状态

Input Trace:
Chapter12.md
沈亦_V12
NBA_Arena_V5
Prompt PV12
image V5

Output:
video_012_v1.mp4
Generation Manifest ID
Version
Quality status

RELATED:
Previous event / Next event
Open Shot
Open Prompt
Open Workflow
Open Asset

USER-FACING EXPLANATION:
“本次重新生成是因为连续性检查发现 Shot013 持球手与上一镜不一致，因此 AI导演锁定沈亦_V12 并更新运动提示词。”
Do NOT expose private chain of thought.
Only concise action/reason summary.

ERROR:
If generation fails:
错误类型 / 影响 / 建议
Actions:
重试 / 切换模型 / 打开工作流 / 查看技术日志.

TECHNICAL DETAILS:
collapsed advanced area:
request ID / API / raw logs / latency / token/cost if available.

RIGHT:
生产助手
Summarize:
Episode01 78%
3 risks
2 pending approvals
recent failures
Actions:
生成生产报告 / 查看风险 / 优化流程.

PRODUCTION REPORT:
Include generation count, failures, duration, models, prompt versions, fixes, manual approvals, optional cost.

All generic UI Chinese.
```

---

## 本页专用页面标准

### 两层日志
- 默认：创作生产事件。
- 展开：技术执行日志。
这样同时服务创作者和开发者。

### 追溯链
事件要能回到：
Source / Shot / Asset / Prompt / Workflow / Manifest / Output。

---

## 验收清单

- [ ] 有时间线式事件流。
- [ ] 能按 Shot/Agent/Prompt/Model 搜索。
- [ ] 事件有输入和输出追溯。
- [ ] AI解释是用户可读原因摘要，不展示原始 CoT。
- [ ] 错误支持重试/切模型/开 Workflow。
- [ ] 技术日志默认折叠。
- [ ] 可生成生产报告。

---

## Codex + StitchMCP 制作注意事项

P11 与 P7 不同：P7 以“生成配置和 Prompt 版本”为主；P11 以“整个生产过程发生了什么”为主。
