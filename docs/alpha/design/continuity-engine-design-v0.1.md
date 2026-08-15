# AI 漫剧 Studio Continuity Engine 详细设计 v0.1

**文档状态：** Draft
**阶段：** MVP → Alpha
**上游文档：**

* 《AI 漫剧 Studio Alpha 阶段架构与迭代规划 v0.1》
* 《AI 漫剧 Studio 核心领域模型详细设计 v0.1》
* 《AI 漫剧 Studio 数据库 Schema 与数据关系设计 v0.1》
* 《AI 漫剧 Studio Asset / Generation / Version 系统详细设计 v0.1》
* 《AI 漫剧 Studio Job Queue & Generation State Machine 详细设计 v0.1》
* 《AI Director Agent Alpha 架构详细设计 v0.2》

**目标：**

建立 AI 漫剧 Studio 的连续性引擎，使：

```text
Scene 01 / Shot 01
        ↓
Shot 02
        ↓
Shot 03
        ↓
Shot 04
```

不再是互相独立生成的四段 AI 内容，而是共享同一套：

```text
角色身份
角色版本
服装
道具
位置
朝向
动作
时间
地点
环境
伤势
情绪
镜头空间关系
首尾帧状态
```

最终让系统能够回答：

> **“上一镜头结束时世界是什么状态，下一镜头应该从什么状态继续？”**

---

# 1. Continuity Engine 的产品定位

普通 AI 视频生产：

```text
Prompt A
 ↓
Video A

Prompt B
 ↓
Video B
```

两个镜头之间没有真正的数据关系。

AI 漫剧 Studio 必须变成：

```text
Shot A
 ↓
End State
 ↓
Continuity Engine
 ↓
Shot B Start State
 ↓
Generation
```

因此 Continuity Engine 是：

> **连接“剧情结构”与“媒体生成”的状态桥梁。**

---

# 2. 为什么它是核心壁垒

AI 漫剧最大的问题通常不是：

```text
单个镜头不好看
```

而是：

```text
每个镜头单独都不错，
放在一起却不像同一个故事。
```

典型问题：

```text
角色变脸

服装变化

人物忽左忽右

篮球突然消失

伤口突然恢复

晚上突然变白天

场景布局变化

上一镜头向左跑，
下一镜头突然向右跑

上一镜头右手拿球，
下一镜头左手拿球
```

这些不是单纯 Prompt 优化能完全解决的。

---

# 3. Continuity Engine 核心职责

系统负责：

```text
建立状态

继承状态

修改状态

解析当前状态

检测冲突

生成约束

生成 Warning

关联 Asset

关联 Generation

影响 Prompt

影响首尾帧

影响下一 Shot
```

---

# 4. Continuity 不只是 Character Consistency

必须区分：

```text
Identity Consistency
```

和：

```text
Narrative Continuity
```

前者：

```text
这个人还是不是沈亦？
```

后者：

```text
沈亦上一镜头右手拿篮球，
这一镜头为什么篮球突然没了？
```

Continuity Engine 重点解决第二类。

---

# 5. 连续性五层模型

建议将连续性分成五层：

```text
L1 Identity
L2 Appearance
L3 World State
L4 Action State
L5 Cinematic State
```

---

# 6. L1 Identity Continuity

关注：

```text
Character ID

Character Version

Location ID

Prop ID
```

例如：

```text
沈亦必须始终是 character_shenyi
```

---

# 7. L2 Appearance Continuity

关注：

```text
Character Master Version

服装

发型

身材

伤势

汗水

污渍

配饰

道具外观
```

---

# 8. L3 World State

关注：

```text
地点

时间

天气

灯光

环境状态

场景破坏状态

人物在场情况

道具位置
```

---

# 9. L4 Action State

关注：

```text
人物动作

动作阶段

手持物

身体朝向

移动方向

速度

坐 / 站 / 跑

互动关系
```

---

# 10. L5 Cinematic State

关注：

```text
屏幕方向

180°轴线

视线方向

Camera Side

Shot Size

Last Frame Composition

Next Frame Entry Direction
```

Alpha 第一版优先实现：

```text
L1
L2
L3
部分 L4
```

L5 先做基础。

---

# 11. 核心模型

Continuity Engine 建议围绕：

```text
SceneContinuityProfile

ContinuityState

ContinuityDelta

ContinuityRule

ContinuityWarning

ContinuitySnapshot
```

展开。

---

# 12. 状态组织方式

推荐：

```text
Scene Base State
        ↓
Shot 01 Delta
        ↓
Resolved Shot 01 State
        ↓
Shot 02 Delta
        ↓
Resolved Shot 02 State
        ↓
Shot 03 Delta
```

而不是：

```text
每个 Shot 保存一份完整世界状态
```

---

# 13. 为什么使用 Base + Delta

例如：

Scene：

```text
地点 = 篮球馆
时间 = 晚上
服装 = 白色7号球衣
```

连续 20 个 Shot 都一样。

如果每个 Shot 重复保存：

```text
篮球馆
晚上
白色7号
```

会造成：

```text
大量重复

修改困难

状态冲突

数据维护复杂
```

所以采用：

```text
Base State + Delta
```

---

# 14. Scene Base State

定义：

> Scene 开始时默认成立的世界状态。

例如：

```json
{
  "location": "gym_01",
  "timeOfDay": "NIGHT",
  "characters": {
    "shenyi": {
      "costume": "white_uniform_7",
      "physicalState": "NORMAL"
    },
    "coach": {
      "costume": "coach_tracksuit"
    }
  }
}
```

---

# 15. Shot Delta

表示：

> 当前 Shot 相对于上一状态发生了什么变化。

例如：

```json
{
  "characters": {
    "shenyi": {
      "position": "left_wing",
      "emotion": "focused",
      "holding": {
        "rightHand": "basketball_01"
      }
    }
  }
}
```

---

# 16. 下一 Shot Delta

例如 Shot 02：

```json
{
  "characters": {
    "shenyi": {
      "action": "passes_ball",
      "holding": {
        "rightHand": null
      }
    },
    "coach": {
      "holding": {
        "leftHand": "basketball_01"
      }
    }
  }
}
```

于是篮球不是：

```text
消失
```

而是：

```text
沈亦 → 教练
```

---

# 17. ContinuityState

推荐领域模型：

```text
ContinuityState
{
    id

    projectId

    scopeType
    scopeId

    parentStateId

    characterStates

    propStates

    environmentState

    temporalState

    cinematicState

    createdAt
    updatedAt
}
```

---

# 18. ScopeType

```text
SCENE_BASE

SHOT_START

SHOT_END

SNAPSHOT
```

Alpha 简化可以：

```text
SCENE
SHOT
```

但领域层最好明确：

```text
Start
End
```

语义。

---

# 19. 为什么需要 Shot Start / End

视频镜头不是静态状态。

例如：

```text
Shot 23 Start:
沈亦拿球
```

镜头结束：

```text
Shot 23 End:
篮球传给赵承泽
```

下一 Shot 应继承：

```text
Shot 23 End
```

而不是：

```text
Shot 23 Start
```

---

# 20. 推荐进一步建模

```text
ShotContinuity
{
    shotId

    startStateId

    endStateId

    delta
}
```

---

# 21. Alpha 第一版实现策略

为减少复杂度：

数据库继续保留：

```text
continuity_states
```

但业务层区分：

```text
START
END
```

通过：

```text
state_type
```

实现。

---

# 22. CharacterState

```text
CharacterState
{
    characterId

    characterVersionId

    costumeId

    locationZone

    position

    orientation

    screenPosition

    pose

    action

    emotion

    physicalState

    holding

    relationships

    visibility
}
```

---

# 23. Character Version

必须记录：

```text
characterVersionId
```

例如：

```text
沈亦 v4
```

如果 Scene 中途不换形象：

后续 Shot 默认继承。

---

# 24. Costume State

例如：

```text
costumeId = white_uniform_7
```

状态变化必须有：

```text
Change Reason
```

例如：

```text
换衣室换装
```

而不是 Agent 任意切换。

---

# 25. Costume Transition

允许：

```text
Shot 12
White Uniform
```

↓

Scene Change：

```text
更衣室
```

↓

```text
Shot 20
Training Suit
```

但系统必须存在：

```text
explicit change
```

---

# 26. PhysicalState

建议：

```text
NORMAL

SWEATING

TIRED

INJURED

WET

DIRTY

BLOODY
```

但实际使用：

```text
structured state + metadata
```

例如：

```json
{
  "fatigue": 0.8,
  "sweating": true,
  "injuries": []
}
```

---

# 27. Emotion

情绪不是绝对连续。

例如：

```text
FOCUSED
ANGRY
SURPRISED
```

可以快速变化。

所以 Emotion 的 Continuity Rule：

```text
Soft
```

而 Costume：

```text
Strong
```

---

# 28. Position

Position 不建议一开始使用：

```text
真实 3D 坐标
```

Alpha 可以使用：

```text
semantic position
```

例如：

```text
LEFT_WING

RIGHT_WING

CENTER_COURT

BENCH

DOORWAY

DESK
```

---

# 29. LocationZone

一个 Location 内进一步定义区域：

```text
Gym
├── Court
├── Bench
├── Entrance
├── Stands
└── Tunnel
```

Scene 内人物：

```text
locationZone = COURT
```

---

# 30. 为什么需要 LocationZone

否则：

上一 Shot：

```text
人物在球场中央
```

下一 Shot：

```text
突然出现在观众席
```

数据库只看：

```text
location = Gym
```

会认为正常。

---

# 31. Orientation

推荐：

```text
LEFT

RIGHT

FORWARD

BACK

TOWARD_TARGET
```

或：

```text
towardCharacterId
```

---

# 32. ScreenPosition

用于画面连续性：

```text
SCREEN_LEFT

SCREEN_CENTER

SCREEN_RIGHT
```

例如：

上一镜：

```text
沈亦 = LEFT
教练 = RIGHT
```

下一镜突然：

```text
沈亦 = RIGHT
教练 = LEFT
```

可能跳轴。

---

# 33. ActionState

建议：

```text
actionType

phase

target

direction
```

例如：

```json
{
  "actionType": "PASS_BALL",
  "phase": "END",
  "targetCharacterId": "coach"
}
```

---

# 34. Action Phase

推荐：

```text
START

IN_PROGRESS

END
```

这对：

```text
动作跨镜头
```

特别重要。

---

# 35. 跨镜头动作

例如：

Shot 23：

```text
沈亦起跳
```

End：

```text
JUMP
phase = IN_PROGRESS
```

Shot 24：

必须：

```text
落地
```

或者：

```text
仍然处于空中
```

不能：

```text
突然坐在板凳上
```

---

# 36. PropState

```text
PropState
{
    propId

    holderCharacterId

    locationZone

    position

    state

    visibility
}
```

---

# 37. Basketball 示例

```json
{
  "propId": "basketball_01",
  "holderCharacterId": "shenyi",
  "position": "RIGHT_HAND",
  "state": "NORMAL"
}
```

---

# 38. Prop Ownership vs Holder

区分：

```text
owner
```

和：

```text
holder
```

例如篮球属于：

```text
球队
```

但当前：

```text
沈亦拿着
```

Continuity 主要关注：

```text
holder
```

---

# 39. Prop Visibility

一个道具：

```text
存在
```

但不一定：

```text
出现在镜头中
```

所以：

```text
visibility
```

和：

```text
existence
```

分开。

---

# 40. EnvironmentState

```text
EnvironmentState
{
    locationId

    locationVersionId

    lighting

    weather

    crowdState

    environmentChanges

    damageState
}
```

---

# 41. Location Version

与 Character 类似：

```text
Gym MASTER v2
```

Shot 实际绑定：

```text
locationVersionId = v2
```

MASTER 更新后：

相关生成 Asset：

```text
STALE
```

---

# 42. Lighting

建议：

```text
DAYLIGHT

SUNSET

NIGHT

COOL_INDOOR

WARM_INDOOR

STADIUM_LIGHT
```

也允许：

```text
custom description
```

---

# 43. Weather

例如：

```text
CLEAR

RAIN

SNOW

FOG
```

户外连续性重要。

---

# 44. CrowdState

体育漫剧尤其需要：

```text
EMPTY

SPARSE

HALF_FULL

FULL

CHAOTIC
```

上一镜满场观众，

下一镜背景空无一人，

是典型 AI 问题。

---

# 45. Environment Change

例如：

```text
篮球馆灯熄灭
```

需要显式：

```text
environmentChanges
```

而不是直接改：

```text
lighting
```

没有来源。

---

# 46. TemporalState

```text
TemporalState
{
    storyTime

    timeOfDay

    elapsedSinceSceneStart

    temporalRelation
}
```

---

# 47. Story Time

不一定需要真实时间戳。

可以：

```text
2046-12-03 20:30
```

或者：

```text
MATCH_Q4_02_31
```

---

# 48. Elapsed Time

Shot：

```text
duration = 4s
```

并不代表故事世界只经过 4 秒。

需要区分：

```text
Screen Duration
```

和：

```text
Story Time
```

Alpha 可以暂时简单处理。

---

# 49. Temporal Relation

例如：

```text
CONTINUOUS

AFTER_5_MINUTES

NEXT_DAY

FLASHBACK

MONTAGE
```

---

# 50. Scene Transition

Continuity Engine 必须知道：

```text
CONTINUOUS
```

和：

```text
TIME_SKIP
```

否则会错误要求：

```text
换衣服不能发生
```

---

# 51. ContinuityBoundary

推荐：

```text
ContinuityBoundary
{
    fromSceneId

    toSceneId

    transitionType

    carryCharacterState

    carryPropState

    carryEnvironmentState
}
```

---

# 52. TransitionType

```text
CONTINUOUS

TIME_SKIP

LOCATION_CHANGE

FLASHBACK

DREAM

MONTAGE

HARD_RESET
```

---

# 53. HARD_RESET

例如：

```text
下一天
+
完全不同地点
```

多数视觉状态不继承。

---

# 54. CONTINUOUS

例如：

```text
Scene 05A
篮球馆球场
```

↓

```text
Scene 05B
篮球馆球员通道
```

人物：

```text
服装
伤势
汗水
道具
```

继续继承。

---

# 55. Continuity Inheritance Policy

不同字段继承策略不同：

```text
Character Identity → ALWAYS

Costume → DEFAULT

Injury → DEFAULT

Emotion → WEAK

Position → SAME_SCENE

Location → SCENE_DEFINED

Weather → DEFAULT

Prop Holder → DEFAULT
```

---

# 56. InheritancePolicy

建议：

```text
ALWAYS

SCENE

SOFT

NONE
```

---

# 57. State Resolver

核心：

```text
ContinuityStateResolver
```

职责：

```text
loadSceneBase()

loadPreviousEndState()

applyDelta()

resolveShotStart()

resolveShotEnd()
```

---

# 58. Resolve Shot Start

流程：

```text
Scene Base
   +
Previous Shot End
   +
Current Shot Explicit Overrides
   =
Shot Start State
```

---

# 59. Resolve Shot End

```text
Shot Start
   +
Shot Action Delta
   =
Shot End
```

---

# 60. Shot 01 特例

第一个 Shot：

```text
Scene Base
+
Shot 01 Delta
```

没有 Previous Shot。

---

# 61. State Mutation

不建议直接：

```text
update previous state
```

应该：

```text
Previous State
 ↓
New State
```

保证历史可追踪。

---

# 62. Continuity Snapshot

长 Scene 有：

```text
100 Shot
```

如果每次 Resolve：

```text
Scene Base
+
1~99 Delta
```

效率太差。

所以需要：

```text
Snapshot
```

---

# 63. Snapshot Strategy

例如每：

```text
10 Shot
```

生成一次：

```text
Resolved Snapshot
```

Shot 87：

从：

```text
Shot 80 Snapshot
```

继续解析。

---

# 64. Alpha 简化

30～80 Shot 场景通常不多。

第一版可以：

```text
Scene Base
+
Previous End State
```

直接保存每个 Shot End 的 resolved state。

实际上最简单。

---

# 65. 推荐 Alpha 数据结构

每个 Shot 保存：

```text
StartResolvedState

EndResolvedState

Delta
```

优点：

```text
查询快

Context 快

调试简单
```

缺点：

```text
有一定重复
```

Alpha 可接受。

---

# 66. 后期优化

Beta 再演进：

```text
Base + Delta + Snapshot
```

不必 Alpha 过度优化。

---

# 67. ContinuityRule

定义：

> 对连续状态的一项可执行检查规则。

例如：

```text
COSTUME_CHANGED_WITHOUT_TRANSITION
```

---

# 68. Rule Structure

```text
ContinuityRule
{
    code

    category

    severity

    evaluator

    autoFixPolicy

    enabled
}
```

---

# 69. RuleCategory

```text
IDENTITY

APPEARANCE

PROP

LOCATION

TEMPORAL

ACTION

SPATIAL

CAMERA

ENVIRONMENT
```

---

# 70. 第一批规则

Alpha 推荐实现：

```text
CHARACTER_VERSION_CHANGED

COSTUME_CHANGED

LOCATION_CHANGED

PROP_HOLDER_CHANGED

PROP_DISAPPEARED

TIME_OF_DAY_CHANGED

WEATHER_CHANGED

INJURY_DISAPPEARED

POSITION_JUMP

ORIENTATION_FLIP
```

---

# 71. Character Version Rule

如果：

```text
Previous:
ShenYi v4
```

Current：

```text
ShenYi v5
```

且不存在：

```text
explicit transition
```

产生：

```text
ERROR
```

---

# 72. Costume Rule

如果：

```text
white_uniform
→
black_training
```

连续镜头之间：

```text
ERROR
```

如果跨：

```text
TIME_SKIP
```

则：

```text
允许
```

---

# 73. Prop Disappearance

上一镜：

```text
basketball holder = shenyi
```

当前：

```text
basketball absent
```

如果没有：

```text
pass
drop
offscreen
```

产生：

```text
ERROR
```

---

# 74. Location Change

Shot 内：

```text
Gym
→
Bedroom
```

没有 Scene Boundary：

```text
ERROR
```

---

# 75. Position Jump

上一镜：

```text
left_wing
```

下一镜：

```text
bench
```

如果：

```text
连续 2 秒
```

可能：

```text
WARNING / ERROR
```

---

# 76. Orientation Flip

上一镜：

```text
face RIGHT
```

下一镜：

```text
face LEFT
```

不一定错误。

需要结合：

```text
Camera Reverse
```

所以 Alpha：

```text
WARNING
```

而不是 ERROR。

---

# 77. Rule Engine

```text
ContinuityRuleEngine
```

输入：

```text
Previous End State

Current Start State

Scene Boundary
```

输出：

```text
ContinuityWarning[]
```

---

# 78. Deterministic First

所有能：

```text
if old != new
```

判断的问题，

先规则处理。

不要使用 LLM。

---

# 79. Continuity Agent 的角色

Agent 负责：

```text
语义合理性

剧情合理性

动作逻辑

视觉跳跃

镜头衔接质量
```

例如：

> 人物上一镜头情绪刚刚爆发，下一镜头立刻完全平静是否合理？

这更适合 Agent。

---

# 80. Rule Engine + Agent

流程：

```text
Resolve State
 ↓
Rule Engine
 ↓
Deterministic Warnings
 ↓
Continuity Agent
 ↓
Semantic Warnings
 ↓
Merge
```

---

# 81. Warning 数据模型

```text
ContinuityWarning
{
    id

    projectId

    sceneId

    shotId

    previousShotId

    ruleCode

    category

    severity

    message

    source

    status

    suggestedFix

    createdAt
}
```

---

# 82. Warning Source

```text
RULE

AGENT

USER
```

---

# 83. WarningStatus

```text
OPEN

ACKNOWLEDGED

IGNORED

RESOLVED

INVALID
```

---

# 84. Severity

```text
INFO

WARNING

ERROR

BLOCKING
```

Alpha 尽量少用：

```text
BLOCKING
```

---

# 85. BLOCKING 示例

例如：

```text
Generation 输入要求 characterVersionId
```

但状态引用：

```text
不存在 CharacterVersion
```

这不是创作警告，

是：

```text
结构错误
```

应该阻止生成。

---

# 86. ERROR 是否阻止 Generation

Alpha 默认：

```text
不阻止
```

但 UI 强提醒。

用户仍然可以：

```text
Generate Anyway
```

因为创作系统不能太死。

---

# 87. Generation Gate

可以分：

```text
VALID

WARNING

BLOCKED
```

只有：

```text
BLOCKED
```

真正不能生成。

---

# 88. SuggestedFix

例如：

```json
{
  "type": "INHERIT_PREVIOUS_COSTUME",
  "characterId": "shenyi",
  "value": "white_uniform_7"
}
```

---

# 89. Auto Fix

Alpha 只允许非常安全的：

```text
SAFE_AUTOFIX
```

例如：

当前 Costume 空值，

上一镜：

```text
white_uniform
```

系统可以自动继承。

---

# 90. 不自动修复显式变化

如果用户明确选择：

```text
black_uniform
```

系统不能偷偷改回。

只 Warning。

---

# 91. Explicit vs Inherited

所有状态字段最好知道来源：

```text
EXPLICIT

INHERITED

AGENT_INFERRED

DEFAULT
```

---

# 92. StateValue

概念：

```text
StateValue<T>
{
    value

    source

    confidence
}
```

Alpha 数据库不一定完全实现，

但业务逻辑应保留这个概念。

---

# 93. 为什么需要来源

例如：

```text
costume = white_uniform
```

可能来自：

```text
用户设置
```

或：

```text
Agent 猜测
```

两者可信度不同。

---

# 94. User Explicit 优先级最高

优先级：

```text
USER_EXPLICIT
>
DOMAIN_EXPLICIT
>
INHERITED
>
AGENT_INFERRED
>
DEFAULT
```

Agent 永远不能覆盖用户明确设定。

---

# 95. Continuity Override

用户需要：

```text
在这个 Shot 特意换衣服
```

可以：

```text
ContinuityOverride
```

并写：

```text
reason
```

---

# 96. OverrideReason

例如：

```text
TIME_SKIP

OFFSCREEN_CHANGE

DIRECTOR_INTENT

FLASHBACK

MANUAL
```

---

# 97. Continuity 与 ShotVisualSpec

ShotVisualSpec 中：

```text
character expression
action
location
```

与 Continuity State 有重叠。

必须定义：

```text
哪个是 Source of Truth？
```

---

# 98. 正确边界

```text
ContinuityState
=
事实状态
```

```text
ShotVisualSpec
=
这个镜头怎么呈现这些事实
```

---

# 99. 示例

Continuity：

```text
沈亦拿篮球
```

VisualSpec：

```text
close-up

篮球位于画面下方

沈亦看向教练
```

---

# 100. Visual Agent 不能改变事实

Visual Agent 可以决定：

```text
怎么拍
```

不能自己决定：

```text
篮球消失
```

除非通过：

```text
Proposal
```

修改剧情状态。

---

# 101. Continuity 与 Script Agent

Script Agent 决定：

```text
发生了什么
```

例如：

```text
沈亦把球传给教练
```

Continuity Engine 将其转成：

```text
Prop Holder Transition
```

---

# 102. Action Extractor

可以引入：

```text
ContinuityActionExtractor
```

将：

```text
Script / Shot Action
```

转换成结构化：

```text
State Delta
```

---

# 103. Alpha 实现

第一版：

Visual / Script Agent 直接输出：

```text
continuityDelta
```

避免额外 Agent。

---

# 104. ShotPlan Schema 扩展

建议：

```json
{
  "description": "...",
  "visualSpec": {},
  "continuityDelta": {
    "characters": {},
    "props": {}
  }
}
```

---

# 105. Director Proposal

因此一组 Shot：

不仅创建：

```text
Shot
ShotVisualSpec
```

还创建：

```text
ContinuityDelta
```

---

# 106. Continuity Apply 顺序

Apply Proposal：

```text
Create Shots
 ↓
Store Deltas
 ↓
Resolve States
 ↓
Run Rule Engine
 ↓
Create Warnings
```

---

# 107. 修改前面的 Shot

这是复杂点。

例如：

```text
Shot 10
```

改变篮球 Holder，

则：

```text
Shot 11
Shot 12
Shot 13...
```

的 resolved continuity 可能都变化。

---

# 108. Invalidation

当 Shot Delta 更新：

```text
Shot 10
```

后：

```text
Shot 10 End
+
all downstream states
```

都标记：

```text
DIRTY
```

---

# 109. ContinuityDirtyRange

可以：

```text
sceneId

fromOrderIndex
```

表示：

```text
从 Shot 10 往后重新 Resolve
```

---

# 110. Recompute

流程：

```text
Shot 10 changed
 ↓
Find Previous Valid State
 ↓
Recompute Shot 10
 ↓
Recompute 11
 ↓
Recompute 12...
 ↓
Run Rules
```

---

# 111. 是否重新生成媒体

Continuity State 改变：

不直接重新生成。

只是：

```text
Asset → STALE
```

如果该变化影响 Asset。

---

# 112. Continuity 与 ResourceDependency

例如：

```text
Shot 23 ContinuityState
 ↓
Shot Image v3
```

Generation Input 应记录：

```text
CONTINUITY_STATE
```

因此 State 更新后：

```text
Image v3 → STALE
```

---

# 113. 但不要所有 State 改动都 Stale

例如：

```text
Continuity Warning status
```

变化，

不影响图像。

需要：

```text
GenerationRelevantStateHash
```

---

# 114. Relevant State

对于 Shot Image：

```text
CharacterVersion

Costume

Position

Expression

Prop

Location

Lighting
```

影响生成。

而：

```text
warningStatus
```

不影响。

---

# 115. Continuity Hash

GenerationPlanner 可以构建：

```text
continuityContextHash
```

基于：

```text
真正进入 Generation 的连续性字段
```

---

# 116. Hash Change

如果：

```text
Old hash != New hash
```

相关 Asset：

```text
STALE
```

---

# 117. 与 Asset STALE 联动

流程：

```text
Continuity Recompute
 ↓
Generation Relevant State Changed
 ↓
DependencyService
 ↓
Affected Image
 ↓
STALE
 ↓
Affected Video
 ↓
STALE
```

---

# 118. Shot Status

如果 Active Image / Video STALE：

Shot 可以：

```text
status = STALE
```

但不要因为非 Active 历史 Asset Stale：

整个 Shot 变 STALE。

只看：

```text
Active
```

---

# 119. Continuity 与 Character MASTER

Character MASTER：

```text
v4 → v5
```

后：

Scene 当前 Shot State 可能仍：

```text
characterVersionId = v4
```

这是合法的。

---

# 120. 为什么不自动修改 Continuity State

历史 Scene 可能已经确认使用：

```text
v4
```

MASTER 变化不能偷偷改变。

---

# 121. New Shot Resolution

MASTER 更新以后：

新创建 Shot：

默认使用：

```text
v5
```

旧 Shot：

仍：

```text
v4
```

系统产生：

```text
Outdated Master Warning
```

---

# 122. Master Continuity Warning

例如：

```text
CURRENT CHARACTER VERSION = v4

PROJECT MASTER = v5
```

Warning：

```text
CHARACTER_REFERENCE_OUTDATED
```

---

# 123. 用户可以 Lock Character Version

Scene：

```text
Character Version Lock
```

例如整场比赛：

```text
沈亦 v4
```

即使 MASTER 变 v5：

该 Scene 不提示过时。

---

# 124. SceneContinuityProfile

建议：

```text
SceneContinuityProfile
{
    sceneId

    lockedCharacterVersions

    lockedLocationVersion

    defaultCostumes

    baseState

    boundaryType
}
```

---

# 125. 这种 Lock 很重要

长篇生产时：

如果制作 Episode 01 到一半，

角色 MASTER 更新，

不能让前半集：

```text
v4
```

后半集突然：

```text
v5
```

---

# 126. Episode Continuity Lock

后续也可以：

```text
EpisodeProductionSnapshot
```

冻结：

```text
Character Versions

Location Versions

Style Version
```

与 Batch Job Snapshot 一致。

---

# 127. Generation Snapshot

实际上完整生成链应使用：

```text
Production Snapshot
```

而不只是当前 MASTER。

---

# 128. First Frame / Last Frame

视频连接是 Continuity Engine 与生成模型真正连接的核心。

每个 Shot Video：

最好能提取：

```text
FirstFrameAsset

LastFrameAsset
```

---

# 129. Frame Asset

类型：

```text
SHOT_FIRST_FRAME

SHOT_LAST_FRAME
```

或者：

```text
FRAME_REFERENCE
```

并用 metadata：

```text
frameRole
```

---

# 130. 视频生成后

流程：

```text
Shot Video
 ↓
Frame Extraction
 ├── First Frame
 └── Last Frame
```

注册成：

```text
DERIVED Asset
```

---

# 131. 下一 Shot Generation

如果 Provider 支持：

```text
First Frame Control
```

则：

```text
Previous Shot Last Frame
```

可以作为：

```text
Current Shot First Frame Reference
```

---

# 132. Frame Bridge

定义：

```text
ShotTransitionBridge
{
    fromShotId

    toShotId

    strategy

    sourceFrameAssetId

    targetFrameAssetId
}
```

---

# 133. TransitionStrategy

```text
NONE

LAST_TO_FIRST

REFERENCE_ONLY

MATCH_COMPOSITION

MATCH_MOTION

MANUAL
```

---

# 134. LAST_TO_FIRST

最直接：

```text
Shot A Last Frame
         ↓
Shot B First Frame Input
```

---

# 135. 不是所有镜头都适合 LAST_TO_FIRST

例如：

```text
Wide Shot
→
Close-up
```

完全复制上一帧会限制新镜头。

此时更适合：

```text
REFERENCE_ONLY
```

---

# 136. Transition Planner

未来：

```text
ShotTransitionPlanner
```

决定：

```text
直接续帧

参考上一帧

重新构图

硬切
```

---

# 137. Alpha 第一版

先支持：

```text
NONE

REFERENCE_ONLY

LAST_TO_FIRST
```

够用。

---

# 138. Composition Continuity

上一 Shot：

```text
沈亦 SCREEN_LEFT
```

下一 Shot：

```text
沈亦 SCREEN_RIGHT
```

如果是：

```text
Reverse Shot
```

可能合理。

需要 Shot Transition Metadata：

```text
CUT_TYPE
```

---

# 139. CutType

```text
CONTINUITY_CUT

REVERSE_CUT

MATCH_CUT

JUMP_CUT

HARD_CUT

FADE

MONTAGE
```

---

# 140. Continuity Cut

需要更强空间连续性。

Jump Cut：

允许明显位置变化。

---

# 141. ShotTransition

推荐：

```text
ShotTransition
{
    fromShotId

    toShotId

    cutType

    continuityStrength

    frameStrategy

    notes
}
```

---

# 142. continuityStrength

```text
STRICT

NORMAL

LOOSE

RESET
```

---

# 143. STRICT

例如：

```text
同一个动作跨镜头
```

必须严密衔接。

---

# 144. LOOSE

例如：

```text
蒙太奇训练片段
```

可以忽略部分位置和动作。

---

# 145. RESET

例如：

```text
第二天
```

空间状态基本重置。

---

# 146. Prompt Integration

Prompt Agent 不应该只看到：

```text
ShotVisualSpec
```

还应该看到：

```text
Resolved Continuity Context
```

---

# 147. Prompt Context 示例

```text
Character:
ShenYi v4

Costume:
White #7 jersey

Current State:
Sweating
Right hand holding basketball

Screen Position:
Left

Location:
Basketball court

Previous Action:
Stopped dribbling
```

---

# 148. Prompt Constraint

Prompt Agent生成：

```text
continuityConstraints
```

例如：

```text
same white #7 jersey

basketball remains in right hand

maintain sweaty appearance

same basketball gym environment
```

---

# 149. Provider Prompt

最终：

```text
CanonicalPromptSpec
+
ContinuityConstraints
 ↓
Provider Adapter
```

---

# 150. Continuity Weight

不同字段的重要程度不同。

例如：

```text
Character identity = 1.0

Costume = 0.9

Prop = 0.9

Position = 0.6

Emotion = 0.4
```

---

# 151. ContinuityPriority

可定义：

```text
CRITICAL

HIGH

MEDIUM

LOW
```

供 Prompt Builder 控制。

---

# 152. 角色身份

```text
CRITICAL
```

---

# 153. 服装 / 道具

通常：

```text
HIGH
```

---

# 154. 情绪

```text
MEDIUM
```

甚至动态变化。

---

# 155. Background Crowd

根据场景：

```text
LOW / MEDIUM
```

---

# 156. Generation Capability

Continuity Constraints 还要考虑 Provider 能力。

例如模型只能接受：

```text
1 Reference Image
```

系统必须决定优先级。

---

# 157. Reference Selection

```text
ReferenceSelector
```

根据：

```text
ContinuityPriority
```

选择：

```text
Character Master
Previous Last Frame
Location Reference
```

谁优先。

---

# 158. 示例

模型只能两张 Reference：

```text
1. Character Reference
2. Previous Last Frame
```

Location 通过 Prompt 描述。

---

# 159. Reference Budget

Provider Capability：

```text
maxReferenceImages
```

Continuity Engine 结合：

```text
ReferenceSelector
```

处理。

---

# 160. Continuity QA

生成后不能只相信 Prompt。

可以增加：

```text
PostGenerationContinuityCheck
```

---

# 161. 第一阶段 QA

图片生成后：

人工：

```text
Approve / Reject
```

即可。

---

# 162. 第二阶段 QA

Vision Model 检查：

```text
服装

角色

关键道具

场景
```

并与 Continuity State 比较。

---

# 163. QA 不自动改

发现：

```text
篮球缺失
```

则：

```text
Asset Review Warning
```

用户可以：

```text
Regenerate
```

---

# 164. Generation Result Warning

这类 Warning 应关联：

```text
Asset
```

而不是只关联 Shot。

---

# 165. ContinuityWarning Scope

推荐：

```text
PLANNING

STATE

GENERATION_RESULT
```

---

# 166. Planning Warning

Agent 规划阶段就发现。

---

# 167. State Warning

结构化状态冲突。

---

# 168. Generation Result Warning

实际生成媒体与目标状态不一致。

---

# 169. Continuity Inspector

Shot Inspector 增加：

```text
Continuity
```

面板。

显示：

```text
Character
Costume
Location
Prop
Position
Action
Previous State
Next State
Warnings
```

---

# 170. UI 示例

```text
Continuity — Shot 023

沈亦
────────────────
Version      v4
Costume      白色7号
Position     Left Wing
Facing       Basket
State        Sweating
Right Hand   Basketball

Warnings
────────────────
⚠ Screen direction changes in Shot 024
```

---

# 171. State Diff UI

可以展示：

```text
Shot 22 → Shot 23
```

```text
Position:
Center → Left Wing

Emotion:
Calm → Focused

Basketball:
None → Right Hand
```

---

# 172. 非法变化标红

例如：

```text
Costume:
White → Black
```

没有 transition：

```text
红色 Warning
```

---

# 173. Scene Continuity View

整个 Scene 可以看到：

```text
Shot 01
  ↓
Shot 02
  ↓
Shot 03
```

状态链。

---

# 174. Prop Track

例如：

```text
Basketball

Shot01 ShenYi
Shot02 ShenYi
Shot03 Coach
Shot04 Coach
```

对体育题材非常实用。

---

# 175. Character Track

```text
沈亦

Shot01 Court
Shot02 Court
Shot03 Left Wing
Shot04 Bench
```

未来可视化。

Alpha 不必做复杂 Timeline UI。

---

# 176. API

核心：

```text
GET  /scenes/{sceneId}/continuity

GET  /shots/{shotId}/continuity

PUT  /shots/{shotId}/continuity-delta

POST /shots/{shotId}/continuity/recompute

POST /scenes/{sceneId}/continuity/recompute

POST /scenes/{sceneId}/continuity/review

GET  /scenes/{sceneId}/continuity/warnings

POST /continuity/warnings/{warningId}/ignore

POST /continuity/warnings/{warningId}/resolve
```

---

# 177. Shot Continuity Response

```json
{
  "shotId": "shot_23",
  "startState": {},
  "delta": {},
  "endState": {},
  "warnings": []
}
```

---

# 178. Update Delta

```http
PUT /shots/{shotId}/continuity-delta
```

携带：

```text
revision
```

避免用户与 Agent 冲突。

---

# 179. 更新后的链路

```text
Update Delta
 ↓
Recompute Current State
 ↓
Recompute Downstream
 ↓
Run Rules
 ↓
Update Warnings
 ↓
Compare Relevant Hash
 ↓
Mark Assets Stale
 ↓
SSE
```

---

# 180. ContinuityService

职责：

```text
resolveSceneBase()

resolveShotStart()

resolveShotEnd()

applyDelta()

recomputeFromShot()

validateState()

buildGenerationContext()
```

---

# 181. ContinuityRuleEngine

职责：

```text
evaluate()

evaluateTransition()

evaluateCharacter()

evaluateProp()

evaluateEnvironment()
```

---

# 182. ContinuityWarningService

负责：

```text
createWarning()

resolveWarning()

ignoreWarning()

invalidateOldWarnings()
```

---

# 183. ContinuityDependencyService

负责：

```text
compareRelevantState()

updateStateHash()

markGeneratedAssetsStale()
```

---

# 184. TransitionService

负责：

```text
createTransition()

resolveFrameStrategy()

validateCut()

buildNextShotReference()
```

---

# 185. ContinuityContextBuilder

提供给：

```text
Director

Visual Agent

Prompt Agent

Generation Planner
```

不同 Context。

---

# 186. Agent Context

Continuity Agent 不需要：

```text
整个 Episode
```

一般：

```text
Previous Shot
Current Shot
Next Shot
Scene Base
```

足够。

---

# 187. Prompt Agent Context

通常：

```text
Current Resolved State

Previous End State

Current Visual Spec

Reference Assets
```

---

# 188. Director Context

更高层：

```text
Scene Continuity Summary
Warnings Summary
```

而不是所有细节 JSON。

---

# 189. Continuity Summary

例如：

```text
Scene 05:
- All characters remain in gym.
- ShenYi uses white #7 uniform throughout.
- Basketball transfers from ShenYi to coach at Shot 24.
- No unresolved continuity errors.
```

---

# 190. 数据库建议扩展

`continuity_states` 增加：

```text
state_type

resolved_state_json

delta_json

relevant_hash

dirty

revision
```

---

# 191. continuity_warnings

建议正式建表：

```text
id

project_id

scene_id

shot_id

previous_shot_id

asset_id

scope

rule_code

category

severity

source

message

suggested_fix_json

status

created_at

resolved_at
```

---

# 192. shot_transitions

建议：

```text
id

scene_id

from_shot_id

to_shot_id

cut_type

continuity_strength

frame_strategy

source_frame_asset_id

notes
```

---

# 193. Scene Base

可以：

```text
continuity_states
```

中：

```text
scope_type = SCENE_BASE
```

而不再额外建表。

---

# 194. State JSON vs 强类型列

Character State 等复杂状态：

Alpha：

```text
JSON
```

合理。

但这些索引字段建议独立：

```text
scene_id

shot_id

state_type

dirty

revision
```

---

# 195. State Schema Version

JSON 必须记录：

```text
schemaVersion
```

例如：

```json
{
  "schemaVersion": 1,
  "characters": {}
}
```

否则以后字段变更很难迁移。

---

# 196. Continuity Schema Migration

不要假设 JSON 永远兼容。

升级：

```text
v1 → v2
```

时需要：

```text
ContinuityStateMigrator
```

---

# 197. Continuity Rule Version

Warning 应记录：

```text
ruleVersion
```

否则规则升级后：

旧 Warning 可能语义不同。

---

# 198. Re-evaluate Warnings

规则升级：

不必立即全项目扫描。

用户打开 Scene 或：

```text
Verify Project
```

时重新评估。

---

# 199. Continuity Lock

用户可以：

```text
Lock Shot Continuity
```

表示：

```text
Agent 不允许自动修改
```

---

# 200. Scene Lock

整个 Scene APPROVED 后：

```text
Continuity Locked
```

Agent 只能产生 Proposal。

---

# 201. Agent Revision

Continuity Agent 发现问题：

不能直接：

```text
UPDATE shot
```

输出：

```text
ContinuityFixProposal
```

---

# 202. Fix Proposal

例如：

```json
{
  "type": "CONTINUITY_FIX",
  "shotId": "shot_24",
  "changes": {
    "costumeId": "white_uniform_7"
  }
}
```

---

# 203. SAFE_AUTOFIX 特例

如果字段完全没有设置：

```text
costume = null
```

上一镜已有：

```text
white_uniform
```

可以自动继承，

因为没有覆盖用户事实。

---

# 204. 用户 Override 永远优先

如果：

```text
costume = black_uniform
source = USER
```

Agent：

```text
不能自动覆盖
```

---

# 205. Continuity 与 Version System

State 本身也存在版本语义。

Alpha 不建议建立：

```text
ContinuityStateVersion
```

而使用：

```text
revision
+
AuditLog
```

即可。

---

# 206. 为什么不做 State Version

Continuity State 是：

```text
派生 / 编辑状态
```

频繁变化。

完整 Version 会制造大量噪声。

真正媒体结果：

```text
Asset Version
```

才必须长期版本化。

---

# 207. Undo

Continuity 修改需要支持：

```text
Audit + ChangeSet
```

从而后续：

```text
Undo
```

不依赖完整 Version Entity。

---

# 208. Continuity 与 Job Queue

Recompute 本身：

Scene 只有几十 Shot 时可以：

```text
同步
```

但 Episode 级大规模：

应该：

```text
CONTINUITY_RECOMPUTE Job
```

---

# 209. Batch Review

```text
POST /episodes/{id}/continuity/review
```

创建：

```text
Job
```

多个：

```text
Continuity Agent Task
```

---

# 210. Media Result Review

后续 Vision 检查也进入：

```text
Job Queue
```

不是阻塞普通 API。

---

# 211. Alpha Phase CE1

第一阶段：

```text
Scene Base State

Shot Delta

Start / End State

Character State

Costume

Location

Prop Holder

Rule Engine
```

---

# 212. CE1 验收

10 Shot Scene：

系统能正确追踪：

```text
沈亦

服装

位置

篮球 Holder
```

并检测：

```text
无解释换衣

篮球消失
```

---

# 213. Phase CE2

增加：

```text
Dirty Range

Downstream Recompute

STALE Integration

Warning UI

Continuity Agent
```

---

# 214. CE2 验收

修改 Shot 5：

```text
篮球交给教练
```

后：

```text
Shot 6～10
```

状态自动重新计算。

相关 Active Asset：

正确：

```text
STALE
```

---

# 215. Phase CE3

增加：

```text
ShotTransition

First / Last Frame

Frame Bridge

Screen Position

Orientation

Basic Camera Continuity
```

---

# 216. CE3 验收

Shot A：

```text
Last Frame
```

能够被下一 Shot：

```text
REFERENCE_ONLY
```

或：

```text
LAST_TO_FIRST
```

使用。

---

# 217. Phase CE4

增加：

```text
Generation Result QA

Vision Review

Production Snapshot

Advanced Action Continuity
```

进入 Beta。

---

# 218. Codex 第一批任务

```text
Task 01
定义 ContinuityState Schema

Task 02
定义 CharacterState

Task 03
定义 PropState

Task 04
定义 EnvironmentState

Task 05
实现 Scene Base State

Task 06
实现 Shot Continuity Delta

Task 07
实现 Shot Start Resolver

Task 08
实现 Shot End Resolver

Task 09
实现 Continuity Repository

Task 10
实现 Continuity API
```

---

# 219. 第二批任务

```text
Task 11
实现 Costume Rule

Task 12
实现 Character Version Rule

Task 13
实现 Location Rule

Task 14
实现 Prop Holder Rule

Task 15
实现 Prop Disappearance Rule

Task 16
实现 Time Rule

Task 17
实现 Warning Model

Task 18
实现 Warning Service

Task 19
实现 Scene Continuity Query

Task 20
实现 Shot Continuity Inspector Query
```

---

# 220. 第三批任务

```text
Task 21
实现 Dirty Range

Task 22
实现 Downstream Recompute

Task 23
实现 Relevant State Hash

Task 24
实现 Asset STALE Integration

Task 25
实现 Continuity Context Builder

Task 26
接入 Director Agent

Task 27
接入 Visual Agent

Task 28
接入 Prompt Agent

Task 29
实现 Continuity Agent

Task 30
实现 Continuity Fix Proposal
```

---

# 221. 第四批任务

```text
Task 31
实现 ShotTransition

Task 32
实现 Transition Strategy

Task 33
实现 Video First Frame Extraction

Task 34
实现 Video Last Frame Extraction

Task 35
实现 Frame Reference Asset

Task 36
实现 Frame Bridge

Task 37
实现 Screen Position Rule

Task 38
实现 Orientation Rule

Task 39
实现 Transition Inspector

Task 40
建立 Continuity Integration Tests
```

---

# 222. 必须测试场景

至少：

```text
角色版本连续

角色版本突变

服装连续

无解释换装

篮球传递

篮球消失

角色移动

地点变化

时间跳跃

Scene Boundary

Flashback

伤势持续

汗水状态持续

Explicit Override

MASTER 更新

修改前序 Shot

Downstream Recompute

Asset Stale

First/Last Frame Reference

Agent Fix Proposal
```

---

# 223. Test A — Costume

Shot 01：

```text
White #7
```

Shot 02：

```text
White #7
```

结果：

```text
PASS
```

---

# 224. Test B — Costume Break

Shot 01：

```text
White #7
```

Shot 02：

```text
Black Training
```

Transition：

```text
CONTINUOUS
```

结果：

```text
ERROR
COSTUME_CHANGED
```

---

# 225. Test C — Time Skip

同样：

```text
White → Black
```

但 Scene Boundary：

```text
NEXT_DAY
```

结果：

```text
PASS
```

---

# 226. Test D — Ball Pass

Shot 10 End：

```text
Basketball
holder = ShenYi
```

Shot 11：

```text
PASS_BALL
ShenYi → Coach
```

Shot 11 End：

```text
holder = Coach
```

结果：

```text
PASS
```

---

# 227. Test E — Ball Missing

Shot 10：

```text
holder = ShenYi
```

Shot 11：

```text
basketball missing
```

无 Transition。

结果：

```text
ERROR
PROP_DISAPPEARED
```

---

# 228. Test F — Dirty Range

修改：

```text
Shot 5 Delta
```

必须：

```text
Shot 5～End
```

重新 Resolve。

Shot 1～4：

```text
不变
```

---

# 229. Test G — STALE

Active Image 使用：

```text
ContinuityHash A
```

修改 Continuity：

```text
Hash B
```

则：

```text
Image → STALE
Video → STALE
```

---

# 230. Test H — User Override

Agent 建议：

```text
White Costume
```

用户明确：

```text
Black Costume
```

系统：

```text
Warning
```

但不得自动修改用户值。

---

# 231. Test I — Scene Version Lock

Scene Lock：

```text
ShenYi v4
```

项目 MASTER：

```text
v5
```

Scene 内：

```text
继续 v4
```

不应自动升级。

---

# 232. Test J — Frame Bridge

Shot A：

```text
Last Frame Asset
```

Shot B：

```text
frameStrategy = LAST_TO_FIRST
```

GenerationInput：

必须包含：

```text
Shot A Last Frame
```

---

# 233. Continuity Engine 禁止事项

## 禁止 1

```text
只用 Prompt 文本记录连续状态。
```

---

## 禁止 2

```text
Agent Memory 作为连续性事实来源。
```

---

## 禁止 3

```text
每个 Shot 独立推断全部状态。
```

---

## 禁止 4

```text
角色 MASTER 改变自动替换历史 Shot。
```

---

## 禁止 5

```text
Continuity Warning 自动触发昂贵 Generation。
```

---

## 禁止 6

```text
所有状态变化都视为 Error。
```

---

## 禁止 7

```text
忽略 Scene Boundary。
```

---

## 禁止 8

```text
Visual Agent 可以随意改剧情事实。
```

---

## 禁止 9

```text
把人物位置一开始设计成复杂 3D 物理系统。
```

---

## 禁止 10

```text
每一个连续性问题都调用 LLM。
```

---

# 234. 最核心的数据链

```text
Scene Base State
        ↓
Shot Start State
        ↓
Shot Delta
        ↓
Shot End State
        ↓
Next Shot Start
```

与此同时：

```text
Resolved State
      ↓
Continuity Context
      ↓
Prompt Agent
      ↓
Generation
      ↓
Asset
```

---

# 235. 状态变化链

```text
User / Agent
 ↓
Update Shot Delta
 ↓
Continuity Resolver
 ↓
Downstream Recompute
 ↓
Rule Engine
 ↓
Warnings
 ↓
Relevant Hash Compare
 ↓
Dependency Service
 ↓
Asset STALE
```

---

# 236. 视频衔接链

```text
Shot A Video
 ↓
Extract Last Frame
 ↓
Frame Asset
 ↓
Transition Strategy
 ↓
Shot B Generation Input
 ↓
Shot B Video
```

---

# 237. Director 集成链

```text
Script Agent
 ↓
Narrative Action
 ↓
Visual Agent
 ↓
ShotPlan
+
ContinuityDelta
 ↓
Continuity Engine
 ↓
Warnings
 ↓
Continuity Agent
 ↓
Fix Proposal / PASS
```

---

# 238. Prompt 集成链

```text
ShotVisualSpec
+
Resolved Continuity State
+
Previous Shot End
+
Transition Strategy
 ↓
CanonicalPromptSpec
 ↓
Provider Prompt
```

---

# 239. Alpha 完成定义

当系统能够：

1. 为 Scene 建立 Base State；
2. 每个 Shot 保存结构化 Continuity Delta；
3. 自动解析 Shot Start State；
4. 自动解析 Shot End State；
5. 下一 Shot 默认继承上一 Shot End；
6. 正确追踪 CharacterVersion；
7. 正确追踪 Costume；
8. 正确追踪 Location；
9. 正确追踪关键 Prop；
10. 正确追踪 Prop Holder；
11. 正确识别无解释的道具消失；
12. 正确识别无解释换装；
13. 支持 Scene Boundary；
14. 支持 Time Skip；
15. 用户显式状态优先于 Agent；
16. 修改前置 Shot 后自动重新计算下游 State；
17. 不影响的前序 Shot 不重算；
18. Generation Relevant State 变化时正确标记 Asset STALE；
19. 不自动触发重新生成；
20. Continuity Rule Engine 可以独立于 LLM 工作；
21. Continuity Agent 可以补充语义检查；
22. Warning 有严重级别和状态；
23. Warning 可以 Ignore / Resolve；
24. Prompt Agent 能获取 Resolved Continuity Context；
25. Director ShotPlan 能同时输出 Continuity Delta；
26. Character MASTER 更新不会静默改变已确认 Scene；
27. Scene 可以锁定角色版本；
28. 视频能够提取 First / Last Frame；
29. 下一镜头可以使用上一镜头 Last Frame 作为 Reference；
30. Continuity 状态在 Studio 重启后完整存在。

则：

> **AI 漫剧 Studio Continuity Engine Alpha v0.1 成立。**

---

# 240. 到这里 Alpha 后端核心已经基本闭环

当前已经形成：

```text
Project Domain
      │
      ├── Database
      │
      ├── Asset / Version
      │
      ├── Generation
      │
      ├── Job Queue
      │
      ├── AI Director
      │
      └── Continuity Engine
```

完整核心链：

```text
Novel
 ↓
Director
 ↓
Scene
 ↓
Shot
 ↓
Continuity State
 ↓
Prompt
 ↓
Generation Plan
 ↓
Job Queue
 ↓
Provider
 ↓
Asset Version
 ↓
Continuity / STALE
```

这已经是比较完整的 **AI-native 漫剧生产后端**。

---

# 241. 下一份设计文档

下一步建议进入：

# 《AI 漫剧 Studio Alpha 前端 UX / 信息架构与交互设计 v0.1》

原因是后端领域语义已经足够稳定，现在前端可以真正围绕这些对象设计，而不是先画一个漂亮壳子。

重点应该包含：

```text
Home / Projects

Studio Shell

Project Explorer

Episode / Scene / Shot Tree

Main Canvas

Shot Editor

Inspector

Character Library

Location Library

Asset Browser

Version Browser

Generation Queue

Agent Panel

Continuity Inspector

Timeline

Bottom Panel

Command Palette

Context Menu

MASTER / ACTIVE / STALE UI

Human Review

Agent Proposal Diff

Job Progress

错误 / Retry / Resume

桌面窗口布局

多 Panel Resizable Layout

Light / Dark Theme

Studio 状态保存
```

这份完成后，就能进一步拆成：

> **前端页面 + Component Tree + Store + API Contract + Codex 开发任务。**
