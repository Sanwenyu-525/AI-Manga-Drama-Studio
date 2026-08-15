# AI Director Agent Alpha 架构详细设计 v0.2

**文档状态：** Draft
**阶段：** MVP → Alpha
**核心技术：** LangChain + LangGraph
**上游文档：**

* 《AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1》
* 《AI 漫剧 Studio 核心领域模型详细设计 v0.1》
* 《AI 漫剧 Studio Alpha Backend API & Service 详细设计 v0.1》
* 《AI 漫剧 Studio Asset / Generation / Version 系统详细设计 v0.1》
* 《AI 漫剧 Studio Job Queue & Generation State Machine 详细设计 v0.1》

**目标：**

把 MVP 中：

```text
Novel
 ↓
LLM
 ↓
JSON
```

式的一次性内容生成，升级为：

> **能够理解项目状态、分阶段决策、调用领域工具、产生结构化 Proposal、接受人工审核、暂停/恢复并长期维持漫剧生产一致性的 AI Director Runtime。**

---

# 1. AI Director 在 Studio 中的定位

AI Director 不是：

```text
聊天机器人
```

也不是：

```text
Prompt Generator
```

更不是：

```text
一个超级 Prompt
```

它是：

> **整个 AI 漫剧生产过程中负责叙事规划、视觉规划和跨 Agent 协调的智能决策层。**

整体：

```text
Project State
      │
      ▼
Context Resolver
      │
      ▼
AI Director
      │
 ┌────┼────┬─────────┐
 ▼    ▼    ▼         ▼
Script Visual Prompt Continuity
Agent  Agent Agent    Agent
      │
      ▼
Structured Proposal
      │
      ▼
Validation
      │
      ▼
Application Service
      │
      ▼
Project State
```

---

# 2. Agent 不能成为 Source of Truth

整个系统必须坚持：

```text
Project Database
=
Source of Truth
```

而不是：

```text
LLM Memory
```

或者：

```text
LangGraph State
```

LangGraph 的 checkpoint 适合保存一个 graph thread 的执行状态和历史状态，并可以支撑暂停后继续运行，但它不应该取代 Studio 的 Project Domain Database。

因此：

```text
Agent State
=
Execution State
```

```text
Project State
=
Business State
```

必须分离。

---

# 3. 推荐总体架构

```text
┌─────────────────────────────────────┐
│          Studio Core Backend        │
│                                     │
│ Project / Shot / Asset / Generation │
└──────────────────┬──────────────────┘
                   │
                   │ AgentGateway
                   ▼
┌─────────────────────────────────────┐
│          Agent Runtime              │
│                                     │
│ LangGraph                           │
│                                     │
│ Director Graph                      │
│ Script Graph                        │
│ Visual Graph                        │
│ Continuity Graph                    │
│ Prompt Graph                        │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│             LangChain               │
│                                     │
│ Models                              │
│ Tools                               │
│ Structured Output                   │
│ Middleware                          │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│             LLM Provider            │
└─────────────────────────────────────┘
```

当前 LangGraph 官方定位就是面向长期运行、stateful agent orchestration 的低层运行框架，而 LangChain 更适合提供模型、工具、结构化输出等 Agent 构件，因此两者在这里分别承担 Graph Runtime 与 Agent Component Layer。

---

# 4. 为什么 Director 应该使用 LangGraph

Director Workflow 不是简单：

```text
Prompt A
 ↓
Prompt B
 ↓
Prompt C
```

它会出现：

```text
判断

循环

回退

审核

失败恢复

人工介入

不同 Agent 分支
```

例如：

```text
Analyze Story
      ↓
Plan Scene
      ↓
Plan Shots
      ↓
Continuity Check
      │
      ├── PASS ──→ Finalize
      │
      └── FAIL
            ↓
        Revise Shots
            ↓
        Check Again
```

这种流程天然适合 Graph。

---

# 5. LangGraph 负责什么

LangGraph 层负责：

```text
Node

Edge

Conditional Edge

State

Checkpoint

Interrupt

Resume

Subgraph
```

当前官方机制中，checkpointer 会在 graph 执行过程中保存 thread 的 checkpoint；interrupt 可以暂停执行并等待外部输入，再基于持久化状态继续。

---

# 6. LangChain 负责什么

LangChain 主要承担：

```text
Model abstraction

Tool definition

Structured output

Agent harness

Middleware
```

当前 LangChain 官方支持通过 schema 让 Agent 返回可预测的结构化结果，而不是依赖自然语言解析。

---

# 7. Alpha Agent 划分

第一阶段不要搞：

```text
15～30 Agent
```

推荐只有：

```text
Director Agent

Script Agent

Visual Agent

Prompt Agent

Continuity Agent
```

共五个核心角色。

---

# 8. Director Agent

Director 是 Orchestrator。

负责：

```text
理解整体剧情目标

确定 Scene 目的

控制节奏

决定是否需要重新规划

协调 Script / Visual / Continuity

输出最终制作 Proposal
```

它不负责：

```text
直接写 ComfyUI Workflow

直接生成图片

操作数据库

处理文件
```

---

# 9. Script Agent

负责：

```text
小说解析

剧情 Beat

对白

动作

Scene 分解

人物关系

叙事信息密度

节奏
```

---

# 10. Visual Agent

负责：

```text
Scene → Shot

景别

机位

人物位置

构图

运镜

表情

动作

光线

画面情绪
```

最终输出：

```text
ShotVisualSpec
```

---

# 11. Prompt Agent

Prompt Agent 不负责重新设计镜头。

它负责：

```text
Domain Specification
         ↓
Provider-specific Prompt
```

例如：

```text
ShotVisualSpec
+
Character Master
+
Location Master
+
Style
```

转成：

```text
Image Prompt
```

或者：

```text
Video Prompt
```

---

# 12. Continuity Agent

负责：

```text
发现跨 Shot / Scene 的潜在连续性问题
```

例如：

```text
角色服装

手持道具

人物位置

时间

天气

伤势

角色状态

镜头方向
```

但：

> 能通过结构化 Rule Engine 判断的问题，优先不用 LLM。

---

# 13. Continuity 两层结构

```text
Continuity Rule Engine
         ↓
Continuity Agent
```

Rule Engine：

```text
确定性检测
```

Agent：

```text
语义 / 叙事 / 视觉检测
```

---

# 14. Director Graph

推荐：

```text
START
  ↓
Load Context
  ↓
Analyze Story
  ↓
Script Planning
  ↓
Visual Planning
  ↓
Continuity Review
  ↓
Evaluate Result
  │
  ├── PASS
  │     ↓
  │   Human Review?
  │     ↓
  │   Build Proposal
  │     ↓
  │   END
  │
  └── REVISE
        ↓
      Revision
        ↓
      Continuity Review
```

---

# 15. 不要让 Director 直接“思考所有事情”

错误：

```text
一个 30000 token Prompt
+
请规划整集漫剧
```

正确：

```text
Story Analysis
      ↓
Scene Planning
      ↓
Shot Planning
      ↓
Visual Review
```

将问题拆小。

---

# 16. Director Graph State

推荐：

```text
DirectorState
{
    runId

    projectId

    episodeId
    sceneId

    taskType

    sourceContext

    storyAnalysis

    scriptProposal

    visualProposal

    continuityReport

    revisionCount

    validationErrors

    humanDecision

    finalProposal
}
```

---

# 17. Graph State 禁止内容

不要塞：

```text
所有项目 Asset 二进制

整本小说

完整生成历史

大量 ComfyUI JSON
```

Graph State 应保持：

```text
Small
+
Serializable
+
Recoverable
```

---

# 18. Thread ID

每一次长期 Agent Run：

```text
thread_id
```

建议与 Studio：

```text
agentRunId
```

一一对应。

例如：

```text
thread_id = agent_run_01K...
```

LangGraph 的 persistence 以 `thread_id` 组织 checkpoint 状态，因此这一映射可以用于恢复特定 Director Run。

---

# 19. AgentRun

建议正式加入领域模型：

```text
AgentRun
{
    id

    projectId

    agentType

    targetType
    targetId

    threadId

    model

    status

    inputContextHash

    proposalId

    tokenUsage

    cost

    createdAt

    startedAt

    finishedAt
}
```

---

# 20. AgentRunStatus

```text
CREATED

RUNNING

WAITING_HUMAN

SUCCEEDED

FAILED

CANCELLED

INTERRUPTED
```

---

# 21. AgentRun 与 Generation

有两种方案：

### 方案 A

AgentRun 独立。

### 方案 B

全部当：

```text
GenerationType = AGENT
```

推荐 Alpha：

> **AgentRun 独立，但保留关联 Generation 的能力。**

因为 Agent 生命周期和媒体 Generation 差异很大。

---

# 22. 为什么 AgentRun 独立更合理

未来 Agent 可能：

```text
多次调用 LLM

多次 Tool Call

多 Node

Human Review

循环修改
```

一个 Director Run：

可能内部产生：

```text
10～30 次 LLM Call
```

不适合全部塞到一个传统 Generation 对象。

---

# 23. LLMCall

未来可以增加：

```text
LLMCall
```

记录：

```text
agentRunId

node

provider

model

promptHash

inputTokens

outputTokens

cachedTokens

latency

cost
```

Alpha 可以暂时记录到 AgentRun Trace。

---

# 24. Context Resolver

这是整个 Agent 系统的地基。

```text
ContextResolver
```

作用：

> 根据当前任务，从 Project Domain 中构建最小而充分的 Agent Context。

---

# 25. 为什么 Context Resolver 比 Memory 更重要

Agent 真正需要的是：

```text
正确项目事实
```

而不是：

```text
记住之前聊天说了什么
```

所以：

```text
Project Context
>
Conversation Memory
```

---

# 26. Context Source

ContextResolver 可以读取：

```text
Project

SourceDocument

Episode

Scene

Shot

Character

CharacterVersion

Location

Asset

Prompt

ContinuityState

Previous Approved Shot
```

---

# 27. ContextPolicy

根据不同任务使用不同 Context：

```text
STORY_ANALYSIS

SCENE_PLANNING

SHOT_PLANNING

PROMPT_BUILDING

CONTINUITY_REVIEW
```

---

# 28. Story Analysis Context

加载：

```text
当前 SourceDocument Chunk

前文摘要

角色表

项目类型

目标 Episode 长度

用户 Director Instructions
```

不需要：

```text
所有 Shot Assets
```

---

# 29. Scene Planning Context

加载：

```text
Episode Story Analysis

当前 Narrative Beats

Character Profiles

Known Locations

上一 Scene Summary

下一剧情目标
```

---

# 30. Shot Planning Context

加载：

```text
Current Scene

Current Characters

Current Location

Previous 1～3 Shots

Scene Continuity State

Project Visual Style

Director Intent
```

---

# 31. Prompt Context

加载：

```text
ShotVisualSpec

CharacterVersion

Reference Assets Metadata

LocationVersion

Project Style

Provider Capability
```

---

# 32. Continuity Context

加载：

```text
Previous Shot State

Current Shot State

Next Shot Plan

Character State

Prop State

Scene Time

Location
```

---

# 33. Context Budget

ContextResolver 应支持：

```text
maxTokens
```

例如：

```text
Director Planning:
24k

Shot Planning:
12k

Prompt:
8k
```

这些数字以后根据实际模型调整。

---

# 34. Context Priority

如果超预算：

优先保留：

```text
Current Target

Current Character

Continuity

Direct Previous Context

User Constraints
```

优先压缩：

```text
很远的历史 Scene

非相关 Character

大量生成日志
```

---

# 35. Context Summarization

长篇项目：

```text
200 Episode
```

不能反复送原始全文。

推荐引入：

```text
StorySummary

EpisodeSummary

SceneSummary
```

---

# 36. Summary 是领域资源，不是临时 Chat Memory

例如：

```text
EpisodeSummary
```

应该：

```text
Versioned
```

并关联：

```text
SourceDocument Revision
```

否则上游小说修改后 Summary 可能过期。

---

# 37. Agent 输入原则

Agent 接收：

```text
Facts

Constraints

Goal

Expected Schema
```

而不是：

```text
自己去数据库里找所有信息
```

---

# 38. Tool Calling 的定位

Agent 可以拥有 Tool。

当前 LangChain Tool 机制支持让 Agent 调用预定义能力；在 Studio 中这些 Tool 应只暴露受控的领域查询或 Proposal 操作。

推荐：

```text
Read Tools

Analysis Tools

Proposal Tools
```

---

# 39. Read Tools

例如：

```text
get_character(characterId)

get_scene(sceneId)

get_previous_shots(sceneId, count)

get_location(locationId)

get_continuity_state(shotId)
```

---

# 40. 禁止 Database Tool

不要给：

```text
execute_sql()
```

这种 Tool。

否则 Agent 可以：

```text
直接改项目
```

违反领域边界。

---

# 41. Proposal Tool

可以：

```text
propose_scene_plan()

propose_shot_plan()

propose_visual_update()
```

Tool 输出：

```text
Proposal
```

而不是直接写 DB。

---

# 42. Agent Proposal

统一领域对象：

```text
AgentProposal
{
    id

    agentRunId

    proposalType

    targetType
    targetId

    status

    operations[]

    warnings[]

    rationaleSummary

    createdAt
}
```

---

# 43. ProposalStatus

```text
DRAFT

PENDING_REVIEW

APPROVED

PARTIALLY_APPROVED

REJECTED

APPLIED

EXPIRED
```

---

# 44. ProposalOperation

例如：

```text
CREATE_SCENE

UPDATE_SCENE

CREATE_SHOT

UPDATE_SHOT

UPDATE_VISUAL_SPEC

CREATE_PROMPT_VERSION

UPDATE_CONTINUITY
```

---

# 45. Operation 示例

```json
{
  "operation": "CREATE_SHOT",
  "temporaryId": "shot_temp_01",
  "data": {
    "description": "沈亦抬头看向教练",
    "shotType": "MEDIUM_CLOSE_UP",
    "duration": 4.5
  }
}
```

---

# 46. Agent 永远不产生真实 ID

Proposal 中使用：

```text
temporaryId
```

Application Service Apply 时：

```text
Generate Domain ID
```

这样 Agent 无法伪造数据库实体。

---

# 47. Structured Output

所有核心 Agent 输出必须：

```text
Schema-first
```

而不是：

```text
自然语言 → regex
```

当前 LangChain Structured Output 可以基于 JSON object、Pydantic model、dataclass 等 schema 返回结构化数据，适合直接进入 Validation Layer。

---

# 48. Python Schema

如果 Agent Runtime 使用 Python：

推荐：

```text
Pydantic
```

例如：

```text
ShotPlanProposal

ScenePlanProposal

ContinuityReport
```

---

# 49. Schema Validation Pipeline

```text
LLM
 ↓
Structured Output
 ↓
Schema Validation
 ↓
Domain Validation
 ↓
Proposal
```

---

# 50. Schema Validation 不等于 Domain Validation

例如模型返回：

```text
duration = 4.5
```

Schema 正确。

但它引用：

```text
characterId = abc
```

不存在。

这是：

```text
Domain Validation Failure
```

---

# 51. Validation 两层

```text
Layer 1
SchemaValidator
```

```text
Layer 2
ProposalDomainValidator
```

---

# 52. Domain Validator

检查：

```text
Character Exists

Location Exists

Same Project

Shot Duration Legal

Order Valid

Character Version Valid

No Duplicate Scene
```

---

# 53. Invalid Output Repair

流程：

```text
Agent Output
 ↓
Invalid
 ↓
Repair Node
 ↓
LLM correction
 ↓
Validate Again
```

最多：

```text
1～2 次
```

不要无限修。

---

# 54. Retry 分类

Agent Retry：

```text
Technical Retry
```

和：

```text
Semantic Revision
```

必须分开。

---

# 55. Technical Retry

例如：

```text
Timeout

Rate Limit

Invalid JSON
```

属于：

```text
Runtime Retry
```

---

# 56. Semantic Revision

例如：

```text
Shot 太多

镜头重复

Continuity Fail
```

属于：

```text
Director Revision Loop
```

不是 Retry。

---

# 57. Revision Count

Graph State：

```text
revisionCount
```

例如限制：

```text
maxRevision = 2
```

超过后：

```text
Human Review
```

而不是无限循环烧 Token。

---

# 58. Director Evaluation Node

负责判断：

```text
PASS

REVISE

HUMAN_REVIEW
```

---

# 59. Evaluate Criteria

例如：

```text
Narrative completeness

Shot count

Duration fit

Visual diversity

Continuity

Character coverage

Generation feasibility
```

---

# 60. Generation Feasibility

这是 AI 漫剧 Director 很重要的一点。

不能只考虑电影理论。

还要知道：

```text
AI 能不能稳定生成？
```

例如避免：

```text
一个镜头同时 12 个人剧烈交互

极复杂手部动作

连续 30 秒长镜头
```

如果当前模型能力不适合。

---

# 61. Capability Profile

引入：

```text
GenerationCapabilityProfile
```

描述当前 Provider：

```text
maxDuration

recommendedCharacters

cameraMotionSupport

firstLastFrameSupport

referenceImageSupport

resolution
```

---

# 62. Visual Agent 读取 Capability

例如：

```text
Video Model Max Duration = 6s
```

Visual Agent 不应该设计：

```text
18s 单 Shot
```

---

# 63. Model Capability 不硬编码在 Prompt

应该：

```text
ProviderCapabilityService
```

提供结构化信息。

---

# 64. Project Director Instructions

用户可以定义：

```text
Director Instructions
```

例如：

```text
节奏快

少用远景

主角镜头占比高

比赛阶段更多低机位

保持 2D 动漫风
```

---

# 65. Director Instructions 是 Project State

不能只存在：

```text
聊天记录
```

建议：

```text
ProjectDirectorProfile
```

---

# 66. ProjectDirectorProfile

```text
{
    visualStyle

    pacing

    shotPreferences

    forbiddenPatterns

    narrativePreferences

    customInstructions
}
```

---

# 67. Episode Director Override

某 Episode 可以覆盖：

```text
EpisodeDirectorProfile
```

优先级：

```text
Shot Override
 ↓
Scene Override
 ↓
Episode Override
 ↓
Project Director Profile
```

---

# 68. Prompt Agent Pipeline

```text
Domain Facts
 ↓
Canonical Prompt Spec
 ↓
Provider Prompt Adapter
 ↓
PromptVersion
```

---

# 69. Canonical Prompt Spec

例如：

```text
Character

Action

Expression

Location

Composition

Camera

Lighting

Style

Continuity Constraints
```

---

# 70. Provider Prompt Adapter

```text
Canonical Prompt
      │
 ┌────┼──────────┐
 ▼    ▼          ▼
Image MiniMax   Other
```

Agent 不应该维护：

```text
所有模型特殊语法
```

---

# 71. Prompt Agent 与 Adapter 区别

Prompt Agent：

```text
语言与语义优化
```

Adapter：

```text
Provider 格式映射
```

---

# 72. Prompt Versioning

每次 Agent 修改 Prompt：

```text
PromptVersion vN+1
```

不能覆盖旧 Prompt。

这样：

```text
Generation
```

才能准确追溯。

---

# 73. Scene Planning Graph

推荐：

```text
Load Episode Context
 ↓
Analyze Narrative Beats
 ↓
Draft Scenes
 ↓
Check Duration
 ↓
Check Character Coverage
 ↓
Validate
 ↓
Proposal
```

---

# 74. Shot Planning Graph

```text
Load Scene Context
 ↓
Determine Narrative Beats
 ↓
Draft Shot Sequence
 ↓
Assign Camera
 ↓
Assign Duration
 ↓
Check Visual Variety
 ↓
Continuity Check
 ↓
Proposal
```

---

# 75. Visual Variety Rule

避免：

```text
Close Up
Close Up
Close Up
Close Up
Close Up
```

可以加入规则：

```text
ShotScaleRepetition
```

检测连续相同景别。

---

# 76. Camera Rule Engine

未来可以逐步加入：

```text
180-degree rule

screen direction

shot/reverse-shot

establishing shot

reaction shot
```

但 Alpha 只做基础。

---

# 77. Alpha Visual Rule

第一版：

```text
Duration Bounds

Shot Count Bounds

Repeated Shot Type

Character Presence

Location Match

Video Duration Capability
```

---

# 78. Continuity Review Graph

```text
Load Continuity
 ↓
Rule Check
 ↓
LLM Semantic Review
 ↓
Merge Warnings
 ↓
Severity Classification
 ↓
Return Report
```

---

# 79. Continuity Severity

```text
INFO

WARNING

ERROR
```

---

# 80. ERROR

例如：

```text
角色突然换衣服

地点错误

篮球上一镜头在手里，下一镜头毫无解释消失
```

---

# 81. WARNING

例如：

```text
Shot direction 可能跳轴
```

---

# 82. INFO

例如：

```text
连续 4 个镜头景别相似
```

---

# 83. Auto Fix Policy

不要所有 Continuity Warning：

```text
自动改
```

推荐：

```text
SAFE_AUTOFIX

PROPOSE_FIX

HUMAN_REQUIRED
```

---

# 84. Human in the Loop

Director 的 Human Review 推荐直接利用 Graph Interrupt 模式。

LangGraph 当前 interrupt 机制允许 graph 在节点中暂停，把 JSON-serializable payload 返回给调用方，并在外部输入后继续运行；这正适合 Scene/Shot Proposal 审核。

---

# 85. Human Review 节点

```text
Director
 ↓
Proposal Ready
 ↓
Interrupt
 ↓
Studio Review UI
```

用户：

```text
Approve

Edit

Reject
```

---

# 86. Review Decision

```text
HumanDecision
{
    action

    edits

    comment
}
```

action：

```text
APPROVE

EDIT_AND_APPROVE

REVISE

REJECT
```

---

# 87. Resume Graph

用户审核后：

```text
AgentRun
```

从：

```text
WAITING_HUMAN
```

恢复：

```text
RUNNING
```

然后继续后续 Node。

---

# 88. 哪些地方需要 Human Review

Alpha 推荐：

```text
Episode Plan

Major Scene Rewrite

Character Master Change

Large Batch Shot Rewrite
```

默认需要。

---

# 89. 哪些地方可以自动

例如：

```text
Prompt Generate

Small Visual Spec

Continuity Warning
```

可以自动生成 Proposal。

---

# 90. Auto Mode

项目可以设置：

```text
ReviewMode
```

```text
MANUAL

SMART

AUTO
```

---

# 91. MANUAL

每个关键 Proposal：

```text
Interrupt
```

---

# 92. SMART

只有：

```text
高风险操作
```

需要审核。

---

# 93. AUTO

Agent 自动 Apply。

但：

```text
Database 写入
```

仍然经过 Application Service。

---

# 94. Human Review 与 Tool Approval

LangChain 现在也提供 Human-in-the-Loop middleware，可针对 Agent tool call 进行策略化审批，并依赖 checkpoint/interrupt 保存等待状态。

但 Studio Alpha 推荐：

> **领域 Proposal Review 为主，Tool Approval 为辅。**

---

# 95. 为什么不用每个 Tool Call 都审核

如果：

```text
get_scene()

get_character()

get_previous_shots()
```

每次都问用户，

系统完全不可用。

只有：

```text
可能改变 Project State
```

的动作需要审核。

---

# 96. Agent Tool 权限

分三级：

```text
READ

PROPOSE

EXECUTE
```

Alpha Agent 默认：

```text
READ + PROPOSE
```

禁止：

```text
EXECUTE Project Mutation
```

---

# 97. Execution Tool

例如：

```text
generate_shot_image()
```

是否让 Director 调用？

Alpha 推荐：

```text
不直接调用
```

Director 只创建：

```text
Generation Proposal
```

然后 Job System 执行。

---

# 98. 原因

否则 Director Graph 会被：

```text
几十秒～几分钟的视频生成
```

长时间阻塞。

Agent Runtime 应负责：

```text
Planning
```

Job Runtime 负责：

```text
Production
```

---

# 99. Planning Plane 与 Execution Plane

正式定义：

```text
AI Planning Plane
```

负责：

```text
Director
Script
Visual
Prompt
Continuity
```

```text
Production Execution Plane
```

负责：

```text
Generation
Job
Provider
ComfyUI
Storage
```

---

# 100. 两个 Plane 的连接

通过：

```text
Proposal

GenerationPlan

JobPlan
```

连接。

---

# 101. Subgraph

可以把：

```text
Script

Visual

Continuity
```

设计成独立 Subgraph。

LangGraph 当前支持 subgraph，并允许根据需要配置子图的持久化行为。

---

# 102. Director Parent Graph

```text
DirectorGraph
├── ScriptSubgraph
├── VisualSubgraph
└── ContinuitySubgraph
```

Prompt Agent 可以：

```text
独立按 Shot 调用
```

不一定每次进入 Director。

---

# 103. 不要 Multi-Agent 自由聊天

避免：

```text
Director:
Script你怎么看？

Script:
我觉得……

Visual:
我不同意……
```

这种：

```text
Agent Chatroom
```

难控制：

```text
Token

结果

循环

责任
```

---

# 104. 推荐 Agent Contract

每个 Agent：

```text
Input Schema
 ↓
Agent
 ↓
Output Schema
```

清晰完成自己的任务。

---

# 105. Script Agent Contract

Input：

```text
StoryContext
```

Output：

```text
ScriptPlan
```

---

# 106. Visual Agent Contract

Input：

```text
ScenePlan
+
VisualContext
```

Output：

```text
ShotPlan[]
```

---

# 107. Continuity Agent Contract

Input：

```text
ShotPlan[]

PreviousState
```

Output：

```text
ContinuityReport
```

---

# 108. Prompt Agent Contract

Input：

```text
ShotVisualSpec

ProviderProfile
```

Output：

```text
CanonicalPromptSpec
```

---

# 109. Director Contract

Input：

```text
ProductionGoal
```

Output：

```text
AgentProposal
```

---

# 110. AgentGateway

Spring Core 只依赖：

```text
AgentGateway
```

例如：

```text
planEpisode()

planScene()

planShots()

buildPrompt()

reviewContinuity()

resumeAgentRun()
```

---

# 111. Python Runtime API

如果拆服务：

```text
POST /internal/agent-runs

GET  /internal/agent-runs/{id}

POST /internal/agent-runs/{id}/resume

POST /internal/agent-runs/{id}/cancel
```

---

# 112. Core Backend 不给 Python DB Credentials

Python Agent Runtime 不应该：

```text
直接连接 project.db
```

它通过：

```text
Context API
```

获取必要 Project Facts。

---

# 113. 为什么这样设计

未来即使 Agent Runtime：

```text
远程部署
```

也不会暴露整个 Studio 数据库。

---

# 114. Context API

内部：

```text
POST /internal/agent-context
```

输入：

```text
target
contextPolicy
```

返回：

```text
resolvedContext
```

---

# 115. 更推荐 Gateway Push Context

甚至可以：

```text
Spring
 ↓
ContextResolver
 ↓
AgentGateway
```

直接把 Context 传给 Python。

这样 Python 完全不用访问 Core。

---

# 116. 推荐 Alpha

采用：

```text
Core builds context
        ↓
Agent Runtime
```

安全且边界最清晰。

---

# 117. Agent Checkpoint

LangGraph checkpoint 用于：

```text
恢复 Agent Run
```

不用于：

```text
恢复 Project 数据
```

---

# 118. Agent Crash Recovery

Agent Runtime 崩溃：

```text
threadId
```

仍然存在 checkpoint。

重启：

```text
resume Agent Run
```

前提是持久 checkpointer 与 Runtime 生命周期解耦。官方 persistence 机制正是为 thread-level state 与 long-running workflow continuation 提供基础。

---

# 119. Checkpointer 存储

开发：

```text
Memory
```

可以。

Alpha 正式环境：

必须：

```text
Persistent Checkpointer
```

不能 Agent Runtime 一关全丢。

---

# 120. Project DB 与 Agent Checkpointer

两者：

```text
不要共用 Repository Model
```

即使底层都使用 SQLite，也视为两个不同 Store。

---

# 121. Agent State Version

每次 Graph 架构更新：

AgentRun 应记录：

```text
graphVersion
```

例如：

```text
director_graph_v2
```

否则升级后旧 checkpoint 可能无法安全恢复。

---

# 122. Graph Compatibility

若：

```text
graphVersion incompatible
```

旧 AgentRun：

```text
INTERRUPTED
```

允许：

```text
Restart from Proposal Input
```

不要强行恢复。

---

# 123. Prompt Template Version

每个 Agent Node：

建议记录：

```text
promptTemplateId
promptTemplateVersion
```

便于：

```text
评估
Debug
回归测试
```

---

# 124. System Prompt 分层

不要一个：

```text
DirectorSystemPrompt.txt
```

数千行。

建议：

```text
Base Role

Task Instruction

Project Rules

Output Contract
```

拼装。

---

# 125. Prompt Composition

```text
Base Agent Prompt
        +
Task Prompt
        +
Project Director Profile
        +
Context
        +
Schema
```

---

# 126. 用户 Prompt 不直接拼接系统 Prompt

用户指令：

```text
User Constraints
```

应作为明确字段传入，

避免 Prompt 层级混乱。

---

# 127. Token Tracking

AgentRun 记录：

```text
inputTokens

outputTokens

cachedTokens

totalCost
```

每个 Node 进一步记录。

---

# 128. Token Budget

AgentRun 支持：

```text
tokenBudget
```

例如：

```text
Episode Plan:
100k total
```

超过：

```text
pause / fail
```

防止异常循环。

---

# 129. Revision Budget

同时：

```text
maxNodeRetries

maxRevisionLoops

maxToolCalls
```

都应该有限制。

---

# 130. Agent 不能无限自主

必须存在：

```text
Execution Budget
```

限制：

```text
Token

Cost

Tool Calls

Graph Iterations
```

---

# 131. Agent Cost

最终 Studio 应能显示：

```text
Director Planning     ¥1.4
Script Agent          ¥0.8
Visual Agent          ¥1.1
Continuity            ¥0.3
Prompt Generation     ¥0.5
```

---

# 132. Model Router

不同 Agent 不必使用同一个 LLM。

例如：

```text
Director → Strong Reasoning Model

Script → Strong Language Model

Prompt → Fast Model

Continuity → Fast Model
```

---

# 133. AgentModelProfile

```text
AgentModelProfile
{
   agentType

   provider

   model

   temperature

   maxTokens

   fallbackModel
}
```

---

# 134. Fallback Model

主模型失败：

```text
technical failure
```

可以：

```text
fallback
```

但：

```text
模型切换
```

必须记录到 AgentRun。

---

# 135. 不建议语义失败自动切模型

例如：

```text
Continuity Check Fail
```

不是模型技术故障。

不要直接换模型。

---

# 136. Agent Provider Adapter

和媒体 Provider 一样：

```text
LlmProviderAdapter
```

避免 Agent Graph 直接绑定：

```text
某一家 SDK
```

---

# 137. LangChain Model 层

LangChain 可以作为：

```text
Provider Interop Layer
```

但领域层只看到：

```text
ModelProfile
```

---

# 138. Agent Evaluation

Agent 功能不能只：

```text
人工感觉好不好
```

需要建立：

```text
Eval Dataset
```

---

# 139. Director Eval Dataset

例如：

```text
10 个小说片段
```

每个包含：

```text
Expected Scene Count Range

Required Plot Beats

Required Characters

Forbidden Hallucinations

Duration Range
```

---

# 140. Shot Plan Eval

指标：

```text
Plot Coverage

Character Correctness

Shot Count

Duration

Visual Variety

Continuity Warnings

Invalid Reference Rate
```

---

# 141. Structured Output Success Rate

关键指标：

```text
schemaValid / totalRuns
```

目标：

```text
> 99%
```

经 Repair 后。

---

# 142. Hallucinated Reference Rate

Agent 输出：

```text
不存在角色
不存在地点
不存在 Asset
```

必须统计。

目标：

```text
接近 0
```

---

# 143. Proposal Apply Success Rate

```text
成功 Apply Proposal
------------------
全部 Proposal
```

如果低：

说明：

```text
Agent Contract
```

或：

```text
Domain Validator
```

设计有问题。

---

# 144. Human Edit Rate

统计：

```text
Proposal 被用户修改比例
```

这会告诉你：

```text
Director 哪些决策最不可靠
```

---

# 145. Continuity Warning Precision

后期可以：

```text
Useful Warning / Total Warning
```

否则 Agent 警告太多会造成：

```text
Warning Fatigue
```

---

# 146. Agent Trace

每个 AgentRun 最少能看到：

```text
Node Timeline

Model

Duration

Tokens

Tool Calls

Validation

Interrupt

Result
```

---

# 147. Studio Agent Panel

建议：

```text
AI Director
────────────────

Planning Scene 05

✓ Story Analysis
✓ Script Plan
● Visual Planning
○ Continuity Review
○ Final Proposal
```

---

# 148. 点击 Node

显示：

```text
Visual Planning

Duration
14.2s

Model
...

Tokens
...

Status
Succeeded

Output
Shot Plan v3
```

---

# 149. 不向普通用户展示 Chain-of-Thought

UI 展示：

```text
Decision Summary

Proposal

Warnings

Sources
```

不要把内部推理轨迹当产品功能。

---

# 150. Rationale Summary

Agent 输出允许包含：

```text
rationaleSummary
```

例如：

```text
“这里采用连续近景，是因为剧情重点是两人心理对峙。”
```

它是简洁决策说明，不是内部推理过程。

---

# 151. Agent Chat 在 Alpha 的位置

可以存在：

```text
Director Chat Panel
```

但只是：

```text
交互入口
```

最终所有动作必须落成：

```text
Proposal
```

---

# 152. Chat 示例

用户：

```text
Scene 05 节奏太慢，
压到 6 个镜头。
```

Director：

```text
生成 ShotPlanChangeProposal
```

UI：

```text
8 Shots → 6 Shots

[Review]
```

而不是只回复：

```text
好的。
```

---

# 153. Natural Language Command

这会成为 Studio 很强的能力：

```text
“把这场比赛拍得更紧张一点。”
```

↓

```text
Intent Resolver
 ↓
Target Resolver
 ↓
Director Agent
 ↓
Proposal
```

---

# 154. Intent Resolver

后期：

```text
NL Command
```

转：

```text
IMPROVE_SCENE_PACING

CHANGE_SHOT_STYLE

REWRITE_DIALOGUE
```

Alpha 可以先做有限命令集。

---

# 155. Director Agent 与 Job Queue

Agent Run 也应该：

```text
进入 Job Queue
```

例如：

```text
Job
PLAN_SCENE
```

Task：

```text
AGENT_TASK
```

Executor：

```text
AgentTaskExecutor
```

---

# 156. 为什么 Agent 也进 Queue

这样统一获得：

```text
Cancel

Retry

Progress

Priority

Recovery
```

---

# 157. Agent Task 与 Media Task

两者：

```text
同属 JobTask
```

但 Worker Pool 不同。

```text
AgentWorker
```

不会被：

```text
ComfyUI Worker
```

阻塞。

---

# 158. Agent Job 示例

```text
Job: Plan Scene 05

Task 1
Load Context

Task 2
Director Agent

Task 3
Validate Proposal

Task 4
Apply Proposal
```

---

# 159. Alpha 更简单的实现

可以将：

```text
Load / Validate
```

封装进 AgentTaskExecutor。

所以：

```text
一个 AGENT_TASK
```

即可。

以后再拆细。

---

# 160. Agent Retry Policy

可自动 Retry：

```text
429

Timeout

Provider 5xx

Structured Output Parse Failure
```

---

# 161. 不自动 Retry

```text
Domain Validation Persistent Failure

Token Budget Exceeded

Human Rejected
```

---

# 162. Agent Cancel

用户取消：

```text
Director Run
```

如果 LLM 请求不能取消：

等返回后：

```text
Discard Result
```

AgentRun：

```text
CANCELLED
```

---

# 163. Agent Proposal Apply

Application Service：

```text
ApplyAgentProposalService
```

流程：

```text
Load Proposal
 ↓
Validate Not Expired
 ↓
Validate Current Revision
 ↓
Apply Operations
 ↓
Audit
 ↓
Proposal = APPLIED
```

---

# 164. Proposal Revision Conflict

例如 Agent 基于：

```text
Scene revision 10
```

产生 Proposal。

用户期间改成：

```text
revision 12
```

Apply 时：

```text
冲突
```

不能静默 Apply。

---

# 165. Proposal BaseRevision

Proposal 应保存：

```text
baseRevision
```

涉及多个实体时保存：

```text
baseRevisions{}
```

---

# 166. Conflict UI

```text
This proposal was created from an older version.

[Regenerate Proposal]

[Compare]

[Apply Anyway]
```

Alpha 可以只：

```text
Regenerate
```

---

# 167. Proposal Expiration

如果项目状态变化太多：

```text
Proposal = EXPIRED
```

不要长期积累危险 Proposal。

---

# 168. Director 输出和 Project Version

大规模自动修改前：

建议：

```text
Project Snapshot
```

或者至少：

```text
Audit Batch ID
```

便于整体撤销。

---

# 169. Agent ChangeSet

可以建立：

```text
ChangeSet
```

包含：

```text
Proposal

Applied Operations

Before Snapshot

After Snapshot
```

---

# 170. Undo

Alpha 后期：

```text
Undo Agent ChangeSet
```

比：

```text
数据库恢复
```

粒度更好。

---

# 171. Prompt Injection 防护

SourceDocument 属于：

```text
Untrusted Content
```

即使是用户自己的小说，

也不能把文本中：

```text
“忽略之前所有指令……”
```

当系统命令执行。

---

# 172. Context 分区

Prompt 中明确：

```text
SYSTEM RULES

PROJECT RULES

USER GOAL

SOURCE CONTENT
```

避免 Source Content 混成 Instruction。

---

# 173. Tools 最小权限

Agent Tool：

```text
只暴露任务需要的能力
```

不要一个 Director 拥有：

```text
文件系统
Shell
SQL
HTTP 任意访问
```

---

# 174. Alpha Director Tools

推荐仅：

```text
GetProjectProfile

GetEpisodeContext

GetScene

GetCharacters

GetLocations

GetPreviousShots

GetContinuityState

GetGenerationCapabilities
```

---

# 175. 不需要 Web Search Tool

普通漫剧生产：

```text
不自动联网
```

如果后续用户明确要求：

```text
历史资料研究
```

再引入 Research Agent。

---

# 176. Research Agent

属于未来：

```text
Director Extension
```

不是 Alpha Core。

---

# 177. Character Agent

同样延后。

Alpha 中 Character 创建可以：

```text
Script Agent 提取
+
Visual Agent 描述
```

先够用。

---

# 178. 为什么 Alpha 不做 Camera Agent

Visual Agent 已经可以承担：

```text
camera
```

过早拆 Camera Agent：

```text
增加 Token
增加协调成本
```

价值不高。

---

# 179. Alpha Agent 最小集合

最终确定：

```text
Director

Script

Visual

Prompt

Continuity
```

不要再扩。

---

# 180. Phase DA1

首先完成：

```text
AgentGateway

AgentRun

ContextResolver

Structured Output

Script Agent

Visual Agent
```

---

# 181. DA1 验收

输入：

```text
一个小说 Scene
```

输出：

```text
Scene Proposal

Shot Plan

ShotVisualSpec
```

并且：

```text
Schema 100% 可解析
```

---

# 182. Phase DA2

增加：

```text
Director Graph

Continuity Agent

Revision Loop

Proposal Validation
```

---

# 183. DA2 验收

完整：

```text
Story
 ↓
Script
 ↓
Visual
 ↓
Continuity
 ↓
Revision
 ↓
Proposal
```

---

# 184. Phase DA3

增加：

```text
LangGraph Checkpoint

Interrupt

Human Review

Resume

Agent Recovery
```

---

# 185. DA3 验收

Director：

```text
生成 Scene Plan
```

暂停：

```text
WAITING_HUMAN
```

关闭 Studio。

重新打开。

用户：

```text
Approve
```

Graph 正确继续执行。

---

# 186. Phase DA4

增加：

```text
Prompt Agent

Provider Capability

Token Budget

Cost

Agent Trace

Evaluation Dataset
```

---

# 187. Codex 第一批任务

```text
Task 01
定义 AgentGateway

Task 02
定义 AgentRun

Task 03
实现 AgentRun Repository

Task 04
定义 Agent Context Schema

Task 05
实现 ContextResolver

Task 06
定义 ScenePlan Schema

Task 07
定义 ShotPlan Schema

Task 08
定义 ShotVisualSpec Agent Schema

Task 09
实现 Structured Output Validator

Task 10
实现 Agent Proposal
```

---

# 188. 第二批任务

```text
Task 11
实现 Script Agent

Task 12
实现 Visual Agent

Task 13
实现 Director Graph

Task 14
实现 Continuity Rule Engine Integration

Task 15
实现 Continuity Agent

Task 16
实现 Director Evaluation Node

Task 17
实现 Revision Loop

Task 18
实现 ProposalDomainValidator

Task 19
实现 Proposal Apply Service

Task 20
实现 Agent Job Integration
```

---

# 189. 第三批任务

```text
Task 21
实现 LangGraph Persistent Checkpointer

Task 22
实现 Agent threadId

Task 23
实现 Human Review Interrupt

Task 24
实现 Resume Agent Run

Task 25
实现 Cancel Agent Run

Task 26
实现 Agent Crash Recovery

Task 27
实现 Proposal BaseRevision

Task 28
实现 Proposal Conflict Detection

Task 29
实现 Agent SSE Events

Task 30
实现 Agent Panel Query
```

---

# 190. 第四批任务

```text
Task 31
实现 Prompt Agent

Task 32
实现 CanonicalPromptSpec

Task 33
实现 Provider Capability Profile

Task 34
实现 Prompt Adapter Integration

Task 35
实现 Agent Token Usage

Task 36
实现 Agent Cost

Task 37
实现 Agent Trace

Task 38
建立 Director Eval Dataset

Task 39
实现 Eval Runner

Task 40
建立 Agent Regression Tests
```

---

# 191. 必须测试场景

```text
正常 Scene Planning

结构化输出失败

不存在角色引用

重复 Shot

Continuity Fail

Revision Loop

超过 Revision Budget

用户 Reject

用户 Edit

Graph Interrupt

应用重启 Resume

LLM Timeout

LLM Rate Limit

Agent Cancel

Proposal Revision Conflict

Project Context 超 Token Budget
```

---

# 192. 核心集成测试 A

小说：

```text
训练结束，
教练留下沈亦。
```

期望：

```text
Scene

4～8 Shots

Characters:
沈亦
教练
```

禁止：

```text
凭空创造新主角
```

---

# 193. Test B

Shot Planning：

连续：

```text
8 个 Close Up
```

Visual Review：

应该产生：

```text
Visual Variety Warning
```

---

# 194. Test C

上一 Shot：

```text
沈亦白色7号球衣
```

当前：

```text
黑色训练服
```

没有换装剧情。

Continuity：

```text
ERROR
```

---

# 195. Test D

Proposal 基于：

```text
revision = 4
```

用户编辑：

```text
revision = 5
```

Apply：

```text
409 / PROPOSAL_REVISION_CONFLICT
```

---

# 196. Test E

Director：

```text
WAITING_HUMAN
```

关闭进程。

重启后：

```text
Resume
```

继续。

---

# 197. Agent 系统禁止事项

## 禁止 1

```text
LLM 直接操作数据库。
```

---

## 禁止 2

```text
自然语言输出直接写 Project。
```

---

## 禁止 3

```text
Agent Graph State 充当项目数据库。
```

---

## 禁止 4

```text
Agent Memory 作为角色事实来源。
```

---

## 禁止 5

```text
Director 直接执行视频 Generation。
```

---

## 禁止 6

```text
一个 Agent 承担所有漫剧流程。
```

---

## 禁止 7

```text
多个 Agent 自由聊天协商结果。
```

---

## 禁止 8

```text
Agent 无限 Revision。
```

---

## 禁止 9

```text
Tool 直接暴露 SQL / Shell。
```

---

## 禁止 10

```text
Proposal 在 Project 已变化后静默 Apply。
```

---

# 198. Director 最终主链路

```text
SourceDocument
      ↓
ContextResolver
      ↓
Director Graph
      ↓
Script Agent
      ↓
Scene Plan
      ↓
Visual Agent
      ↓
Shot Plan
      ↓
Continuity Rules
      ↓
Continuity Agent
      ↓
Director Evaluation
      │
      ├── REVISE ──────────┐
      │                    │
      └── PASS             │
            ↓              │
       Human Review        │
            ↓              │
         Proposal ◄────────┘
            ↓
     Application Service
            ↓
      Project Domain
```

---

# 199. Production 链路

Director 规划完成后：

```text
Shot
 ↓
ShotVisualSpec
 ↓
Prompt Agent
 ↓
PromptVersion
 ↓
GenerationPlanner
 ↓
Job Queue
 ↓
Provider
 ↓
Asset
```

Director 不参与 Provider 执行。

---

# 200. AI Director Alpha 完成定义

满足以下条件：

1. 小说能够进入 ContextResolver；
2. Script Agent 输出结构化剧情规划；
3. Visual Agent 输出合法 ShotPlan；
4. ShotPlan 可以转换为正式 Shot / ShotVisualSpec；
5. Agent 不直接写数据库；
6. 所有变更通过 Proposal；
7. Proposal 支持 Domain Validation；
8. Director 可以执行 Script → Visual → Continuity；
9. Continuity Fail 可以进入 Revision Loop；
10. Revision 有明确上限；
11. Structured Output 失败可以修复或安全退出；
12. Context 受到 Token Budget 控制；
13. Agent 只加载与当前任务相关的数据；
14. Project Database 始终是 Source of Truth；
15. LangGraph Checkpoint 可保存 Agent Run；
16. Agent Run 可以在 Human Review 点暂停；
17. 用户批准后可以 Resume；
18. Studio 重启后可以恢复未完成 Director Run；
19. Agent Proposal 带 BaseRevision；
20. 过期 Proposal 不会静默覆盖用户修改；
21. Prompt Agent 可以生成 Provider-independent Canonical Prompt；
22. Agent Model 可以独立配置；
23. Agent Token / Cost 可以统计；
24. Agent Job 接入现有 Persistent Job Queue；
25. Agent 失败不会破坏 Project State。

则：

> **AI Director Agent Alpha v0.2 核心架构成立。**

---

# 201. 现在整个 Alpha 架构已经形成的主干

到这里已经完成：

```text
01 Product / Alpha Planning

02 Core Domain Model

03 Database Schema

04 Backend API & Service

05 Asset / Generation / Version

06 Job Queue & State Machine

07 AI Director Agent
```

这意味着：

```text
Project State
      │
      ├── Asset System
      ├── Version System
      ├── Generation System
      ├── Production Queue
      └── AI Planning Plane
```

已经基本闭环。

---

# 202. 下一份设计文档

下一步最合理的不是继续拆 Agent，而是把目前仍然比较抽象、但会直接决定“连续漫剧能不能看”的系统正式单独设计：

# 《AI 漫剧 Studio Continuity Engine 详细设计 v0.1》

这一份需要重点解决：

```text
Scene Base State

Shot State

State Delta

Character State

Costume State

Prop State

Location State

Time State

Position

Orientation

Action Continuity

Shot-to-Shot Inheritance

Rule Engine

Agent Review

Warning

Severity

Auto Fix

STALE Integration

Character MASTER Change

First / Last Frame

Video Transition

Continuity Snapshot

Context Resolver Integration
```

它将解决 AI 漫剧真正困难的问题之一：

> **不仅“每个镜头好看”，而且前后镜头确实像同一段连续发生的故事。**
