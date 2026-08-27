# P4 — AI 工作流画布

## 页面定位

P4 是 DeepSeek Harness 漫剧智能体最能体现 Agent 编排能力的页面。它必须是一条真正可运行、可观察、可修改、可版本化的生产 Pipeline，而不是概念节点 Demo。

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
工作流

LEFT:
Workflow library:
Episode 01 主流程
标准漫剧流程
动作场景流程
角色生成流程
视频生产流程
自定义流程

CENTER:
Large node canvas with a complete readable pipeline, approximately 15-20 nodes.

Required pipeline:

智能体工作区文件读取
↓
剧情分析 Agent
├→ 角色提取
├→ 场景提取
└→ 世界观提取
↓
剧本 Agent
↓
镜头规划 Agent
↓
分镜 Agent
↓
提示词编译器
↓
图片生成
↓
视频生成
↓
连续性检查
├─ 通过 → 人工审核
└─ 不通过 → AI导演修正 → Prompt/Shot 新版本 → 重新生成 → 再检查
↓
时间线装配
↓
导出

Required node types with distinct but restrained visual language:
- 数据/源文件节点
- AI智能体节点
- 提示词节点
- 模型/生成节点
- 外部工具节点
- 条件节点
- 人工审核节点
- 输出节点

PROMPT COMPILER NODE:
Input structured fields:
角色 / 动作 / 场景 / 景别 / 镜头运动 / 风格 / 约束
Output:
画面提示词 / 运动提示词 / 负面提示词 / 参数 / Prompt Version

GENERATION NODES:
GPT Image / ComfyUI / MiniMax H3.
Show queue/progress/version and outputs.

HUMAN APPROVAL:
待确认
通过 / 请求修改 / 打开结果

AI LOOP:
Continuity score < threshold → AI导演修正 → new prompt version → regenerate.

RIGHT:
工作流导演
Detect bottlenecks and propose structural changes.
Example:
“视频生成占总耗时 72%，建议增加并行队列，但角色高一致性镜头保留主队列。”
Actions:
预览变更 / 应用优化 / 查看原因

TOP CANVAS TOOLBAR:
运行 / 运行选中 / 暂停 / 停止 / 调试 / 单步 / 验证 / 自动布局 / 保存版本.

NODE INSPECTOR:
Name / Type / Agent / Model / System Prompt / Tools / Inputs / Outputs / Retry / Timeout / Parallelism / Cache / Version / Logs / Trace.

All UI Chinese.
```

---

## 本页专用页面标准

### 工作流必须体现
- Agent 不是单纯模型调用。
- Prompt Compiler 是独立节点。
- 连续性检查后有“失败回路”。
- 至少一个人工审核 Gate。
- External Tool 如 ComfyUI 必须可见。
- 节点支持执行记录与版本。

### 可读性
- 分组：前期分析 / 创作规划 / 生成 / 审核 / 后期输出。
- 不要做成密密麻麻的 ComfyUI 低层参数图。

---

## 验收清单

- [ ] 至少 15 个有意义节点。
- [ ] Source→Agent→Prompt→Image→Video→QA→Human→Timeline→Export 完整。
- [ ] 有条件分支和自动修正回路。
- [ ] 有人工审核节点。
- [ ] 节点能查看 Prompt/输入/输出/Trace。
- [ ] 右侧 AI 能提出工作流结构优化。

---

## Codex + StitchMCP 制作注意事项

如果 Stitch 画面只有 6-8 个大节点，要求 `show the complete end-to-end pipeline with 15-20 compact nodes and grouped stages`。
