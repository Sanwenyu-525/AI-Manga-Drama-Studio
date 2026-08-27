# P6 — 镜头检查器 Shot Inspector

## 页面定位

P6 汇聚单镜头所有生产数据，是整个系统最重要的深度编辑页面之一。必须把剧情意图、相机、角色、场景、Prompt、Reference、模型参数、局部重生成、版本、连续性整合到一起。

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
镜头

Layout:
Left: Shot navigator
Center: large image/video preview
Right: Shot Inspector + Shot Director
Bottom: mini timeline

LEFT:
Episode 01 / Scene 03
Shot list with thumbnail, duration, status, version.
Selected: Shot 012.

CENTER PREVIEW:
Video/image preview.
Controls:
播放 / 暂停 / 逐帧 / 全屏 / A-B 比较 / 查看输入 / 查看输出.
Overlay:
Shot 012 · V5 当前
MiniMax H3
5.8s

RIGHT INSPECTOR sections:

1. 剧情意图
来源 Chapter 12
剧情目标
情绪
叙事重要度
Previous/Next Shot links

2. 相机
景别 / 角度 / 机位 / 镜头运动 / 镜头焦段 / 景深

3. 角色
沈亦_V12
动作 / 表情 / 朝向 / 姿态 / 服装
一致性锁定

4. 场景
NBA球馆_V5
灯光 / 时间 / 环境 / 相机位置

5. 视觉风格
Anime_Cinematic_V3
style lock

6. 提示词
Separate clearly:
画面提示词
运动提示词
负面提示词
技术参数
Prompt Version
Button: 查看提示词历史

7. References
角色参考 / 场景参考 / 风格参考 / 上一镜参考
Lock / replace / remove

8. 生成
Image model / Video model
Seed / resolution / duration / mode
Generate Image / Generate Video / Regenerate / Create Variant

LOCAL REGENERATION:
Support:
角色区域 / 背景 / 光影 / 局部区域 / 镜头运动 / 音频
Show region preview and preserve locked layers/references.

VERSION COMPARE:
V4 vs V5
Prompt Diff / Asset Diff / Model Diff / quality changes
Choose V4 / V5 / branch.

RIGHT AI:
镜头导演
“Shot 012 与 Shot 011 持球手存在连续性风险。”
Actions:
应用建议 / 预览修改 / 打开连续性检查 / 忽略

BOTTOM:
Shot011 / Shot012 / Shot013
video/dialogue/subtitle/sfx tracks.

All generic UI Chinese.
```

---

## 本页专用页面标准

### Prompt 必须拆分
- 画面提示词
- 运动提示词
- 负面提示词
- 技术参数
不要把图生视频所有控制混成一个大文本框。

### 局部重生成
这是核心差异功能，UI 必须明显支持“只改角色/区域/运动，不推翻整镜头”。

### 与 P7
P6 展示“当前镜头 Prompt 摘要和入口”；完整历史、Diff、Manifest 在 P7。

---

## 验收清单

- [ ] 左/中/右/底四区结构清晰。
- [ ] Prompt 至少分画面/运动/负面。
- [ ] 有 Reference 锁定。
- [ ] 有局部重生成。
- [ ] 有 V4/V5 比较。
- [ ] 能打开 P7 提示词历史。
- [ ] 能打开 P9 连续性问题。

---

## Codex + StitchMCP 制作注意事项

优先保留现有 Shot Inspector 原型的“大预览 + 右 Inspector”骨架，再把更技术化候选版本里的 Prompt Diff、Seed、局部区域生成能力合入。
