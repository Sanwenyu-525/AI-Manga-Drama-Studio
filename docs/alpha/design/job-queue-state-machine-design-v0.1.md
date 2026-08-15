# AI 漫剧 Studio Job Queue & Generation State Machine 详细设计 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**上游文档：**

* 《AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1》
* 《AI 漫剧 Studio 核心领域模型详细设计 v0.1》
* 《AI 漫剧 Studio 数据库 Schema 与数据关系设计 v0.1》
* 《AI 漫剧 Studio Alpha Backend API & Service 详细设计 v0.1》
* 《AI 漫剧 Studio Asset / Generation / Version 系统详细设计 v0.1》

**目标：**

建立 AI 漫剧 Studio 的统一异步执行系统，使：

```text
单 Shot
Scene
Episode
Agent
ComfyUI
Image
Video
Voice
Render
```

等任务能够稳定完成：

```text
计划
→ 排队
→ 调度
→ 执行
→ Retry
→ Pause
→ Resume
→ Cancel
→ Recovery
→ Progress
→ Partial Failure
→ Complete
```

最终使 Studio 从：

> “点击一个按钮生成一个镜头”

升级为：

> **能够连续生产几十乃至数百个 Shot 的持久化 AI 漫剧生产系统。**

---

# 1. 系统定位

Job Queue 解决的不是：

```text
如何生成视频？
```

而是：

```text
什么时候生成？

先生成什么？

哪些任务能并行？

哪些必须等待？

失败后怎么办？

软件关掉后怎么办？

GPU 忙了怎么办？

怎么知道整个 Scene 完成了多少？
```

因此本系统位于：

```text
Application Layer
      ↓
Generation Planner
      ↓
Job Queue
      ↓
Generation Executor
      ↓
Provider Adapter
```

之间。

---

# 2. 核心模型

调度系统定义四个主要概念：

```text
Job

JobTask

TaskDependency

Worker
```

并与已有：

```text
Generation
```

形成：

```text
Job
 │
 ├── Task
 │    │
 │    └── Generation
 │
 ├── Task
 │    └── Generation
 │
 └── Task
      └── Generation
```

---

# 3. Job 定义

Job 表示：

> 用户理解的一次完整业务操作。

例如：

```text
Generate Shot 023

Generate Scene 05

Generate Episode 01

Render Episode 01

Plan Episode

Generate Character References
```

因此 Job 是：

```text
Business Operation
```

而不是模型执行。

---

# 4. Task 定义

JobTask 表示：

> 一个可以独立被 Queue 调度的最小工作单元。

例如：

```text
Shot 01 Image

Shot 01 Video

Shot 02 Image

Shot 02 Video
```

---

# 5. Generation 定义

Generation 仍然表示：

> 一次具体 AI / Workflow / Render 执行。

因此：

```text
Job
=
业务任务
```

```text
Task
=
调度任务
```

```text
Generation
=
执行记录
```

三个概念必须永久分离。

---

# 6. 为什么 Task 不等于 Generation

有些 Task 不调用 AI。

例如：

```text
CHECK_ASSET

BUILD_PROMPT

REGISTER_ASSET

GENERATE_THUMBNAIL

FINALIZE_SCENE

TIMELINE_UPDATE
```

所以：

```text
Task
```

可以没有：

```text
generationId
```

---

# 7. 为什么 Generation 不直接 Queue

如果直接：

```text
Queue<Generation>
```

以后无法很好支持：

```text
准备 Prompt
→ 生成 Image
→ 检查 Image
→ 生成 Video
→ 创建 Thumbnail
```

这类复杂 DAG。

所以 Queue 调度：

```text
JobTask
```

而不是 Generation。

---

# 8. 顶层架构

```text
User Action
    ↓
Application Service
    ↓
Generation Planner
    ↓
Job Planner
    ↓
Create Job
    ↓
Create Tasks
    ↓
Create Dependencies
    ↓
Persistent Queue
    ↓
Scheduler
    ↓
Worker Pool
    ↓
Task Executor
    ↓
Generation Executor
    ↓
Provider
```

---

# 9. 为什么必须 Persistent Queue

禁止只使用：

```text
BlockingQueue<JobTask>
```

这种纯内存 Queue。

否则软件：

```text
关闭
崩溃
电脑重启
```

以后任务全部消失。

真正 Source of Truth：

```text
job_tasks table
```

内存 Queue 只能作为：

```text
性能缓存
```

不能作为任务真相来源。

---

# 10. JobType

建议 Alpha：

```text
GENERATE_SHOT_IMAGE

GENERATE_SHOT_VIDEO

GENERATE_SHOT

GENERATE_SCENE

GENERATE_EPISODE

GENERATE_CHARACTER

GENERATE_LOCATION

PLAN_EPISODE

PLAN_SCENE

GENERATE_VOICE

RENDER_TIMELINE

VERIFY_PROJECT

CUSTOM
```

---

# 11. TaskType

建议：

```text
AGENT_TASK

PROMPT_TASK

IMAGE_GENERATION

VIDEO_GENERATION

VOICE_GENERATION

MUSIC_GENERATION

SUBTITLE_GENERATION

COMFYUI_WORKFLOW

MEDIA_PROCESS

MEDIA_VALIDATE

THUMBNAIL_GENERATION

TIMELINE_RENDER

FINALIZE

CUSTOM
```

---

# 12. JobStatus

推荐：

```text
CREATED

QUEUED

RUNNING

PAUSE_REQUESTED

PAUSED

CANCEL_REQUESTED

COMPLETED

PARTIAL_FAILED

FAILED

CANCELLED

INTERRUPTED
```

---

# 13. TaskStatus

推荐：

```text
CREATED

BLOCKED

READY

QUEUED

RUNNING

PAUSE_REQUESTED

CANCEL_REQUESTED

SUCCEEDED

FAILED

CANCELLED

SKIPPED

INTERRUPTED
```

---

# 14. 为什么需要 BLOCKED

例如：

```text
Shot Image
     ↓
Shot Video
```

Video Task 已创建，

但 Image 没完成。

因此：

```text
Video = BLOCKED
```

而不是：

```text
QUEUED
```

依赖满足后：

```text
BLOCKED
 ↓
READY
```

---

# 15. READY 与 QUEUED 的区别

```text
READY
```

表示：

> 所有业务依赖满足，可以调度。

```text
QUEUED
```

表示：

> Scheduler 已经正式将任务交给某 Worker Queue。

Alpha 如果想简化，也可以暂时合并。

但建议保留两个概念。

---

# 16. Job 正常状态流

```text
CREATED
   ↓
QUEUED
   ↓
RUNNING
   ↓
COMPLETED
```

---

# 17. Job 部分失败

例如 Scene：

```text
20 Shots

18 success
2 failed
```

则：

```text
PARTIAL_FAILED
```

不要直接：

```text
FAILED
```

因为已有 18 个结果可以继续使用。

---

# 18. Job FAILED

只有当：

```text
核心任务无法继续
```

或：

```text
全部任务失败
```

时使用：

```text
FAILED
```

例如：

```text
Episode Planning Agent
```

第一步就失败，

后续所有任务无法创建。

---

# 19. Task DAG

Scene 生成：

```text
Shot 01 Image
      ↓
Shot 01 Video

Shot 02 Image
      ↓
Shot 02 Video

Shot 03 Image
      ↓
Shot 03 Video
```

这是一个：

```text
Directed Acyclic Graph
```

DAG。

---

# 20. 为什么不是简单队列

简单：

```text
Task1
Task2
Task3
Task4
```

无法表达：

```text
Image01 和 Image02 可以并行

Video01 必须等 Image01

Video02 必须等 Image02
```

因此必须支持：

```text
Task Dependency Graph
```

---

# 21. DependencyType

Task Dependency：

```text
HARD

SOFT
```

## HARD

上游失败：

```text
下游不能执行
```

## SOFT

上游失败：

```text
下游仍可决定继续
```

Alpha 绝大部分生成依赖使用：

```text
HARD
```

---

# 22. Shot Pipeline 示例

一个 Shot 可以被规划为：

```text
Build Prompt
    ↓
Generate Image
    ↓
Validate Image
    ↓
Generate Video
    ↓
Validate Video
    ↓
Generate Thumbnail
```

但 Alpha 第一阶段可以简化成：

```text
Image Generation
       ↓
Video Generation
```

其余动作由 Task Executor 内部完成。

---

# 23. Scene DAG

```text
                  ┌─ Shot01 Image ─ Shot01 Video
                  │
Generate Scene ───┼─ Shot02 Image ─ Shot02 Video
                  │
                  ├─ Shot03 Image ─ Shot03 Video
                  │
                  └─ Shot04 Image ─ Shot04 Video
                                      │
                                      ▼
                               Finalize Scene
```

---

# 24. Episode DAG

未来：

```text
Scene 01 Generation ─┐
Scene 02 Generation ─┤
Scene 03 Generation ─┼→ Voice / Timeline → Render
Scene 04 Generation ─┤
Scene 05 Generation ─┘
```

但不要为 Scene 再嵌套 Job。

推荐：

```text
Parent Job
+
Task grouping
```

而不是无限：

```text
Job
 └ Job
   └ Job
```

---

# 25. Parent Job

如果未来确实需要：

```text
Episode Job
```

拆多个：

```text
Scene Job
```

可以增加：

```text
parent_job_id
```

但 Alpha 推荐先避免。

通过：

```text
task_group
```

即可。

---

# 26. Task Group

例如：

```text
group = scene_01
group = scene_02
```

或者：

```text
group = shot_023
```

便于 UI：

```text
Scene 01  80%

Scene 02  42%
```

---

# 27. Job Planner

核心：

```text
JobPlanner
```

负责把：

```text
Generate Scene
```

转换为：

```text
Job
+
Tasks
+
Dependencies
```

---

# 28. JobPlanner 输入

例如：

```text
GenerateSceneCommand
{
  sceneId

  generateImage
  generateVideo

  skipApproved
  staleOnly
}
```

---

# 29. JobPlanner 输出

内部：

```text
JobPlan
{
    jobType

    tasks[]

    dependencies[]
}
```

---

# 30. TaskDefinition

```text
TaskDefinition
{
    tempId

    taskType

    targetType
    targetId

    executorType

    priority

    resourceRequirement

    metadata
}
```

---

# 31. 计划阶段不执行 Provider

JobPlanner：

```text
只规划
```

禁止：

```text
调用 ComfyUI
```

保证：

```text
Plan
```

和：

```text
Execute
```

彻底分离。

---

# 32. TaskScheduler

Scheduler 负责：

```text
扫描 READY Task

检查资源

检查并发

检查 Provider

分配 Worker

Atomic Claim
```

---

# 33. Scheduler Loop

概念：

```text
while running:

    find ready tasks

    sort by priority

    check resource availability

    claim task

    dispatch worker
```

但不建议：

```text
while(true)
sleep(10ms)
```

疯狂扫数据库。

---

# 34. Scheduler 唤醒机制

可以使用：

```text
Application Event
+
Periodic Fallback
```

例如：

新 Task：

```text
TaskCreatedEvent
```

立即唤醒 Scheduler。

同时：

```text
每 1 秒
```

做一次 fallback scan。

---

# 35. Task Claim

多 Worker 必须避免重复消费。

错误：

```text
SELECT task
↓
Worker A
Worker B
同时拿到
```

必须：

```text
Atomic State Transition
```

例如：

```text
READY
 ↓
RUNNING
```

只有成功 Claim 的 Worker 执行。

---

# 36. SQLite Claim

SQLite 单 Writer 条件下：

在短事务中：

```text
BEGIN IMMEDIATE

检查 Task READY

UPDATE status = RUNNING

COMMIT
```

即可。

不要长时间持锁。

---

# 37. Worker 定义

Worker 表示：

> 可以执行特定 TaskType 的执行单元。

例如：

```text
AgentWorker

ComfyUIWorker

RemoteImageWorker

RemoteVideoWorker

MediaWorker

RenderWorker
```

---

# 38. WorkerPool

统一：

```text
WorkerPoolManager
```

内部：

```text
Agent Pool

ComfyUI Pool

Remote AI Pool

Media Pool

Render Pool
```

---

# 39. 为什么不能一个通用线程池

如果：

```text
Video Generation
```

全部占满线程，

那么：

```text
Prompt Generation
Asset Validation
Thumbnail
```

也无法执行。

所以必须：

```text
按资源类型隔离
```

---

# 40. ResourceType

建议：

```text
CPU

LOCAL_GPU

REMOTE_LLM

REMOTE_IMAGE

REMOTE_VIDEO

REMOTE_VOICE

COMFYUI

MEDIA_IO
```

---

# 41. ResourceRequirement

Task 可以声明：

```text
ResourceRequirement
{
   type
   providerId
   gpuId
   slots
}
```

例如：

```text
COMFYUI
provider = local_comfyui
slots = 1
```

---

# 42. 单 GPU 默认策略

Alpha：

```text
maxConcurrentComfyUITasks = 1
```

因为：

```text
图像生成
视频生成
```

同时抢显存非常容易：

```text
OOM
```

---

# 43. ComfyUI 自己也有 Queue

是的，ComfyUI 本身有执行队列。

但 Studio 仍然需要自己的 Queue。

因为 Studio 还需要管理：

```text
Job

DAG

Dependency

Version

Retry

Cancel

Resume

Provider Switching

Progress
```

因此：

```text
Studio Queue
```

是业务调度。

```text
ComfyUI Queue
```

是 Provider 内部执行队列。

两者不是重复。

---

# 44. 是否一次提交很多 ComfyUI Prompt

Alpha 推荐：

```text
Studio 控制节奏
```

不要一次向 ComfyUI 塞：

```text
100 个 Workflow
```

否则：

```text
取消困难
优先级困难
恢复困难
状态同步困难
```

建议保持：

```text
1～少量 in-flight
```

---

# 45. Provider Concurrency

Provider Profile 应允许：

```text
maxConcurrency
```

例如：

```text
ComfyUI Local = 1

Remote Image API = 4

Remote Video API = 2

LLM API = 8
```

---

# 46. ResourceSemaphore

调度层可以维护：

```text
ResourceSemaphore
```

例如：

```text
COMFYUI_LOCAL = 1

VIDEO_API = 2
```

Worker 只有获得 Slot 才运行。

---

# 47. GPU Resource Manager

后续可增加：

```text
GpuResourceManager
```

记录：

```text
GPU 0

VRAM total
VRAM available
running task
```

Alpha 第一版不做动态显存预测。

先：

```text
每 GPU 1 Task
```

即可。

---

# 48. Multi-GPU

未来：

```text
GPU 0
GPU 1
```

可配置：

```text
Worker A → GPU0

Worker B → GPU1
```

Provider Adapter 注入：

```text
gpuId
```

Alpha 只预留。

---

# 49. Priority

Task：

```text
priority INTEGER
```

推荐范围：

```text
0～100
```

例如：

```text
USER_IMMEDIATE = 100

USER_BATCH = 70

BACKGROUND = 30

MAINTENANCE = 10
```

---

# 50. 为什么需要 Priority

用户正在编辑 Shot 23，

点击：

```text
Regenerate
```

应该优先于：

```text
后台 Episode 200 个 Shot
```

否则交互体验极差。

---

# 51. Priority Inheritance

如果：

```text
Video Task priority = 100
```

依赖：

```text
Image Task priority = 50
```

可以临时提升：

```text
Image Task
```

到：

```text
100
```

避免高优先级任务被低优先级依赖阻塞。

Alpha 可后续实现。

---

# 52. Fair Scheduling

不能让：

```text
高优先级 Job
```

永久饿死低优先级任务。

后续可以：

```text
effectivePriority =
basePriority + waitingAge
```

实现：

```text
aging
```

Alpha 初期可只按：

```text
priority DESC
created_at ASC
```

---

# 53. Queue Selection

推荐：

```text
ORDER BY
priority DESC,
created_at ASC
```

---

# 54. Task Executor

不同 TaskType 使用：

```text
TaskExecutor
```

接口：

```text
supports(taskType)

execute(taskContext)

cancel(taskId)
```

---

# 55. Executor Registry

```text
TaskExecutorRegistry
```

映射：

```text
IMAGE_GENERATION
→ ImageGenerationTaskExecutor

VIDEO_GENERATION
→ VideoGenerationTaskExecutor

AGENT_TASK
→ AgentTaskExecutor

TIMELINE_RENDER
→ TimelineRenderTaskExecutor
```

---

# 56. TaskContext

执行时：

```text
TaskContext
{
   job
   task
   project
   cancellationToken
   progressReporter
}
```

---

# 57. Generation Task

对于 AI 生成 Task：

```text
TaskExecutor
 ↓
GenerationExecutor
```

GenerationExecutor 仍然负责：

```text
Provider 调用
Asset 注册
Generation 状态
```

Queue 不应该重写 Generation 逻辑。

---

# 58. Progress 模型

进度分为：

```text
Task Progress

Job Progress
```

Task：

```text
0.0 ～ 1.0
```

Job：

根据 Task 汇总。

---

# 59. 为什么不能简单 Task 数量平均

例如：

```text
Prompt = 2s

Image = 30s

Video = 180s
```

如果等权：

```text
1/3
1/3
1/3
```

进度会很奇怪。

所以 Task 应支持：

```text
weight
```

---

# 60. Task Weight

例如：

```text
Image = 2

Video = 8

Prompt = 1
```

Job Progress：

```text
Σ task.weight × task.progress
----------------------------
Σ task.weight
```

---

# 61. Alpha 简化

如果模型执行时间差异还不确定：

第一版可以：

```text
所有 Task weight = 1
```

以后根据历史统计自动调整。

---

# 62. Provider Progress

有的 Provider 提供：

```text
progress %
```

有的不提供。

因此 Task Progress 支持两种：

```text
DETERMINATE

INDETERMINATE
```

---

# 63. 无真实 Progress 的视频任务

UI 显示：

```text
Generating...
```

而不是伪造：

```text
73%
```

如果没有真实数据，不要制造虚假精确度。

---

# 64. Job Progress 持久化

不要每个 Provider 回调：

```text
1%
2%
3%
```

都写 DB。

推荐：

内存实时：

```text
ProgressTracker
```

持久化：

```text
状态切换时立即写

或每 1～2 秒节流写
```

---

# 65. Progress Event

SSE：

```text
TASK_PROGRESS
```

例如：

```json
{
  "jobId": "job_1",
  "taskId": "task_3",
  "progress": 0.64
}
```

---

# 66. Job Progress Event

同时可以：

```json
{
  "type": "JOB_PROGRESS",
  "jobId": "job_1",
  "progress": 0.37,
  "completed": 14,
  "failed": 1,
  "total": 40
}
```

---

# 67. Retry Policy

Retry 决策不应该写死：

```text
catch(Exception) retry
```

统一：

```text
RetryPolicy
```

---

# 68. Error Classification

统一：

```text
RetryableError

NonRetryableError

UserActionRequiredError
```

---

# 69. Retryable

例如：

```text
NETWORK_TIMEOUT

RATE_LIMIT

PROVIDER_BUSY

TEMPORARY_SERVER_ERROR

COMFYUI_BUSY
```

---

# 70. Non-Retryable

例如：

```text
INVALID_WORKFLOW

MODEL_NOT_FOUND

INVALID_ASSET

PROMPT_SCHEMA_ERROR

UNSUPPORTED_FORMAT
```

---

# 71. User Action Required

例如：

```text
DISK_FULL

CREDENTIAL_MISSING

PROVIDER_NOT_CONFIGURED

ASSET_MISSING
```

这种错误不应不停自动 Retry。

---

# 72. Retry Backoff

推荐：

```text
Attempt 1
2s

Attempt 2
5s

Attempt 3
15s
```

并加入少量：

```text
jitter
```

防止多个任务同时重新冲 Provider。

---

# 73. Retry 与 Generation

第一次：

```text
Task
 ↓
Generation 100
FAILED
```

Retry：

Task 不一定创建新的 Task。

推荐：

```text
同一个 JobTask
```

增加：

```text
retry_count
```

但创建：

```text
Generation 101
parent = 100
```

---

# 74. 为什么 Task 可以复用

Task 代表：

```text
完成 Shot 23 Video
```

其业务目标没有变。

Generation 代表：

```text
Attempt
```

所以：

```text
1 Task
→ N Generations
```

更合理。

---

# 75. Task.currentGenerationId

Task：

```text
generation_id
```

始终指向：

```text
当前 Attempt
```

历史通过：

```text
Generation Retry Chain
```

追踪。

---

# 76. Manual Retry

用户点击：

```text
Retry Failed
```

Task：

```text
FAILED
 ↓
READY
```

retry_count + 1，

创建新 Generation。

---

# 77. Retry Failed Job

```text
POST /jobs/{jobId}/retry-failed
```

只对：

```text
FAILED
INTERRUPTED
```

Task 重置。

不碰：

```text
SUCCEEDED
```

---

# 78. Pause Job

用户：

```text
Pause
```

语义：

> 不再开始新的 Task。

已经运行的 Task：

Alpha 推荐：

```text
允许完成
```

然后 Job：

```text
PAUSED
```

---

# 79. 为什么 Pause 不强制停止运行中的生成

AI Video API / ComfyUI：

```text
强制暂停
```

往往根本不支持。

所以：

```text
Pause
```

应该是：

```text
Stop Scheduling New Tasks
```

而不是操作系统级冻结。

---

# 80. Pause 状态流

```text
RUNNING
 ↓
PAUSE_REQUESTED
```

Scheduler：

```text
停止 dispatch
```

正在 RUNNING Task 完成后：

```text
PAUSED
```

---

# 81. Immediate Pause

未来可以增加：

```text
Pause & Cancel Running
```

但 Alpha 暂不需要。

---

# 82. Resume

```text
PAUSED
 ↓
QUEUED
 ↓
RUNNING
```

Scheduler 继续调度：

```text
READY Task
```

---

# 83. Cancel Job

Cancel 比 Pause 更强。

语义：

```text
不再执行剩余 Task

尽量取消运行 Task
```

---

# 84. Cancel 流程

```text
RUNNING
 ↓
CANCEL_REQUESTED
```

然后：

```text
BLOCKED / READY / QUEUED
→ CANCELLED
```

运行中：

```text
Task.cancel()
```

如果 Provider 支持：

```text
cancel execution
```

---

# 85. 无法取消的 Task

如果 Provider 不支持：

```text
Task
```

继续运行。

完成后：

结果可以：

```text
Discard
```

或：

```text
Archive
```

Job 最终仍：

```text
CANCELLED
```

---

# 86. CancellationToken

TaskExecutor 应接收：

```text
CancellationToken
```

在长 CPU / 文件任务中周期检查：

```text
if cancelled:
    stop
```

---

# 87. Crash Recovery

这是 Alpha 必须做好的能力。

应用异常关闭时：

数据库可能存在：

```text
Job RUNNING

Task RUNNING

Generation RUNNING
```

但真正 Worker 已不存在。

---

# 88. Startup Recovery

启动：

```text
RecoveryService
```

扫描：

```text
RUNNING
QUEUED
PAUSE_REQUESTED
CANCEL_REQUESTED
```

状态。

---

# 89. RUNNING Task 恢复

本地进程任务：

```text
RUNNING
```

通常视为：

```text
INTERRUPTED
```

因为 Worker 已消失。

---

# 90. Remote Provider 特例

云 Provider 可能：

```text
请求已提交
```

即使 Studio 关闭，

任务仍在运行。

如果保存了：

```text
externalExecutionId
```

启动恢复时可以：

```text
queryStatus()
```

---

# 91. RecoveryDecision

统一：

```text
RecoveryDecision
```

返回：

```text
REATTACH

RETRY

INTERRUPT

FAIL
```

---

# 92. ComfyUI Recovery

如果 ComfyUI 仍在运行：

可以通过：

```text
prompt_id
```

查询历史 / Queue。

若还能找到：

```text
REATTACH
```

若找不到：

```text
INTERRUPTED
```

---

# 93. Local Process Recovery

例如 FFmpeg：

应用死了，

子进程可能已经死。

直接：

```text
INTERRUPTED
```

然后允许 Retry。

---

# 94. Interrupted != Failed

这是重要区分：

```text
FAILED
```

表示：

> 执行明确失败。

```text
INTERRUPTED
```

表示：

> 执行状态因系统中断无法确认。

UI 应显示不同。

---

# 95. Resume Job

用户打开 Project：

```text
1 interrupted job found
```

点击：

```text
Resume
```

系统：

```text
INTERRUPTED Task
→ READY
```

已经：

```text
SUCCEEDED
```

的 Task 不动。

---

# 96. Checkpoint

Checkpoint 的本质不是：

```text
保存一个巨大 JSON
```

而是：

> 每一个重要 Task / Generation 状态都已经持久化。

因此 Persistent Queue 本身就是主要 Checkpoint。

---

# 97. Scene Checkpoint

例如：

```text
Scene 05

Shot01 Image ✓
Shot01 Video ✓
Shot02 Image ✓
Shot02 Video ✗
Shot03 Image ✓
Shot03 Video running
```

关闭软件后：

这些状态全部来自 DB。

不需要重新从头计算。

---

# 98. Result Checkpoint

每一个成功 Asset：

```text
立即注册
```

不能等：

```text
整个 Scene 完成
```

再一起写数据库。

否则中途崩溃会丢失大量已经生成的结果。

---

# 99. Transaction Granularity

每一个 Task：

```text
独立 commit
```

不要：

```text
整个 Job 一个事务
```

Job 可能执行数小时。

---

# 100. Partial Failure

Scene Job：

```text
Task 1 ✓
Task 2 ✓
Task 3 ✗
Task 4 ✓
```

剩余无依赖任务继续。

最终：

```text
PARTIAL_FAILED
```

---

# 101. Fail Fast

某些 Job 可以配置：

```text
failurePolicy
```

例如：

```text
CONTINUE

FAIL_FAST
```

---

# 102. Scene Generation

推荐：

```text
CONTINUE
```

因为某一个 Shot 失败：

不应该停止整个 Scene。

---

# 103. Episode Planning

例如 Director 核心 Agent：

第一步失败，

后续全部没有意义。

可以：

```text
FAIL_FAST
```

---

# 104. Dependency Failure

如果：

```text
Shot Image FAILED
```

其 Video：

```text
BLOCKED
```

应该变：

```text
SKIPPED
```

并记录：

```text
DEPENDENCY_FAILED
```

而不是：

```text
FAILED
```

因为 Video 本身没有真正执行。

---

# 105. SKIPPED

SKIPPED 语义：

```text
没有执行
```

原因可能：

```text
DEPENDENCY_FAILED

USER_FILTER

ALREADY_APPROVED

NOT_STALE

JOB_CANCELLED
```

---

# 106. skipApprovedShots

Scene Batch：

```text
skipApprovedShots = true
```

已 APPROVED Shot：

相关 Task：

```text
SKIPPED
```

不重新生成。

---

# 107. staleOnly

```text
regenerateStaleOnly = true
```

Planner 只为：

```text
STALE Active Asset
```

的 Shot 建立 Task。

---

# 108. Planner 应尽量避免创建无用 Task

相比：

```text
创建 100 个 Task
然后全部 SKIPPED
```

更好：

```text
规划阶段直接过滤
```

SKIPPED 更适合运行期间条件变化。

---

# 109. Dynamic DAG

运行过程中可能创建新 Task。

例如：

```text
Image Generation
```

结果检测：

```text
需要 Upscale
```

动态加入：

```text
Upscale Task
```

Alpha 第一版可以支持：

```text
Job RUNNING 时 addTask()
```

但必须谨慎。

---

# 110. DAG Cycle

每次建立 Dependency：

必须确保：

```text
无环
```

否则：

```text
Task A waits B
Task B waits A
```

Job 永远挂死。

---

# 111. Cycle Detection

JobPlan 创建时：

执行：

```text
topological sort
```

如果失败：

```text
JOB_PLAN_CYCLE_DETECTED
```

拒绝 Job。

---

# 112. Dead Task Detection

Job RUNNING：

如果：

```text
没有 RUNNING
没有 READY
存在 BLOCKED
```

说明：

```text
可能有依赖异常
```

JobMonitor 应检测：

```text
deadlock
```

---

# 113. JobMonitor

后台：

```text
JobMonitorService
```

周期检查：

```text
stuck jobs

invalid dependency state

progress inconsistency

orphan running tasks
```

---

# 114. Stuck Task

可以定义：

```text
heartbeat_at
```

Task Worker 定期：

```text
heartbeat
```

如果：

```text
RUNNING
+
heartbeat 超时
```

可判断：

```text
Worker Lost
```

---

# 115. Alpha 是否需要 Heartbeat

本地单进程 Alpha：

可以暂缓。

因为：

```text
进程活着
```

通常 Worker 就活着。

如果后续拆：

```text
Python Agent Runtime
Remote Worker
```

再正式加。

---

# 116. Worker Process

如果 Agent Runtime 独立 Python：

Task：

```text
AGENT_TASK
```

可能通过：

```text
HTTP
```

提交。

此时要记录：

```text
externalExecutionId
```

并与 Remote Provider 类似管理。

---

# 117. Timeout

Task 必须有：

```text
timeout
```

但不同类型不同。

例如：

```text
LLM = 120s

Image = 10min

Video = 30min

Render = 60min
```

---

# 118. TimeoutPolicy

不能所有：

```text
5 min
```

统一。

放在：

```text
ProviderProfile
```

或：

```text
TaskType defaults
```

---

# 119. Timeout 后

```text
Task Executor
```

尝试取消 Provider。

Generation：

```text
FAILED
errorCode = TIMEOUT
```

然后 RetryPolicy 决定：

```text
是否 Retry
```

---

# 120. Rate Limit

Remote Provider：

可能：

```text
429
```

RetryPolicy：

```text
读取 Retry-After
```

将 Task 延迟：

```text
next_run_at
```

---

# 121. Delayed Task

JobTask 建议增加：

```text
next_run_at
```

Scheduler 只选择：

```text
next_run_at <= now
```

的 READY Task。

---

# 122. Backoff 不应该 sleep Worker

错误：

```text
Worker sleep 30 seconds
```

正确：

```text
Task → READY
next_run_at = future
```

释放 Worker。

---

# 123. Scheduled Retry

```text
FAILED attempt
 ↓
Retryable
 ↓
Task READY
next_run_at = now + backoff
```

---

# 124. Provider Unavailable

如果：

```text
ComfyUI offline
```

不要让 100 个 Task：

```text
连续失败
```

应该引入：

```text
ProviderCircuitBreaker
```

---

# 125. Circuit Breaker

状态：

```text
CLOSED

OPEN

HALF_OPEN
```

连续错误超过阈值：

```text
OPEN
```

暂时不调度该 Provider 的 Task。

---

# 126. Alpha 简化 Circuit Breaker

可以先：

```text
ProviderHealthService
```

检测：

```text
UNAVAILABLE
```

Scheduler 暂停对应资源任务。

UI：

```text
ComfyUI disconnected

12 tasks waiting
```

---

# 127. Waiting For Provider

Task 仍然：

```text
READY
```

但 Scheduler 因：

```text
resource unavailable
```

不执行。

不要设：

```text
FAILED
```

---

# 128. Queue UI

Studio 底部：

```text
Generation Queue
```

建议分：

```text
Running

Queued

Blocked

Failed

Completed
```

---

# 129. Job UI

例如：

```text
Generate Scene 05

13 / 24

54%

Running 1
Queued 7
Failed 1
Completed 13
```

操作：

```text
Pause

Cancel

Retry Failed
```

---

# 130. Task UI

点击 Job：

```text
Shot 01 Image      ✓
Shot 01 Video      ✓
Shot 02 Image      ✓
Shot 02 Video      Failed
Shot 03 Image      Running
Shot 03 Video      Blocked
```

---

# 131. Generation Detail

点击 Task：

进一步：

```text
Generation #1038

Provider
Model
Prompt
Inputs
Workflow
Duration
Cost
Error
```

保持：

```text
Job → Task → Generation
```

三层 UI 语义。

---

# 132. SSE Events

推荐：

```text
JOB_CREATED

JOB_STARTED

JOB_PROGRESS

JOB_PAUSED

JOB_COMPLETED

JOB_FAILED

TASK_READY

TASK_STARTED

TASK_PROGRESS

TASK_SUCCEEDED

TASK_FAILED

TASK_RETRY_SCHEDULED

GENERATION_STARTED

GENERATION_SUCCEEDED

GENERATION_FAILED
```

---

# 133. Event 不保证永远在线

SSE 断线后：

前端必须：

```text
reconnect
```

并重新：

```text
GET /jobs/{jobId}
```

同步状态。

数据库仍然是 Source of Truth。

---

# 134. Event Sequence

每个 Project Event 可以有：

```text
sequence
```

方便：

```text
lastEventId
```

恢复。

Alpha 可以先使用：

```text
eventId + timestamp
```

不必复杂化。

---

# 135. API

核心：

```text
POST /scenes/{sceneId}/generate

POST /episodes/{episodeId}/generate

GET /projects/{projectId}/jobs

GET /jobs/{jobId}

GET /jobs/{jobId}/tasks

POST /jobs/{jobId}/pause

POST /jobs/{jobId}/resume

POST /jobs/{jobId}/cancel

POST /jobs/{jobId}/retry-failed
```

---

# 136. Job Detail Response

```json
{
  "id": "job_01",
  "type": "GENERATE_SCENE",
  "status": "RUNNING",
  "progress": 0.58,
  "totalTasks": 20,
  "completedTasks": 11,
  "failedTasks": 1,
  "runningTasks": 1,
  "queuedTasks": 7
}
```

---

# 137. Scene Generate Request

```json
{
  "steps": [
    "IMAGE",
    "VIDEO"
  ],
  "skipApprovedShots": true,
  "staleOnly": false,
  "priority": "NORMAL"
}
```

---

# 138. Immediate Shot Regeneration

单 Shot 用户操作：

优先级：

```text
100
```

Episode Batch：

```text
70
```

后台：

```text
30
```

这样用户不需要等整个 Batch 完成才能预览新 Shot。

---

# 139. Preemption

是否需要：

```text
停止当前低优先级 Video
```

给高优先级任务让路？

Alpha：

```text
不做
```

当前正在执行的任务完成后：

Scheduler 选择高优先级。

这样安全得多。

---

# 140. Scene Complete

不是看：

```text
所有 Shot status
```

决定 Job。

Job 只看：

```text
JobTask
```

最终状态。

如果全部：

```text
SUCCEEDED / SKIPPED
```

则：

```text
COMPLETED
```

---

# 141. Partial Failed 判断

存在：

```text
FAILED
```

同时至少一个：

```text
SUCCEEDED
```

则：

```text
PARTIAL_FAILED
```

---

# 142. Failed 判断

全部核心 Task：

```text
FAILED / CANCELLED / SKIPPED due failure
```

无成功产物：

```text
FAILED
```

---

# 143. Job Finalizer

统一：

```text
JobFinalizer
```

计算：

```text
Job final status

progress

statistics

duration
```

---

# 144. Finalize Task

某些 Job 可以有显式：

```text
FINALIZE
```

Task。

例如 Scene：

```text
所有 Shot Tasks
      ↓
Finalize Scene
```

Finalize：

```text
计算 Scene status

更新摘要

发布 SceneGenerationCompleted
```

---

# 145. Finalize Dependency

Finalize Task 依赖：

```text
所有末端 Task
```

但如果允许 Partial Failure，

依赖类型不能严格 HARD。

可以：

```text
WAIT_ALL
```

这种特殊依赖。

---

# 146. Alpha 简化 Finalizer

无需 DAG 特殊依赖。

JobService 检测：

```text
无未终止 Task
```

后执行：

```text
Job Finalizer
```

更简单。

---

# 147. Episode Batch

Episode 可能：

```text
80～300 Shots
```

不建议一次：

```text
同时创建全部 Generation
```

但 Task 可以全部提前创建。

Generation 最好：

```text
Task 开始执行前
```

或：

```text
排队时
```

再创建。

---

# 148. 什么时候创建 Generation

推荐：

```text
Task 第一次进入 QUEUED / RUNNING
```

时由：

```text
GenerationPlanner
```

创建具体 Generation。

原因：

长时间等待期间：

```text
Prompt
MASTER
Workflow
```

可能变化。

---

# 149. 但这会影响可预测性

需要定义：

Job 创建时使用：

```text
Snapshot Mode
```

还是：

```text
Latest Mode
```

---

# 150. Snapshot Mode

Job 开始时冻结：

```text
Character Version
Prompt Version
Workflow Version
```

整个 Job 都使用相同快照。

适合：

```text
Episode Production
```

一致性更强。

---

# 151. Latest Mode

Task 真正执行时：

重新 Resolve 当前：

```text
MASTER
Active Prompt
```

适合：

```text
交互性操作
```

---

# 152. 推荐默认

Batch：

```text
SNAPSHOT
```

单 Shot：

```text
LATEST
```

但用户重新修改 Batch 中未执行镜头时：

可以提示：

```text
This job uses an earlier project snapshot.
```

---

# 153. JobContextSnapshot

Batch Job 可保存：

```text
context_snapshot_json
```

至少记录：

```text
Character masterVersionId

Location masterVersionId

Workflow version

Project generation settings
```

---

# 154. Snapshot 不复制媒体

只保存：

```text
ID references
```

因为 Asset 本身 immutable。

---

# 155. Job Creation Transaction

创建：

```text
Job
Tasks
Dependencies
Snapshot
```

必须一个事务。

如果 DAG 创建一半失败：

全部 Rollback。

---

# 156. Task Creation Idempotency

重复点击 Generate Scene：

通过：

```text
Idempotency-Key
```

避免两个 Job。

同时检查：

```text
same target
same jobType
RUNNING
```

---

# 157. Allow Duplicate Batch

用户有时确实想：

```text
并行生成两个版本
```

可以显式：

```text
forceNew = true
```

Alpha UI 暂时不暴露。

---

# 158. Job Lock

同一个：

```text
Scene
```

是否只能一个 Batch Job？

推荐：

默认：

```text
同类型只一个 ACTIVE Job
```

否则：

```text
两个 Scene Generate
```

容易产生版本爆炸。

---

# 159. Single Shot 与 Scene Job

Scene Batch 正在跑时，

用户可以：

```text
手动 Regenerate Shot 23
```

允许。

但会生成独立高优先级 Job。

---

# 160. 版本竞争

如果 Batch 和手动任务都生成：

```text
Shot 23 Image
```

两个结果：

```text
v4
v5
```

都合法。

默认不自动覆盖 Active。

因此冲突风险有限。

---

# 161. Cost Budget

Episode Batch 可能非常贵。

建议 Job 可预留：

```text
estimated_cost
budget_limit
```

Alpha 可以先只计算预计值，不阻断。

---

# 162. Job Cost

Job 完成后汇总：

```text
Σ Generation Cost
```

例如：

```text
Generate Scene 05
¥26.4
```

---

# 163. Token / GPU / Provider Metrics

Job Stats：

```text
executionTime

queueTime

retryCount

generationCount

cost
```

未来用于调度优化。

---

# 164. Historical Duration Estimation

以后根据：

```text
GenerationType
Provider
Model
Resolution
Duration
```

统计平均执行时间。

可以预测：

```text
Estimated Remaining Time
```

Alpha 第一版不用做 ETA。

不要给出虚假 ETA。

---

# 165. Database Fields — jobs

建议：

```text
id

project_id

job_type

target_type
target_id

status

priority

failure_policy

context_mode

context_snapshot_json

total_tasks
completed_tasks
failed_tasks
skipped_tasks

progress

created_at
queued_at
started_at
finished_at

pause_requested_at
cancel_requested_at

error_code
error_message
```

---

# 166. Database Fields — job_tasks

建议扩展：

```text
id

job_id

task_type

target_type
target_id

executor_type

status

priority
weight
progress

generation_id

retry_count
max_retry_count
next_run_at

timeout_seconds

error_code
error_message

created_at
queued_at
started_at
finished_at
```

---

# 167. Resource Requirement

可以先放：

```text
resource_type

provider_id
```

将来复杂时再拆 JSON。

---

# 168. Task Dependencies

```text
task_id

depends_on_task_id

dependency_type
```

建立索引：

```text
task_id

depends_on_task_id
```

---

# 169. Queue Query Index

非常重要：

```text
(status, priority, next_run_at, created_at)
```

便于 Scheduler 找 READY Task。

---

# 170. Project Scope Index

```text
(job_id, status)

(project_id, status)

(target_type, target_id)
```

---

# 171. Worker 并发配置

全局：

```text
scheduler:
  agentWorkers: 4
  mediaWorkers: 2
  comfyUiWorkers: 1
  remoteImageWorkers: 4
  remoteVideoWorkers: 2
```

实际值：

应该可配置。

---

# 172. 不建议用户一开始看到线程数

Studio Settings 可以显示更业务化：

```text
Local GPU concurrency

Remote generation concurrency
```

高级设置再暴露详细 Worker。

---

# 173. SchedulerService

核心职责：

```text
enqueue()

wake()

findReadyTasks()

claim()

dispatch()

releaseResource()
```

---

# 174. JobApplicationService

负责：

```text
createJob()

pause()

resume()

cancel()

retryFailed()

getJob()
```

---

# 175. JobPlanner

负责：

```text
planShot()

planScene()

planEpisode()

validateDag()
```

---

# 176. TaskExecutionService

负责：

```text
executeTask()

handleSuccess()

handleFailure()

handleCancellation()
```

---

# 177. RecoveryService

负责：

```text
recoverJobs()

recoverTasks()

recoverGenerations()

reattachProviderExecutions()
```

---

# 178. RetryPolicyService

负责：

```text
classify(error)

shouldRetry()

calculateBackoff()
```

---

# 179. ProgressService

负责：

```text
reportTaskProgress()

calculateJobProgress()

publishProgress()
```

---

# 180. ProviderResourceManager

负责：

```text
acquireSlot()

releaseSlot()

isAvailable()

currentUsage()
```

---

# 181. 推荐模块

```text
job
├── api
├── application
├── domain
│   ├── Job
│   ├── JobTask
│   ├── TaskDependency
│   ├── JobPlanner
│   └── RetryPolicy
│
├── scheduler
│   ├── TaskScheduler
│   ├── WorkerPoolManager
│   ├── ResourceManager
│   └── JobMonitor
│
├── executor
│   ├── TaskExecutor
│   ├── AgentTaskExecutor
│   ├── GenerationTaskExecutor
│   └── RenderTaskExecutor
│
└── recovery
    └── JobRecoveryService
```

---

# 182. Phase JQ1

第一阶段只实现：

```text
Job

Task

Persistent Queue

Single Worker

Image / Video DAG

Progress
```

---

# 183. JQ1 验收

Scene：

```text
10 Shots
```

建立：

```text
20 Tasks
```

自动按照：

```text
Image → Video
```

执行。

应用 UI 可以看到：

```text
Running
Queued
Completed
Failed
```

---

# 184. Phase JQ2

增加：

```text
Worker Pools

Priority

Retry

Backoff

Partial Failure

SSE
```

---

# 185. JQ2 验收

运行：

```text
20 Shot Scene
```

其中：

```text
3 个 Video 网络超时
```

系统：

```text
自动 Retry

其他 Shot 不停止

最终 19 success / 1 failed
```

Job：

```text
PARTIAL_FAILED
```

---

# 186. Phase JQ3

增加：

```text
Pause

Resume

Cancel

Interrupted Recovery

Provider Reattach
```

---

# 187. JQ3 验收

Scene：

```text
30 / 60 Tasks
```

强制关闭 Studio。

重新打开：

```text
30 个完成结果仍存在
```

Job：

```text
INTERRUPTED / PAUSED
```

用户：

```text
Resume
```

只执行剩余任务。

---

# 188. Phase JQ4

增加：

```text
Episode Job

Snapshot Context

Provider Health

Circuit Breaker

Cost

Storage Maintenance Job
```

进入完整 Alpha。

---

# 189. Codex 第一批任务

```text
Task 01
实现 Job Domain

Task 02
实现 JobTask Domain

Task 03
实现 TaskDependency

Task 04
实现 JobRepository

Task 05
实现 JobPlanner Interface

Task 06
实现 Scene Job Planner

Task 07
实现 DAG Validation

Task 08
实现 Persistent Task Queue

Task 09
实现 Scheduler

Task 10
实现 Generation Task Executor
```

---

# 190. Codex 第二批任务

```text
Task 11
实现 Job Progress

Task 12
实现 Job Finalizer

Task 13
实现 Worker Pool

Task 14
实现 Resource Semaphore

Task 15
实现 ComfyUI Resource Slot

Task 16
实现 Task Priority

Task 17
实现 Retry Policy

Task 18
实现 Retry Backoff

Task 19
实现 Failed Task Retry API

Task 20
实现 SSE Job Events
```

---

# 191. Codex 第三批任务

```text
Task 21
实现 Pause

Task 22
实现 Resume

Task 23
实现 Cancel

Task 24
实现 CancellationToken

Task 25
实现 Interrupted State

Task 26
实现 Startup Recovery

Task 27
实现 ComfyUI Execution Reattach

Task 28
实现 Remote Provider Recovery

Task 29
实现 Partial Failure

Task 30
实现 Scene Batch Generation UI Query
```

---

# 192. Codex 第四批任务

```text
Task 31
实现 Episode Job Planner

Task 32
实现 Batch Context Snapshot

Task 33
实现 Provider Health Gate

Task 34
实现 Circuit Breaker

Task 35
实现 Job Cost Summary

Task 36
实现 Job Statistics

Task 37
实现 Queue Maintenance

Task 38
实现 Stuck Job Detection

Task 39
实现 Job Cleanup Policy

Task 40
实现 Scheduler Integration Tests
```

---

# 193. 必须测试的场景

至少：

```text
正常生成

单 Task 失败

自动 Retry

Retry 后成功

Retry 全失败

Image 失败导致 Video Skip

Scene Partial Failure

Pause

Resume

Cancel

应用强制关闭

启动 Recovery

ComfyUI Disconnect

ComfyUI Recover

重复点击 Generate

高优先级 Shot 插队
```

---

# 194. 关键集成测试

## Test A

```text
Shot01 Image ✓
Shot01 Video ✓
```

Job：

```text
COMPLETED
```

---

## Test B

```text
Image FAILED
```

Video：

```text
SKIPPED
DEPENDENCY_FAILED
```

---

## Test C

Video 第一次：

```text
TIMEOUT
```

第二次：

```text
SUCCEEDED
```

Task：

```text
SUCCEEDED
retryCount = 1
```

Generation：

```text
Gen100 FAILED
 ↓
Gen101 SUCCEEDED
```

---

## Test D

Scene 20 Shot，

第 12 Shot 失败。

结果：

```text
其他 Shot 继续
```

Job：

```text
PARTIAL_FAILED
```

---

## Test E

执行到：

```text
17 / 40
```

Kill Backend。

重新启动：

```text
17 个结果保留

RUNNING Task → INTERRUPTED

Job 可 Resume
```

---

# 195. 调度系统禁止事项

## 禁止 1

```text
Queue 只存在内存。
```

---

## 禁止 2

```text
一个 Scene 使用一个长事务。
```

---

## 禁止 3

```text
一个失败 Shot 停掉整个 Scene。
```

除非 Job 明确：

```text
FAIL_FAST
```

---

## 禁止 4

```text
Retry 修改历史 Generation。
```

---

## 禁止 5

```text
Worker sleep 等 Backoff。
```

---

## 禁止 6

```text
Scheduler 同时塞 100 个任务进 ComfyUI。
```

---

## 禁止 7

```text
无 Provider Progress 时伪造百分比。
```

---

## 禁止 8

```text
Pause 等于强制 Kill。
```

---

## 禁止 9

```text
应用崩溃后所有 RUNNING 直接重跑。
```

应先：

```text
Recovery / Reattach
```

---

## 禁止 10

```text
Job 与 Generation 合并。
```

---

# 196. 最终核心执行链

```text
User
 ↓
Generate Scene
 ↓
JobPlanner
 ↓
Job
 ↓
Task DAG
 ↓
Persistent Queue
 ↓
Scheduler
 ↓
Resource Manager
 ↓
Worker
 ↓
TaskExecutor
 ↓
GenerationExecutor
 ↓
Provider
 ↓
Asset
 ↓
Task Success
 ↓
Dependency Unlock
 ↓
Next Task
 ↓
Job Finalizer
 ↓
Scene Completed / Partial Failed
```

---

# 197. 崩溃恢复链

```text
Studio Crash
 ↓
Backend Restart
 ↓
RecoveryService
 ↓
Find RUNNING Tasks
 ↓
Provider Query
 ├─ Still Running → Reattach
 └─ Unknown       → Interrupted
 ↓
Job Paused
 ↓
User Resume
 ↓
Only unfinished Tasks execute
```

---

# 198. 单 GPU 调度链

```text
Task A Image READY
Task B Video READY
Task C Image READY

        ↓

ComfyUI Slot = 1

        ↓

Task A RUNNING

B / C waiting

        ↓

A Complete

        ↓

Scheduler

        ↓

Highest Priority Next Task
```

---

# 199. Alpha 完成定义

当用户可以：

1. 对一个 30～80 Shot Episode 创建批量生成任务；
2. Image 与 Video 自动按 DAG 执行；
3. 本地 ComfyUI 自动按单 GPU 排队；
4. 云 Provider 可以按并发数执行；
5. 单个任务失败不会破坏整个 Job；
6. 网络错误可以自动 Retry；
7. 不可恢复错误会停止对应 Task；
8. 下游依赖失败时正确 Skip；
9. 用户可以暂停 Job；
10. 用户可以 Resume；
11. 用户可以 Cancel；
12. Studio 强制关闭后重新打开；
13. 已生成 Asset 不丢失；
14. 未完成 Task 可以恢复；
15. 远程运行任务可尝试 Reattach；
16. Job 可以正确显示 Completed / Partial Failed / Failed；
17. 前端能够实时接收 SSE Progress；
18. 用户进行单 Shot Regenerate 时可以优先插队；
19. Retry 每次都产生新的 Generation 历史；
20. Scene / Episode 不需要重新从头开始。

则：

> **AI 漫剧 Studio Job Queue & Generation State Machine v0.1 完成。**

---

# 200. 下一份设计文档

Job Queue 完成以后，整个 Studio 已经具备：

```text
Project

Asset

Version

Generation

Persistent Production Queue
```

下一块应该正式进入 AI 漫剧 Studio 的核心智能能力：

# 《AI Director Agent Alpha 架构详细设计 v0.2》

这次不再停留在：

```text
LLM → JSON
```

而应该真正设计：

```text
Director Graph

Script Agent

Visual Agent

Prompt Agent

Continuity Agent

Context Resolver

Structured Output

Agent Proposal

LangChain

LangGraph

Tool Calling

Project State Tools

Human Review

Agent Retry

Agent Checkpoint

Token / Cost

Prompt Versioning
```

以及最重要的一条完整 Agent 链：

```text
Novel
 ↓
Story Analysis
 ↓
Episode Planning
 ↓
Scene Planning
 ↓
Shot Planning
 ↓
Visual Specification
 ↓
Continuity Review
 ↓
Prompt Generation
 ↓
Project Domain Objects
```

这会把此前设计的 **LangChain / LangGraph** 真正接入整个 Studio，而不是作为一个孤立的 AI 聊天模块。
