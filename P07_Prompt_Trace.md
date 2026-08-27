# P7 — 提示词追溯中心 + Generation Manifest

## 页面定位

P7 是产品差异化核心。目标不是“查看历史 Prompt”，而是让每一次文生图、图生视频、文生视频都具备可复现、可比较、可复用、可回滚的生成记录。

应把 Prompt 当成“创作代码”，把每次生成当成“Generation Manifest”。

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
提示词历史

Core concept:
Git-like version control for AI generations.

LEFT:
Prompt / Generation Library
Categories:
镜头 / 角色 / 场景 / 风格 / 图片 / 视频 / 工作流Prompt / 模板

Filters:
生成类型 / 模型 / Agent / Episode / Shot / 成功/失败 / 时间.

CENTER:
Select Shot 012.
Show a version graph/timeline:
PV9 → PV10 → PV11 → PV12 ★
Support branches.

DEFAULT DIFF VIEW:
Compare PV11 → PV12.

Clearly show:
新增
+ dramatic stadium lighting
+ low angle push-in

删除
- close up

保留
character lock: 沈亦_V12

Show output previews for both versions and result notes:
V12 角色一致性 +8%
V12 动作稳定性 +4%

RIGHT:
Generation Manifest for the selected generation.

Required fields:
生成ID
生成类型：图生视频
来源：Episode01 / Scene03 / Shot012
Agent：镜头导演
模型：MiniMax H3
模型版本
Provider
Workflow
Workflow Version
画面提示词
运动提示词
负面提示词
Seed
分辨率
宽高比
时长
输入图片
角色参考
场景参考
风格参考
父版本
Prompt Version
输出文件
生成时间
耗时
状态
质量检查结果

Actions:
复用此配置
创建变体
创建分支
回滚到此版本
复制提示词
导出 Manifest
打开镜头

PROMPT TEMPLATE:
Allow converting a successful prompt into a reusable parameterized template:
{角色}
{动作}
{场景}
{景别}
{镜头运动}
{风格}

AI PROMPT ANALYST:
“PV12 成功的主要原因是角色锁定 + 明确低机位 + 独立运动提示词。”
Actions:
生成复用模板 / 对比失败版本 / 优化下一版

Do not make default view too code-heavy. Keep an optional advanced technical diff view inspired by Git.
All generic UI Chinese.
```

---

## 本页专用页面标准

### 核心数据对象：Generation Manifest
每次生成不是只存 Prompt，而要记录生成上下文完整快照。

### 默认交互
- 创作者：可视化 Version Graph + Diff + Output。
- 高级用户：技术 Diff / JSON Manifest 可展开查看。
- 默认不能像纯 Git 页面一样过度技术化。

### 必备操作
复用 / 回滚 / 分支 / 创建变体 / 模板化 / 导出 Manifest。

---

## 验收清单

- [ ] 文生图、图生视频、文生视频都能统一追溯。
- [ ] 有 Prompt Diff。
- [ ] 有版本图和分支。
- [ ] Manifest 包含模型/Seed/Reference/Workflow/Agent/Output。
- [ ] 能从 Prompt 直接回到 Shot。
- [ ] 能一键复用完整配置，而不是只复制文本。
- [ ] 支持导出 Generation Manifest。

---

## Codex + StitchMCP 制作注意事项

P7 建议作为正式开发中的一级数据模型，而不是 UI 后补功能。Codex 后续建数据库时，应围绕 Generation Manifest 设计表结构。
