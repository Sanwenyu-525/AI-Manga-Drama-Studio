// Settings page (功能版): backend-backed provider management. The ComfyUI
// "test connection" button hits POST /providers/comfyui/test (health + workflow
// preflight); the mock provider is a built-in and reports no test endpoint.
// P-LocalModels: LLM 卡「检测本地服务」（Ollama/LM Studio 端口探测一键填入）+
// 图像卡 ComfyUI 本地引擎（地址/checkpoint 拉取选用/本地模型扫描与导入）。
// P2-E4-T02: 工作流 live 健康检查面板（WorkflowHealthCheck）：模板下拉 + 逐节点 live 校验。

import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowClockwise,
  ArrowLeft,
  CheckCircle,
  Cpu,
  FlowArrow,
  FolderOpen,
  ImageSquare,
  Plug,
  VideoCamera,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { listComfyWorkflows, validateComfyWorkflow } from "../../api/providers";
import type { ComfyWorkflowNodeCheck, ComfyWorkflowValidateResult } from "../../api/providers";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { lastProjectId } from "../../lib/lastProject";
import { formatBytes } from "../../lib/format";
import { isTauriRuntime, pickDirectory } from "../../lib/nativeDialog";
import { DirectoryBrowserModal } from "./DirectoryBrowserModal";
import type { ProviderStatus } from "../../api/types";
import { Link, useLocation, useSearchParams } from "react-router-dom";

// LLM 运行时连接配置（mode/base_url/api_key/model）。api_key 始终只回传掩码，不回传明文。
// P-LLM-Profiles：config 读取激活连接；profile_id/profile_name/capabilities 为增量字段。
interface LLMConfig {
  mode: "fake" | "openai";
  base_url: string | null;
  model: string;
  api_key_set: boolean;
  api_key_hint: string | null;
  profile_id?: string | null;
  profile_name?: string | null;
  capabilities?: LLMCapabilities | null;
}

// 能力标记（启发式 + 用户覆写，advisory）。
interface LLMCapabilities {
  tools: boolean;
  vision: boolean;
  reasoning: boolean;
  source: "heuristic" | "override";
}

// 命名连接 Profile（GET /llm/profiles）。
interface LLMProfile {
  id: string;
  name: string;
  mode: "fake" | "openai";
  base_url: string | null;
  model: string | null;
  api_key_set: boolean;
  api_key_hint: string | null;
  is_active: boolean;
  bound_tasks: string[];
  capabilities: LLMCapabilities;
}

interface LLMTaskBinding {
  profile_id: string;
  profile_name: string;
}

// 任务 → 有序降级链（P-LLM-Fallback）：只有显式配置的连接才参与降级尝试。
interface LLMProfilesResponse {
  profiles: LLMProfile[];
  active_profile_id: string;
  task_bindings: Record<string, LLMTaskBinding | null>;
  task_fallbacks: Record<string, LLMTaskBinding[]>;
  tasks: { id: string; label: string }[];
}

// 图像生成运行时配置（provider/agnes_base_url/api_key）。key 同样只回传掩码。
// video_provider/video_model 是视频服务（与图像共用 Agnes 账号与配置层）。
// comfyui_url/checkpoint/comfyui_models_root 是 ComfyUI 本地链路（P-LocalModels）。
interface ImageConfig {
  provider: "mock" | "comfyui" | "agnes";
  agnes_base_url: string | null;
  api_key_set: boolean;
  api_key_hint: string | null;
  video_provider: "mock" | "agnes";
  video_model: string | null;
  comfyui_url: string | null;
  checkpoint: string | null;
  comfyui_models_root: string | null;
}

interface ImageTestResult {
  connected: boolean | null;
  provider: string;
  latency_ms?: number | null;
  detail?: string;
  image_model_available?: boolean;
  error?: string;
}

// GET /image/video-models：视频模型目录（后端单一事实源，不再前端硬编码）。
// verified=后端是否实测出片；available=该账号 /models 列表实测是否包含（未探测为 null）。
interface VideoModelInfo {
  id: string;
  label: string | null;
  verified: boolean;
  available?: boolean | null;
}

interface VideoModelsResponse {
  models: VideoModelInfo[];
  probed: boolean;
  probe_error?: string | null;
}

interface TestResult {
  connected: boolean;
  latency_ms: number | null;
  workflow: { id: string; status: string; error?: string } | null;
}

interface AgnesTestResult {
  connected: boolean;
  key_set: boolean;
  latency_ms?: number;
  models_count?: number;
  sample_models?: string[];
  image_model_available?: boolean;
  error?: string;
}

// --- 本地模型发现（P-LocalModels）----------------------------------------------

// POST /llm/detect-local：本机运行中的 OpenAI 兼容服务（Ollama/LM Studio/...）。
interface LocalLLMServer {
  kind: string;
  label: string;
  base_url: string;
  models_count: number;
  sample_models: string[];
}

// GET /providers/comfyui/models：ComfyUI 端 checkpoint 列表（never-raise）。
interface ComfyModelsResult {
  connected: boolean;
  base_url: string;
  models: string[];
}

// POST /providers/models/scan：path 扫描 / 默认位置自动检索（两种互斥形态）。
interface ScanFile {
  name: string;
  path: string;
  dir: string;
  kind: string;
  size_bytes: number;
}
interface ScanResult {
  mode: "path" | "autodetect";
  path?: string;
  files?: ScanFile[];
  total?: number;
  truncated?: boolean;
  locations?: { kind: string; label: string; path: string; model_count: number; sample_models: string[] }[];
}

// GET /operations/{id}：导入任务的轮询载体（202 + Operation，契约 §81-82）。
interface ImportOperation {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  result: { source: string; target: string; strategy: string; size_bytes: number } | null;
  error: string | null;
}

const KIND_LABELS: Record<string, string> = {
  checkpoint: "底模",
  lora: "LoRA",
  vae: "VAE",
  controlnet: "ControlNet",
  diffusion: "扩散模型",
  text_encoder: "CLIP",
  upscale: "放大",
  other: "其他",
};

// 轮询 Operation 直到 completed/failed（契约 §81-82；导入 GB 级模型可能耗时数分钟）。
async function pollOperation(opId: string): Promise<ImportOperation> {
  for (;;) {
    const op = await api.get<ImportOperation>(`/operations/${opId}`);
    if (op.status === "completed" || op.status === "failed") return op;
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
}

const STATUS_LABELS: Record<string, string> = {
  connected: "已连接",
  active: "使用中",
  unknown: "未检测",
  disconnected: "已断开",
  error: "异常",
};

// 设置分类 Tab（真页面状态：单 Tab 单内容区，其余服务配置卸载；状态同步到 ?tab= 可深链）
const TABS = [
  { id: "ai", label: "AI 服务" },
  { id: "image", label: "图像服务" },
  { id: "video", label: "视频服务" },
  { id: "providers", label: "生成服务" },
] as const;
type SettingsTabId = (typeof TABS)[number]["id"];

// URL 字段即时校验：只接受 http/https 绝对地址（ComfyUI/Agnes/LLM 端点通用）。
function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

// Tab 状态 ↔ URL search param（/settings?tab=image 可深链；非法值回落 ai）
function useSettingsTab(): [SettingsTabId, (id: SettingsTabId) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: SettingsTabId = TABS.some((t) => t.id === raw) ? (raw as SettingsTabId) : "ai";
  const set = (id: SettingsTabId) => {
    setParams(id === "ai" ? {} : { tab: id }, { replace: true });
  };
  return [tab, set];
}

// Tab 导航条（role=tablist；active 由 URL 状态驱动，非滚动探测）
function SettingsTabs({ tab, onChange }: { tab: SettingsTabId; onChange: (id: SettingsTabId) => void }) {
  return (
    <div className="settings-tabs" role="tablist" aria-label="设置分类">
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          id={`settings-tab-${t.id}`}
          aria-selected={tab === t.id}
          aria-controls={`settings-panel-${t.id}`}
          className={`settings-tab${tab === t.id ? " active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// 三条服务线的当前生效 Provider 摘要（真实注册表数据；点按跳对应 Tab）。
// 状态含义收敛到整行的原生 tooltip，不再占一块常驻图例卡。
function StatusStrip({
  providers,
  onOpenTab,
}: {
  providers?: ProviderStatus[];
  onOpenTab: (id: SettingsTabId) => void;
}) {
  if (!providers || providers.length === 0) return null;
  const lines: { tab: SettingsTabId; label: string; ids: string[] }[] = [
    { tab: "ai", label: "AI", ids: ["llm_openai", "llm_fake"] },
    { tab: "image", label: "图像", ids: ["agnes", "comfyui_local", "mock"] },
    { tab: "video", label: "视频", ids: ["video_agnes", "video_mock"] },
  ];
  return (
    <div
      className="settings-statusline"
      title="使用中＝当前配置选定；已连接＝内置随 Studio Service 运行；未检测＝尚未执行「测试连接」；异常/已断开＝最近一次检测失败或离线"
    >
      {lines.map(({ tab: lineTab, label, ids }) => {
        const active = ids
          .map((id) => providers.find((p) => p.id === id))
          .find((p): p is ProviderStatus => !!p && (p.status === "active" || p.status === "connected"));
        if (!active) return null;
        return (
          <button key={lineTab} type="button" className="statusline-item" onClick={() => onOpenTab(lineTab)}>
            <span className={`provider-dot ${active.status}`} />
            <strong>{label}</strong>
            <span className="muted">{active.name}</span>
            <span className={`badge ${active.status === "connected" || active.status === "active" ? "ok" : "neutral"}`}>
              {STATUS_LABELS[active.status] ?? active.status}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// 统一的 Tab 底部保存条：即时操作留在字段附近，保存/重置固定在面板底部
function SettingsActionBar({
  dirty,
  saved,
  savePending,
  onSave,
  onReset,
}: {
  dirty: boolean;
  saved: boolean;
  savePending: boolean;
  onSave: () => void;
  onReset: () => void;
}) {
  return (
    <div className="settings-actions-bar">
      {dirty && !saved && <span className="dirty-badge">未保存</span>}
      {saved && (
        <span className="test-result ok">
          <CheckCircle size={14} weight="fill" /> 已保存，立即生效
        </span>
      )}
      <span className="grow" />
      <button type="button" className="btn secondary compact" disabled={!dirty || savePending} onClick={onReset}>
        重置
      </button>
      <button className="btn primary compact" disabled={savePending} onClick={onSave}>
        {savePending ? "保存中…" : "保存配置"}
      </button>
    </div>
  );
}

// 骨架屏：与单列面板同形（感知性能；jsdom/无障碍下 aria-hidden）。
function SettingsSkeleton() {
  return (
    <div className="settings-skeleton" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div className="skeleton-card" key={i}>
          <div className="skeleton-line w-40" style={{ height: 14 }} />
          <div className="skeleton-line h-field" />
          <div className="skeleton-line h-field" />
          <div className="skeleton-line w-60 h-field" />
        </div>
      ))}
    </div>
  );
}

export function SettingsPage() {
  const location = useLocation();
  const backProjectId = (location.state as { fromProject?: string } | null)?.fromProject ?? lastProjectId();
  const queryClient = useQueryClient();
  const [tab, setTab] = useSettingsTab();

  const {
    data: providers,
    isLoading,
    isError,
  } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: () => api.get<ProviderStatus[]>("/providers"),
    refetchInterval: 30_000, // 设置页低频场景：30s 轮询足够，降低后台请求量
  });

  const refresh = () => void queryClient.invalidateQueries({ queryKey: queryKeys.providers });

  return (
    <div className="project-console">
      <main className="project-home-main">
        {/* 吸顶页头：滚动时固定在滚动容器顶部，内容从其下方穿过（毛玻璃） */}
        <div className="settings-topbar">
          <div className="page-heading">
            <div>
              <span className="eyebrow">系统设置</span>
              <h1>设置</h1>
              <p>生成服务与连接状态 · 真实反映 Studio Service 的 Provider 注册表</p>
            </div>
            <div className="row gap">
              {backProjectId ? (
                <Link to={`/projects/${backProjectId}`} className="btn secondary compact">
                  <ArrowLeft size={15} /> 返回工作台
                </Link>
              ) : (
                <Link to="/" className="btn secondary compact">
                  <ArrowLeft size={15} /> 返回项目
                </Link>
              )}
              <button className="btn secondary compact" onClick={refresh}>
                刷新状态
              </button>
            </div>
          </div>
        </div>

        <div className="settings-page">
          {isError && <div className="error-banner">设置读取失败，请确认 Studio Service 已启动。</div>}

          {!isError && (
            <div className="settings-body">
              <SettingsTabs tab={tab} onChange={setTab} />
              <StatusStrip providers={providers} onOpenTab={setTab} />

              {/* 单 Tab 单内容区：非当前服务的配置整体卸载（key=tab 保证切换时重放入场动画） */}
              {tab === "providers" ? (
                isLoading ? (
                  <SettingsSkeleton />
                ) : (
                  <ProviderRegistryTab providers={providers ?? []} />
                )
              ) : (
                <div
                  key={tab}
                  className="settings-panel"
                  role="tabpanel"
                  id={`settings-panel-${tab}`}
                  aria-labelledby={`settings-tab-${tab}`}
                >
                  {tab === "ai" && <LlmConfigCard />}
                  {tab === "image" && <ImageConfigCard />}
                  {tab === "video" && <VideoConfigCard onOpenTab={setTab} />}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

// 生成服务 Tab：Provider 注册表（只读状态 + 连通性测试；执行层暂无开放配置，诚实说明）。
function ProviderRegistryTab({ providers }: { providers: ProviderStatus[] }) {
  const [results, setResults] = useState<Record<string, TestResult | { error: string }>>({});

  const test = useMutation({
    mutationFn: () => api.post<TestResult>("/providers/comfyui/test"),
    onSuccess: (result) => setResults((r) => ({ ...r, comfyui_local: result })),
    onError: (error) =>
      setResults((r) => ({ ...r, comfyui_local: { error: error instanceof Error ? error.message : String(error) } })),
  });

  // Agnes 探测：200+{connected} 形态永不抛错（契约 §47.4）；无 Key 时提示配置位置。
  const agnesTest = useMutation({
    mutationFn: () => api.post<AgnesTestResult>("/providers/agnes/test"),
  });

  return (
    <div
      className="settings-panel"
      role="tabpanel"
      id="settings-panel-providers"
      aria-labelledby="settings-tab-providers"
    >
      <div className="settings-registry-head">
        <span className="section-kicker">注册表 · {providers.length} 个 Provider</span>
        <span className="muted small">
          生成队列为内置 DB 轮询执行器（并发 1）；超时/重试由 Service 内置策略管理，暂未开放配置
        </span>
      </div>
      <div className="settings-list">
        {providers.map((provider) => {
          const result = results[provider.id];
          return (
            <section key={provider.id} className="provider-card">
              <div className="provider-card-head">
                <span className={`provider-dot ${provider.status}`} />
                <strong>{provider.name}</strong>
                <span
                  className={`badge ${provider.status === "connected" ? "ok" : provider.status === "error" || provider.status === "disconnected" ? "failed" : "neutral"}`}
                >
                  {STATUS_LABELS[provider.status] ?? provider.status}
                </span>
                {provider.base_url && <code className="provider-url">{provider.base_url}</code>}
              </div>
              <div className="provider-capabilities">
                {Object.entries(provider.capabilities ?? {}).map(([key, enabled]) => (
                  <span key={key} className={enabled ? "cap-on" : "cap-off"}>
                    {enabled ? <CheckCircle size={13} weight="fill" /> : <XCircle size={13} />} {capLabel(key)}
                  </span>
                ))}
              </div>
              <div className="provider-card-actions">
                {provider.id === "comfyui_local" ? (
                  <button className="btn secondary compact" disabled={test.isPending} onClick={() => test.mutate()}>
                    <Plug size={14} /> {test.isPending ? "测试中…" : "测试连接"}
                  </button>
                ) : provider.id === "agnes" ? (
                  <button
                    className="btn secondary compact"
                    disabled={agnesTest.isPending}
                    onClick={() => agnesTest.mutate()}
                    title="用已配置的 STUDIO_AGNES_API_KEY 探测网关（GET /models，不消耗生图额度）"
                  >
                    <Plug size={14} /> {agnesTest.isPending ? "测试中…" : "测试连接"}
                  </button>
                ) : (
                  <span className="muted small">内置 Provider · 随 Studio Service 运行</span>
                )}
                {result && <TestResultView result={result} />}
                {provider.id === "agnes" && agnesTest.data && <AgnesResultView result={agnesTest.data} />}
              </div>
              {provider.id === "comfyui_local" && <WorkflowHealthCheck />}
            </section>
          );
        })}
      </div>

      <div className="settings-note">
        <span className="field-label">当前生成服务</span>
        <p>
          生成任务按创建时选定的 Provider 执行；默认值由「图像服务」Tab 的配置决定（env 仅作未配置时的兜底）。连接
          ComfyUI 后建议先「测试连接」确认健康检查与默认工作流预检通过。
        </p>
      </div>
    </div>
  );
}

function AgnesResultView({ result }: { result: AgnesTestResult }) {
  if (!result.connected) {
    return (
      <span className="test-result fail">
        <WarningCircle size={14} /> {result.error ?? "连接失败"}
      </span>
    );
  }
  return (
    <span className="test-result ok">
      <CheckCircle size={14} weight="fill" /> 已连接
      {result.latency_ms != null ? ` · ${result.latency_ms}ms` : ""}
      {result.models_count != null ? ` · ${result.models_count} 个模型` : ""}
      {result.image_model_available ? " · agnes-image-2.1-flash 可用" : ""}
    </span>
  );
}

function TestResultView({ result }: { result: TestResult | { error: string } }) {
  if ("error" in result) {
    return (
      <span className="test-result fail">
        <WarningCircle size={14} /> {result.error}
      </span>
    );
  }
  if (!result.connected) {
    return (
      <span className="test-result fail">
        <WarningCircle size={14} /> 无法连接（ComfyUI 未启动？）
      </span>
    );
  }
  const wf = result.workflow;
  return (
    <span className={`test-result ${wf?.status === "ok" ? "ok" : "warn"}`}>
      {wf?.status === "ok" ? <CheckCircle size={14} weight="fill" /> : <WarningCircle size={14} />}
      已连接 · {result.latency_ms != null ? `${result.latency_ms}ms` : "—"}
      {wf ? (wf.status === "ok" ? ` · 工作流 ${wf.id} 预检通过` : ` · 工作流预检失败：${wf.error ?? "未知"}`) : ""}
    </span>
  );
}

// P2-E4-T02: 工作流 live 健康检查（ComfyUI 卡）：模板下拉（未手动选择时默认 is_default
// 项）+「检查」→ POST validate（200 永不 500，失败语义在 status 字段）→ 逐节点渲染
// 正常 / 缺节点 / 缺模型 / 断链；unreachable / static_error 无逐节点数据，直接展示顶层文案。
function WorkflowHealthCheck() {
  const listQuery = useQuery({
    queryKey: queryKeys.comfyuiWorkflows,
    queryFn: listComfyWorkflows,
    staleTime: 30_000,
    retry: 0,
  });
  const workflows = listQuery.data?.workflows ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 未手动选择时默认 is_default 项，否则取目录第一项
  const selected =
    workflows.find((w) => w.id === selectedId) ?? workflows.find((w) => w.is_default) ?? workflows[0] ?? null;

  const validate = useMutation({
    mutationFn: (workflowId: string) => validateComfyWorkflow(workflowId),
  });

  return (
    <div className="workflow-check">
      <div className="provider-card-actions">
        <span className="field-label">工作流检查</span>
        {listQuery.isPending && <span className="muted small">正在读取工作流目录…</span>}
        {listQuery.isError && (
          <span className="muted small">工作流目录读取失败，请确认 Studio Service 已启动。</span>
        )}
        {listQuery.isSuccess && workflows.length === 0 && (
          <span className="muted small">未发现工作流模板（workflows/ 目录为空）。</span>
        )}
        {workflows.length > 0 && (
          <>
            <select
              aria-label="工作流模板"
              value={selected?.id ?? ""}
              disabled={validate.isPending}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.is_default ? `${w.id}（默认）` : w.id}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn secondary compact"
              disabled={validate.isPending || !selected}
              onClick={() => selected && validate.mutate(selected.id)}
              title="逐节点校验该工作流：节点注册 / 模型文件 / 连线完整性"
            >
              <FlowArrow size={14} /> {validate.isPending ? "检查中…" : "检查"}
            </button>
          </>
        )}
      </div>
      {validate.data && <WorkflowHealthResult result={validate.data} />}
      {validate.isError && (
        <div className="provider-card-actions">
          <span className="test-result fail" role="status">
            <WarningCircle size={14} /> 检查请求失败，请重试。
          </span>
        </div>
      )}
    </div>
  );
}

function WorkflowHealthResult({ result }: { result: ComfyWorkflowValidateResult }) {
  // 不可达：ComfyUI 未启动 / 地址不对——没有节点级数据
  if (result.status === "unreachable") {
    return (
      <div className="provider-card-actions">
        <span className="test-result fail" role="status">
          <WarningCircle size={14} weight="fill" /> 无法连接 ComfyUI：{result.error ?? "服务未启动或地址不可达"}
        </span>
      </div>
    );
  }
  // 模板静态解析失败（JSON 坏 / 缺必需字段）
  if (result.status === "static_error") {
    return (
      <div className="provider-card-actions">
        <span className="test-result fail" role="status">
          <WarningCircle size={14} weight="fill" /> 模板静态解析失败：{result.static_error ?? result.error ?? "未知错误"}
        </span>
      </div>
    );
  }
  // ok / invalid：汇总行 + 逐节点行
  const problemCount = result.missing_nodes.length + result.missing_models.length + result.broken_links.length;
  return (
    <>
      <div className="provider-card-actions">
        <span className={`test-result ${result.ok ? "ok" : "warn"}`} role="status">
          {result.ok ? <CheckCircle size={14} weight="fill" /> : <WarningCircle size={14} weight="fill" />}
          工作流 {result.workflow_id} {result.ok ? "检查通过 · 全部节点可用" : `检查未通过（${problemCount} 项问题）`}
        </span>
      </div>
      {result.nodes.map((node) => (
        <WorkflowNodeRow key={node.node_id} node={node} />
      ))}
    </>
  );
}

function WorkflowNodeRow({ node }: { node: ComfyWorkflowNodeCheck }) {
  const tone = node.status === "ok" ? "ok" : node.status === "missing_node" ? "fail" : "warn";
  const statusLabel =
    node.status === "ok"
      ? "正常"
      : node.status === "missing_node"
        ? "缺节点"
        : node.status === "missing_model"
          ? "缺模型"
          : "断链";
  return (
    <div className="scan-row">
      <span className={`test-result ${tone}`}>
        {node.status === "ok" ? (
          <CheckCircle size={13} weight="fill" />
        ) : node.status === "missing_node" ? (
          <XCircle size={13} />
        ) : (
          <WarningCircle size={13} weight="fill" />
        )}
        {statusLabel}
      </span>
      <code className="provider-url">{node.node_id}</code>
      <code className="provider-url">{node.class_type}</code>
      {node.status === "missing_model" && node.missing_choices.length > 0 && (
        <span className="muted small">缺 {node.missing_choices.length} 个模型候选</span>
      )}
      {node.detail && <span className="muted small">{node.detail}</span>}
    </div>
  );
}

function capLabel(key: string): string {
  return (
    (
      { image_generation: "图片生成", reference_image: "参考图", video_generation: "视频生成" } as Record<
        string,
        string
      >
    )[key] ?? key
  );
}

// LLM 连接配置卡：读写运行时 LLM config（mode/base_url/api_key/model）。
// 保存后后端重置 gateway，下次 AI 调用即用新连接；api_key 只存后端的掩码提示。
// 业界标配：测试连接（POST /llm/test，可测未保存参数）+ 模型列表（GET /llm/models）。
function LlmConfigCard() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.llmConfig,
    queryFn: () => api.get<LLMConfig>("/llm/config"),
  });
  const [mode, setMode] = useState<LLMConfig["mode"]>("fake");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saved, setSaved] = useState(false);
  // 即时校验：仅在用户动过表单（或尝试保存）后展示错误，避免初始空表满屏红字
  const [touched, setTouched] = useState(false);
  // 内联「存为新连接」命名行（替代原生 window.prompt：可即时校验、不脱离页面）
  const [namingProfile, setNamingProfile] = useState(false);
  const [profileName, setProfileName] = useState("");

  // openai 模式才校验端点与模型；fake 模式全部免填
  const urlProblem =
    mode === "openai"
      ? baseUrl.trim() === ""
        ? "请填写 Base URL"
        : !isHttpUrl(baseUrl)
          ? "需要合法的 http(s) 地址"
          : null
      : null;
  const modelProblem = mode === "openai" && model.trim() === "" ? "请填写模型 ID" : null;
  const hasErrors = Boolean(urlProblem || modelProblem);
  // 未保存更改指示：表单与后端配置不一致（输入了新 Key 也算未保存）
  const dirty =
    !!data && (mode !== data.mode || baseUrl !== (data.base_url ?? "") || model !== data.model || apiKey.trim() !== "");

  const saveFromBar = () => {
    setTouched(true);
    if (hasErrors) return; // 校验不过不发请求（错误已在字段下标红）
    save.mutate();
  };
  const reset = () => {
    if (!data) return;
    setMode(data.mode);
    setBaseUrl(data.base_url ?? "");
    setModel(data.model);
    setApiKey("");
    setTouched(false);
    setSaved(false);
  };

  // 保存成功提示 3.2s 后自动消失（避免「已保存」长期驻留变成过期信息）
  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), 3200);
    return () => clearTimeout(timer);
  }, [saved]);

  // 配置读回后同步表单（api_key 不回填明文）。
  const loaded = data ? JSON.stringify([data.mode, data.base_url, data.model]) : "";
  useEffect(() => {
    if (data) {
      setMode(data.mode);
      setBaseUrl(data.base_url ?? "");
      setModel(data.model);
      setApiKey("");
      setSaved(false);
    }
  }, [loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = { mode, base_url: baseUrl.trim(), model: model.trim() };
      if (apiKey.trim()) body.api_key = apiKey.trim(); // 未改动则不回传 key
      return api.put<LLMConfig>("/llm/config", body);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<LLMConfig>(queryKeys.llmConfig, updated);
      setMode(updated.mode);
      setBaseUrl(updated.base_url ?? "");
      setModel(updated.model);
      setApiKey("");
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: queryKeys.llmConfig });
      // 保存成功 → 模型列表缓存失效，可拉取新端点的 /models
      void queryClient.invalidateQueries({ queryKey: ["llm-models"] });
    },
  });

  // 连接测试：带上表单当前值（未保存也能测）；api_key 只在输入了新值时才传。
  const test = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = {};
      if (mode === "openai" || baseUrl.trim()) {
        body.base_url = baseUrl.trim();
        if (apiKey.trim()) body.api_key = apiKey.trim();
        if (model.trim()) body.model = model.trim();
      }
      return api.post<{
        connected: boolean;
        mode: string;
        latency_ms?: number | null;
        detail?: string;
        models_count?: number;
        sample_models?: string[];
        error?: string;
      }>("/llm/test", body);
    },
  });

  // 模型列表（基于已保存配置）：成功填 datalist 建议，失败静默回退手输。
  const modelsQuery = useQuery({
    queryKey: ["llm-models"],
    queryFn: () => api.get<{ models: string[] }>("/llm/models"),
    enabled: data?.mode === "openai",
    staleTime: 60_000,
    retry: 0,
  });
  const modelOptions = modelsQuery.data?.models ?? [];

  // 本地服务探测（P-LocalModels）：并发探测 Ollama/LM Studio/vLLM 等常见端口，
  // never-raise 200+{servers}；「使用」一键把 mode/base_url/模型名填进表单（再手动保存）。
  const detect = useMutation({
    mutationFn: () => api.post<{ servers: LocalLLMServer[] }>("/llm/detect-local", {}),
  });

  const applyLocalServer = (server: LocalLLMServer) => {
    setMode("openai");
    setBaseUrl(server.base_url);
    if (!model.trim() && server.sample_models.length > 0) setModel(server.sample_models[0]);
    setSaved(false);
  };

  // --- 多连接 Profile Registry（P-LLM-Profiles）：命名连接 + 激活切换 + 任务绑定 ---
  const profilesQuery = useQuery({
    queryKey: queryKeys.llmProfiles,
    queryFn: () => api.get<LLMProfilesResponse>("/llm/profiles"),
  });
  const refreshConnection = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.llmProfiles });
    void queryClient.invalidateQueries({ queryKey: queryKeys.llmConfig });
    void queryClient.invalidateQueries({ queryKey: ["llm-models"] });
  }, [queryClient]);
  const activate = useMutation({
    mutationFn: (id: string) => api.post<LLMProfile>(`/llm/profiles/${id}/activate`, {}),
    onSuccess: refreshConnection,
  });
  const saveAsProfile = useMutation({
    mutationFn: (name: string) =>
      api.post<LLMProfile>("/llm/profiles", {
        name,
        mode,
        base_url: baseUrl.trim() || null,
        model: model.trim() || null,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      }),
    onSuccess: () => setSaved(true),
  });
  const removeProfile = useMutation({
    mutationFn: (id: string) => api.delete(`/llm/profiles/${id}`),
  });
  const bindTask = useMutation({
    mutationFn: (payload: { task: string; profileId: string | null }) =>
      api.put<LLMProfilesResponse>("/llm/task-bindings", {
        bindings: { [payload.task]: payload.profileId },
      }),
  });
  // 降级链（P-LLM-Fallback）：显式配置、后端事件宣告，绝不静默掩盖故障。
  const setFallbacks = useMutation({
    mutationFn: (payload: { task: string; ids: string[] }) =>
      api.put<LLMProfilesResponse>("/llm/task-fallbacks", {
        fallbacks: { [payload.task]: payload.ids },
      }),
  });
  // 任一 profile 变更后统一刷新连接面（激活态/绑定/模型列表缓存）。
  useEffect(() => {
    if (
      activate.isSuccess ||
      saveAsProfile.isSuccess ||
      removeProfile.isSuccess ||
      bindTask.isSuccess ||
      setFallbacks.isSuccess
    ) {
      refreshConnection();
    }
  }, [
    activate.isSuccess,
    saveAsProfile.isSuccess,
    removeProfile.isSuccess,
    bindTask.isSuccess,
    setFallbacks.isSuccess,
    refreshConnection,
  ]);

  const nameTrimmed = profileName.trim();
  const submitNewProfile = () => {
    if (!nameTrimmed) return;
    saveAsProfile.mutate(nameTrimmed);
    setProfileName("");
    setNamingProfile(false);
  };
  // 防御性读取：后端契约保证数组形状，但部分/失败响应不阻塞整卡渲染。
  const savedProfiles = profilesQuery.data?.profiles ?? [];
  const bindableTasks = profilesQuery.data?.tasks ?? [];
  const taskBindings = profilesQuery.data?.task_bindings ?? {};
  const taskFallbacks = profilesQuery.data?.task_fallbacks ?? {};

  const addFallback = (task: string, pid: string) => {
    const current = (taskFallbacks[task] ?? []).map((f) => f.profile_id);
    if (!current.includes(pid)) setFallbacks.mutate({ task, ids: [...current, pid] });
  };
  const removeFallback = (task: string, pid: string) => {
    setFallbacks.mutate({
      task,
      ids: (taskFallbacks[task] ?? []).map((f) => f.profile_id).filter((id) => id !== pid),
    });
  };
  const moveUpFallback = (task: string, index: number) => {
    const ids = (taskFallbacks[task] ?? []).map((f) => f.profile_id);
    if (index <= 0) return;
    [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]];
    setFallbacks.mutate({ task, ids });
  };

  return (
    <section className="provider-card">
      <div className="provider-card-head">
        <Cpu size={16} />
        <strong>LLM 连接</strong>
        {data && <span className="badge neutral">{mode === "openai" ? "openai · 真实模型" : "fake · 无 Key"}</span>}
      </div>

      {isLoading && <p className="muted small link-note">正在读取 LLM 配置…</p>}
      {isError && <div className="error-banner">LLM 配置读取失败，请确认 Studio Service 已启动。</div>}

      {savedProfiles.length > 0 && (
        <div className="llm-profiles" role="list" aria-label="已保存的 LLM 连接">
          <span className="muted small">已存连接</span>
          {savedProfiles.map((p) => (
            <span key={p.id} className={`llm-profile-chip${p.is_active ? " active" : ""}`} role="listitem">
              <button
                type="button"
                className="chip-btn"
                disabled={p.is_active || activate.isPending}
                onClick={() => activate.mutate(p.id)}
                title={p.is_active ? "当前激活连接" : "切换到此连接（立即生效）"}
              >
                <strong>{p.name}</strong>
                <span className="badge neutral">{p.mode}</span>
                {p.model && <span className="muted small mono">{p.model}</span>}
                {p.bound_tasks.length > 0 && (
                  <span className="muted small" title={p.bound_tasks.join("、")}>
                    · {p.bound_tasks.length} 任务绑定
                  </span>
                )}
              </button>
              {!p.is_active && (
                <button
                  type="button"
                  className="chip-del"
                  onClick={() => removeProfile.mutate(p.id)}
                  disabled={removeProfile.isPending}
                  title="删除此连接"
                >
                  ×
                </button>
              )}
            </span>
          ))}
          {namingProfile ? (
            <span className="new-profile-row">
              <input
                autoFocus
                value={profileName}
                placeholder="连接名称（如：本地 Qwen）"
                aria-label="连接名称"
                onChange={(e) => setProfileName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitNewProfile();
                  if (e.key === "Escape") setNamingProfile(false);
                }}
              />
              <button
                type="button"
                className="btn secondary compact"
                disabled={!nameTrimmed || saveAsProfile.isPending}
                onClick={submitNewProfile}
              >
                保存
              </button>
              <button type="button" className="btn secondary compact" onClick={() => setNamingProfile(false)}>
                取消
              </button>
            </span>
          ) : (
            <button
              type="button"
              className="btn secondary compact"
              disabled={saveAsProfile.isPending}
              onClick={() => setNamingProfile(true)}
              title="把当前表单配置保存为一条命名连接"
            >
              {saveAsProfile.isPending ? "保存中…" : "+ 存为新连接"}
            </button>
          )}
        </div>
      )}
      {profilesQuery.isError && <ApiErrorPanel error={profilesQuery.error} />}

      {!isLoading && data && (
        <>
          <div className="settings-llm-grid">
            <div className="field">
              <label className="field-label" htmlFor="llm-mode">
                模式
              </label>
              <select
                id="llm-mode"
                value={mode}
                onChange={(e) => {
                  setMode(e.target.value as LLMConfig["mode"]);
                  setTouched(true);
                }}
              >
                <option value="fake">fake（开发/测试，确定性规则，无需 Key）</option>
                <option value="openai">openai（真实 OpenAI 兼容端点）</option>
              </select>
              <span className="field-hint">
                fake＝内置确定性模型（离线可用）；openai＝接入真实模型，保存后立即生效、无需重启
              </span>
            </div>
            <div className={`field${touched && urlProblem ? " invalid" : ""}`}>
              <label className="field-label" htmlFor="llm-base-url">
                Base URL
              </label>
              <input
                id="llm-base-url"
                value={baseUrl}
                placeholder="如 https://api.deepseek.com 或 http://127.0.0.1:11434/v1"
                onChange={(e) => {
                  setBaseUrl(e.target.value);
                  setTouched(true);
                }}
              />
              {touched && urlProblem ? (
                <span className="field-error" role="alert">
                  {urlProblem}
                </span>
              ) : (
                <span className="field-hint">OpenAI 兼容端点地址（DeepSeek / Ollama / LM Studio 等均可）</span>
              )}
            </div>
            <div className={`field${touched && modelProblem ? " invalid" : ""}`}>
              <label className="field-label" htmlFor="llm-model">
                模型
                {modelOptions.length > 0 && (
                  <button
                    type="button"
                    className="mini-refresh"
                    onClick={() => void queryClient.invalidateQueries({ queryKey: ["llm-models"] })}
                    title="从已保存的端点重新拉取模型列表"
                  >
                    <ArrowClockwise size={11} weight="bold" /> 刷新列表
                  </button>
                )}
              </label>
              <input
                id="llm-model"
                value={model}
                list="llm-model-options"
                placeholder={
                  modelsQuery.isError ? "如 deepseek-chat（列表拉取失败，可手输）" : "如 deepseek-chat / qwen2"
                }
                onChange={(e) => {
                  setModel(e.target.value);
                  setTouched(true);
                }}
              />
              <datalist id="llm-model-options">
                {modelOptions.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
              {touched && modelProblem ? (
                <span className="field-error" role="alert">
                  {modelProblem}
                </span>
              ) : (
                <span className="field-hint">模型 ID；保存后可自动从端点拉取候选列表</span>
              )}
            </div>
            <div className="field">
              <label className="field-label" htmlFor="llm-api-key">
                API Key {data.api_key_set && <span className="llm-key-hint">{data.api_key_hint}</span>}
              </label>
              <input
                id="llm-api-key"
                type="password"
                value={apiKey}
                autoComplete="off"
                placeholder={data.api_key_set ? "已设置（留空保持不变）" : "留空则跳过"}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setTouched(true);
                }}
              />
              <span className="field-hint">仅保存在本机后端，界面只回显掩码；本地服务通常可留空</span>
            </div>
            <div className="settings-llm-actions">
              <button
                type="button"
                className="btn secondary compact"
                disabled={test.isPending}
                onClick={() => test.mutate()}
                title={
                  mode === "openai" || baseUrl.trim()
                    ? "探测该连接（GET /models，失败时降级最小 chat 探测）"
                    : "fake 模式无需连接"
                }
              >
                {test.isPending ? "测试中…" : "测试连接"}
              </button>
              <button
                type="button"
                className="btn secondary compact"
                disabled={detect.isPending}
                onClick={() => detect.mutate()}
                title="探测本机常见本地模型服务（Ollama 11434 / LM Studio 1234 / vLLM 8000 等），一键填入"
              >
                <Plug size={14} /> {detect.isPending ? "探测中…" : "检测本地服务"}
              </button>
            </div>

            {bindableTasks.length > 0 && (
              <div className="llm-task-bindings" aria-label="任务分配">
                <span className="muted small">任务分配</span>
                {bindableTasks.map((t) => {
                  const bound = taskBindings[t.id];
                  const fallbacks = taskFallbacks[t.id] ?? [];
                  const chainIds = new Set(
                    [bound?.profile_id, ...fallbacks.map((f) => f.profile_id)].filter((id): id is string =>
                      Boolean(id),
                    ),
                  );
                  const addCandidates = savedProfiles.filter((p) => !chainIds.has(p.id));
                  return (
                    <div className="field" key={t.id}>
                      <span className="field-label">{t.label}</span>
                      <select
                        aria-label={t.label}
                        value={bound?.profile_id ?? ""}
                        disabled={bindTask.isPending}
                        onChange={(e) => bindTask.mutate({ task: t.id, profileId: e.target.value || null })}
                      >
                        <option value="">跟随激活连接</option>
                        {savedProfiles.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                      {fallbacks.length > 0 && (
                        <span className="llm-fallback-chain">
                          {fallbacks.map((f, i) => (
                            <span key={f.profile_id} className="llm-profile-chip">
                              <span className="chip-btn" title="主连接失败时按序降级到此连接（后端事件宣告）">
                                ↓ {f.profile_name}
                              </span>
                              {i > 0 && (
                                <button
                                  type="button"
                                  className="chip-del"
                                  title="前移（更早尝试）"
                                  onClick={() => moveUpFallback(t.id, i)}
                                >
                                  ↑
                                </button>
                              )}
                              <button
                                type="button"
                                className="chip-del"
                                title="移除降级"
                                onClick={() => removeFallback(t.id, f.profile_id)}
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        </span>
                      )}
                      {addCandidates.length > 0 && (
                        <select
                          aria-label={`添加降级-${t.label}`}
                          className="llm-fallback-add"
                          value=""
                          disabled={setFallbacks.isPending}
                          title="主连接失败时按序降级；降级发生时后端会发 llm.fallback.used 事件"
                          onChange={(e) => {
                            if (e.target.value) addFallback(t.id, e.target.value);
                          }}
                        >
                          <option value="">+ 添加降级…</option>
                          {addCandidates.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {detect.data && (
              <div className="settings-llm-actions" role="status">
                {detect.data.servers.length === 0 ? (
                  <span className="muted small">
                    未发现运行中的本地模型服务——请确认 Ollama / LM Studio 等已启动（也可直接手填 Base URL）。
                  </span>
                ) : (
                  detect.data.servers.map((server) => (
                    <div className="scan-row" key={server.base_url}>
                      <span className="badge ok">{server.label}</span>
                      <code className="provider-url">{server.base_url}</code>
                      <span className="muted small mono">
                        {server.models_count} 个模型
                        {server.sample_models.length > 0 ? ` · ${server.sample_models.slice(0, 3).join("、")}` : ""}
                      </span>
                      <button type="button" className="btn secondary compact" onClick={() => applyLocalServer(server)}>
                        使用
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
            {detect.isError && <ApiErrorPanel error={detect.error} />}

            {test.data && (
              <div className={`test-result ${test.data.connected ? "ok" : "fail"}`} role="status">
                {test.data.connected ? (
                  <CheckCircle size={14} weight="fill" />
                ) : (
                  <WarningCircle size={14} weight="fill" />
                )}
                <span>
                  {test.data.connected
                    ? `连接成功 · ${test.data.mode}${test.data.latency_ms != null ? ` · ${test.data.latency_ms}ms` : ""}${
                        test.data.models_count != null ? ` · ${test.data.models_count} 个模型` : ""
                      }${test.data.detail ? ` · ${test.data.detail}` : ""}`
                    : `连接失败：${test.data.error ?? "未知错误"}`}
                </span>
                {test.data.connected && (test.data.sample_models?.length ?? 0) > 0 && (
                  <span className="muted small mono">{test.data.sample_models!.slice(0, 4).join(" · ")}</span>
                )}
              </div>
            )}
            {test.isError && <ApiErrorPanel error={test.error} />}
          </div>
          {/* 说明钉在卡底（.settings-duo 等高拉伸时吸收高度差） */}
          <p className="muted small link-note">
            fake 用于开发/测试（确定性输出，无需 Key）；openai 接入真实模型需提供 Base URL。保存后模型下拉自动拉取
            /models； 测试连接可对未保存的表单值先行探测。「检测本地服务」会探测本机常见端口（Ollama/LM Studio/vLLM
            等）。 切换后立即生效，无需重启。
          </p>
        </>
      )}

      <SettingsActionBar
        dirty={dirty}
        saved={saved}
        savePending={save.isPending}
        onSave={saveFromBar}
        onReset={reset}
      />

      {save.isError && <ApiErrorPanel error={save.error} />}
    </section>
  );
}

// 图像服务配置卡：读写运行时 image config（provider/agnes_base_url/api_key）。
// 保存后后端重置 image provider 缓存，下次生图即用新配置；api_key 只存后端。
// agnes 探测走 GET /models（不消耗生图额度）；mock 无需连接。
// ComfyUI 本地区块（P-LocalModels）：地址编辑、连接测试（可测未保存地址）、
// checkpoint 拉取/选用、本地模型目录扫描 + 一键导入（202 + Operation 轮询）。
function ImageConfigCard() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.imageConfig,
    queryFn: () => api.get<ImageConfig>("/image/config"),
  });
  const [provider, setProvider] = useState<ImageConfig["provider"]>("mock");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [comfyUrl, setComfyUrl] = useState("");
  const [checkpoint, setCheckpoint] = useState("");
  const [modelsRoot, setModelsRoot] = useState("");
  const [scanPath, setScanPath] = useState("");
  // 目录浏览（P-LocalModels）：桌面壳走原生目录对话框（唯一能拿绝对路径的原生方案）；
  // 浏览器环境/旧壳调用失败时回落内置 DirectoryBrowserModal（后端列目录）。
  const [browserTarget, setBrowserTarget] = useState<"scanPath" | "modelsRoot" | null>(null);
  const [importing, setImporting] = useState<string | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importErr, setImportErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // 即时校验（用户动过表单或尝试保存后才展示，避免初始满屏红字）
  const [touched, setTouched] = useState(false);
  // ComfyUI 本地引擎折叠态：provider=comfyui 时自动展开，其余默认折叠（渐进披露，
  // 压缩图像卡高度差）；用户可手动展开/收起，切走 provider 不强制收起
  const [comfyOpen, setComfyOpen] = useState(false);

  // URL 即时校验：ComfyUI 地址与 Agnes 端点都要求合法 http(s)（填了才校验）
  const comfyUrlProblem = comfyUrl.trim() !== "" && !isHttpUrl(comfyUrl) ? "需要合法的 http(s) 地址" : null;
  const agnesUrlProblem =
    provider === "agnes" && baseUrl.trim() !== "" && !isHttpUrl(baseUrl) ? "需要合法的 http(s) 地址" : null;
  const hasErrors = Boolean(comfyUrlProblem || agnesUrlProblem);
  // agnes 无 Key 是「会失败」的警告（env 可能兜底提供），提示但不阻止保存
  const agnesKeyMissing = provider === "agnes" && !data?.api_key_set && apiKey.trim() === "";
  const dirty =
    !!data &&
    (provider !== data.provider ||
      baseUrl !== (data.agnes_base_url ?? "") ||
      apiKey.trim() !== "" ||
      comfyUrl !== (data.comfyui_url ?? "") ||
      checkpoint !== (data.checkpoint ?? "") ||
      modelsRoot !== (data.comfyui_models_root ?? ""));

  // 保存成功提示 3.2s 后自动消失
  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), 3200);
    return () => clearTimeout(timer);
  }, [saved]);

  // 切到 comfyui 时自动展开本地引擎块（初次加载 provider=comfyui 也展开）
  useEffect(() => {
    if (provider === "comfyui") setComfyOpen(true);
  }, [provider]);

  const saveFromBar = () => {
    setTouched(true);
    if (comfyUrlProblem) setComfyOpen(true); // 折叠块内的校验错误要可见
    if (hasErrors) return; // URL 校验不过不发请求
    save.mutate();
  };
  const reset = () => {
    if (!data) return;
    setProvider(data.provider);
    setBaseUrl(data.agnes_base_url ?? "");
    setApiKey("");
    setComfyUrl(data.comfyui_url ?? "");
    setCheckpoint(data.checkpoint ?? "");
    setModelsRoot(data.comfyui_models_root ?? "");
    setTouched(false);
    setSaved(false);
  };

  // 配置读回后同步表单（api_key 不回填明文）。
  const loaded = data
    ? JSON.stringify([data.provider, data.agnes_base_url, data.comfyui_url, data.checkpoint, data.comfyui_models_root])
    : "";
  useEffect(() => {
    if (data) {
      setProvider(data.provider);
      setBaseUrl(data.agnes_base_url ?? "");
      setApiKey("");
      setComfyUrl(data.comfyui_url ?? "");
      setCheckpoint(data.checkpoint ?? "");
      setModelsRoot(data.comfyui_models_root ?? "");
      setSaved(false);
    }
  }, [loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = { provider };
      if (provider === "agnes") {
        if (baseUrl.trim()) body.agnes_base_url = baseUrl.trim();
        if (apiKey.trim()) body.api_key = apiKey.trim(); // 未改动则不回传 key
      }
      // ComfyUI 字段只在用户改动后才提交（避免把 env 默认值固化成覆盖层）；
      // 清空提交 "" = 后端清除覆盖、回落默认。
      if (data) {
        if (comfyUrl.trim() !== (data.comfyui_url ?? "")) body.comfyui_url = comfyUrl.trim();
        if (checkpoint.trim() !== (data.checkpoint ?? "")) body.checkpoint = checkpoint.trim();
        if (modelsRoot.trim() !== (data.comfyui_models_root ?? "")) body.comfyui_models_root = modelsRoot.trim();
      }
      return api.put<ImageConfig>("/image/config", body);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<ImageConfig>(queryKeys.imageConfig, updated);
      setProvider(updated.provider);
      setBaseUrl(updated.agnes_base_url ?? "");
      setApiKey("");
      setComfyUrl(updated.comfyui_url ?? "");
      setCheckpoint(updated.checkpoint ?? "");
      setModelsRoot(updated.comfyui_models_root ?? "");
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: queryKeys.imageConfig });
      void queryClient.invalidateQueries({ queryKey: queryKeys.comfyuiModels });
      // 生效中徽标（生成服务列表的 agnes/active）同步刷新
      void queryClient.invalidateQueries({ queryKey: queryKeys.providers });
    },
  });

  // 连接测试：带上表单当前值（未保存也能测）。
  const test = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = { provider };
      if (provider === "agnes") {
        if (baseUrl.trim()) body.agnes_base_url = baseUrl.trim();
        if (apiKey.trim()) body.api_key = apiKey.trim();
      }
      return api.post<ImageTestResult>("/image/test", body);
    },
  });

  // --- ComfyUI 本地引擎（P-LocalModels）-----------------------------------------

  // ComfyUI 连接测试：携带未保存的表单地址（后端支持 base_url 覆盖，不碰已存配置）。
  const comfyTest = useMutation({
    mutationFn: () =>
      api.post<TestResult>("/providers/comfyui/test", comfyUrl.trim() ? { base_url: comfyUrl.trim() } : {}),
  });

  // checkpoint 列表：读已保存配置指向的 ComfyUI（保存成功后自动失效重拉）。
  const comfyModelsQuery = useQuery({
    queryKey: queryKeys.comfyuiModels,
    queryFn: () => api.get<ComfyModelsResult>("/providers/comfyui/models"),
    enabled: !!data,
    staleTime: 30_000,
    retry: 0,
  });

  // 本地模型扫描：带 path → 扫描该目录；不带 → 自动检索常见默认位置。坏路径 → 422。
  const scan = useMutation({
    mutationFn: (path?: string) =>
      api.post<ScanResult>("/providers/models/scan", path && path.trim() ? { path: path.trim() } : {}),
  });

  // 浏览目录：桌面壳优先原生目录对话框（取消 → null 不动表单）；浏览器环境或旧壳
  // 未注册 dialog 插件（调用抛错）时回落内置 DirectoryBrowserModal。
  const browseFor = async (target: "scanPath" | "modelsRoot") => {
    const title = target === "modelsRoot" ? "选择 ComfyUI 模型目录" : "选择要扫描的模型目录";
    const initial = (target === "modelsRoot" ? modelsRoot : scanPath).trim();
    if (isTauriRuntime()) {
      try {
        const picked = await pickDirectory(title, initial);
        if (picked) {
          if (target === "modelsRoot") setModelsRoot(picked);
          else setScanPath(picked);
        }
        return;
      } catch {
        // 原生对话框不可用 → 落到下面的内置浏览
      }
    }
    setBrowserTarget(target);
  };

  // 导入模型文件到 ComfyUI models 目录：202 + operation_id → 轮询至完成。
  const runImport = async (file: ScanFile) => {
    setImporting(file.name);
    setImportMsg(null);
    setImportErr(null);
    try {
      const started = await api.post<{ operation_id: string }>("/providers/models/import", {
        source: file.path,
        kind: file.kind,
      });
      const op = await pollOperation(started.operation_id);
      if (op.status === "completed" && op.result) {
        setImportMsg(
          `已导入 ${file.name} → ${op.result.target}（${op.result.strategy === "hardlink" ? "硬链接" : "复制"}）。ComfyUI 未立即显示时重启一次即可。`,
        );
      } else {
        setImportErr(op.error ?? "导入失败");
      }
    } catch (error) {
      setImportErr(error instanceof Error ? error.message : String(error));
    } finally {
      setImporting(null);
    }
  };

  return (
    <section className="provider-card">
      <div className="provider-card-head">
        <ImageSquare size={16} />
        <strong>图像服务</strong>
        {data && (
          <span className="badge neutral">
            {provider === "agnes" ? "agnes · 真实生图" : provider === "comfyui" ? "comfyui · 本地" : "mock · 占位图"}
          </span>
        )}
      </div>

      {isLoading && <p className="muted small link-note">正在读取图像服务配置…</p>}
      {isError && <div className="error-banner">图像服务配置读取失败，请确认 Studio Service 已启动。</div>}

      {!isLoading && data && (
        <>
          <div className="settings-llm-grid">
            <div className="field">
              <label className="field-label" htmlFor="image-provider">
                Provider
              </label>
              <select
                id="image-provider"
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value as ImageConfig["provider"]);
                  setTouched(true);
                }}
              >
                <option value="mock">mock（占位图，无需 Key）</option>
                <option value="comfyui">comfyui（本地 ComfyUI 服务器）</option>
                <option value="agnes">agnes（真实云端生图）</option>
              </select>
              <span className="field-hint">生成任务默认走这里选定的 Provider；切换后保存即生效</span>
            </div>
            {provider === "agnes" && (
              <>
                <div className={`field${touched && agnesUrlProblem ? " invalid" : ""}`}>
                  <label className="field-label" htmlFor="agnes-base-url">
                    Agnes Base URL
                  </label>
                  <input
                    id="agnes-base-url"
                    value={baseUrl}
                    placeholder="默认 https://api.agnes-ai.cn/v1"
                    onChange={(e) => {
                      setBaseUrl(e.target.value);
                      setTouched(true);
                    }}
                  />
                  {touched && agnesUrlProblem ? (
                    <span className="field-error" role="alert">
                      {agnesUrlProblem}
                    </span>
                  ) : (
                    <span className="field-hint">一般保持官方端点默认值即可，除非使用代理网关</span>
                  )}
                </div>
                <div className="field">
                  <label className="field-label" htmlFor="agnes-api-key">
                    Agnes API Key {data.api_key_set && <span className="llm-key-hint">{data.api_key_hint}</span>}
                  </label>
                  <input
                    id="agnes-api-key"
                    type="password"
                    value={apiKey}
                    autoComplete="off"
                    placeholder={data.api_key_set ? "已设置（留空保持不变）" : "必填：Agnes 图像 API Key"}
                    onChange={(e) => {
                      setApiKey(e.target.value);
                      setTouched(true);
                    }}
                  />
                  {agnesKeyMissing ? (
                    <span className="field-warn">
                      尚未设置 Key——生成会失败；在上方填入，或用环境变量 STUDIO_AGNES_API_KEY 提供
                    </span>
                  ) : (
                    <span className="field-hint">仅保存在本机后端，界面只回显掩码</span>
                  )}
                </div>
              </>
            )}

            {/* ComfyUI 本地引擎（P-LocalModels）：渐进披露折叠块——地址 / checkpoint / 模型目录 + 扫描导入。
                provider=comfyui 自动展开，其余折叠（压缩与 LLM 卡的高度差，消灭行内空腔） */}
            <details
              className="comfyui-block"
              open={comfyOpen}
              onToggle={(e) => setComfyOpen((e.target as HTMLDetailsElement).open)}
            >
              <summary>
                ComfyUI 本地引擎
                <span className="comfyui-summary-hint">{comfyUrl.trim() || "未配置地址"}</span>
              </summary>
              <div className="comfyui-block-body">
                <div className={`field${touched && comfyUrlProblem ? " invalid" : ""}`}>
                  <label className="field-label" htmlFor="comfyui-url">
                    ComfyUI 地址
                  </label>
                  <input
                    id="comfyui-url"
                    value={comfyUrl}
                    placeholder="如 http://127.0.0.1:8188"
                    onChange={(e) => {
                      setComfyUrl(e.target.value);
                      setTouched(true);
                    }}
                  />
                  {touched && comfyUrlProblem ? (
                    <span className="field-error" role="alert">
                      {comfyUrlProblem}
                    </span>
                  ) : (
                    <span className="field-hint">
                      本机默认 http://127.0.0.1:8188；改动后可用「测试 ComfyUI 连接」先行探测
                    </span>
                  )}
                </div>
                <div className="field">
                  <label className="field-label" htmlFor="comfyui-checkpoint">
                    生成模型（checkpoint）
                    {(comfyModelsQuery.data?.models?.length ?? 0) > 0 && (
                      <button
                        type="button"
                        className="mini-refresh"
                        onClick={() => void queryClient.invalidateQueries({ queryKey: queryKeys.comfyuiModels })}
                        title="从 ComfyUI 重新拉取 checkpoint 列表"
                      >
                        <ArrowClockwise size={11} weight="bold" /> 刷新列表
                      </button>
                    )}
                  </label>
                  <input
                    id="comfyui-checkpoint"
                    value={checkpoint}
                    list="comfy-checkpoint-options"
                    placeholder={
                      comfyModelsQuery.data && !comfyModelsQuery.data.connected
                        ? "ComfyUI 未连接，可手动输入文件名"
                        : "从列表选择，或手输 ComfyUI models 里的文件名"
                    }
                    onChange={(e) => {
                      setCheckpoint(e.target.value);
                      setTouched(true);
                    }}
                  />
                  <datalist id="comfy-checkpoint-options">
                    {(comfyModelsQuery.data?.models ?? []).map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                  <span className="field-hint">ComfyUI models 目录中的 checkpoint 文件名；连上后可下拉选择</span>
                </div>
                <div className="field">
                  <label className="field-label" htmlFor="comfyui-models-root">
                    ComfyUI 模型目录（models 根目录，导入目标）
                  </label>
                  <div className="path-input-row">
                    <input
                      id="comfyui-models-root"
                      value={modelsRoot}
                      placeholder="如 D:\ComfyUI_windows_portable\ComfyUI\models"
                      onChange={(e) => {
                        setModelsRoot(e.target.value);
                        setTouched(true);
                      }}
                    />
                    <button
                      type="button"
                      className="btn secondary compact"
                      onClick={() => void browseFor("modelsRoot")}
                      title="浏览并选择 ComfyUI 模型目录（桌面壳调原生对话框）"
                    >
                      <FolderOpen size={14} /> 浏览
                    </button>
                  </div>
                  <span className="field-hint">「导入到 ComfyUI」文件时的目标目录（同盘硬链接优先，跨盘自动拷贝）</span>
                </div>
                <div className="settings-llm-actions">
                  <button
                    type="button"
                    className="btn secondary compact"
                    disabled={comfyTest.isPending}
                    onClick={() => comfyTest.mutate()}
                    title="健康检查 + 默认工作流预检；携带上方未保存的地址先行探测"
                  >
                    <Plug size={14} /> {comfyTest.isPending ? "测试中…" : "测试 ComfyUI 连接"}
                  </button>
                  {comfyTest.data && <TestResultView result={comfyTest.data} />}
                  {comfyTest.isError && (
                    <span className="test-result fail">
                      <WarningCircle size={14} /> 测试请求失败
                    </span>
                  )}
                </div>

                <div className="field">
                  <label className="field-label" htmlFor="scan-path">
                    扫描模型目录路径
                  </label>
                  <div className="path-input-row">
                    <input
                      id="scan-path"
                      value={scanPath}
                      placeholder="如 D:\Models，或 ComfyUI 的 models 目录"
                      onChange={(e) => setScanPath(e.target.value)}
                    />
                    <button
                      type="button"
                      className="btn secondary compact"
                      onClick={() => void browseFor("scanPath")}
                      title="浏览并选择要扫描的目录（桌面壳调原生对话框）"
                    >
                      <FolderOpen size={14} /> 浏览
                    </button>
                  </div>
                  <span className="field-hint">递归扫描该目录下的模型文件（safetensors/ckpt/gguf…，限深 4 层）</span>
                </div>
                <div className="settings-llm-actions">
                  <button
                    type="button"
                    className="btn secondary compact"
                    disabled={scan.isPending || !scanPath.trim()}
                    onClick={() => scan.mutate(scanPath)}
                    title="递归扫描该目录下的模型文件（safetensors/ckpt/gguf…，限深 4 层）"
                  >
                    {scan.isPending ? "扫描中…" : "扫描该目录"}
                  </button>
                  <button
                    type="button"
                    className="btn secondary compact"
                    disabled={scan.isPending}
                    onClick={() => scan.mutate(undefined)}
                    title="自动检索 Ollama / LM Studio / ComfyUI Desktop / HuggingFace 缓存等常见位置"
                  >
                    {scan.isPending ? "检索中…" : "自动检索常见位置"}
                  </button>
                </div>
                {scan.error && (
                  <div className="settings-llm-actions">
                    <span className="test-result fail" role="status">
                      <WarningCircle size={14} /> {(scan.error as Error).message}
                    </span>
                  </div>
                )}
                {scan.data?.mode === "path" && (
                  <div className="settings-llm-actions">
                    {(scan.data.files ?? []).length === 0 ? (
                      <span className="muted small">
                        该目录下未发现模型文件（支持 safetensors/ckpt/pt/gguf/onnx）。
                      </span>
                    ) : (
                      <>
                        <span className="muted small">
                          发现 {scan.data.total ?? 0} 个模型文件{scan.data.truncated ? "（已达上限，结果截断）" : ""}：
                        </span>
                        {(scan.data.files ?? []).map((file) => (
                          <div className="scan-row" key={file.path}>
                            <span className="badge neutral">{KIND_LABELS[file.kind] ?? file.kind}</span>
                            <code className="provider-url">
                              {file.dir ? `${file.dir}/` : ""}
                              {file.name}
                            </code>
                            <span className="muted small mono">{formatBytes(file.size_bytes)}</span>
                            <button
                              type="button"
                              className="btn secondary compact"
                              disabled={importing != null}
                              onClick={() => void runImport(file)}
                              title="导入到 ComfyUI models 目录（同盘硬链接优先，跨盘复制）"
                            >
                              {importing === file.name ? "导入中…" : "导入到 ComfyUI"}
                            </button>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )}
                {scan.data?.mode === "autodetect" && (
                  <div className="settings-llm-actions">
                    {(scan.data.locations ?? []).length === 0 ? (
                      <span className="muted small">
                        未在本机常见位置发现模型目录（Ollama / LM Studio / ComfyUI Desktop / HF 缓存均未找到）。
                      </span>
                    ) : (
                      (scan.data.locations ?? []).map((loc) => (
                        <div className="scan-row" key={loc.path}>
                          <span className="badge ok">{loc.label}</span>
                          <code className="provider-url">{loc.path}</code>
                          <span className="muted small mono">
                            {loc.model_count} 个模型
                            {loc.sample_models.length > 0 ? ` · ${loc.sample_models.slice(0, 3).join("、")}` : ""}
                          </span>
                          <button
                            type="button"
                            className="btn secondary compact"
                            onClick={() => {
                              setScanPath(loc.path);
                              scan.mutate(loc.path);
                            }}
                          >
                            查看
                          </button>
                          {loc.kind === "comfyui" && (
                            <button
                              type="button"
                              className="btn secondary compact"
                              onClick={() => setModelsRoot(loc.path)}
                              title="把该目录填为导入目标（记得点保存）"
                            >
                              设为模型目录
                            </button>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                )}
                {importMsg && (
                  <div className="settings-llm-actions">
                    <span className="test-result ok" role="status">
                      <CheckCircle size={14} weight="fill" /> {importMsg}
                    </span>
                  </div>
                )}
                {importErr && (
                  <div className="settings-llm-actions">
                    <span className="test-result fail" role="status">
                      <WarningCircle size={14} /> {importErr}
                    </span>
                  </div>
                )}
              </div>
            </details>

            <div className="settings-llm-actions">
              <button
                type="button"
                className="btn secondary compact"
                disabled={test.isPending || provider === "comfyui"}
                onClick={() => test.mutate()}
                title={
                  provider === "agnes"
                    ? "探测该连接（GET /models，不消耗生图额度）"
                    : provider === "mock"
                      ? "mock 无需连接"
                      : "comfyui 请使用下方 ComfyUI 区块的「测试 ComfyUI 连接」"
                }
              >
                {test.isPending ? "测试中…" : "测试连接"}
              </button>
            </div>

            {test.data && (
              <div
                className={`test-result ${test.data.connected === true ? "ok" : test.data.connected === false ? "fail" : "warn"}`}
                role="status"
              >
                {test.data.connected === false ? (
                  <WarningCircle size={14} weight="fill" />
                ) : (
                  <CheckCircle size={14} weight="fill" />
                )}
                <span>
                  {test.data.connected === true
                    ? `连接成功 · ${test.data.provider}${test.data.latency_ms != null ? ` · ${test.data.latency_ms}ms` : ""}${
                        test.data.image_model_available ? " · agnes-image-2.1-flash 可用" : ""
                      }`
                    : (test.data.detail ?? test.data.error ?? "未知状态")}
                </span>
              </div>
            )}
            {test.isError && <ApiErrorPanel error={test.error} />}
          </div>
          {/* 说明钉在卡底（.settings-duo 等高拉伸时吸收高度差） */}
          <p className="muted small link-note">
            保存后立即生效，无需重启；之后在分镜板或镜头检查器点「生成」即按此 Provider 执行。ComfyUI
            本地引擎支持地址编辑、checkpoint 拉取选用、目录浏览选择（桌面壳 原生对话框 ·
            浏览器内置浏览）、本地目录扫描与一键导入（同盘硬链接优先）；agnes 探测不消耗生图额度。
          </p>
        </>
      )}

      <SettingsActionBar
        dirty={dirty}
        saved={saved}
        savePending={save.isPending}
        onSave={saveFromBar}
        onReset={reset}
      />

      {save.isError && <ApiErrorPanel error={save.error} />}
      {/* 目录浏览弹窗：把选中的目录回填到发起浏览的路径输入框 */}
      <DirectoryBrowserModal
        open={browserTarget !== null}
        title={browserTarget === "modelsRoot" ? "选择 ComfyUI 模型目录" : "选择要扫描的模型目录"}
        initialPath={browserTarget === "modelsRoot" ? modelsRoot : scanPath}
        onClose={() => setBrowserTarget(null)}
        onSelect={(path) => {
          if (browserTarget === "modelsRoot") setModelsRoot(path);
          else setScanPath(path);
          setBrowserTarget(null);
        }}
      />
    </section>
  );
}

// 视频服务配置卡：provider（mock/agnes）+ 模型。Agnes Key 与「图像服务」共用
// 同一账号（读写同一个后端配置层），因此这里不重复收集 key。
function VideoConfigCard({ onOpenTab }: { onOpenTab: (id: SettingsTabId) => void }) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.imageConfig,
    queryFn: () => api.get<ImageConfig>("/image/config"),
  });
  const [videoProvider, setVideoProvider] = useState<ImageConfig["video_provider"]>("mock");
  const [videoModel, setVideoModel] = useState("agnes-video-2.5-flash");
  const [saved, setSaved] = useState(false);
  // 未保存更改指示 + Agnes Key 缺失提醒（Key 与图像服务共用同一账号配置）
  const dirty =
    !!data && (videoProvider !== data.video_provider || videoModel !== (data.video_model ?? "agnes-video-2.5-flash"));
  const keyMissing = videoProvider === "agnes" && !!data && !data.api_key_set;
  const reset = () => {
    if (!data) return;
    setVideoProvider(data.video_provider);
    setVideoModel(data.video_model ?? "agnes-video-2.5-flash");
    setSaved(false);
  };

  // 保存成功提示 3.2s 后自动消失
  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), 3200);
    return () => clearTimeout(timer);
  }, [saved]);
  // 模型目录来自后端（GET /image/video-models），不在前端硬编码；只在 agnes 下需要
  const modelsQuery = useQuery({
    queryKey: queryKeys.videoModels,
    queryFn: () => api.get<VideoModelsResponse>("/image/video-models"),
    enabled: videoProvider === "agnes",
  });

  const loaded = data ? JSON.stringify([data.video_provider, data.video_model]) : "";
  useEffect(() => {
    if (data) {
      setVideoProvider(data.video_provider);
      setVideoModel(data.video_model ?? "agnes-video-2.5-flash");
      setSaved(false);
    }
  }, [loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () =>
      api.put<ImageConfig>("/image/config", { video_provider: videoProvider, video_model: videoModel.trim() }),
    onSuccess: (updated) => {
      queryClient.setQueryData<ImageConfig>(queryKeys.imageConfig, updated);
      setVideoProvider(updated.video_provider);
      setVideoModel(updated.video_model ?? "agnes-video-2.5-flash");
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: queryKeys.imageConfig });
      void queryClient.invalidateQueries({ queryKey: queryKeys.providers });
    },
  });

  // 下拉选项 = 后端目录（verified/available 转成可读标记）；目录未就绪/读取失败时
  // 至少保住当前已保存值，避免 select 悬空
  const videoModelOptions = modelsQuery.data?.models ?? [];
  const currentModel = videoModelOptions.find((m) => m.id === videoModel) ?? null;
  const savedModelOutsideCatalog =
    !modelsQuery.isPending && videoModel !== "" && !videoModelOptions.some((m) => m.id === videoModel);
  const videoModelLabel = (m: VideoModelInfo) => {
    const extra: string[] = [];
    if (m.label) extra.push(m.label);
    if (m.available === true) extra.push("实测可用");
    if (m.available === false) extra.push("不在账号可用列表");
    if (!m.verified && m.available !== true) extra.push("未验证");
    return extra.length ? `${m.id}（${extra.join(" · ")}）` : m.id;
  };

  return (
    <section className="provider-card">
      <div className="provider-card-head">
        <VideoCamera size={16} />
        <strong>视频服务</strong>
        {data && (
          <span className="badge neutral">{videoProvider === "agnes" ? "agnes · 真实视频" : "mock · 不可用"}</span>
        )}
      </div>

      {isLoading && <p className="muted small link-note">正在读取视频服务配置…</p>}
      {isError && <div className="error-banner">视频服务配置读取失败，请确认 Studio Service 已启动。</div>}

      {!isLoading && data && (
        <>
          <div className="settings-llm-grid">
            <div className="field">
              <label className="field-label" htmlFor="video-provider">
                Provider
              </label>
              <select
                id="video-provider"
                value={videoProvider}
                onChange={(e) => setVideoProvider(e.target.value as ImageConfig["video_provider"])}
              >
                <option value="mock">mock（占位，不可用）</option>
                <option value="agnes">agnes（真实云端视频，2.5-flash 当前免费）</option>
              </select>
              <span className="field-hint">视频为异步任务（提交 → 轮询 → 下载），约 1–2 分钟出片</span>
            </div>
            {videoProvider === "agnes" && keyMissing && (
              <div className="test-result warn" role="status">
                <WarningCircle size={14} weight="fill" />
                <span>尚未设置 Agnes API Key（视频与图像共用同一账号）。</span>
                <button type="button" className="btn secondary compact" onClick={() => onOpenTab("image")}>
                  去图像服务设置
                </button>
              </div>
            )}
            {videoProvider === "agnes" && (
              <div className="field">
                <span className="field-label">视频模型</span>
                <select aria-label="视频模型" value={videoModel} onChange={(e) => setVideoModel(e.target.value)}>
                  {savedModelOutsideCatalog && (
                    <option value={videoModel}>{`${videoModel}（当前保存 · 不在目录）`}</option>
                  )}
                  {videoModelOptions.map((m) => (
                    <option key={m.id} value={m.id}>
                      {videoModelLabel(m)}
                    </option>
                  ))}
                </select>
                <span className="field-hint">模型清单来自后端 /image/video-models 实测目录，不在前端硬编码</span>
              </div>
            )}
            {videoProvider === "agnes" && modelsQuery.isPending && (
              <p className="muted small link-note">正在读取视频模型目录…</p>
            )}
            {videoProvider === "agnes" && modelsQuery.isError && (
              <p className="muted small link-note">模型目录读取失败，仅保留当前已保存模型。</p>
            )}
            {videoProvider === "agnes" && currentModel?.available === false && (
              <div className="test-result warn" role="status">
                <WarningCircle size={14} weight="fill" />
                <span>{currentModel.id} 不在该账号可用模型列表，生成会失败；建议切回 agnes-video-2.5-flash。</span>
              </div>
            )}
          </div>
          {/* 说明钉在卡底（.settings-duo 等高拉伸时吸收高度差） */}
          <p className="muted small link-note">
            视频为异步任务（提交 → 轮询 → 下载），在镜头检查器点「生成视频」发起，约 1–2 分钟出片； Agnes Key
            与「图像服务」Tab 共用同一账号。
          </p>
        </>
      )}

      <SettingsActionBar
        dirty={dirty}
        saved={saved}
        savePending={save.isPending}
        onSave={() => save.mutate()}
        onReset={reset}
      />

      {save.isError && <ApiErrorPanel error={save.error} />}
    </section>
  );
}
