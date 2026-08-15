# AI 漫剧 Studio Alpha 前端 Component / Store / API Contract 详细设计 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**定位：** Frontend Implementation Specification
**建议技术基线：**

```text
Vue 3
TypeScript
Vite
Pinia
Vue Router
```

本文不绑定 Electron / Tauri 等桌面壳实现，Studio Renderer 与桌面运行时通过独立 Adapter 隔离。

---

# 1. 本文档目标

上一阶段已经确定：

```text
Studio UX
```

这一阶段不再讨论“页面长什么样”，而是确定：

```text
页面怎么拆组件？

业务状态放在哪里？

哪个 Store 拥有什么？

API 怎么调用？

SSE 事件怎么更新状态？

Shot / Asset / Job 怎么避免重复数据？

Tabs 和 Layout 怎么恢复？

前端怎么处理 Revision Conflict？
```

最终实现目标：

```text
UX Specification
        ↓
Component
        ↓
Store
        ↓
API Contract
        ↓
Codex Task
```

---

# 2. 前端架构核心原则

Alpha 前端遵守七个原则。

### 原则一：后端才是业务状态 Source of Truth

前端不能自己推导：

```text
Asset Version

Job Final Status

STALE

MASTER

Continuity
```

这些必须以后端结果为准。

---

### 原则二：Server State 与 UI State 分离

例如：

```text
Shot
Asset
Job
Generation
```

属于 Server State。

而：

```text
Panel Width
Active Tab
Selected Node
Grid Zoom
Inspector Section
```

属于 UI State。

不能混在一起。

---

### 原则三：Entity Normalize

禁止：

```text
project
 └ episode
    └ scene
       └ shot
          └ assets
```

长期保存在一个深层 reactive Object。

采用：

```text
projectsById
episodesById
scenesById
shotsById
assetsById
```

---

### 原则四：Selection 驱动 Inspector

整个 Studio 只维护一个核心选择：

```ts
type Selection = {
  type: SelectionType
  id: string
}
```

Inspector 根据 Selection 自动解析。

---

### 原则五：SSE 不直接进入 Component

正确：

```text
SSE
 ↓
Event Dispatcher
 ↓
Store Reducer
 ↓
Component
```

禁止：

```text
ShotCard → EventSource
JobItem → EventSource
```

---

### 原则六：Workspace 组件不直接操作 API

正确：

```text
Component
 ↓
Store Action / Application Hook
 ↓
API Client
```

避免：

```text
ShotCard.vue
```

里面到处：

```ts
fetch(...)
```

---

### 原则七：生成结果永远作为新版本出现

Frontend 不假定：

```text
Generation Success
=
Active changed
```

这是后续所有 Version UX 的核心约束。

---

# 3. 前端总体分层

推荐：

```text
Presentation
     ↓
Feature / Workspace
     ↓
Store / Frontend Application
     ↓
API Client
     ↓
Backend
```

内部：

```text
src/
│
├── app/
├── router/
├── layouts/
├── workspaces/
├── features/
├── components/
├── stores/
├── services/
├── api/
├── events/
├── models/
├── adapters/
├── composables/
└── utils/
```

---

# 4. 推荐目录结构

```text
src/
│
├── app/
│   ├── App.vue
│   ├── bootstrap.ts
│   └── providers/
│
├── router/
│   └── index.ts
│
├── layouts/
│   ├── StudioShell.vue
│   ├── StudioTopBar.vue
│   ├── StudioSidebar.vue
│   ├── StudioInspector.vue
│   └── StudioBottomPanel.vue
│
├── workspaces/
│   ├── story/
│   ├── storyboard/
│   ├── shot/
│   ├── character/
│   ├── location/
│   ├── assets/
│   ├── timeline/
│   └── workflow/
│
├── features/
│   ├── project-tree/
│   ├── versioning/
│   ├── generation/
│   ├── jobs/
│   ├── agent/
│   ├── continuity/
│   ├── provenance/
│   └── command-palette/
│
├── stores/
│   ├── project.ts
│   ├── episode.ts
│   ├── scene.ts
│   ├── shot.ts
│   ├── character.ts
│   ├── location.ts
│   ├── asset.ts
│   ├── generation.ts
│   ├── job.ts
│   ├── agent.ts
│   ├── continuity.ts
│   ├── timeline.ts
│   ├── selection.ts
│   └── workspace.ts
│
├── api/
│   ├── client.ts
│   ├── project.api.ts
│   ├── shot.api.ts
│   ├── asset.api.ts
│   ├── generation.api.ts
│   ├── job.api.ts
│   ├── agent.api.ts
│   └── continuity.api.ts
│
├── events/
│   ├── sse-client.ts
│   ├── event-types.ts
│   ├── event-dispatcher.ts
│   └── reducers/
│
├── models/
│   ├── domain/
│   ├── dto/
│   ├── view/
│   └── enums/
│
└── services/
    ├── workspace-persistence.ts
    ├── notification-service.ts
    └── command-service.ts
```

---

# 5. Studio Shell Component Tree

核心：

```text
StudioShell
│
├── StudioTopBar
│
├── StudioBody
│   │
│   ├── ProjectExplorer
│   │
│   ├── EditorContainer
│   │   ├── EditorTabs
│   │   └── WorkspaceHost
│   │
│   └── InspectorHost
│
└── StudioBottomPanel
    ├── GenerationPanel
    ├── AgentPanel
    ├── ContinuityPanel
    └── ConsolePanel
```

`StudioShell` 只负责：

```text
布局

Panel Resize

Collapse

Workspace Placement
```

禁止塞：

```text
Shot Logic
Generation Logic
Agent Logic
```

---

# 6. Editor Tab 模型

建议：

```ts
interface EditorTab {
  id: string
  type:
    | 'STORY'
    | 'SCENE'
    | 'SHOT'
    | 'CHARACTER'
    | 'LOCATION'
    | 'ASSET'
    | 'TIMELINE'
    | 'WORKFLOW'

  resourceId?: string

  title: string

  closable: boolean

  dirty?: boolean
}
```

例如：

```text
Scene 05
Shot 023
沈亦
Episode 01 Timeline
```

---

# 7. WorkspaceHost

不要写：

```vue
<ShotWorkspace v-if="..."/>
<CharacterWorkspace v-if="..."/>
...
```

不断膨胀。

建议建立：

```text
WorkspaceRegistry
```

逻辑：

```text
tab.type
 ↓
Workspace Component
```

例如：

```ts
const workspaceRegistry = {
  SCENE: SceneWorkspace,
  SHOT: ShotWorkspace,
  CHARACTER: CharacterWorkspace,
  LOCATION: LocationWorkspace,
  ASSET: AssetWorkspace,
  TIMELINE: TimelineWorkspace,
}
```

---

# 8. Project Explorer Component

拆分：

```text
ProjectExplorer
│
├── ExplorerHeader
├── EpisodeTree
│   └── EpisodeNode
│       └── SceneNode
│           └── ShotNode
│
└── LibrarySection
    ├── CharactersNode
    ├── LocationsNode
    └── AssetsNode
```

---

# 9. Tree Node 不持有完整 Entity

例如：

```ts
interface ProjectTreeShotNode {
  id: string
  sceneId: string
  orderIndex: number

  label: string

  status: ShotStatus

  activeImageStatus?: AssetStatus
  activeVideoStatus?: AssetStatus

  hasError: boolean
  hasWarning: boolean
}
```

Project Tree 使用：

```text
Summary DTO
```

不要加载完整 Prompt / VisualSpec。

---

# 10. Storyboard Workspace

组件：

```text
StoryboardWorkspace
│
├── SceneToolbar
├── SceneSummary
├── ShotSelectionToolbar
└── ShotGrid
    └── ShotCard
```

`ShotCard` 只负责：

```text
Thumbnail
Shot Number
Duration
Generation Status
Stale
Selection
```

详细属性放 Inspector。

---

# 11. ShotCard Model

```ts
interface ShotCardView {
  id: string

  number: number

  thumbnailUrl?: string

  duration: number

  shotType?: ShotType

  status: ShotStatus

  imageVersion?: number
  videoVersion?: number

  imageStatus?: AssetStatus
  videoStatus?: AssetStatus

  generationRunning: boolean

  continuitySeverity?: ContinuitySeverity
}
```

---

# 12. Shot Workspace Component Tree

```text
ShotWorkspace
│
├── ShotWorkspaceHeader
│
├── MediaPreview
│   ├── ImagePreview
│   └── VideoPreview
│
├── PreviewToolbar
│
└── VersionArea
    ├── ImageVersionStrip
    └── VideoVersionStrip
```

---

# 13. MediaPreview 独立

`MediaPreview` 不应该知道：

```text
Generation

Shot API

Asset Version API
```

只接受：

```ts
interface MediaPreviewProps {
  asset?: AssetView
  mode: 'IMAGE' | 'VIDEO'
}
```

---

# 14. VersionStrip

```text
VersionStrip
│
├── VersionItem
├── VersionItem
└── VersionItem
```

每个版本显示：

```text
v4

ACTIVE

LATEST

STALE

REJECTED
```

这些标签可以组合。

---

# 15. VersionItem Model

```ts
interface AssetVersionView {
  assetId: string
  versionNumber: number

  active: boolean
  latest: boolean

  assetStatus: AssetStatus
  reviewStatus?: AssetReviewStatus

  thumbnailUrl?: string

  createdAt: string
}
```

注意：

```text
active
```

必须由后端返回。

不要：

```text
取最大版本号 = active
```

---

# 16. Inspector 架构

不要建立：

```text
右侧一个 3000 行 Inspector.vue
```

采用：

```text
InspectorHost
      ↓
InspectorRegistry
```

---

# 17. Inspector Registry

例如：

```text
SHOT
→ ShotInspector

CHARACTER
→ CharacterInspector

LOCATION
→ LocationInspector

ASSET
→ AssetInspector

GENERATION
→ GenerationInspector

TIMELINE_CLIP
→ TimelineClipInspector
```

---

# 18. ShotInspector Component Tree

```text
ShotInspector
│
├── ShotGeneralSection
├── CameraSection
├── ShotCharactersSection
├── ShotContinuitySection
├── ShotPromptSection
├── ShotGenerationSection
└── ShotOutputSection
```

每个 Section 独立组件。

---

# 19. Inspector Section 折叠状态

存到：

```text
workspaceStore
```

而不是：

```text
shotStore
```

例如：

```ts
inspectorSections: {
  SHOT: {
    general: true,
    camera: true,
    continuity: false,
    prompt: false
  }
}
```

---

# 20. Selection Store

这是整个前端最核心的 UI Store 之一。

```ts
interface SelectionState {
  current: Selection | null

  selectedShotIds: string[]
}
```

Action：

```text
select()

clear()

selectShot()

toggleShot()

selectShotRange()
```

---

# 21. 单对象与多选分开

`current`：

用于 Inspector。

```text
selectedShotIds
```

用于 Storyboard 批量操作。

不要用一个数组承担全部语义。

---

# 22. Project Store

只保存 Project 本体。

```ts
interface ProjectState {
  currentProjectId: string | null

  projectsById: Record<string, Project>

  loading: boolean
}
```

Actions：

```text
openProject()

loadProject()

updateProject()

closeProject()
```

---

# 23. Episode / Scene / Shot Store

分别：

```text
episodesById

scenesById

shotsById
```

索引：

```text
episodeIdsByProject

sceneIdsByEpisode

shotIdsByScene
```

---

# 24. Shot Store

示例：

```ts
interface ShotState {
  shotsById: Record<string, Shot>

  idsByScene: Record<string, string[]>

  loadingById: Record<string, boolean>

  inspectorCache: Record<string, ShotInspectorView>
}
```

Actions：

```text
loadShot()

updateShot()

moveShot()

duplicateShot()

archiveShot()

loadInspector()
```

---

# 25. 为什么 Inspector Cache 单独放

`Shot` Domain Object：

不包含：

```text
Generation Summary

Prompt History

Continuity Warning

Version Lists
```

这些是：

```text
Read Model
```

所以：

```text
ShotInspectorView
```

单独缓存。

---

# 26. Character Store

```text
charactersById

versionsByCharacter

detailCache
```

Actions：

```text
loadCharacters()

loadCharacter()

loadVersions()

setMaster()

generateReference()
```

---

# 27. Asset Store

这是复杂 Store。

建议结构：

```ts
interface AssetState {
  assetsById: Record<string, AssetView>

  browser: {
    ids: string[]
    cursor?: string
    hasMore: boolean
    loading: boolean
    filters: AssetFilters
  }

  versionsByGroup: Record<string, string[]>

  provenanceByAssetId: Record<string, ProvenanceView>
}
```

---

# 28. Asset Browser 不一次加载全部

使用：

```text
cursor
+
filters
```

例如：

```text
type = VIDEO
scene = scene05
status = STALE
```

修改过滤器：

清空：

```text
browser.ids
```

重新加载。

---

# 29. Generation Store

负责：

```text
generationsById

historyByTarget

activeGenerationIds
```

但不要承担 Job Queue。

---

# 30. Job Store

Job 是 Generation Panel 的主要状态源。

```ts
interface JobState {
  jobsById: Record<string, JobView>

  tasksById: Record<string, JobTaskView>

  taskIdsByJob: Record<string, string[]>

  activeJobIds: string[]

  historyCursor?: string
}
```

---

# 31. Job Store Actions

```text
loadActiveJobs()

loadJob()

loadTasks()

pauseJob()

resumeJob()

cancelJob()

retryFailed()
```

---

# 32. SSE 更新 Job Store

例如：

```text
TASK_STARTED
```

Reducer：

```text
task.status = RUNNING

job.runningTasks += ...
```

但注意：

不要在前端复杂地重新推导 Job 最终状态。

`JOB_UPDATED` / REST 仍应提供后端计算结果。

---

# 33. Agent Store

```ts
interface AgentState {
  runsById: Record<string, AgentRunView>

  proposalsById: Record<string, AgentProposalView>

  activeRunIds: string[]

  reviewQueue: string[]
}
```

Actions：

```text
planScene()

loadRun()

loadProposal()

approveProposal()

rejectProposal()

requestRevision()

resumeRun()
```

---

# 34. Continuity Store

```ts
interface ContinuityState {
  shotContinuityById:
    Record<string, ShotContinuityView>

  sceneViews:
    Record<string, SceneContinuityView>

  warningsById:
    Record<string, ContinuityWarning>

  warningIdsByScene:
    Record<string, string[]>
}
```

---

# 35. Timeline Store

```ts
interface TimelineState {
  timelinesById: Record<string, TimelineView>

  tracksById: Record<string, TimelineTrack>

  clipsById: Record<string, TimelineClip>

  trackIdsByTimeline: Record<string, string[]>

  clipIdsByTrack: Record<string, string[]>
}
```

---

# 36. Workspace Store

Workspace Store 只负责 UI：

```ts
interface WorkspaceState {
  activeWorkspace: WorkspaceType

  tabs: EditorTab[]
  activeTabId: string | null

  leftPanelWidth: number
  rightPanelWidth: number
  bottomPanelHeight: number

  leftCollapsed: boolean
  rightCollapsed: boolean
  bottomCollapsed: boolean

  bottomPanelTab:
    | 'GENERATION'
    | 'AGENT'
    | 'CONTINUITY'
    | 'CONSOLE'
}
```

---

# 37. Workspace 持久化

建议保存：

```text
每个 Project 单独 Workspace State
```

例如：

```text
workspace:{projectId}
```

内容：

```text
Tabs

Active Tab

Selection

Panel Sizes

Bottom Panel
```

---

# 38. 不持久化过多 Server State

Local Storage 不保存：

```text
shotsById
assetsById
jobsById
```

否则非常容易：

```text
数据过期
```

重启后重新从后端加载。

---

# 39. API Client 分层

推荐：

```text
HttpClient
    ↓
Domain API
    ↓
Store
```

---

# 40. HttpClient

统一处理：

```text
Base URL

Local Session Token

JSON

Timeout

Request ID

Error Parsing
```

---

# 41. Domain API

例如：

```text
projectApi

shotApi

assetApi

generationApi

jobApi

agentApi

continuityApi

timelineApi
```

---

# 42. Shot API 示例

```ts
export interface ShotApi {
  getShot(id: string): Promise<ShotDto>

  getInspector(
    id: string
  ): Promise<ShotInspectorDto>

  updateShot(
    id: string,
    request: UpdateShotRequest
  ): Promise<ShotDto>

  generateImage(
    id: string,
    request: GenerateShotImageRequest
  ): Promise<JobAcceptedDto>

  generateVideo(
    id: string,
    request: GenerateShotVideoRequest
  ): Promise<JobAcceptedDto>
}
```

---

# 43. API DTO 与 Frontend View Model 分离

不要所有后端 DTO 直接在组件里使用。

例如：

```text
ShotInspectorDto
```

可以转换：

```text
ShotInspectorView
```

通过：

```text
mapper
```

处理：

```text
Display Label

Derived Display State

Formatting
```

---

# 44. 禁止 Mapper 处理业务事实

Mapper 可以：

```text
SHOT_VIDEO → "视频"
```

但不能：

```text
version 最大 → Active
```

业务事实必须来自 Backend。

---

# 45. API Error Model

统一：

```ts
interface ApiError {
  code: string
  message: string

  requestId?: string

  details?: Record<string, unknown>
}
```

全局 Client 转换：

```text
HTTP Error
 ↓
ApiError
```

---

# 46. 错误处理分三层

### Global

```text
Backend Offline
Auth Failure
Project DB Failure
```

### Feature

```text
Generation Failed
Set Master Failed
```

### Field

```text
Invalid Duration
```

---

# 47. Revision Contract

编辑类 Request：

```ts
interface UpdateShotRequest {
  revision: number

  duration?: number
  description?: string
}
```

Backend 成功返回：

```text
revision = old + 1
```

前端替换本地 Shot。

---

# 48. 409 Conflict

统一处理：

```text
REVISION_CONFLICT
```

例如：

```text
SHOT_REVISION_CONFLICT
```

Store 不自动重试覆盖。

UI：

```text
该镜头已发生变化。

[重新加载]
```

---

# 49. Optimistic Update 策略

允许 Optimistic：

```text
Shot reorder

Timeline clip move

Panel-independent simple field
```

谨慎 Optimistic：

```text
Set Master

Activate Asset

Archive

Agent Proposal Apply
```

这些应该等待 Backend 成功。

---

# 50. 为什么 Set Master 不乐观更新

它可能影响：

```text
23 Shots
```

并触发：

```text
STALE
```

前端无法完整预测。

因此：

```text
Request
 ↓
Backend
 ↓
Response / SSE
 ↓
Update
```

---

# 51. SSE Client

全局唯一：

```text
StudioEventClient
```

生命周期：

```text
Open Project
 ↓
Connect Project SSE
```

离开 Project：

```text
Disconnect
```

---

# 52. SSE Event 类型

前端至少识别：

```text
JOB_CREATED

JOB_UPDATED

TASK_UPDATED

GENERATION_STARTED

GENERATION_SUCCEEDED

GENERATION_FAILED

ASSET_CREATED

ASSET_UPDATED

SHOT_UPDATED

CHARACTER_MASTER_CHANGED

AGENT_RUN_UPDATED

AGENT_REVIEW_REQUIRED

CONTINUITY_WARNING_CREATED

CONTINUITY_WARNING_UPDATED
```

---

# 53. Event Envelope

建议：

```ts
interface StudioEvent<T = unknown> {
  eventId: string

  projectId: string

  type: StudioEventType

  timestamp: string

  payload: T
}
```

---

# 54. Event Dispatcher

```text
SSE
 ↓
EventDispatcher
 ├── JobEventReducer
 ├── AssetEventReducer
 ├── ShotEventReducer
 ├── AgentEventReducer
 └── ContinuityEventReducer
```

---

# 55. 为什么使用 Reducer

否则：

```text
sse-client.ts
```

最后会出现：

```ts
if (...)
if (...)
switch (...)
2000 lines
```

分模块 Reducer 更容易测试。

---

# 56. GenerationSucceeded Event

处理流程：

```text
Generation succeeded
 ↓
generationStore update
 ↓
assetStore register summary
 ↓
shotStore invalidate inspector
 ↓
jobStore update
```

注意：

不能：

```text
shot.activeAsset = newAsset
```

除非 Event 明确告诉前端 Active 已变化。

---

# 57. CHARACTER_MASTER_CHANGED

Reducer：

```text
characterStore update masterVersion
```

然后：

```text
projectTree
scene
shot inspector
```

可能过期。

不要前端自行算全部 STALE。

可以：

```text
invalidate relevant queries
```

等待 Backend Event / Reload。

---

# 58. Store Cache Invalidation

建议 Store 提供：

```text
invalidateShotInspector(shotId)

invalidateSceneView(sceneId)

invalidateCharacterDetail(characterId)
```

而不是粗暴：

```text
reload entire project
```

---

# 59. Read Model Cache

每种 Read Model：

```text
data

loadedAt

loading

stale
```

例如：

```ts
interface CachedView<T> {
  data?: T

  loading: boolean

  stale: boolean

  loadedAt?: number
}
```

---

# 60. Cache 策略

Project Tree：

```text
Long-lived
+
SSE updates
```

Shot Inspector：

```text
Load on open
+
invalidate on relevant events
```

Provenance：

```text
Lazy
```

Generation History：

```text
Lazy
```

---

# 61. 页面进入不要 Reload Everything

切：

```text
Shot 23
→ Shot 24
→ Shot 23
```

如果缓存仍有效：

直接使用。

后台按需 refresh。

---

# 62. Command Layer

复杂用户操作可以通过：

```text
Frontend Command Service
```

例如：

```text
generateCurrentShot()

setCharacterMaster()

reviewAgentProposal()

replaceTimelineAsset()
```

这样 Component 不需要知道多个 Store 的组合流程。

---

# 63. 示例：Generate Current Shot

```text
ShotWorkspace
 ↓
GenerationCommandService
 ↓
shotApi.generateImage()
 ↓
JobAccepted
 ↓
jobStore.add()
 ↓
Open Generation Panel
```

---

# 64. Generate Button Component

建议做成：

```text
GenerateButton
```

复用：

```text
Shot Workspace

Storyboard Toolbar

Character Library
```

但业务参数由父 Feature 提供。

---

# 65. JobAccepted DTO

```ts
interface JobAcceptedDto {
  jobId: string

  taskId?: string

  generationId?: string

  status: JobStatus
}
```

收到后立即：

```text
jobStore
```

添加轻量 Job。

SSE 再持续更新。

---

# 66. Asset Version API Contract

Shot Image：

```text
GET
/shots/{shotId}/image-versions
```

返回：

```ts
interface ShotAssetVersionsDto {
  groupId: string

  activeAssetId?: string

  latestAssetId?: string

  versions: AssetVersionDto[]
}
```

---

# 67. Activate Version

```text
POST
/shots/{shotId}/image-versions/{assetId}/activate
```

返回：

```text
updated shot summary

updated version group
```

前端无需自己修改两个 Store。

---

# 68. Character Master Contract

```text
POST
/characters/{characterId}/versions/{versionId}/set-master
```

成功建议返回：

```ts
interface SetMasterResultDto {
  characterId: string

  previousMasterVersionId?: string

  masterVersionId: string

  affectedShotCount: number
}
```

---

# 69. Set Master Preview

更推荐增加：

```text
GET
/characters/{id}/versions/{versionId}/master-impact
```

返回：

```text
affectedShots
affectedAssets
```

Modal 先显示影响。

---

# 70. Agent API Contract

Plan Scene：

```text
POST
/scenes/{sceneId}/agent/plan-shots
```

返回：

```text
JobAccepted
```

Agent 是异步任务。

---

# 71. AgentRun View

```ts
interface AgentRunView {
  id: string

  type: AgentType

  status: AgentRunStatus

  targetType: string
  targetId: string

  currentNode?: string

  completedNodes: string[]

  waitingHuman: boolean

  proposalId?: string

  tokenUsage?: TokenUsage

  cost?: number
}
```

---

# 72. Proposal Review DTO

```ts
interface AgentProposalView {
  id: string

  proposalType: ProposalType

  status: ProposalStatus

  baseRevisions:
    Record<string, number>

  summary: string

  operations: ProposalOperationView[]

  warnings: ProposalWarning[]
}
```

---

# 73. Proposal Diff 不在 Component 即时计算全部

后端最好返回：

```text
diff
```

或者 Frontend Feature 层统一计算。

不要：

```text
ProposalReview.vue
```

里面塞大量领域比较逻辑。

---

# 74. Continuity API Contract

Scene：

```text
GET
/scenes/{sceneId}/continuity
```

返回：

```ts
interface SceneContinuityView {
  sceneId: string

  summary: ContinuitySummary

  warnings: ContinuityWarning[]

  shotStates:
    ShotContinuitySummary[]
}
```

---

# 75. Shot Continuity

```ts
interface ShotContinuityView {
  shotId: string

  startState: ContinuityResolvedState

  delta: ContinuityDelta

  endState: ContinuityResolvedState

  warnings: ContinuityWarning[]

  revision: number
}
```

---

# 76. Timeline Component Tree

```text
TimelineWorkspace
│
├── TimelineToolbar
├── TimelineRuler
├── TimelineTrackList
│   ├── VideoTrack
│   ├── VoiceTrack
│   ├── MusicTrack
│   └── SubtitleTrack
│
├── TimelinePlayhead
└── TimelinePreview
```

---

# 77. Timeline 渲染状态

不要每次拖 Clip：

直接调用后端 Render。

Timeline Edit 和：

```text
Final Render
```

分开。

---

# 78. Timeline Optimistic Update

拖 Clip：

```text
UI immediately moves
```

然后：

```text
PATCH clip
```

失败：

rollback。

这是适合 Optimistic 的场景。

---

# 79. Timeline Clip Revision

建议 TimelineClip 同样带：

```text
revision
```

避免重复拖动 / 多操作冲突。

---

# 80. Workspace Persistence Service

接口：

```ts
interface WorkspacePersistence {
  load(projectId: string): WorkspaceSnapshot | null

  save(
    projectId: string,
    snapshot: WorkspaceSnapshot
  ): void

  clear(projectId: string): void
}
```

---

# 81. Workspace Snapshot

```ts
interface WorkspaceSnapshot {
  version: number

  tabs: EditorTab[]

  activeTabId?: string

  selection?: Selection

  layout: {
    leftWidth: number
    rightWidth: number
    bottomHeight: number

    leftCollapsed: boolean
    rightCollapsed: boolean
    bottomCollapsed: boolean
  }

  bottomPanelTab: string
}
```

---

# 82. Workspace Snapshot Version

必须：

```text
version
```

因为未来 Layout Schema 会变化。

如果旧版本无法迁移：

```text
reset layout
```

不能影响 Project Data。

---

# 83. Desktop Adapter

前端不要直接到处使用：

```text
window.electron
```

或者其他 runtime API。

建立：

```text
DesktopAdapter
```

---

# 84. DesktopAdapter

负责：

```text
Open File Dialog

Reveal in Folder

Open External URL

Window Control

Native Notification
```

Workspace / Feature 只依赖：

```text
DesktopAdapter
```

---

# 85. 这样未来切桌面壳不需要重写业务 UI

结构：

```text
Frontend
   ↓
DesktopAdapter
   ├── ElectronAdapter
   └── TauriAdapter
```

Alpha 实现一个即可。

---

# 86. Thumbnail / Media URL

Asset API 不应该前端自己：

```text
resolve storage_path
```

Backend 返回：

```text
previewUrl
mediaUrl
```

前端不知道实际：

```text
C:\...
```

文件路径。

---

# 87. Virtualized Storyboard

Scene 可能几十甚至上百 Shot。

`ShotGrid` 必须从结构上允许：

```text
virtualization
```

不要在每张 ShotCard 中：

```text
watch 20 个 global store 字段
```

---

# 88. ShotCard 更新粒度

最好：

```text
ShotCard receives ShotCardView
```

只更新当前 Card 的 Summary。

避免一次 Generation Event：

```text
整个 Storyboard 100 Card 全重渲染
```

---

# 89. Asset Browser Virtualization

尤其图片数达到：

```text
1000+
```

必须：

```text
virtual grid
```

以及 Thumbnail Lazy Load。

---

# 90. Large List Key

永远：

```text
:key="asset.id"
```

不能：

```text
:key="index"
```

Shot reorder 特别重要。

---

# 91. Frontend Loading State 模型

统一：

```ts
type AsyncState =
  | 'IDLE'
  | 'LOADING'
  | 'SUCCESS'
  | 'ERROR'
```

不要每个 Store 随机：

```text
isLoading

fetching

pending

busy
```

命名不统一。

---

# 92. Mutation State

例如 Set Master：

```text
mutationByCharacterId
```

避免一个全局：

```text
loading = true
```

导致所有 Character 按钮禁用。

---

# 93. Job 不属于 Mutation Loading

用户点击：

```text
Generate Video
```

HTTP 接受成功后：

```text
button loading 结束
```

后续是：

```text
Job RUNNING
```

不能让按钮：

```text
转圈 5 分钟
```

---

# 94. Toast 与 Persistent Status

Request Accepted：

可以 Toast：

```text
Video generation queued.
```

真正失败：

留在：

```text
Generation Queue
```

中。

---

# 95. Global Project Event Indicator

TopBar 可显示：

```text
Generating 3

Review 1

Warnings 4
```

点击跳对应 Bottom Panel。

---

# 96. Command Palette 架构

不要硬编码：

```text
100 个 if
```

建立：

```ts
interface StudioCommand {
  id: string
  title: string

  keywords: string[]

  enabled(context: CommandContext): boolean

  execute(context: CommandContext): void
}
```

---

# 97. Command Registry

例如：

```text
shot.generate-image

shot.generate-video

scene.generate

scene.review-continuity

agent.plan-scene

asset.open

timeline.render
```

---

# 98. Context Menu 与 Command 共用

右键菜单不应该重复实现业务动作。

例如：

```text
Shot Context Menu
```

调用：

```text
shot.generate-video command
```

Command Palette 也调用相同 Command。

---

# 99. 这样避免三个地方行为不一致

否则容易出现：

```text
Toolbar Generate

Context Menu Generate

Command Palette Generate
```

三套不同逻辑。

---

# 100. Frontend Error Boundary

Workspace 级别应该存在 Error Boundary。

如果：

```text
Timeline Workspace
```

发生渲染异常，

不要让整个 Studio 白屏。

---

# 101. Error Boundary UI

```text
Timeline could not be displayed.

Your project data is safe.

[Reload Workspace]
```

---

# 102. Project Open State Machine

建议前端：

```text
CLOSED
 ↓
OPENING
 ↓
OPEN
```

异常：

```text
OPEN_ERROR
```

OPENING 过程：

```text
open backend project

load project

load project tree

restore workspace

connect SSE

load active jobs
```

---

# 103. 不要组件自己负责项目启动流程

由：

```text
ProjectSessionService
```

统一处理。

---

# 104. ProjectSessionService

```text
openProject()

closeProject()

recoverSession()

connectEvents()

restoreWorkspace()
```

---

# 105. Close Project

流程：

```text
persist workspace

disconnect SSE

clear project-specific caches

close backend project
```

---

# 106. Project-specific Store Reset

每个 Store 提供：

```text
resetProjectState()
```

避免打开 Project B 后仍混入：

```text
Project A assets
```

---

# 107. API Contract 版本

Frontend 定义：

```text
/api/v1
```

所有 API Domain Client 统一使用同一 Base。

不要在 Component 写 URL。

---

# 108. DTO 目录

推荐：

```text
models/dto/
├── project.dto.ts
├── shot.dto.ts
├── asset.dto.ts
├── job.dto.ts
├── agent.dto.ts
├── continuity.dto.ts
└── timeline.dto.ts
```

---

# 109. Domain Model 目录

```text
models/domain/
```

只放：

```text
核心稳定前端业务类型
```

例如：

```text
Shot

Asset

Character
```

---

# 110. View Model 目录

```text
models/view/
```

例如：

```text
ShotCardView

ShotInspectorView

AssetCardView

JobQueueItemView
```

这些专门服务 UI。

---

# 111. Enum 统一

例如：

```text
ShotStatus

AssetStatus

GenerationStatus

JobStatus

ContinuitySeverity
```

必须集中定义。

不能组件内部：

```ts
status === "finished"
```

而后端实际：

```text
SUCCEEDED
```

---

# 112. UI Label Mapper

统一：

```text
statusLabel()

shotTypeLabel()

generationTypeLabel()
```

这样以后中文化 / 国际化简单。

---

# 113. 不让 Backend 返回中文状态

Backend：

```text
MEDIUM_CLOSE_UP
```

Frontend：

```text
中近景
```

业务协议保持语言无关。

---

# 114. Testing 分层

Frontend 至少三层测试：

```text
Unit

Component

Integration
```

---

# 115. Unit Test

重点：

```text
Event Reducer

Mapper

Command Enable Logic

Store Mutation

Workspace Persistence
```

---

# 116. Component Test

重点：

```text
ShotCard

VersionStrip

JobItem

ContinuityWarning

ProposalReview
```

---

# 117. Integration Test

重点完整用户流：

```text
Generate → SSE → Version Appears
```

和：

```text
Set Master → Stale Update
```

---

# 118. 核心 Test 1

后端事件：

```text
GENERATION_SUCCEEDED
```

新：

```text
video v4
```

前端结果：

```text
VersionStrip 出现 v4 NEW

v3 仍 ACTIVE
```

---

# 119. 核心 Test 2

事件：

```text
CHARACTER_MASTER_CHANGED
```

然后 Backend 返回：

```text
Shot23 STALE
```

UI：

```text
显示 Stale
```

但：

```text
不自动调用 Generate API
```

---

# 120. 核心 Test 3

用户拖动 Shot 10 → Shot 4。

前端：

```text
Optimistic Move
```

API 失败：

```text
恢复原位置
```

---

# 121. 核心 Test 4

用户编辑 Shot：

revision：

```text
10
```

Backend 返回：

```text
409
currentRevision = 11
```

前端：

```text
Reload
```

不能静默覆盖。

---

# 122. 核心 Test 5

Agent：

```text
WAITING_HUMAN
```

SSE：

```text
AGENT_REVIEW_REQUIRED
```

前端：

```text
Review Badge + Agent Panel
```

---

# 123. 核心 Test 6

SSE Disconnect。

前端：

```text
自动 Reconnect
```

成功后：

```text
reload active jobs
```

最终 UI 与后端一致。

---

# 124. Frontend Phase FE1 — Foundation

实现：

```text
Application Bootstrap

Router

Studio Shell

Workspace Store

Selection Store

Project Session

API Client

Project Store

Project Tree
```

---

# 125. FE1 完成条件

用户可以：

```text
打开 Project

看到 Project Tree

选择 Scene / Shot

打开 Editor Tab

调整 Panel

重启恢复 Layout
```

---

# 126. Phase FE2 — Shot Editing

实现：

```text
Scene Store

Shot Store

Storyboard Workspace

Shot Workspace

Inspector Registry

Shot Inspector

Shot Update

Shot Reorder
```

---

# 127. Phase FE3 — Asset / Version

实现：

```text
Asset Store

Media Preview

Version Strip

Active Version

Asset Browser

Character Library

Location Library

Set Master

STALE UI
```

---

# 128. Phase FE4 — Production Runtime

实现：

```text
SSE Client

Event Dispatcher

Job Store

Generation Store

Generation Panel

Pause

Resume

Retry

Cancel

Provider Status
```

---

# 129. Phase FE5 — AI Director

实现：

```text
Agent Store

Agent Panel

Proposal Review

Proposal Diff

Human Review

Agent Resume

Conflict UI
```

---

# 130. Phase FE6 — Continuity

实现：

```text
Continuity Store

Continuity Inspector

Warning Panel

State Diff

Fix Proposal
```

---

# 131. Phase FE7 — Timeline

实现：

```text
Timeline Store

Tracks

Clips

Drag

Trim

Replace Version

Preview

Render UI
```

---

# 132. Codex 开发任务第一批

```text
F001
初始化前端 Feature-first 目录结构

F002
实现 StudioShell

F003
实现 Resizable Panels

F004
实现 WorkspaceStore

F005
实现 Workspace Persistence

F006
实现 SelectionStore

F007
实现 EditorTab Model

F008
实现 EditorTabs

F009
实现 WorkspaceRegistry

F010
实现 ProjectSessionService
```

---

# 133. 第二批

```text
F011
实现统一 HttpClient

F012
实现 ApiError

F013
实现 ProjectApi

F014
实现 ProjectStore

F015
实现 ProjectTree API

F016
实现 ProjectTreeStore

F017
实现 ProjectExplorer

F018
实现 EpisodeNode

F019
实现 SceneNode

F020
实现 ShotNode
```

---

# 134. 第三批

```text
F021
实现 SceneStore

F022
实现 ShotStore

F023
实现 SceneEditor Read Model

F024
实现 StoryboardWorkspace

F025
实现虚拟化 ShotGrid

F026
实现 ShotCard

F027
实现 Shot Multi Selection

F028
实现 Shot Reorder

F029
实现 ShotWorkspace

F030
实现 MediaPreview
```

---

# 135. 第四批

```text
F031
实现 InspectorHost

F032
实现 InspectorRegistry

F033
实现 ShotInspector

F034
实现 ShotGeneralSection

F035
实现 CameraSection

F036
实现 ShotCharactersSection

F037
实现 PromptSection

F038
实现 GenerationSection

F039
实现 Revision Conflict

F040
实现 Shot Auto Save
```

---

# 136. 第五批

```text
F041
实现 AssetStore

F042
实现 AssetApi

F043
实现 VersionStrip

F044
实现 ImageVersionStrip

F045
实现 VideoVersionStrip

F046
实现 Activate Version

F047
实现 Version Compare

F048
实现 AssetBrowser

F049
实现 AssetInspector

F050
实现 Provenance Drawer
```

---

# 137. 第六批

```text
F051
实现 CharacterStore

F052
实现 CharacterLibrary

F053
实现 CharacterDetail

F054
实现 CharacterVersionList

F055
实现 Master Impact API

F056
实现 Set Master Dialog

F057
实现 LocationLibrary

F058
实现 STALE Badge

F059
实现 Stale Explanation

F060
实现 Library Search
```

---

# 138. 第七批

```text
F061
实现 StudioEventClient

F062
实现 EventDispatcher

F063
实现 JobEventReducer

F064
实现 AssetEventReducer

F065
实现 ShotEventReducer

F066
实现 GenerationStore

F067
实现 JobStore

F068
实现 GenerationPanel

F069
实现 JobItem

F070
实现 JobTaskList
```

---

# 139. 第八批

```text
F071
实现 Retry Failed

F072
实现 Pause Job

F073
实现 Resume Job

F074
实现 Cancel Job

F075
实现 ProviderStatus

F076
实现 SSE Reconnect

F077
实现 Active Job Reload

F078
实现 Interrupted Job UI

F079
实现 Recovery Panel

F080
实现 BottomPanel 状态提示
```

---

# 140. 第九批

```text
F081
实现 AgentStore

F082
实现 AgentApi

F083
实现 AgentPanel

F084
实现 AgentRun Progress

F085
实现 ProposalReview

F086
实现 ProposalOperation Diff

F087
实现 Approve Proposal

F088
实现 Reject Proposal

F089
实现 Request Revision

F090
实现 Proposal Revision Conflict UI
```

---

# 141. 第十批

```text
F091
实现 ContinuityStore

F092
实现 ContinuityApi

F093
实现 ShotContinuitySection

F094
实现 SceneContinuityPanel

F095
实现 WarningItem

F096
实现 StateDiff

F097
实现 Ignore Warning

F098
实现 Resolve Warning

F099
实现 Continuity Fix Proposal

F100
实现 Continuity Event Reducer
```

---

# 142. 第十一批

```text
F101
实现 TimelineStore

F102
实现 TimelineWorkspace

F103
实现 TimelineTrack

F104
实现 TimelineClip

F105
实现 Timeline Drag

F106
实现 Timeline Trim

F107
实现 Clip Inspector

F108
实现 Replace Asset Version

F109
实现 Timeline Preview

F110
实现 Render Episode UI
```

---

# 143. 第十二批

```text
F111
实现 CommandRegistry

F112
实现 CommandPalette

F113
实现 Context Menu Command 复用

F114
实现 Global Search

F115
实现 Keyboard Shortcut

F116
实现 Workspace Error Boundary

F117
实现 Loading Skeleton

F118
实现 Empty States

F119
实现 Dark / Light Theme

F120
实现 Frontend Integration Test Suite
```

---

# 144. Codex 每个 Task 的标准模板

后续开发任务都应包含：

```text
Task ID

目标

涉及模块

允许修改文件

新增文件

API Contract

业务规则

状态变化

异常场景

Acceptance Criteria

Unit Test

Integration Test

禁止事项
```

例如：

```text
F046
Activate Shot Video Version
```

不能只给：

```text
实现版本切换
```

这种模糊任务。

---

# 145. Frontend Definition of Done

一个前端 Task 至少满足：

```text
TypeScript 无错误

Lint 通过

相关 Unit Test 通过

核心 Component Test 通过

无重复 API Logic

无直接 SSE Subscription

业务状态来自 Backend

Loading / Empty / Error 完整
```

---

# 146. 前端核心禁止事项

禁止：

```text
一个 studioStore 管全部状态
```

禁止：

```text
Project Tree 保存完整对象树
```

禁止：

```text
组件直接 fetch
```

禁止：

```text
组件直接 EventSource
```

禁止：

```text
前端推导 MASTER / ACTIVE / STALE
```

禁止：

```text
Generation Success 自动 Active
```

禁止：

```text
Pinia 持久化整个业务数据库镜像
```

禁止：

```text
所有错误 Toast 一闪而过
```

禁止：

```text
所有 Workspace 都用 Modal
```

禁止：

```text
为了复用组件，把所有业务逻辑塞进通用组件
```

---

# 147. 前端最终数据流

普通编辑：

```text
Component
 ↓
Store Action
 ↓
API
 ↓
Backend
 ↓
Response
 ↓
Store
 ↓
Component
```

异步生成：

```text
Component
 ↓
Command
 ↓
API
 ↓
Job Accepted
 ↓
JobStore

Backend Worker
 ↓
SSE
 ↓
EventDispatcher
 ↓
Job / Generation / Asset Store
 ↓
UI
```

---

# 148. Agent 数据流

```text
Scene Workspace
 ↓
Plan With AI
 ↓
Agent API
 ↓
Job Accepted
 ↓
AgentStore
 ↓
SSE
 ↓
WAITING_HUMAN
 ↓
Proposal Review
 ↓
Approve
 ↓
Backend Apply
 ↓
Project Tree / Shot Store Update
```

---

# 149. Version 数据流

```text
Generation Succeeded
 ↓
New Asset Version
 ↓
VersionStrip
 ↓
NEW

User Preview
 ↓
Use Version
 ↓
Backend Activate
 ↓
Shot ActiveAsset updated
 ↓
UI ★ ACTIVE
```

---

# 150. MASTER 数据流

```text
Character Version
 ↓
Set Master
 ↓
Impact Preview
 ↓
User Confirm
 ↓
Backend
 ↓
MASTER Changed
 ↓
Affected Assets STALE
 ↓
SSE
 ↓
Storyboard / Inspector Warning
```

---

# 151. Continuity 数据流

```text
Shot Delta Edit
 ↓
Continuity API
 ↓
Backend Recompute
 ↓
Warnings
 ↓
Affected Asset STALE
 ↓
SSE
 ↓
ContinuityStore
 ↓
Inspector / Scene Panel
```

---

# 152. 这份文档完成后的意义

到这里：

```text
前端 UX
```

已经正式转换成：

```text
Component

Store

API

Event

DTO

State Flow

Codex Task
```

因此已经不应该继续写更多“前端架构概念”。

下一步应该正式从：

> **Architecture Phase**

进入：

> **Development Planning Phase**

---

# 153. 下一份文档

下一份建议直接生成：

# 《AI 漫剧 Studio Alpha Codex 分阶段开发任务清单 v0.1》

这份文档不再继续设计系统，而是把目前所有设计整合成真正的工程开发计划：

```text
Phase 0
现状审查 / MVP Baseline

Phase 1
Domain + Database

Phase 2
Project / Scene / Shot Core

Phase 3
Asset / Version / Generation

Phase 4
ComfyUI Adapter

Phase 5
Job Queue

Phase 6
Studio Frontend

Phase 7
AI Director

Phase 8
Continuity

Phase 9
Timeline

Phase 10
Alpha Hardening
```

每个 Phase 会进一步拆成：

```text
Epic

Task ID

前置依赖

目标

涉及模块

交付物

验收标准

测试要求

Codex 执行顺序

Git Branch 建议
```

做到这一份后，就可以真正把文档交给 Codex：

> **按 Phase → Epic → Task 持续推进 Alpha 开发，而不是再让 Codex 自己临时猜下一步做什么。**
