# P3 一致性引擎预研报告 — 角色参考图注入与相似度回归

> Sprint 04 §6 第 4 条预研授权的交付物 · 2026-08-31
> 事实源：代码盘点（backend/frontend/workflows）+ 文档盘点（Sprint 04 报告 / backlog / phase-4-advanced / database / 契约 / alpha 设计）+ 外部技术调研（2026-08）

---

## 0. 结论（TL;DR）

1. **机制缺口被实证**：Sprint 04 双引擎对跑证明角色一致性失败是**机制缺失**（无参考图输入）而非引擎能力问题——年龄漂移两引擎都顽固，面容一致性零保障。
2. **管道半现成属实**：协议（`ImageRequest.reference_images`）、占位符（`$REFERENCE_IMAGE`）、上传（`upload_image()`）、溯源（`CHARACTER_REFERENCE` 行）全部已存在，断在 7 处接线，**不需要数据模型重设计**。
3. **关键外部发现**：Z-Image Omni 的官方 ComfyUI 节点 `TextEncodeZImageOmni` **原生支持最多 3 张参考图**，而现有 `zimage_turbo.json` 模板已在用该节点 → **主路线零插件、零新依赖**。
4. **落地路径**：M1 管道最小闭环（纯接线）→ M2 多参考图数据模型 → M3 相似度评分 harness（先过 Value Gate）→ M4 Review Loop / prompt 拼装 / 云端参考图。
5. **文档漂移警告**：P8 Continuity 规则引擎已实质落地（两表 + 8 规则 + Agent check/fix + 前端），但 AGENTS.md §5 与 backlog 均未记录——P4-E1-T01 的"Continuity State Domain"不应再按"未开始"排期。

---

## 1. 背景与授权

- Sprint 04（`docs/reports/real-chain-validation-report.md`）：2400 字篮球章节 → 3 Scenes / 38 Shots，20 shots × 双引擎（Agnes 云端 / 本地 ComfyUI + Z-Image-Turbo int8）= 40 张。首跑可用率 Agnes 70% / ComfyUI 85%；最终 85%。
- K2（角色一致性）被证实为最痛点：「同一角色年龄都无法稳定，更遑论面容」；双引擎同漂移 → 问题在机制不在引擎。
- 预研授权原文（§6 第 4 条）：「reference 图机制（IPAdapter 路线）设计与可行性预研——K2 证据已足；应先出设计（依赖 ComfyUI 模板扩展 + `$REFERENCE_IMAGE`），与 P2-E4-T01 解耦可并行论证。」
- 本报告修正一处：调研结论将主路线从「IPAdapter」更新为「**Z-Image 原生参考图输入**」（见 §4.1），IPAdapter 仅覆盖 SD1.5/SDXL，与本项目 DiT 栈不兼容。

---

## 2. 现状盘点：已有骨架与七处断点

### 2.1 已就位的骨架（不重做）

| 层 | 已有 | 证据 |
|---|---|---|
| 数据 | `Character.visual_prompt / negative_prompt / master_version_id`；`CharacterVersion.asset_id`（代表视觉资产）+ 不可变版本链；`ShotCharacter.costume_id` + 连续性字段 | `backend/app/db/models/character.py:35-41,51-106` |
| 溯源 | 生成时已写 `role="character_reference"` 的 generation_inputs（character_id+asset_id metadata） | `backend/app/services/generation_service.py:159-175,302-350` |
| 协议 | `ImageRequest.reference_images: list[str]`（绝对路径）；`VideoRequest` 同 | `backend/app/providers/image/base.py:29` |
| 占位符 | `$REFERENCE_IMAGE` 已在 WorkflowSchema 声明 | `backend/app/providers/comfyui/workflow_schema.py:83-84` |
| 上传 | `ComfyUIClient.upload_image()`（docstring 明示 ControlNet/IPAdapter 用途） | `backend/app/providers/comfyui/client.py:167-180` |
| 能力 | registry `image.comfyui: reference_image=True` / `image.agnes: False` | `backend/app/providers/registry.py:253-256` |
| 契约 | §35 逻辑参数已含 `reference_images`（上传由 provider 负责）；§41 执行链已含 Upload Reference 步骤；§47 capability 已含 `reference_image` | `docs/api-event-contract-v0.1.md`、`docs/backend-architecture-v0.1.md` |
| Continuity | P8 已落地：`scene_continuity_states`/`shot_continuity_states` 两表 + 8 条确定性规则 + `continuity_warnings` + Agent check/fix + 前端 `features/continuity/`；`CHARACTER_REFERENCE_OUTDATED` 规则已存在 | 迁移 `a0b1c2d3e4f7`/`a8b9c0d1e2f3`、`continuity_service.py`（1180 行） |
| 前端 | 角色参考图上传 + 版本管理 UI 完整（上传 → 新版本 → 激活 MASTER） | `frontend/src/features/libraries/EntityVersionBlock.tsx:46-76` |

### 2.2 七处断点（按打通顺序）

| # | 断点 | 位置 |
|---|---|---|
| 1 | worker 不读 CHARACTER_REFERENCE 溯源行、构建 `ImageRequest` 不传 `reference_images` | `backend/app/generations/worker.py:418-426` |
| 2 | 无带 LoadImage / `$REFERENCE_IMAGE` 节点的工作流模板（`default_image_api.json`、`zimage_turbo.json` 均无） | `workflows/*.json` |
| 3 | `upload_image()` 从未接入 provider 生产流；本地绝对路径 ≠ ComfyUI 侧文件名 | `backend/app/providers/image/comfyui.py:62` |
| 4 | `GenerationCreate` / Agent `generate_image` 工具 / ShotInspector 均无参考图入参 | `backend/app/domain/generation.py:8-18`、`backend/app/agents/tools.py:41-46`、`frontend/src/features/storyboard/ShotInspector.tsx:104-127` |
| 5 | prompt 解析链无角色拼装层——`visual_prompt/negative_prompt` 全库无消费方 | `backend/app/services/generation_service.py:80-107` |
| 6 | schema 仅支持单参考图（list 取 `raw[0]`） | `backend/app/providers/comfyui/workflow_schema.py:245-246` |
| 7 | Agnes 云端无一致性输入通道（纯文生图） | `backend/app/providers/image/agnes.py:189-194` |

次级不一致（顺手修）：`generation_io.py:20` 的 `INPUT_ROLES` 常量只有 `("PROMPT_VERSION","SHOT")`，与实际写入的 `character_reference` 不一致；assets 的 `type="reference"` 是死枚举（参考图实际走 `type="image"` + `meta_json.purpose`）。

---

## 3. 设计原则（文档级红线，全部沿用）

来自 `docs/roadmap/phase-4-advanced.md` Epic 4.1 / `docs/alpha/design/continuity-engine-design-v0.1.md` / P4-E4-T01：

1. **Deterministic First**：能用规则判断的先走规则，不上 LLM。
2. **Review 不自动改 Project State**：视觉检查只产出 evidence/confidence 候选 Issue，人工确认；默认不自动重生成。
3. **Generate Anyway**：ERROR/WARNING 不阻止生成，UI 强提醒。
4. **Minimum Sufficient Context**：prompt/上下文只注入相关最小状态，不无限增长。
5. **Latest ≠ Master**：参考图只取 MASTER 指针版本，最新导入不自动生效。
6. **不建通用知识图谱**：只为 Character appearance/costume、location、key props 三类高频判断建模。
7. 架构红线：Provider 只见路径与 prompt，不感知业务语义；Selection 业务逻辑住 Service 层；版本不可变。

---

## 4. 外部技术调研结论（2026-08）

### 4.1 引擎路线对比

| 路线 | 保真 | 训练 | 对本项目 DiT 栈兼容 | 判定 |
|---|---|---|---|---|
| **Z-Image 原生参考图**（`TextEncodeZImageOmni` image1/2/3） | 待实测（社区先例存在） | 免 | ✅ 官方内置节点，现模板已在用 | **首选：M1 主路线** |
| 角色 LoRA | 最高（社区实测通过率 ~85%，+参考图可到 ~95%） | 需 15-20 张图训练 | ✅ Z-Image 社区已有 LoRA 工具链 | 主力角色长期复用时引入（M4+） |
| ReActor 后处理换脸 | 像素级但质感违和 | 免 | ✅ 模型无关（后处理输出图） | 关键特写兜底（M4 评估） |
| PuLID-Flux | Flux 上高 | 免 | ❌ 仅 Flux | 不引入 |
| IPAdapter / InstantID / PhotoMaker | SDXL 上中-高 | 免 | ❌ 仅 SD1.5/SDXL，IPAdapter_plus 已进维护模式 | 不引入 |
| reference-only ControlNet | 低-中 | 免 | ❌ SD1.5 时代产物 | 不引入 |

**Z-Image 家族事实**（来源：Tongyi-MAI/Z-Image 官方仓库、docs.comfy.org 内置节点文档）：S3-DiT 单流 6B 架构，text/视觉语义/VAE token 序列级拼接；家族含 Turbo（8 步蒸馏）/ Omni-Base（生成+编辑底座）/ Z-Image-Edit（2026-01 权重发布）。官方 Omni 节点支持最多 3 张参考图（可选 CLIPVision encoder + VAE reference latents）。

【推测，M1 冒烟必须实测】Turbo 是无 CFG 蒸馏版，对参考图的遵循度可能弱于 Omni-Base/Edit 版——若实测不达标，备选 = 为 Omni-Base/Edit 增加 drop-in 模板（workflow 自动发现机制零代码支持）。

### 4.2 多参考图实践

社区共识：多角度参考显著改善侧脸/背影身份丢失。Omni 3 图上限下的建议组合：**主角色正脸特写 +（可选）服装参考或次要角色**；参考图裁纯脸/上半身，避免背景污染特征。多视角三视图 sheet 是进阶项。

### 4.3 相似度评分

| 指标 | 适用 | 经验阈值 | 风险 |
|---|---|---|---|
| ArcFace (insightface) 512 维余弦 | 写实人脸 | 1:1 约 0.30-0.45，工程常用 0.4-0.5 | 【推测】对漫画/二次元脸判别力下降；antelopev2 权重**非商用许可**；Windows 编译易失败 |
| DINOv2 / CLIP image-image | 风格化角色（本项目主用） | 无公认值，需 Value Gate 样本校准 | 对"同角色不同画风"敏感，需同风格参考图 |

学术佐证（ContextAnyone, arXiv 2512.07328）：一致性评估采用 ArcFace+DINO 双指标。**「只提示不拦截」策略合理**——侧脸/遮挡/极端表情误报率高，硬拦截打断创作流，且与 P4-E4-T01「默认不自动重生成」红线一致。

### 4.4 云端路线

业界已收敛为「统一生成+编辑端点 + 参考图数组参数」：Seedream 4.0 支持最多 10-14 张参考图（`image_urls`，官方明确支持漫画分镜一致性）；GPT-image 走 reference-based generation；Flux Kontext / Qwen-Image-Edit 走指令编辑保身份。**对本项目**：`ImageRequest.reference_images` 契约与该业界形态同构——未来给 Agnes 网关接入支持参考图的云端模型时，只需新增 provider 实现，不动契约。当前 Agnes `reference_image=False` 保持诚实，不伪装。

---

## 5. 架构设计

### 5.1 参考图数据流（红线合规）

```text
Shot ──ShotCharacter(character, costume)──┐
                                          ▼
GenerationService.create
  ├─ prompt 解析（现有链：data.prompt → PromptVersion → shot.image_prompt）
  ├─ ReferenceResolver（新，Service 层，确定性规则）
  │    显式 GenerationCreate.reference_asset_ids 覆盖（可空）
  │    └─ 默认：ShotCharacter → Character.master_version_id
  │              → active CharacterVersion → 参考图集（M1=版本代表 asset_id；M2=character_version_assets 按 role 优先级）
  │              → 排序（face 优先）、上限 3（Omni 限制）
  │              → provider capability.reference_image=False → 不注入，参数记录 reason（诚实降级）
  ├─ 写 generation_inputs（role=character_reference，行已存在；修正 INPUT_ROLES 常量）
  └─ Generation 落库 → 202
        │
worker（关断点 1）
  └─ 读 generation_inputs → AssetService 取绝对路径 → ImageRequest(reference_images=[...])
        │
ComfyUI Provider（关断点 3/6）
  └─ reference_images 非空 → client.upload_image(逐张) → ComfyUI 侧文件名
     → mapper 注入 $REFERENCE_IMAGE_1..3 → 模板 zimage_turbo_ref.json（LoadImage×3 + Omni image1/2/3）
```

红线核对：Provider 只见「路径/文件名 + prompt」✅；角色/MASTER/服装语义全部住 Service 层 ✅；Agent 无需新增理解（R2 审批流不变，`generate_image` 工具可不加参数——参考图由 Service 按 Shot 绑定自动解析）✅；版本不可变（引用的是不可变 asset 行）✅；Latest ≠ Master（只走 MASTER 指针）✅。

### 5.2 契约与模板增量

| 项 | 变更 | 量级 |
|---|---|---|
| `GenerationCreate` | + `reference_asset_ids: list[str] \| None`（显式覆盖；缺省自动解析） | 小 |
| WorkflowSchema | `$REFERENCE_IMAGE` → `$REFERENCE_IMAGE_1..3`（保留旧 token = 槽 1 别名，向后兼容） | 小 |
| 模板 | 新增 `workflows/zimage_turbo_ref.json`：现模板 + LoadImage×3 + Omni image1/2/3 接线；旧模板不动 | drop-in JSON + WORKFLOW_CATALOG 一行 |
| `INPUT_ROLES` | 修正为与实际写入一致（+`CHARACTER_REFERENCE`） | 一行 |
| 前端 ShotInspector | 生成体可带 `reference_asset_ids`（默认「自动」，可查看/自选/清空）；生成详情展示所用参考图（provenance 可视化） | 小-中 |
| Mock provider | 接受并忽略 `reference_images`（或渲染占位角标，便于测试断言） | 极小 |

### 5.3 相似度回归（M3，独立可并行）

- **形态**：离线 harness（`backend/scripts/consistency_eval.py`），**不入生成主路径**，feature flag 后才进产品 UI。
- **样本与基线（Value Gate）**：phase-4-advanced 要求「至少 20 个真实 Scene 的问题样本与人工基线」——Sprint 04 的 40 张图 + 快评记录是首批样本，需补充问题样本至达标。
- **指标**：DINOv2 为主（风格化脸、torch hub 加载、CPU 可跑、无许可坑），ArcFace 为辅（仅写实角色）；**阈值由样本校准产出，不拍脑袋**。
- **产品形态**：结果存 generation meta + evidence 文案（如「与角色版本 v2 参考图相似度位于基线后 25%」），Inspector/VersionReview 展示为**提示**；不自动重试、不拦截。
- **对齐**：即 P4-E1-T02（视觉 Continuity 检查）的参考图维度子集，先行验证「视觉模型可靠性是否达到阈值」，避免 XL 任务盲启。

### 5.4 明确不做（本期）

- prompt 拼装层（消费 `visual_prompt`）→ 归 P2-E4-T02 prompt profile，语义漂移与身份漂移是两个问题（Sprint 04：双引擎同崩 = prompt 问题）。
- Agent 工具新增参考图参数 → Service 自动解析已覆盖；显式覆盖留在 API 层。
- LoRA 训练管线 / ReActor / Z-Image-Edit 模板 → M4+。
- 云端参考图 provider（Seedream 式）→ 契约已同构，待 Agnes 网关接入此类模型时做。

---

## 6. 分期实施计划

| 期 | 内容 | 验收标准（DoD） |
|---|---|---|
| **M1 管道最小闭环** | 关断点 1/2/3/6 + `GenerationCreate.reference_asset_ids` + `INPUT_ROLES` 修正 + mock E2E | ① mock 生成请求携带 reference_images；② comfyui provider 单测：upload → mapper 注入 3 槽位；③ pytest 全绿 + 真实 ComfyUI 冒烟 1 张带参考图生成（dev 环境） |
| **M2 多参考图数据模型** | `character_version_assets` 表（role: FACE/BODY/FRONT/SIDE/EXPRESSION/STYLE，落 Alpha 设计 §30-31）+ 迁移 + ReferenceResolver role 优先级规则 + EntityVersionBlock 多图管理 | 角色版本可挂多张参考图并标 role；生成自动按优先级取 ≤3 张；缺 face 回退版本代表图；pytest + vitest 全绿 |
| **M3 评分 harness** | 样本集补足 + 人工基线 + 离线 harness + 阈值校准报告 + feature flag 提示 UI | Value Gate 达标（≥20 问题样本）；harness 在人工基线上区分度达预设阈值；产品内只提示不拦截 |
| **M4（Phase 2）** | Z-Image-Edit/Omni-Base 模板 A/B、LoRA 试点、ReActor 兜底评估、Review Loop 集成（P4-E4-T01）、prompt 拼装（P2-E4-T02）、云端参考图 provider | 按 backlog Value Gate 逐项立项 |

依赖关系：M1 ← 无（纯接线，可立即开工）；M2 ← M1（消费同一解析入口）；M3 ← 无（与 M1/M2 并行，但产品化依赖 M1 产出带参考图的图）；M4 ← M1-M3 结论。

---

## 7. 风险与开放问题

| 风险 | 等级 | 缓解 |
|---|---|---|
| Turbo 蒸馏版参考图遵循度不达标【推测】 | 高 | M1 冒烟即测；备选 Omni-Base/Edit drop-in 模板（零代码注册） |
| 漫画脸对 ArcFace 判别力弱【推测】 | 中 | DINOv2 为主；阈值由人工基线校准 |
| 参考图风格污染（参考图与目标画风不一致 → 画风漂移） | 中 | 参考图须同风格；Selection 加风格一致性人工检查项；文档写明导入规范 |
| 多角色 >3 张取舍（Omni 上限） | 中 | 主角色 face 优先 + 次要角色靠 prompt 文字兜底；M2 规则显式化 |
| upload 文件名冲突 / 路径安全 | 低 | AssetService 路径逃逸守卫已有；upload 用 uuid 文件名 |
| insightface Windows 编译 + antelopev2 非商用 | 低 | M3 先 DINOv2；ArcFace 仅写实角色按需引入 |

**开放问题（需拍板）**：
1. M1 是否纳入下一 Sprint（建议：是，量级小、纯接线、证据充分）。
2. 显式 `reference_asset_ids` 是否长期暴露给 Agent 工具（建议：不暴露，保持 Service 自动；API 层保留覆盖用于调试）。

---

## 8. 文档漂移修正清单（批准后同步）

1. **AGENTS.md §5 与 docs/tasks/backlog.md 未记录 P8 Continuity 落地**——P4-E1-T01 的 Continuity State Domain 部分应标注「已由 P8 并行交付」，剩余工作收敛为 T02 视觉检查。
2. AGENTS.md §5 记载模板文件名 `workflows/zimage_turbo_api.json`，实际为 `workflows/zimage_turbo.json`（目录自动发现按文件名 stem 注册）。
3. `generation_io.py` `INPUT_ROLES` 常量与实际写入不一致（M1 顺手修）。

---

## 9. 来源

内部：`docs/reports/real-chain-validation-report.md` · `docs/tasks/sprint-04-real-chain-validation.md` · `docs/tasks/backlog.md` · `docs/roadmap/phase-4-advanced.md`（Epic 4.1/4.4）· `docs/database-v0.1.md` §7/§19-22 · `docs/api-event-contract-v0.1.md` §35/§41/§47/§130-131/§142-143 · `docs/backend-architecture-v0.1.md` §41-42 · `docs/agent-director-v0.1.md` §18-20/§44-45 · `docs/alpha/design/continuity-engine-design-v0.1.md` · `docs/alpha/design/database-schema-design-v0.1.md` §30-31 · `docs/alpha/design/asset-generation-version-design-v0.1.md` · `docs/adr/ADR-001-asset-self-versioning.md`

外部（2026-08 检索）：docs.comfy.org/built-in-nodes/TextEncodeZImageOmni（3 参考图口，官方）· github.com/Tongyi-MAI/Z-Image（S3-DiT/家族）· apatero.com PuLID vs InstantID vs IPAdapter FaceID 对比（2025-12）· github.com/lldacing/ComfyUI_PuLID_Flux_ll · insightface.ai 阈值指南（2026-04）· arxiv.org/abs/2512.07328（ContextAnyone，ArcFace+DINO 双指标）· seed.bytedance.com Seedream 4.0 发布（多图参考 API）
