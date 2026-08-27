# P5 — AI 漫剧资产中心

## 页面定位

P5 不是素材 Gallery，而是可复用、可约束、可追踪的 IP 资产数据库。角色、场景、道具、风格包必须能影响后续生成，并能做一致性锁定与依赖影响分析。

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
资产

LEFT:
Asset categories:
角色 / 场景 / 道具 / 风格包 / 图片 / 视频 / 音频 / 参考资料 / 生成历史 / 回收站

CENTER:
Dense asset browser, not empty cards.
Show 8-16 assets in the current viewport depending on size.

Default:
角色

Character card example:
沈亦
主角
V12 ★ 主版本
一致性 96%
引用 48 个镜头
状态：已锁定
thumbnail/reference count

Other character cards and scene cards should also be visible to create realistic density.

SELECTED CHARACTER DETAIL:
来源：智能体工作区 / characters/沈亦.md
主版本：V12
主参考
脸部参考
全身参考
侧脸
表情表
动作表
服装
年龄变化
Prompt Version
生成模型
最近使用
引用镜头

CONSISTENCY LOCK:
可锁定：
脸型 / 发型 / 身材比例 / 服装特征 / 色彩 / 风格

GENERATION ACTIONS:
生成立绘 / 补侧脸 / 生成表情 / 生成动作 / 创建服装变体 / 创建新版本.

DEPENDENCY:
沈亦_V12 used by:
Episode01 Shot001 / 012 / 025...
If modifying:
影响 18 个镜头
Options:
创建新版本 / 仅当前镜头使用 / 评估替换影响

PROMPT ASSOCIATION:
Every generated asset stores:
Prompt / Negative Prompt / Model / Seed / References / Workflow / Agent / Version.
Action:
查看提示词历史

SCENE ASSET:
NBA总决赛球馆 V5
References 18
Used by 42 shots
Lighting / time / environment / camera references / prompt / versions.

STYLE PACK:
现代动漫电影风
Preview + line style + color tone + lighting + texture + compatible models.

RIGHT:
资产导演
Example:
“沈亦 V12 是当前一致性最高主版本，建议锁定，并补充侧脸与高速突破动作参考。”
Actions:
锁定主版本 / 生成补充 / 查看影响

Use Chinese UI and consistent basketball project content.
```

---

## 本页专用页面标准

### 密度
- 资产浏览区不能大片空白。
- 默认一屏至少展示 8 个可识别资产条目/卡片。
- 角色详情可用侧栏/Inspector，不要让每张卡过大。

### 角色资产是“资产包”
一名角色不是一张图，而是一组 Reference + Rules + Prompt + Version + Usage。

---

## 验收清单

- [ ] 一屏资产密度足够。
- [ ] 沈亦有主版本和一致性锁定。
- [ ] 能查看来源设定、Prompt、版本、引用镜头。
- [ ] 修改资产前显示影响范围。
- [ ] 支持“创建新版本”而不是直接覆盖。
- [ ] 场景和风格包不是角色页面的装饰项，而是完整资产类型。

---

## Codex + StitchMCP 制作注意事项

P5 和 P8 不同：P5 管“可用于生成的生产资产”，P8 管“Agent 理解和约束生产的知识”。
