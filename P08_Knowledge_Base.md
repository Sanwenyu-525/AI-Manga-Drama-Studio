# P8 — 项目知识库 / 知识图谱

## 页面定位

P8 是 Agent 的长期项目记忆和事实约束系统。不是普通 Wiki。知识应能追溯到源文件证据，并能影响角色、场景、分镜、Prompt 和连续性检查。

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
知识库

LEFT:
Knowledge categories:
角色知识 / 人物关系 / 世界观 / 剧情事件 / 时间线 / 地点 / 规则 / 风格规范 / 生产约束

CENTER:
Provide multiple views:
图谱视图 / 列表视图 / 规则视图 / 时间线视图

Default graph:
沈亦 in center.
Connections:
教练
主要对手
球队
Chapter 12
NBA球馆
Shot 012
角色资产 沈亦_V12
Prompt PV12
“比赛服装为白色主场球衣” rule

SELECTED KNOWLEDGE DETAIL:
Fact:
沈亦身高 204cm
Type: 角色事实
Source evidence:
characters/沈亦.md line/section
Chapter 01
Confidence: 98%
Last verified
Version

RIGHT:
知识助手 / 路径与证据

Show evidence path:
源文件 → 提取知识 → 角色知识 → 资产规则 → Shot/Prompt 使用

IMPACT:
If a fact changes:
“沈亦比赛服装规则已修改”
Affected:
3 Character Assets
12 Shots
8 Prompts
2 continuity rules
Actions:
分析影响 / 创建新版本 / 查看冲突

AI QUERY:
“沈亦第一次失败发生在哪一章？”
Answer with clickable source references and confidence.

KNOWLEDGE INGESTION:
Analyze workspace → propose extracted characters, relationships, locations, rules, timeline events.
Require review:
全部接受 / 选择接受 / 拒绝.

RULE VIEW:
Show enforceable production rules such as:
- 主角脸型不得漂移
- 比赛场景球衣号码固定
- 同一场景时间/灯光保持一致

All generic UI Chinese.
```

---

## 本页专用页面标准

### 图谱不是唯一视图
规则、时间线、长列表不适合只用 Graph；必须提供列表/规则/时间线。

### 证据优先
每条重要知识尽量能回到源文件/来源。
显示置信度与版本。

### 与 P5 的边界
P8 是“事实与规则”；P5 是“生产资产”。

---

## 验收清单

- [ ] 有 Graph/List/Rule/Timeline 至少 3 种视图。
- [ ] 知识节点能显示证据来源。
- [ ] 知识变化能分析对资产/Shot/Prompt 的影响。
- [ ] AI问答显示来源。
- [ ] 知识提取必须经过用户审核。
- [ ] 有可执行的生产规则，不只是百科文字。

---

## Codex + StitchMCP 制作注意事项

如果 Stitch 只做一个漂亮的关系图，要求补 `evidence panel, rule view, source references, and downstream impact`。
