# P9 — 连续性检查 / AI QA

## 页面定位

P9 负责把大量独立 AI 输出变成连贯作品。重点不是评分，而是“哪里错、为什么、影响什么、怎么修、修复形成哪个新版本”。

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
连续性检查

LEFT:
Episode / Scene filter
Check categories:
角色一致性 / 场景一致性 / 动作连续性 / 镜头连续性 / 剧情连续性 / Prompt一致性 / 音频连续性

CENTER:
Issue-driven QA workspace.

Example issue:
Shot 012 → Shot 013
类型：动作连续性
严重等级：高
状态：待处理

Problem:
沈亦在 Shot 012 使用右手持球，但 Shot 013 变成左手，且没有换手动作。

Evidence:
Shot012 V5 preview
Shot013 V3 preview
Character asset: 沈亦_V12
Prompt PV11 / PV12 difference

Cause:
Shot013 使用旧 Reference + Prompt 中缺少持球手约束.

Impact:
Shot013 / Shot014
Timeline transition
2 downstream video generations

Recommendation:
Use 沈亦_V12
Lock right-hand ball control
Regenerate character/action region only
Create Shot013 V4

Actions:
预览修复 / 自动修复 / 打开镜头 / 查看Prompt / 忽略

BOTTOM OR CENTER SEQUENCE:
Shot011 → Shot012 → Shot013 → Shot014
show direction/pose/continuity markers.

BATCH CHECK:
检查整个 Episode / 当前 Scene / 选中角色 / 选中镜头.

ISSUE STATES:
待处理 / 修复中 / 已修复 / 已忽略 / 需人工判断.
Ignored issues require a reason.

BEFORE/AFTER FIX:
Old version vs fixed version.
Show what changed:
Prompt / Asset / local regeneration / quality result.
Fix creates a new version, never silently overwrite.

RIGHT:
连续性导演
Summarize top risks and propose a fix plan.
Do not just display scores.

All generic UI Chinese.
```

---

## 本页专用页面标准

### 检查维度
- 人物外观与服装
- 动作阶段、朝向、持球手
- 空间、时间、天气、灯光
- 180 度规则、视线、景别跳变
- 剧情前后逻辑
- Prompt 冲突
- 可扩展对白/音频连续性

### 修复原则
- 生成新版本。
- 默认局部重生成优先。
- 必须记录修复原因与 Agent。

---

## 验收清单

- [ ] 页面主角是“问题”，不是仪表盘分数。
- [ ] 每个问题有证据、原因、影响、方案。
- [ ] 修复前/后可比较。
- [ ] 修复生成新版本。
- [ ] Ignore 需要原因。
- [ ] 能跳 P6/P7。
- [ ] 支持 Episode 批量检查。

---

## Codex + StitchMCP 制作注意事项

P9 原型如果已经接近要求，StitchMCP 应使用“modify/refine existing screen”而不是重新生成。
