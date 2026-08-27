# P10 — AI 漫剧时间线

## 页面定位

P10 是后期装配中心，但明确不做 Premiere 克隆。重点是 Shot 版本装配、对白/字幕/音乐/音效、AI 节奏分析、智能替换和基础剪辑。

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
时间线

LEFT:
Episode structure:
Episode 01
Scene 01
Scene 02
Scene 03
with shot lists.

CENTER:
Professional simplified timeline.

Required tracks:
视频
对白
字幕
音乐
音效

Every video clip MUST show:
Shot 012 · V5
5.8s
status/quality marker

Clicking a clip provides actions:
打开镜头
替换版本
重新生成
查看提示词
查看来源

Basic edit controls only:
播放 / 暂停 / 拖动 / Trim / Split / Move / Replace.
Avoid advanced color grading and professional NLE complexity.

DIALOGUE:
character + text + voice profile + timing
Actions:
重新生成语音 / 修改语气 / 打开文本来源

SUBTITLE:
automatic sync / edit / translation

MUSIC:
emotion label + range
SFX:
events aligned to shots

AI RHYTHM ANALYSIS:
Show narrative structure:
开场 / 建立 / 冲突 / 高潮 / 收束
Highlight slow/fast regions.

RIGHT:
AI剪辑导演
Example:
“Scene 03 节奏偏慢，建议缩短 Shot 028 的停留 1.8 秒，并延长 Shot 032 高潮动作 0.6 秒。”
Actions:
预览方案 / 应用 / 查看理由

AI AUTO EDIT:
Options:
剧情优先 / 节奏优先 / 情绪优先
Always preview before applying.

VERSION:
Episode01 Timeline V5
Compare / restore / branch.

EXPORT:
导出视频 / 字幕 / 音频 / 发布版本.

All generic UI Chinese.
```

---

## 本页专用页面标准

### 不做 Premiere
只做漫剧真正需要的轻量编辑 + AI辅助。
复杂调色、复杂混音、插件链不是 P10 MVP 重点。

### Shot 是一等公民
时间线 Clip 不只是 mp4 文件，必须关联 Shot ID + Version + Prompt + Source。

---

## 验收清单

- [ ] 所有视频 Clip 显示 Shot + Version。
- [ ] Clip 可跳 Shot Inspector/Prompt。
- [ ] 有对白/字幕/音乐/音效轨。
- [ ] AI 能分析节奏并先预览再应用。
- [ ] 有 Timeline 版本。
- [ ] 没有变成复杂 Premiere Clone。

---

## Codex + StitchMCP 制作注意事项

Timeline 页应与 P6/P7 建立非常强的跳转关系，否则会变成孤立剪辑器。
