# AI 漫剧 Studio — AI Director Agent 详细设计 v0.1

> 文档类型：**Agent Architecture Specification**
> 状态：**draft**（主创定稿，Agent 层实现与前端 Director UI 的事实源）
> 目标阶段：MVP → V1
> Agent Runtime：LangGraph
> AI Components：LangChain
> 业务执行层：Studio Application Services
> 核心原则：Agent 负责决策，Service 负责执行，Project State 负责事实
> 关联文档：[PRD v0.1](./prd-v0.1.md) · [系统架构设计 v0.1](./architecture-v0.1.md) · [数据库与 ER 模型设计 v0.1](./database-v0.1.md) · [后端 API 与 Service 架构 v0.1](./backend-architecture-v0.1.md)

---

# 1. AI Director 的产品定位

AI Director 不是：

> 一个放在 Studio 右侧的聊天机器人。

也不是：

> 一个替用户写 Prompt 的助手。

AI Director 应被定义为：

> **AI 漫剧 Studio 的智能控制层。**

它能够理解用户的自然语言意图，读取当前项目状态，制定修改或生产计划，调用 Studio 能力执行操作，并持续检查结果。

例如用户输入：

> "第三场节奏有点拖，把它压缩到 25 秒左右，减少两个没必要的镜头，然后重新生成受影响的分镜。"

AI Director 应执行：

```text
理解请求
 ↓
定位 Scene 03
 ↓
读取 Scene + Shots + Characters + 当前版本
 ↓
分析节奏
 ↓
生成 ModificationPlan
 ↓
识别将删除 / 合并 / 修改的 Shot
 ↓
风险判断
 ↓
请求用户确认
 ↓
创建版本快照
 ↓
修改 Scene / Shot
 ↓
标记受影响镜头 Dirty
 ↓
创建 Storyboard Generation Tasks
 ↓
返回操作结果
```

所以它本质上是：

```text
Natural Language
      ↓
Production Intent
      ↓
Project Operation
```

---

# 2. AI Director 的核心职责

AI Director 第一阶段负责六类事情。

## 2.1 理解

理解用户想干什么：

```text
修改剧情
修改镜头
修改角色
生成图片
生成视频
重新生成
检查连续性
查询项目
比较版本
批量处理
```

---

## 2.2 定位

把自然语言对象映射到真实 Project Entity。

例如：

```text
"第三场"
→ scene_003

"刚才那个近景"
→ shot_014

"男主"
→ character_001

"上一镜"
→ shot.previous_shot_id
```

---

## 2.3 规划

复杂任务不直接执行。

先生成：

```text
ExecutionPlan
```

例如：

```text
Step 1 修改 Shot 12 duration

Step 2 合并 Shot 13 和 Shot 14

Step 3 调整 Shot 15 camera

Step 4 更新对应 Prompt

Step 5 检查连续性

Step 6 标记 4 个镜头需要重新生成
```

---

# 3. 执行

AI Director 不直接操作基础设施。

它调用：

```text
Studio Tools
      ↓
Application Services
```

例如：

```text
update_shot
      ↓
ShotService.update()
```

而不能：

```text
LLM
 ↓
UPDATE shots SET ...
```

---

# 4. 验证

执行后不能马上宣布成功。

必须验证：

```text
目标是否完成

数据库是否正确更新

业务约束是否满足

连续性是否遭到破坏

是否产生新的待处理任务
```

---

# 5. 协调

AI Director 可以协调：

```text
Script
Storyboard
Assets
Generation
Continuity
Version
Workflow
```

但不负责亲自执行底层 GPU / API 工作。

---

# 6. 汇报

完成后输出：

```text
做了什么

影响了哪些 Scene / Shot

生成了哪些任务

哪些任务仍在进行

是否需要用户下一步决定
```

不要输出大量内部 Chain-of-Thought。

---

# 7. 系统核心结构

```text
                    User
                      │
                      ▼
               AI Director API
                      │
                      ▼
                Director Graph
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
       Context       Skills       Tools
          │           │            │
          │           │            ▼
          │           │      Application Service
          │           │            │
          └───────────┼────────────┘
                      ▼
                 Project State
```

---

# 8. 为什么使用 LangGraph

Director 属于典型的：

```text
Stateful
+
Multi-step
+
Conditional
+
Human-in-the-loop
+
Long-running
```

Agent。

LangGraph 当前的官方设计就是通过共享 State、Nodes 和 Edges 建立这类有状态执行图，同时提供 persistence、interrupt 和恢复执行等能力。([Docs by LangChain][1])

因此：

```text
Director Runtime
=
LangGraph
```

---

# 9. Director Graph 总体设计

MVP 建议控制在大约 10 个核心节点。

```text
START
  │
  ▼
Understand
  │
  ▼
Resolve Entities
  │
  ▼
Load Context
  │
  ▼
Plan
  │
  ▼
Risk Evaluate
  │
  ├──── Approval Required ──────┐
  │                             ▼
  │                        Human Approval
  │                             │
  │                             ▼
  └────────────────────────── Execute
                                │
                                ▼
                              Observe
                                │
                                ▼
                              Review
                       ┌────────┴─────────┐
                       │                  │
                   Need Fix            Complete
                       │                  │
                       └──→ Execute       ▼
                                         END
```

LangGraph 的 interrupt 可以在节点执行期间暂停 Graph，持久化状态并等待外部输入，然后再恢复，因此特别适合批量生成、删除、覆盖等审批操作。([Docs by LangChain][2])

---

# 10. DirectorState

Agent运行时必须拥有明确 State Schema。

建议：

```python
class DirectorState(TypedDict):

    # Identity
    run_id: str
    project_id: str
    session_id: str

    # User
    user_message: str

    # Understanding
    intent: dict | None
    entities: list

    # Context
    context: dict

    # Planning
    plan: dict | None
    current_step: int

    # Execution
    tool_requests: list
    tool_results: list

    # Changes
    affected_entities: list
    created_entities: list
    dirty_entities: list

    # Risk
    risk_level: str
    approval_request: dict | None
    approval_result: dict | None

    # Review
    review_result: dict | None

    # Runtime
    errors: list
    retry_count: int
    status: str

    # Result
    final_result: dict | None
```

---

# 11. DirectorState 不保存什么

不要在 DirectorState 中长期保存：

```text
完整小说

全部角色

全部 Shot

全部图片

整个聊天记录

完整 Workflow JSON
```

这些属于：

```text
Project Database
Asset Storage
```

Agent State只保存当前工作需要的数据和引用。

---

# 12. Runtime Context

区分：

```text
State
```

和：

```text
Runtime Context
```

Runtime Context 保存不应该成为业务状态的执行配置，例如：

```text
current_user

selected_model

LLM Gateway

Service Container

feature flags

permissions
```

LangGraph 当前 Graph API 支持在运行时提供 context，并在 node / edge 中读取。([Docs by LangChain][3])

---

# 13. Understand Node

职责：

> 将自然语言转换成标准 ProductionIntent。

输入：

```text
"把后面三个镜头做得更紧张一点。"
```

输出：

```json
{
  "intent_type": "modify_shots",
  "scope": "relative_shots",
  "operation": "increase_tension",
  "requires_generation": false
}
```

---

# 14. ProductionIntent Schema

建议：

```python
class ProductionIntent(BaseModel):

    intent_type: Literal[
        "query",
        "create",
        "modify",
        "generate",
        "review",
        "compare",
        "delete",
        "export"
    ]

    target_type: str | None

    target_reference: str | None

    instruction: str

    batch: bool = False

    destructive: bool = False
```

必须使用 Structured Output。

LangChain 当前支持将 Agent / Model 输出约束为 JSON、Pydantic Model 或 dataclass 等机器可消费结构。([Docs by LangChain][4])

---

# 15. Resolve Entity Node

解决自然语言引用。

例如：

```text
"第五镜"
```

解析：

```text
shot_id = sh_xxx005
```

"上一镜"：

```text
selected_shot.previous_shot_id
```

"女主"：

```text
Character Alias Search
```

---

# 16. Entity Resolver

优先级：

```text
明确 ID
 ↓
当前 Selection
 ↓
结构位置
 ↓
名称 / Alias
 ↓
Semantic Search
 ↓
要求用户消歧
```

例如项目中有两个"医院场景"，不要让 AI 猜。

进入：

```text
Clarification Required
```

Ownership 与歧义规则（P1-E3-T01）：

- 解析结果必须满足：目标存在、未软删除、属于当前 Run 的 project。
- 跨项目 Shot ID / 已删除 Shot / 伪造 selection → rejected/not_found，
  在工具执行前失败（ContextService.resolve_shot_reference 返回结构化
  ShotResolution：resolved | ambiguous | not_found | rejected | none）。
- `shot_number:N` 先用 selection.scene_id 定域；项目内重号且无定域 → ambiguous，
  要求澄清，绝不静默取首个。
- ToolExecutor 是第二道防线：每个工具目标在执行前再次校验 project ownership，
  不能只信任 Planner 的输出。
- Selection 只通过 Run 的 Graph State / 调用参数传递（run-local），
  FakeLLM 从 prompt 解析 selection，不再使用进程全局变量。

---

# 17. Studio Selection Context

这是前端未来非常关键的数据。

Frontend 应向 Director提供：

```json
{
  "selected_episode_id": "...",
  "selected_scene_id": "...",
  "selected_shot_ids": ["..."],
  "selected_asset_ids": [],
  "active_workspace": "storyboard"
}
```

这样用户可以直接说：

> "把这个改成近景。"

AI Director知道：

```text
这个
=
当前选中的 Shot
```

这是 Studio Agent 相比传统聊天 Agent 非常重要的能力。

---

# 18. Load Context Node

ContextService 根据：

```text
Intent
+
Target Entity
+
Current UI Selection
```

构建最小必要 Context。

例如修改 Shot 14：

```text
Project Style

Scene

Shot 13

Shot 14

Shot 15

Character

Costume

Relevant Assets

Continuity State
```

---

# 19. Context Engineering 原则

采用：

> **Minimum Sufficient Context**

而不是：

> Maximum Context。

LangChain 当前也将 context engineering 定义为控制 Agent 在每一步能够看到哪些信息，而 Structured Output、State、Store 和 runtime context 都可参与这一过程。([Docs by LangChain][5])

---

# 20. Context 类型

分成五类。

## Global Context

```text
Project Style
Aspect Ratio
Visual Style
Global Production Rules
```

## Narrative Context

```text
Episode
Scene
Story Beat
```

## Shot Context

```text
Previous Shot
Current Shot
Next Shot
```

## Asset Context

```text
Character
Costume
Location
Prop
Reference
```

## Production Context

```text
Generation
Workflow
Provider
Version
Continuity
```

---

# 21. Planner Node

简单请求：

> 第五镜改成近景。

不需要复杂 Plan。

直接：

```text
update_shot
```

复杂请求：

> "重做第三场，让节奏更紧凑，并重新生成有影响的镜头。"

必须生成：

```text
ModificationPlan
```

---

# 22. ModificationPlan

```python
class PlanStep(BaseModel):

    step_id: str

    operation: str

    entity_type: str

    entity_id: str | None

    parameters: dict

    depends_on: list[str] = []


class ModificationPlan(BaseModel):

    objective: str

    steps: list[PlanStep]

    affected_entities: list[str]

    estimated_generation_tasks: int

    risk_level: str
```

---

# 23. Plan 与 Production Workflow 的区别

Agent Plan：

```text
调整镜头
修改角色
创建生成任务
```

Production Workflow：

```text
真正运行 30 个 GPU / Video Task
```

Agent只负责创建 Workflow Run。

不自己执行长任务。

---

# 24. Risk Evaluation Node

所有操作进入风险分类。

建议四级。

## R0 — Read

```text
查询 Shot
检查场景
分析剧情
```

自动。

## R1 — Reversible Edit

```text
修改 Shot
修改 Prompt
创建角色
```

自动执行，但创建 Version。

## R2 — Expensive

```text
批量图片生成
视频生成
调用收费 API
```

根据用户设置与成本阈值确认。

## R3 — Destructive

```text
删除 Scene
大量删除 Shot
删除资产
覆盖关键内容
```

必须确认。

---

# 25. ApprovalRequest

标准结构：

```python
class ApprovalRequest(BaseModel):

    title: str

    description: str

    risk_level: str

    affected_entities: list[str]

    estimated_tasks: int | None

    estimated_cost: float | None

    options: list[str]
```

Frontend据此生成确认 UI。

---

# 26. Human Approval

例如：

```text
AI 准备执行：

• 删除 2 个 Shot
• 修改 7 个 Shot
• 重新生成 5 张图片

[批准]
[修改计划]
[取消]
```

不是简单：

```text
Are you sure?
```

---

# 27. Execute Node

Execute Node 不实现业务。

只负责：

```text
PlanStep
 ↓
Tool Registry
 ↓
Studio Tool
```

---

# 28. Tool Registry

例如：

```text
project.get

scene.get

scene.update

shot.get

shot.list

shot.create

shot.update

shot.delete

shot.reorder

character.get

character.create

asset.list

generation.create

continuity.check

version.restore
```

LangChain Tool 是具有明确输入输出的 callable abstraction，模型能够根据上下文选择调用。([Docs by LangChain][6])

---

# 29. Tool → Service

严格遵守：

```text
LangChain Tool
       ↓
Tool Adapter
       ↓
Application Service
       ↓
Repository / Infrastructure
```

例如：

```text
update_shot Tool
       ↓
ShotToolAdapter
       ↓
ShotService.update()
```

---

# 30. Tool 禁止事项

Tool 不允许：

```text
直接写 SQL

直接删除文件

直接发送 ComfyUI Workflow

直接写 project.db

直接操作 UI
```

---

# 31. Tool Schema

Tool参数必须严格结构化。

错误：

```text
update_shot("帮我把它改好")
```

正确：

```json
{
  "shot_id": "shot_014",
  "patch": {
    "shot_type": "close_up",
    "emotion": "tense"
  }
}
```

---

# 32. Tool Result

也统一结构：

```python
class ToolResult(BaseModel):

    success: bool

    entity_id: str | None

    changed_fields: list[str]

    created_entities: list[str]

    warnings: list[str]

    error: str | None
```

Agent不依赖任意自然语言结果。

---

# 33. Observe Node

Tool执行后：

```text
读取 ToolResult

更新 DirectorState

记录 affected_entities

记录 dirty_entities

记录 error
```

例如 Shot 修改后：

```text
shot_14 → DIRTY_IMAGE
```

---

# 34. Dirty State

非常建议引入。

例如：

```text
CLEAN

DIRTY_STORYBOARD

DIRTY_IMAGE

DIRTY_VIDEO

DIRTY_AUDIO
```

如果用户只改变：

```text
字幕
```

不需要重新生成图片。

如果改变：

```text
角色服装
```

则：

```text
Image
Video
```

可能全部变 Dirty。

---

# 35. Dependency Impact Analyzer

后期这是非常重要的 Studio 能力。

例如：

```text
Character Outfit 修改
        ↓
找到引用该 Outfit 的 Shots
        ↓
标记受影响 Shots
        ↓
提示重新生成
```

AI Director负责触发。

真正依赖关系由：

```text
ImpactService
```

计算。

---

# 36. Review Node

完成操作后执行任务级 Review。

检查：

```text
用户目标是否完成

Tool是否全部成功

业务数据是否一致

是否仍存在错误

是否产生未满足依赖

是否需要进一步操作
```

---

# 37. ReviewResult

```python
class ReviewResult(BaseModel):

    completed: bool

    objective_score: float

    remaining_issues: list

    recommended_actions: list

    requires_retry: bool
```

---

# 38. Retry Loop

如果：

```text
Tool网络失败
Model暂时失败
Structured Output错误
```

可以 Retry。

如果：

```text
用户需求本身不明确
```

不能盲目 Retry。

应该：

```text
Ask User
```

---

# 39. Retry 策略

建议：

```text
Model transient error
→ 2–3 retries

Tool transient error
→ exponential backoff

Validation error
→ repair once

Permission / business error
→ no retry

User ambiguity
→ interrupt
```

LangChain 当前也提供 model retry 和 tool retry 等 middleware，但 MVP 阶段建议只对明确的 transient failure 使用，避免把控制逻辑隐藏得过深。([Docs by LangChain][7])

---

# 40. Skills

Skill 与 Tool不同。

Tool：

> 系统能做什么。

Skill：

> 一个专业任务应该怎么做。

第一版建议七个。

```text
Script Analysis

Scene Planning

Storyboard

Character Design

Prompt Engineering

Continuity

Generation Review
```

---

# 41. Storyboard Skill

输入：

```text
Scene Context
Character Context
Style
```

输出：

```text
ShotPlan[]
```

流程：

```text
读取 Scene
 ↓
分析 Story Beat
 ↓
估算 Shot 数量
 ↓
安排景别
 ↓
安排摄影机
 ↓
安排动作
 ↓
检查节奏
 ↓
Structured ShotPlan
```

---

# 42. Script Analysis Skill

输出：

```text
Characters

Locations

Story Beats

Conflict

Emotion Curve

Scenes
```

注意：

它负责分析。

不直接创建数据库对象。

之后由 Application Service 写入。

---

# 43. Prompt Skill

不要让 Prompt 成为 Source of Truth。

输入：

```text
Shot
Character
Location
Style
Provider Capability
```

输出：

```text
GenerationPrompt
```

Prompt 是 Shot 的派生结果。

---

# 44. Continuity Skill

负责：

```text
Shot N
+
Shot N+1
+
Visual Assets
 ↓
Continuity Report
```

检查：

```text
角色外观

服装

空间方向

手持物

动作

环境

光线

摄影机

屏幕方向
```

---

# 45. Review Skill

多模态模型可以检查：

```text
Prompt adherence

Character consistency

Composition

Artifacts

Continuity

Visual quality
```

然后输出：

```text
ReviewResult
```

---

# 46. 第一阶段不要拆 Multi-Agent

MVP：

```text
Director Agent
   │
   ├── Script Skill
   ├── Storyboard Skill
   ├── Prompt Skill
   ├── Continuity Skill
   └── Review Skill
```

而不是：

```text
Director Agent

Writer Agent

Storyboard Agent

Camera Agent

Prompt Agent

Review Agent
```

原因：

Multi-Agent 会额外增加：

```text
Context Transfer

Handoff

Debugging

Token Cost

State Synchronization
```

第一版收益不够高。

---

# 47. 什么时候升级为 Sub-Agent

满足至少两个条件时考虑拆分：

```text
拥有独立长期 Context

拥有独立 Tool Set

需要独立循环

任务复杂度明显高

需要独立模型

需要独立评估体系
```

例如未来：

```text
Continuity Agent
```

可能值得独立。

---

# 48. System Prompt 架构

不要写一个 10,000 字超级 System Prompt。

拆成：

```text
Core Identity

Operating Rules

Domain Rules

Tool Rules

Safety Rules

Current Context

Skill Prompt
```

---

# 49. Core System Prompt 应负责

定义：

```text
你是谁

你的目标

Project State 是事实来源

什么时候调用 Tool

什么时候不能猜

什么时候必须审批

什么时候停止
```

---

# 50. Prompt 不应该保存业务事实

错误：

```text
System Prompt:

主角沈亦穿白色7号球衣……
```

正确：

```text
ContextService
 ↓
Character Entity
```

动态注入。

System Prompt只保存稳定规则。

---

# 51. Director 最重要的行为规则

建议写进 System Prompt：

```text
1. Never invent project entities.

2. Resolve references before mutation.

3. Read before write.

4. Use Studio Tools for all project mutations.

5. Never directly manipulate storage.

6. Create reversible changes whenever possible.

7. Request approval before destructive operations.

8. Do not wait synchronously for long generation jobs.

9. Treat Project State as authoritative.

10. Report actual execution results, not intended results.
```

---

# 52. Agent API

创建运行：

```text
POST /api/agent/director/runs
```

Request：

```json
{
  "project_id": "project_001",

  "message": "把第五镜改成近景然后重新生成",

  "selection": {
    "scene_id": "scene_003",
    "shot_ids": ["shot_005"]
  }
}
```

Response：

```json
{
  "run_id": "run_001",
  "status": "running"
}
```

---

# 53. Resume API

如果 Interrupt：

```text
POST /api/agent/director/runs/{run_id}/resume
```

Request：

```json
{
  "decision": "approve"
}
```

---

# 54. Cancel API

```text
POST /api/agent/director/runs/{run_id}/cancel
```

只取消：

```text
Agent Run
```

不自动取消已经创建的 Production Tasks。

这两个生命周期必须分开。

---

# 55. Agent Event Stream

前端应看到结构化状态事件。

例如：

```text
agent.run.started

agent.intent.resolved

agent.context.loaded

agent.plan.created

agent.approval.required

agent.tool.started

agent.tool.completed

agent.review.completed

agent.run.completed

agent.run.failed
```

---

# 56. Event Payload

例如：

```json
{
  "type": "agent.tool.completed",

  "run_id": "run_001",

  "tool": "update_shot",

  "entity_id": "shot_005",

  "timestamp": "..."
}
```

---

# 57. Agent Streaming

不要只 Stream LLM token。

Studio 更应该 Stream：

```text
Execution Events
```

用户真正关心：

```text
正在分析

计划修改5个镜头

已修改3/5

需要确认

生成任务已经提交
```

LangGraph/LangChain 当前支持流式 Agent、tool 与 state updates，可作为这套 Event Stream 的底层能力之一。([Docs by LangChain][8])

---

# 58. UI 不展示 Chain-of-Thought

可以展示：

```text
Plan

Actions

Progress

Reason Summary

Diff

Warnings
```

不要展示模型完整内部推理。

例如展示：

```text
"由于 Shot 13 与 Shot 14 动作重复，我建议合并。"
```

而不是内部逐 token reasoning。

---

# 59. Persistence

LangGraph Checkpoint保存：

```text
Agent Run State
```

Studio Database保存：

```text
Project State
```

严格分开。

LangGraph 官方当前提供 SQLite 与 PostgreSQL 等 checkpointer 实现，因此本地 MVP 可采用 SQLite checkpointer，未来云端再切换生产级持久化方案。([Docs by LangChain][9])

---

# 60. Thread 模型

建议：

```text
Project
 └── Agent Session
       └── Thread
             └── Runs
```

一个 Project 可以拥有多个 AI Director Session。

例如：

```text
Main Production

Character Design Discussion

Episode 03 Rework
```

---

# 61. Conversation Memory

聊天只作为：

```text
Interaction History
```

不是业务状态。

如果用户之前说：

> 男主以后都穿黑衣服。

AI 如果只是"记住"在聊天里是不够的。

应该转换为：

```text
Character / Costume Update
```

保存 Project DB。

---

# 62. Semantic Memory

未来可加入：

```text
Novel

Lore

Character Bible

World Building

Style Bible

Reference Documents
```

Embedding / RAG。

但是查询结果仍然只是：

```text
Context
```

不是 Project State。

---

# 63. Versioning

所有 R1 以上 AI修改建议：

```text
Before Mutation
      ↓
VersionService.snapshot()
      ↓
Mutation
```

这样 Studio 可以：

```text
Undo AI
```

---

# 64. AI Change Set

一个 Agent Run 建议创建：

```text
ChangeSet
```

例如：

```text
ChangeSet #105

Modified
• Shot 12
• Shot 13
• Shot 14

Created
• Shot 15

Deleted
• Shot 10
```

Frontend以后可以直接：

```text
Accept

Undo

Compare
```

---

# 65. Generation Tool

用户说：

> 生成第五镜。

Agent调用：

```text
create_generation
```

Tool返回：

```json
{
  "generation_id": "gen_101",
  "workflow_run_id": "wf_33",
  "status": "queued"
}
```

Agent即可结束：

> 第五镜已经提交生成。

不等待 ComfyUI。

---

# 66. Generation 完成后的行为

Generation完成：

```text
Production Engine
 ↓
GenerationCompleted Event
 ↓
Project State Update
 ↓
Frontend Update
```

必要时再触发：

```text
Review Workflow
```

不是恢复原来的 Director Agent 一直等在那里。

---

# 67. Proactive Agent

MVP 不建议 AI Director随时自行修改项目。

第一版：

```text
User initiated
```

后期可以增加：

```text
Event initiated
```

例如：

```text
Generation Completed
 ↓
自动 Quality Review
```

这种更适合作为 Production Automation，而不是开放式 Director行为。

---

# 68. Agent Permission System

未来建议定义：

```text
READ_PROJECT

MODIFY_SCRIPT

MODIFY_SHOT

CREATE_ASSET

GENERATE_IMAGE

GENERATE_VIDEO

DELETE_ENTITY

EXPORT_PROJECT
```

Tool调用前：

```text
Permission Check
```

为未来团队协作做准备。

---

# 69. Model Routing

Director 不直接绑定一个模型。

例如：

```text
Intent Classification
→ 快速模型

Complex Planning
→ 强推理模型

Storyboard
→ Creative Model

Vision Review
→ Multimodal Model
```

通过：

```text
LLMGateway
```

路由。

---

# 70. 本地模型兼容

Agent设计不能假设所有模型都拥有最强 Tool Calling。

Provider Capability 标记：

```text
tool_calling

structured_output

vision

reasoning

context_window
```

如果本地模型 Tool Calling 弱：

```text
Structured Planner
+
Deterministic Executor
```

仍然可以运行。

---

# 71. 可观测性

每个 Agent Run记录：

```text
run_id

project_id

model

latency

token_usage

tool_calls

retries

interrupt_count

result

error
```

每个 Node记录：

```text
started_at

completed_at

status

input_reference

output_reference
```

---

# 72. Agent 调试界面

开发模式建议未来提供：

```text
Graph Inspector

Current State

Node History

Tool Calls

Context Snapshot

Model Usage

Checkpoint
```

这会极大降低 Agent Debug 难度。

---

# 73. 测试策略

Agent测试不能只写：

> 看起来回答挺好。

至少分四类。

## Unit Test

```text
Entity Resolver

Risk Evaluator

Context Builder

Tool Adapter
```

## Graph Test

```text
Route是否正确

Interrupt是否正确

Retry是否正确
```

## Tool Contract Test

验证：

```text
Agent Tool
↔
Service
```

## Scenario Test

例如：

```text
"删除第三场"
→ 必须进入审批

"第五镜改成近景"
→ 不需要审批

"重新生成100个视频"
→ 必须进入成本审批
```

---

# 74. MVP Agent 范围

第一版不要让 Director 什么都干。

只实现：

```text
查询 Project

查询 Scene

查询 Shot

修改 Scene

修改 Shot

创建 Shot

拆分 Scene → Shots

生成 Storyboard

生成 Image

查询 Generation

恢复 Version
```

足够展示核心价值。

---

# 75. MVP Graph

第一版甚至可以压缩成：

```text
START
 ↓
Understand
 ↓
Context
 ↓
Plan
 ↓
Risk
 ↓
Execute
 ↓
Review
 ↓
END
```

不要一开始做过于复杂的 Agent Graph。

---

# 76. 第一条必须跑通的 Agent Case

用户：

> "把第五镜改成近景然后重新生成。"

执行：

```text
User
 ↓
Resolve shot_005
 ↓
Load Shot Context
 ↓
ModificationPlan
 ↓
Risk = R1
 ↓
Version Snapshot
 ↓
update_shot
 ↓
Shot becomes DIRTY_IMAGE
 ↓
create_generation
 ↓
Generation Queued
 ↓
Agent Review
 ↓
Complete
```

最终回复：

```text
第五镜已改为近景，并已提交新的图片生成任务。
旧版本已经保留。
```

如果这一条链路稳定：

> AI Director 第一阶段成立。

---

# 77. 第二条必须跑通的 Agent Case

用户：

> "第三场太拖了，帮我压缩一下。"

Director：

```text
Load Scene
 ↓
Analyze Shots
 ↓
Create Plan
 ↓
预计：
修改5镜
合并2镜
删除1镜
 ↓
Approval
 ↓
Apply ChangeSet
 ↓
Continuity Review
 ↓
Complete
```

这一条验证：

```text
复杂规划
+
批量修改
+
审批
+
版本
```

---

# 78. 第三条必须跑通的 Agent Case

用户：

> "第八镜和第九镜接不上。"

Director：

```text
Load Shot 8

Load Shot 9

Load Continuity

Load Visual Assets

↓

ContinuitySkill

↓

Detect Issue

↓

Recommend Fix

↓

用户确认

↓

修改 Shot / Prompt

↓

重新生成
```

这一条验证产品真正的：

> 漫剧专业性。

---

# 79. 与前端的接口边界

完成本设计以后，Frontend就可以围绕这些 Agent State设计：

```text
Idle

Thinking

Planning

Waiting Approval

Executing

Generating

Reviewing

Completed

Failed
```

而不是只设计：

```text
聊天气泡
```

---

# 80. AI Director UI 后续需要表现的对象

前端下一份设计必须重点表现：

```text
Agent Message

Execution Plan

Current Action

Tool Progress

Approval Card

ChangeSet

Diff

Generation Tasks

Warnings

Review Result
```

因此右侧虽然可以长得像聊天栏，但本质上应该是：

> **AI Command Center**

而不仅仅是 Chat Panel。

---

# 81. AI Director 最终架构

```text
                         User Intent
                              │
                              ▼
                       Director Graph
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
       Context             Planner             Risk
           │                  │                  │
           └──────────────────┼──────────────────┘
                              ▼
                         Tool Registry
                              │
             ┌────────────────┼─────────────────┐
             ▼                ▼                 ▼
         ShotTool         AssetTool      GenerationTool
             │                │                 │
             ▼                ▼                 ▼
        ShotService      AssetService    GenerationService
             │                │                 │
             └────────────────┼─────────────────┘
                              ▼
                         Project State

                              +

                      Production Engine
```

---

# 82. 最终设计原则

AI Director 必须始终遵守：

### 1.

**Project State > Conversation Memory**

### 2.

**Structured Data > Natural Language Parsing**

### 3.

**Tools > Direct Infrastructure Access**

### 4.

**Services > Agent Business Logic**

### 5.

**Plan Before Complex Mutation**

### 6.

**Version Before Mutation**

### 7.

**Approval Before Risk**

### 8.

**Asynchronous Production > Agent Waiting**

### 9.

**Minimal Context > Whole Project Context**

### 10.

**One Director + Skills First, Multi-Agent Later**

---

# 83. 最终定义

AI Director 不是：

```text
Chatbot
```

而是：

```text
Intent Interpreter
        +
Project Planner
        +
Studio Operator
        +
Production Coordinator
```

它负责把用户的自然语言：

```text
"我想怎么改这部漫剧"
```

转换为：

```text
结构化、可审计、可撤销、可执行的 Studio 操作
```

因此 AI Director 才是 AI 漫剧 Studio 真正意义上的：

> **Agent Layer。**

而 Studio 的 Project / Shot / Asset / Generation / Workflow 系统，则构成 Agent 能够长期可靠工作的"身体"。

---

## 引用

本文档引用的 LangChain / LangGraph 官方文档：

- [1] LangGraph Docs — Why LangGraph / Stateful Graph：https://langchain-ai.github.io/langgraph/concepts/high_level/
- [2] LangGraph Docs — Human in the Loop / Interrupt：https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/
- [3] LangGraph Docs — Runtime Context：https://langchain-ai.github.io/langgraph/concepts/context/
- [4] LangChain Docs — Structured Output：https://python.langchain.com/docs/concepts/structured_outputs/
- [5] LangChain Docs — Context Engineering：https://python.langchain.com/docs/concepts/context_engineering/
- [6] LangChain Docs — Tools：https://python.langchain.com/docs/concepts/tools/
- [7] LangChain Docs — Middleware（Model Retry / Tool Retry）：https://python.langchain.com/docs/concepts/middleware/
- [8] LangChain Docs — Streaming：https://python.langchain.com/docs/concepts/streaming/
- [9] LangGraph Docs — Persistence / Checkpointer：https://langchain-ai.github.io/langgraph/concepts/persistence/
