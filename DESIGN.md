# Design System: DeepSeek Harness 漫剧智能体

## 0. Product Positioning

DeepSeek Harness 是核心宿主环境；“漫剧智能体”是运行在同一 Harness Shell 内的专业领域增强模式，不是独立 SaaS、不是第二个桌面应用、不是 Landing Page。

本设计系统用于 P00-P12 目标态可开发原型。当前运行版本可能尚未实现其中全部模块，原型不得被描述为当前已上线功能。

所有页面默认以 1920×1080 桌面画布设计，并在 1600×900 验证信息完整性。默认展示暗色主题。实际前端实现必须把语义颜色映射到 Harness `--dsw-alias-*` Token，以继续支持 Dark/Light 自动切换。

## 1. Visual Theme & Atmosphere

专业、克制、高密度的桌面生产软件，气质接近现代 IDE、Figma、DaVinci Resolve 与 Unreal Editor 的信息架构，但不直接复制任何产品。

- Density: 8/10，Cockpit Dense
- Variance: 5/10，受控非对称
- Motion: 4/10，克制而明确
- 以 panel、list、inspector、canvas、timeline 为主要结构
- 不使用营销式 Hero、大型 SaaS KPI 卡片或巨大宣传图
- 所有元素占据独立空间，禁止文字、图片、面板互相重叠
- 层级主要由背景、1px 边界、间距和字重表达，不依赖厚重阴影

## 2. Color Palette & Roles

### Neutral foundation

- **Abyss Canvas** (#0D1117) — 应用最底层画布，禁止使用纯黑
- **Workbench Layer** (#121821) — 主工作区与导航背景
- **Panel Layer** (#18202B) — Inspector、列表、工具面板
- **Elevated Layer** (#202A36) — 菜单、弹层、选中详情
- **Structural Border** (#2B3745) — 1px 分隔线、控件边界
- **Primary Ink** (#F0F3F6) — 主标题和主要正文
- **Secondary Ink** (#A2ADBA) — 描述、元数据
- **Tertiary Ink** (#748191) — 占位、禁用、弱辅助文字

### Single brand accent

- **Harness Blue** (#4F7DBA) — 唯一品牌强调色；只用于选中、主操作、焦点、活动连接和播放头

### Semantic state colors

以下是状态色，不是第二组品牌强调色，不得用于装饰：

- **AI Attention Orange** (#C78943) — AI 建议、需注意、待确认
- **Healthy Green** (#4D9F72) — 已完成、健康、已连接
- **Risk Red** (#C45F68) — 错误、高风险、失败
- 状态必须同时包含文字或图标，绝不能只靠颜色区分
- 禁止紫色、蓝紫渐变、霓虹、外发光、过饱和色

## 3. Typography Rules

- **Display / Headline:** Geist，中文回退 `Noto Sans SC`, `PingFang SC`, `Microsoft YaHei`, sans-serif
- **Body / Labels:** Geist，使用同一中文回退栈
- **Technical Mono:** JetBrains Mono，中文回退 `Noto Sans Mono CJK SC`, monospace
- Stitch Theme 中 headline/body/label 均选择 `GEIST`
- H1: 20px / 28px / 650
- H2: 16px / 24px / 650
- Panel title: 13px / 20px / 600
- UI body: 13px / 20px / 400
- Label: 11px / 16px / 600
- Metadata: 11px / 16px / 400
- Technical values: 11–12px mono，所有高密度数字使用等宽数字
- 正文最大行宽 65–72ch
- 仅路径、文件名、Prompt、Seed、模型 ID、版本、Shot ID、日志使用等宽字体
- 禁止 Inter、Times New Roman、Georgia、Garamond 及任何仪表盘衬线字体
- 禁止过度 ALL CAPS；通用 UI 默认简体中文

## 4. Frozen Application Shell

所有 P00-P12 屏幕共享完全相同的 Shell：

1. **Global Application Header — 52px**
   - 左：DeepSeek Harness 品牌与产品标识
   - 中：一级模式切换 `[ Harness ] [ 漫剧智能体 ]`
   - 右：运行环境、Git/通知、用户与返回 Harness 操作
   - P01-P12 默认激活“漫剧智能体”

2. **Project Context Bar — 40px**
   - 二级工作区切换 `[ 智能体工作区 ] [ 漫剧工作区 ]`
   - 同行显示“源工作区 ↔ 漫剧项目”的绑定摘要
   - 禁止使用父子目录 breadcrumb 表示两者关系

3. **Body**
   - 左侧固定 Activity Rail：188px
   - 中央模块画布：自适应
   - 右侧固定 Agent Dock：328px
   - 页面专用 Inspector 可以放在中央画布右缘，或作为 Agent Dock 中的第一个 Tab，但不得改变 Agent Dock 外壳

4. **System Status Bar — 28px**
   - 项目、索引、Provider、队列、Git、保存状态、快捷键
   - 所有页面位置和高度一致

### Frozen Activity Rail order

顺序在所有页面完全一致，不得增删、换序或改名：

1. 项目
2. 工作区
3. AI导演
4. 故事
5. 角色
6. 地点
7. 分镜
8. 工作流
9. 资产
10. 镜头
11. 提示词历史
12. 知识库
13. 连续性检查
14. 时间线
15. 生产日志
16. 设置

可以用细分组标题区分“工作台 / 创作 / 管线 / 追溯 / 系统”，但不能改变上述顺序。

## 5. Layout & Spacing

- 基础间距：4 / 8 / 12 / 16 / 24 / 32px
- Panel 内边距：12–16px
- Panel gap：8–12px
- 表格行高：34–38px
- 工具栏高度：38–42px
- 桌面按钮视觉高度：32–36px；主操作至少 36px
- 移动端或触摸模式命中区至少 44px
- Panel 圆角 8px；输入框和按钮 6–8px；状态胶囊可全圆
- Cards 只在真正需要 elevation 时使用；高密度页面优先用边界、分区和负空间
- 禁止三个等宽大卡片横排
- 使用清晰的 CSS Grid 语义，不使用百分比 `calc()` 拼布局
- 所有全高区域使用 `min-height: 100dvh`，不使用 `h-screen`

## 6. Component Styling

- **Buttons:** 平面、无发光；主按钮 Harness Blue；按下 `translateY(1px)` 或 `scale(.98)`
- **Icon Buttons:** 线性 SVG，24 viewBox，1.8px 描边；禁止 emoji
- **Panels:** 1px Structural Border，几乎无阴影；只有弹层使用轻微染色阴影
- **Inputs:** 标签在上，错误信息在下，不使用 floating label
- **Tabs:** 紧凑横向标签，选中态使用蓝色文字 + 2px 下划线或浅蓝底，不能两种同时过强
- **Status Badge:** 图标/文字/颜色三者中至少使用两项
- **Shot Card:** 预览、Shot ID、时长、版本、来源、资产/角色、Prompt、生成状态
- **Asset Card:** 资产名称、类型、主版本、锁定、一致性、引用镜头
- **Inspector Section:** 标题、可折叠内容、字段组；不使用大卡片套大卡片
- **Agent Proposal:** 建议、原因摘要、影响范围、预览/应用/忽略；不能展示私有思维链
- **Loading:** 与最终布局同尺寸的骨架 shimmer，禁止圆形 spinner
- **Empty State:** 明确下一步操作，不能只写“暂无数据”
- **Error:** 就地说明错误、影响和恢复操作
- **Modal / Drawer / Tooltip:** 保持同一暗色层级、1px 边界和 8px 圆角

## 7. State Language

统一使用：

- 等待
- 排队中
- 运行中
- 已完成
- 失败
- 需要审核
- 已忽略
- 已锁定
- 已保存
- 有未保存修改

允许按场景补充“已取消 / 修复中 / 已修复”，但同一含义不能出现多个近义词。

## 8. Motion & Interaction

- 默认 spring：stiffness 100，damping 20
- 普通反馈 160–220ms，不使用 linear easing
- 列表首次出现使用 20–40ms 级联延迟
- 运行中节点、生成任务、活动 Agent 使用低幅度 opacity pulse，约 1.2s，禁止霓虹呼吸
- 列表和面板不能持续漂浮
- 仅动画 `transform` 与 `opacity`
- `prefers-reduced-motion` 时关闭非必要动效
- 所有可交互控件有清晰 hover、focus-visible、active、disabled 状态
- 禁止自定义鼠标光标

## 9. Responsive Rules

原型主验收为 1920×1080 和 1600×900。

低于 768px 时：

- 多列折叠单列
- Activity Rail 变抽屉
- Agent Dock 和 Inspector 变底部抽屉
- 时间线、工作流提供缩放或分段视图
- 不能出现页面级水平滚动
- 正文最小 14px
- 触控目标最小 44px

## 10. Demo Data Contract

所有屏幕仅使用：

- 项目：《篮球少年》
- 主角：沈亦
- 源工作区：`D:\Novel\BasketballLegend`
- 漫剧项目：《篮球少年》AI漫剧 · Season 1
- 常用镜头：Episode 01 / Scene 03 / Shot 012
- 角色资产：沈亦_V12
- 场景资产：NBA球馆_V5
- Prompt：PV11 → PV12
- Shot 输出版本：V4 → V5
- 模型：DeepSeek / GPT Image / MiniMax H3 / ComfyUI
- 场景：高中球馆、训练馆、NCAA 球馆、NBA 球馆

Chapter 12 的源文件变化可以影响 Episode 03 / Scene 04 / Shot 021–034。
Shot 012 的连续性示例统一为 Shot 012 右手持球、Shot 013 错误变为左手。

禁止出现赛博朋克、武士刀、机械眼、科幻武器、魔法角色和无关项目名。

## 11. Traceability Contract

所有生成相关页面尽量显示并能跳转：

Source → Story/Script → Episode/Scene/Shot → Asset → Prompt → Model → Workflow → Agent → Generation → Version → Output → Review/Fix

生成结果不得只显示图片或视频而没有来源、Prompt、模型或版本。

## 12. Anti-Patterns — NEVER DO

- 不使用 emoji
- 不使用 Inter
- 不使用纯黑 #000000
- 不使用紫色或蓝紫霓虹
- 不使用外发光
- 不使用大面积渐变文字
- 不使用三个等宽大卡片
- 不使用巨大营销式预览
- 不使用居中 Landing Page Hero
- 不使用自定义鼠标
- 不使用通用英文 UI
- 不使用 “Elevate / Seamless / Unleash / Next-Gen” 等 AI 营销文案
- 不使用 John Doe、Acme、Nexus 等假数据
- 不使用 99.99%、50% 等无依据假数字
- 不使用 “Scroll to explore” 或滚动箭头
- 不让文字和图像重叠
- 不使用损坏的外链图片

