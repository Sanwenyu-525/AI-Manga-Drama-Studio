# P3 — 分镜工作区 Storyboard

## 页面定位

分镜页是日常高频生产页面。它不是图片墙，而是“源剧情 + 镜头意图 + 资产 + Prompt + 生成 + 版本 + 连续性”的镜头级总览。

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
Continue the exact same shell and design system.

Active module:
分镜

LEFT:
Episode / Scene / Shot navigation.
Example:
Episode 01
├─ Scene 01 球馆入口
├─ Scene 02 比赛开始
└─ Scene 03 最后一分钟
   ├─ Shot 011
   ├─ Shot 012
   └─ Shot 013

CENTER:
Dense storyboard grid with 6-10 shots visible in one 1920x1080 viewport.
Support card size: 小 / 中 / 大.

Each shot card must show:
Shot 012
preview
5.8s
状态：视频完成
版本：V5
来源：Chapter 12
剧情：最后一次进攻
角色：沈亦_V12
场景：NBA球馆_V5
镜头：低角度推进
Prompt：PV12
generation indicator

Card actions:
打开镜头 / 查看提示词 / 比较版本 / 重新生成 / AI优化 / 检查连续性 / 复制 / 拖拽排序

TOP TOOLBAR:
Episode selector / Scene selector / 搜索 / 筛选 / 网格/时间线 / 创建镜头 / AI生成分镜 / 批量生成 / 批量检查.

RIGHT:
Only a QUICK INSPECTOR, not the full P6 Shot Inspector.
Show selected shot summary:
剧情意图、相机、角色、资产、Prompt、生成状态、连续性提示.
Primary action:
打开镜头检查器

AI section:
“Shot 012 与 Shot 011 的持球手连续性存在风险。”
Actions:
预览建议 / 应用 / 打开连续性检查

BOTTOM:
Mini timeline around current scene:
Shot 011 / 012 / 013 with video/dialogue/subtitle/sfx indicators.

All visible generic UI Chinese.
```

---

## 本页专用页面标准

### 与 P6 的职责边界
- P3：多镜头浏览、排序、批量、Quick Inspector。
- P6：单镜头深度参数、Prompt、生成、局部重生成、版本对比。
- P3 右侧不可塞入完整 P6 参数表。

### 卡片必备数据
Source + Asset + Prompt + Version + Generation Status 至少 4 类必须可见。

---

## 验收清单

- [ ] 一屏至少能看 6 个镜头。
- [ ] 不是纯图片 Gallery。
- [ ] 每张卡有来源、资产/角色、Prompt/版本、状态。
- [ ] Quick Inspector 有“打开镜头检查器”。
- [ ] 支持批量生成和连续性检查。
- [ ] 拖拽排序明显可用。

---

## Codex + StitchMCP 制作注意事项

如果 Stitch 又只生成 3 张超大卡片，要求 `increase storyboard density and show 8 shots in the current viewport`。
