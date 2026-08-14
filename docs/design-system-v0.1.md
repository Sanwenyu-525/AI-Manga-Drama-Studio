# Design System: AI Manga Drama Studio — "Director's Console"

> 本文件是 AI Manga Drama Studio 的视觉设计系统（语义设计语言），服务于 Google Stitch 屏幕生成，同时作为前端实现的视觉规范。
> 关联事实源：`frontend-ux-v0.1.md`（信息架构与交互，94 节）、`styles.css`（现有 Shell，本系统为其视觉升级版）。
> 视觉基调：**深色（Dark Studio）** · 强调色：**琥珀金（Amber Signal）** · 密度：**高（Cockpit Dense）** · 动效：**克制（Restrained）**

---

## 1. Visual Theme & Atmosphere

**"导演的监控台"（The Director's Console）** —— 一间暗房的剪辑室 / 片场监视器墙。

界面是深色、精密、信息密集的工作台：背景像暗房里的无反光黑，内容层通过**明度阶梯**（而非边框线）堆叠出深度，琥珀金像监视器上的录制灯一样只在"需要被看见"的地方亮起。

- **Density: 8/10**（Cockpit Dense）—— 专业制作工具，信息密度高但必须有清晰网格秩序，绝不拥挤混乱。
- **Variance: 6/10** —— 整体网格对称稳定（工具性），局部允许非对称（Storyboard 卡片流、Inspector 字段堆叠）。
- **Motion: 3/10** —— 动效只服务于**状态感知**：状态点呼吸、进度条流动、卡片 hover 微反馈。不做炫耀性动画，不做大段过渡。
- 氛围关键词：精密（precision）、克制（restraint）、沉浸（immersion）、专业（professional）。
- 用户的感受目标（frontend-ux §94）：**"我正在导演一部漫剧"**，而不是"我在操作一堆 AI 工具"。

---

## 2. Color Palette & Roles

深色基底 + 琥珀金单强调色。所有表面色调统一偏暖黑（warm charcoal），**禁止冷暖灰混用**。

### 表面层级（Surface Hierarchy，用明度分层代替边框）

| 名称 | 色值 | 角色 |
|---|---|---|
| **Abyss** | `#0D0F13` | 画布级背景（最深面，Workspace 背景） |
| **Panel** | `#14171D` | 面板级表面（Explorer / RightPanel / BottomDock / TopBar） |
| **Elevated** | `#1B1F27` | 卡片、输入框、悬浮层（Shot Card / Inspector 卡片） |
| **Overlay** | `#232834` | 下拉、Tooltip、Modal（再高一阶） |
| **Hairline** | `rgba(255,255,255,0.06)` | 结构性 1px 细线——**只能用于必需分隔**，优先用明度差 |
| **Ink** | `#E7EAF0` | 主文字（正文/标题，永不纯白 #FFFFFF） |
| **Muted** | `#8B93A5` | 次要文字、描述、元数据 |
| **Faint** | `#5C6472` | 三级文字、时间戳、禁用态、占位符 |

### 强调色（唯一 Accent）

| 名称 | 色值 | 角色 |
|---|---|---|
| **Amber Signal** | `#E8A33D` | 主 CTA、选中态、焦点环、进度条、活动指示（录制灯语义） |
| **Amber Hover** | `#F2B455` | Amber 的 hover 亮态 |
| **Amber Dim** | `rgba(232,163,61,0.14)` | 选中行/卡片的背景填充（如 Explorer 当前项、Inspector 当前 Shot） |
| **Amber Ink** | `#1A1409` | 琥珀色按钮上的文字（琥珀底必须配深色字，对比度与质感都优于白字） |

### 状态色（低饱和、无霓虹）

| 名称 | 色值 | 角色 |
|---|---|---|
| **Signal Green** | `#5FA86B` | 完成 / 就绪 / 在线（Shot Ready、ComfyUI Connected） |
| **Signal Red** | `#D95C5C` | 失败 / 错误 / 断开（Failed、Error 文案） |
| **Signal Blue** | `#6B8FA3` | 中性信息 / Agent 状态（Agent ●、进行中非生成类任务） |
| **Signal Amber** | `#E8A33D` | 生成中 / 警告（与 Accent 同色系，语义一致：正在发生） |

状态徽章统一为：`色点（6px 圆点，可呼吸）+ 11px 文字`，背景用 `色值 at 12% 透明度` 的圆角胶囊。

### Banned Colors

- ❌ 纯黑 `#000000`（一律用 Abyss 暖黑）
- ❌ 紫/蓝霓虹渐变（"AI Purple" 审美，与产品气质冲突）
- ❌ 高饱和 accent（饱和度 > 80%）
- ❌ 冷暖灰混用（全界面只用暖黑灰）
- ❌ 纯白文字大面积使用（用 Ink #E7EAF0）

---

## 3. Typography Rules

界面以中文为主，拉丁字符与数字为辅。

- **Latin Display / Body:** `Geist`（或回退 `Outfit`）—— 标题字重 600–700、正文 400。**Inter 禁用**。
- **Latin Mono:** `Geist Mono`（或 `JetBrains Mono`）—— **所有数字**（时长、百分比、进度、Shot 编号、时间码、版本号）必须用 Mono，强化"专业仪表"感。
- **中文:** `PingFang SC` / `Microsoft YaHei` / `Noto Sans CJK SC`（系统栈，按平台回退）。中文排版规则：
  - 正文 `14px`（0.875rem）起步，行高 `1.6`；
  - 标题层级靠**字重 + 字号**双控制（标题 600 起步），禁止只用超大字号；
  - 中文不适用 `letter-spacing` 负值（勿对中文做 track-tight）；
  - 中文数字（如"第 3 场"）中的数字仍用 Mono 风格。
- **字号阶梯：**
  - `11px`（0.6875rem）—— 元数据标签（大写 + 0.05em 间距，仅拉丁）、徽章文字
  - `13px`（0.8125rem）—— 树节点、面板字段值、时间码
  - `14px`（0.875rem）—— 正文、卡片正文
  - `16px`（1rem）—— 面板标题（字重 600）
  - `20px`（1.25rem）—— 页面标题（字重 600）
  - `32px`（2rem）—— 仪表大数字（项目统计、进度大数字，Mono，字重 500）
- **禁止：** Inter、通用衬线（Times/Georgia/Garamond）、对中文使用负字距、正文小于 13px。

---

## 4. Component Stylings

所有组件基于深色分层体系，**少线、少阴影、多明度差**。

### 按钮 Buttons
- **Primary（琥珀实心）：** 背景 `Amber Signal`，文字 `Amber Ink`，圆角 `8px`，`active` 态 `translateY(1px)` 按压反馈。无外发光、无渐变。
- **Secondary（幽灵/描边）：** 透明背景 + `Hairline` 1px 边框 + `Ink` 文字；hover 背景 `Elevated`。
- **Danger（危险操作）：** 幽灵式 + `Signal Red` 文字，hover 背景 `rgba(217,92,92,0.1)`。
- **Disabled：** 40% 不透明度，无 hover。
- 高度 ≥ 32px（桌面鼠标精度，但保持点击目标舒适）。

### Shot Card（Storyboard 核心组件，frontend-ux §10–11）
- 竖版 `9:16` 预览区（占卡片主要面积），下方元信息行。
- 卡片：背景 `Elevated`，圆角 `10px`，无阴影；**hover：1px `Amber Signal` 描边 + 微上浮（2px transform）**。
- 选中态：背景 `Amber Dim` + 琥珀描边。
- 元信息：左 `Shot 编号`（Mono 13px），右**状态徽章**；次行：景别 + 时长（Mono）。
- 预览区空态：`Abyss` 底 + 居中淡灰"待生成"构图（骨架感），非空白。

### 树 / 列表行（Explorer）
- 行高 28px，圆角 6px；hover 背景 `Elevated`；选中 = `Amber Dim` 背景 + `Amber` 文字。
- 层级缩进用 14px + 引导细线（`Hairline` 半透明）。
- 状态点（Draft ○ / Generating ◐ / Ready ● / Failed ! / Approved ◆）用状态色 6px 圆点前置。

### 输入框 / 表单
- 背景 `Elevated`（比所在面板亮一档），`Hairline` 1px 边框，圆角 8px。
- **Focus：1.5px `Amber Signal` 描边环（ring，2px offset），无外发光。**
- Label 在输入框上方（11px 大写，仅拉丁；中文标签用 12px 常规），错误文案在下方（Signal Red 12px）。无浮动 label。

### 面板结构（Inspector / AI Director / Settings）
- Inspector 字段：`11px 大写标签（Muted）` + `13px 值（Ink）`，字段间 12px 间距；高级参数区默认折叠（`Advanced Generation ▸`）。
- AI Director 状态条：状态色圆点 + 状态名（Idle / Understanding / Planning / Waiting Approval / Executing / Generating / Reviewing / Completed / Failed，frontend-ux §15）。

### AI 计划 / 审批卡（差异化组件，frontend-ux §17–20）
- **Plan Card：** `Elevated` 背景 + 左侧 3px `Amber Signal` 边条；步骤编号（Mono）+ 步骤文字；底部"预计影响：N 个镜头"（Faint）。
- **Approval Card：** `Elevated` 背景 + 1px `rgba(232,163,61,0.35)` 描边（琥珀强调，表示"需要决定"）；含预计影响清单 + 三个按钮（Primary 确认 / Secondary 只生成图片 / 幽灵取消）。
- **ChangeSet Card：** 修改分组列表，标签用状态色（Modified → Signal Blue、Merged → Signal Amber、Created → Signal Green、Deleted → Signal Red），无边框纯列表 + 明度差。
- **Diff 行：** `旧值（Muted + 删除线）→ 新值（Ink + Amber 高亮）`，Mono 显示数值。

### 生成队列（Bottom Dock，frontend-ux §30–31）
- 任务行：`Shot 编号 + 类型（Image/Video，Mono）` + 细进度条（4px 高，琥珀填充，圆角）+ 百分比（Mono 12px）。
- 状态：Queued（Faint）/ Running（Amber 进度条流动）/ Failed（Signal Red + Retry 幽灵按钮）/ Completed（Signal Green 对勾）。
- 进度条流动效果：进度填充内 2% 宽度的高光扫过（低透明度，150ms 循环）——唯一的"永久微动画"，语义 = 正在发生。

### 加载 / 空态
- **Loading：** 骨架屏（与目标布局同尺寸的 `Elevated` 圆角块 + 琥珀色 8% 透明度扫光 shimmer）。**禁止圆形 spinner。**
- **Empty State（frontend-ux §69）：** 构图式空态：居中的简单图形构图（如画框/分镜板轮廓）+ 一行引导文字 + 主按钮（如"AI 生成 Storyboard"），绝不只是"No data"。
- **Toast：** 右下角，`Overlay` 背景 + 左侧 3px 状态色边条（成功绿/失败红），10s 自动消失。

---

## 5. Layout Principles

桌面应用（Tauri），固定五区网格（frontend-ux §3、§78），**不做移动端适配**，但窗口缩小时 Dock 可折叠为状态条。

```
┌──────────────────────────────────────────────────────┐
│ TopBar 44px：项目名 · 工作区切换（Script/Storyboard/   │
│ Canvas/Assets/Timeline）· Generate · 状态点（ComfyUI/  │
│ Agent）                                               │
├──────────┬──────────────────────────┬─────────────────┤
│ Explorer │     Main Workspace       │ RightPanel 320px│
│ 240px    │   （按工作区切换）        │ Inspector /     │
│          │                          │ AI Director Tab │
├──────────┴──────────────────────────┴─────────────────┤
│ BottomDock：Timeline / Generation Queue / Agent Tasks  │
└──────────────────────────────────────────────────────┘
```

- **区域分隔靠明度差**：Explorer / RightPanel / BottomDock 用 `Panel`，Workspace 用 `Abyss`——**顶层区域间不画边框线**。
- Workspace 内（如 Storyboard 卡片流）用 `Elevated` 卡片 + 14px gap 网格：`grid-template-columns: repeat(auto-fill, minmax(170px, 1fr))`。
- Inspector 与 AI Director 为右面板双 Tab（frontend-ux §12），AI Director 常驻不丢会话（§73）。
- 禁止元素重叠、禁止绝对定位堆叠内容。
- 禁止 3 列等宽卡片陈列（Storyboard 是网格卡片流，这是它的唯一正确形态）。

### Stitch 屏幕生成约束

- 默认生成**单张 1440×900 桌面产品屏**；禁止输出手机画布、营销落地页、设备外框或多屏拼贴。
- Storyboard、AI Director、Generation Queue 等生产屏必须保留五区 Studio Shell。Project Home 与 Novel Import / Review 是受控例外，但仍共享同一 TopBar、色彩、字体和组件语言。
- 一张屏幕只表达一个可解释的生命周期状态（如 Waiting Approval、Running、Review Before Commit），禁止把互斥的 Loading、Success、Approval、Completed 状态同时堆在一屏。
- 跨区域数据必须一致：选中的 Scene / Shot、状态、进度、影响数量和版本号在 Explorer、Workspace、Inspector / AI Director、Bottom Dock 中必须互相对应。
- UI 只显示 Studio Domain 语言。禁止出现 `node_id`、ToolMessage、LangGraph 节点名、原始 Provider 异常或内部 API 字段；失败信息必须转为用户可执行的原因与恢复动作。
- 界面文案以中文为主；`Shot`、版本号、时间码、Provider 名称等稳定领域术语可以保留英文。不要把整套导航、状态和按钮做成中英混排。

---

## 6. Motion & Interaction

- **时长曲线：** 所有过渡 `150ms ease-out`；按压 `80ms`。无线性缓动、无弹性动画。
- **永久微动画（仅两处，均为"正在发生"语义）：**
  1. 生成进度条高光扫过（见 §4 生成队列，单次约 1.6s，避免高频闪烁）；
  2. 运行中状态点呼吸（透明度 60%↔100%，1.8s 循环；Generating 用 Amber，Running Agent 用 Blue）。
- 列表/网格出现：stagger `20ms` 级联，总时长 ≤ 300ms——**桌面工具不搞瀑布戏剧**。
- 只动画 `transform` / `opacity`；禁止动画 `width/height/top/left`（进度条用 transform: scaleX 实现）。
- 无自定义鼠标指针、无页面级滚动驱动动画。

---

## 7. Anti-Patterns（Banned）

- ❌ **无 emoji**（任何界面元素；现有 Shell 的 🎬 品牌标记在实现时替换为文字/图形标识）
- ❌ 无 `Inter`；无通用衬线（Times New Roman / Georgia / Garamond）；仪表盘内无任何衬线
- ❌ 无纯黑 `#000000`（用 Abyss `#0D0F13`）
- ❌ 无霓虹外发光 / 默认 box-shadow glow（阴影仅限 Overlay 层，且用暖黑 30% 以下的扩散阴影）
- ❌ 无紫/蓝霓虹渐变（"AI Purple" 审美）
- ❌ 无超过 80% 饱和度的强调色
- ❌ 无元素重叠、无绝对定位堆叠
- ❌ 无 3 列等宽特征卡（Storyboard 网格卡片流除外）
- ❌ 无圆形 loading spinner（骨架屏）
- ❌ 无假数据感文案：不用 "John Doe / Acme / Nexum" 类占位名；**本项目用真实感中文示例**：项目《最后一种打法》、角色 沈亦 / 顾言、地点 体育馆 / 教室
- ❌ 无假整数（用真实感数据：`68%`、`Shot 042`、`12/15`、`3.2s`——允许有机数字）
- ❌ 无 AI 文案陈词滥调（"Elevate / Seamless / Unleash / Next-Gen / 颠覆 / 赋能"）
- ❌ 无 "Scroll to explore / Swipe down" 类引导文案、无滚动箭头
- ❌ 无 broken 图片链接（原型中预览图用 `picsum.photos/seed/{id}/300/533` 竖版或纯色占位构图，9:16 比例）
- ❌ 无居中 Hero 式营销布局（本产品无营销页）
