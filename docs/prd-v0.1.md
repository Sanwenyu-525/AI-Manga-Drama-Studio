# AI Manga Drama Studio — 产品需求文档 PRD v0.1

> 状态：**draft**（已由主创讨论确认，作为后续架构与开发的事实源）
> 归档时间：2025（来自产品定义讨论）
> 关联文档：[系统架构设计 v0.1](./architecture-v0.1.md) · [数据库设计 v0.1](./database-v0.1.md)

---

## 1. 产品名称

暂定：**AI Manga Drama Studio**

定位：AI 原生漫剧制作工作台。

---

## 2. 产品目标

建立一个覆盖 AI 漫剧完整生产流程的桌面级 Studio，使用户无需在 LLM、ComfyUI、图片生成平台、视频生成平台和剪辑工具之间频繁切换。

系统通过 AI Agent 管理漫剧生产流程，并通过标准化生成接口调用不同 AI 模型。

核心目标：

1. 降低 AI 漫剧的制作复杂度。
2. 提高角色、场景和镜头连续性。
3. 自动化重复性的分镜和生成工作。
4. 将漫剧项目从“一堆 Prompt 和文件”变成结构化工程。
5. 允许用户自由选择生成模型，而不绑定某个平台。
6. 为高级用户提供 ComfyUI 深度控制能力。

---

## 3. 核心用户

### 3.1 AI 漫剧创作者

需要：

- 小说改漫剧
- 自动拆剧本
- 自动生成分镜
- 批量生成图片
- 批量生成视频
- 保持人物一致性
- 管理大量素材

### 3.2 AI 视频工作室

需要：

- 多项目管理
- 批量生产
- 模型配置
- 工作流复用
- 成本统计
- 版本管理

### 3.3 ComfyUI 高级用户

需要：

- 自定义 Workflow
- LoRA
- ControlNet
- IPAdapter
- 本地模型
- 高级参数控制

Studio 不替代 ComfyUI，而是在其上提供更高级的制作抽象。

---

## 4. 核心设计原则

### 4.1 项目优先，而不是聊天优先

系统的核心对象不是 Conversation，而是 Project。

项目内部包含：

```
Project
→ Episode
→ Scene
→ Shot
→ Asset
→ Generation
→ Version
```

### 4.2 AI 是操作者，而不是聊天机器人

Agent 可以直接操作：

- 剧本
- 分镜
- 项目
- 角色
- 场景
- 时间线
- Workflow
- Generation Task

例如用户输入："把第二场改得紧张一点。"

Agent 应自动判断：

第二场涉及哪些镜头 → 修改 Shot → 更新 Prompt → 判断哪些镜头需要重新生成 → 提示用户执行生成。

---

## 5. Studio 核心界面

主界面建议采用：

- 左侧：Project Explorer
- 中央：Workspace
- 右侧：AI Director
- 底部：Timeline

### 左侧 Project Explorer

包含：项目、剧集、场景、镜头、角色、场景资产、道具、Workflow、素材。

### 中央 Workspace

根据任务切换：

- **Script View**：小说和剧本编辑。
- **Storyboard View**：分镜浏览。
- **Director Canvas**：可视化制作流程。
- **Preview**：图片和视频预览。
- **Asset Manager**：角色、场景和素材管理。

### 右侧 AI Director

提供自然语言交互。但 AI Director 并不是独立聊天机器人，它拥有对整个项目的操作权限。例如：

- "帮我把这一场拆成八个镜头。"
- "第三镜人物动作不连贯。"
- "全部改成夜景。"
- "重新生成第 4—7 镜。"
- "把第五镜换成近景。"

### 底部 Timeline

展示 Shot 01 / Shot 02 / Shot 03 ……

支持轨：图片、视频、音频、字幕、配音、BGM。

---

## 6. Director Canvas

不要直接复制 ComfyUI。画布节点应该使用影视创作语义。例如：

```
小说章节 → 剧情分析 → Scene → Shot Planning → Storyboard
→ Image Generation → Video Generation → Continuity Check
→ Voice → Composition → Export
```

用户操作的是**影视制作流程**，而不是 KSampler / VAE / CLIP / ControlNet。

ComfyUI Workflow 应该隐藏在 Renderer 层。

---

## 7. Agent 系统

系统不是单 Agent。建议采用：AI Director + 多个专业 Skill / Sub Agent。

第一阶段可以先使用单 Agent + Skills。

### Director Agent

负责：理解用户需求 / 判断项目状态 / 制定任务计划 / 调用 Skills / 更新项目状态。

### Script Skill

小说 → 人物、场景、对话、剧情节点、情绪、冲突、节奏。

### Storyboard Skill

Scene → Shot List。定义：景别、镜头运动、构图、人物、动作、情绪、环境、Prompt。

### Continuity Skill

检查：人物、发型、服装、道具、方位、动作、光线、环境、摄影机位置。

维护：Continuity State。

### Prompt Skill

将结构化 Shot 转换为：GPT Image Prompt / Flux Prompt / SDXL Prompt / 视频 Prompt / ComfyUI 参数。

### Generation Skill

负责：调用生成器 / 创建任务 / 查询状态 / 失败重试 / 保存结果。

### Review Skill

多模态模型检查：人物一致性、画面质量、动作合理性、构图、Prompt 遵循程度、连续性。

---

## 8. Project Memory

不要主要依赖 LLM Context，需要真正的持久化数据库。例如：

- **Character**：ID、Name、Description、Face Reference、Outfit、LoRA、Prompt、Versions
- **Scene**：ID、Location、Time、Lighting、Environment
- **Shot**：ID、Scene ID、Characters、Camera、Composition、Action、Emotion、Dialogue、Prompt、Previous Shot、Next Shot

这样即使模型换掉，项目仍然完整存在。

---

## 9. 模型抽象层

必须做到 Model Agnostic。统一定义：LLM Provider / Image Provider / Video Provider / Vision Provider / Audio Provider。

### LLM

可适配：OpenAI、Anthropic、Gemini、MiniMax、DeepSeek、本地 OpenAI-compatible API。

### Image Generator

支持：ComfyUI、OpenAI Image、云端图片 API、本地模型。

### Video Generator

支持：ComfyUI、API Video Provider、本地 Video Model。

---

## 10. ComfyUI Adapter

ComfyUI 是重点适配对象。Studio 负责：

```
Studio Shot → Parameter Mapping → ComfyUI Workflow JSON
→ ComfyUI API → Queue → Generation → Result → Asset Library
```

用户可以将自己的 ComfyUI Workflow 导入 Studio。Studio 识别 Workflow 中预定义的输入参数，例如：

```
$PROMPT
$NEGATIVE_PROMPT
$REFERENCE_IMAGE
$CHARACTER
$WIDTH
$HEIGHT
$SEED
$FRAME_COUNT
```

然后由 Agent 自动填写。

---

## 11. Workflow Engine

这是整个产品技术上的核心模块之一。每个生成任务成为一个 Task。例如：

```
Episode 01 → Scene 01 → Shot 01 → Storyboard → Image → Review → Video → Review → Completed
```

Workflow Engine 必须支持：DAG / Task Dependency / Queue / Retry / Cancel / Resume / Progress / Parallel Execution / Error Handling。

---

## 12. 版本管理

每一个 Shot 都应该支持版本。例如 Shot 005：V1 / V2 / V3 / V4。

其中：V2 角色更换、V3 构图调整、V4 视频生成。

用户可以：Compare / Restore / Duplicate / Branch。

不建议第一版直接做 Git 式版本控制，先做 Asset Versioning 即可。

---

## 13. MVP 第一阶段

第一版只完成：

- **项目**：创建项目、导入小说、项目保存
- **AI**：小说分析、Scene 拆分、Shot 拆分、Prompt 生成
- **资产**：Character、Scene、Shot
- **生成**：ComfyUI 图片生成
- **界面**：Project Explorer、Storyboard、AI Director、Generation Queue
- **状态**：Shot Version、Generation History

第一版暂时不做：专业剪辑器、音频工作站、多人协作、云同步、完整视频后期、复杂多 Agent。

---

## 14. 第二阶段

增加：GPT Image 等 API、视频生成、Timeline、多模态审核、Continuity Agent、Workflow Canvas、自定义 Workflow、模型 Router。

---

## 15. 第三阶段

增加：自动配音、音效、BGM、自动剪辑、批量生产、Agent 自动运行整集、项目模板、云端任务、团队协作。

最终实现：

```
小说/剧本 → AI Director → 自动建立制作计划 → 角色设定 → 场景设定
→ 分镜 → 图片 → 视频 → 配音 → 剪辑 → 审核 → 成片
```

---

## 16. 技术壁垒

产品核心壁垒不应该是调用某一个 AI 模型。核心壁垒应该形成于：

- **Production Graph**：漫剧生产过程结构化。
- **Project Memory**：长期、稳定、结构化的项目状态。
- **Continuity Engine**：跨镜头连续性。
- **Workflow Orchestration**：复杂生成任务调度。
- **Model Abstraction**：模型可替换。
- **ComfyUI Integration**：高级生成能力。
- **UX**：将复杂 AI Workflow 简化成影视创作语言。

---

## 17. 最终产品定位

产品不应该宣传为"一个可以生成漫剧的 Agent"。更准确的表达是：

> **AI-native Manga Drama Production Studio**

即：一个以 AI Agent 为核心交互方式，以结构化项目系统为记忆，以 Workflow Engine 为执行系统，以 ComfyUI 和生成模型为渲染后端的 AI 原生漫剧生产平台。

---

## 18. MVP 第一刀（闭环验收标准）

开发顺序上不要一开始就做全部功能。第一刀砍在这个闭环：

> **创建项目 → 导入一章小说 → AI 拆 Scene → AI 拆 Shot → 展示 Storyboard → 选中一个 Shot → 调 ComfyUI 生成 → 图片自动回填 Shot → 保存版本。**

只要这个闭环跑通，产品就已经不是 Demo，而是一个真正的 **MVP Studio**。
