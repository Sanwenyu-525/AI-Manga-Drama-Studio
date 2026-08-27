// Settings page (功能版): backend-backed provider management. The ComfyUI
// "test connection" button hits POST /providers/comfyui/test (health + workflow
// preflight); the mock provider is a built-in and reports no test endpoint.

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle,
  Cpu,
  Plug,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { lastProjectId } from "../../lib/lastProject";
import type { ProviderStatus } from "../../api/types";
import { Link, useLocation } from "react-router-dom";

// LLM 运行时连接配置（mode/base_url/api_key/model）。api_key 始终只回传掩码，不回传明文。
interface LLMConfig {
  mode: "fake" | "openai";
  base_url: string | null;
  model: string;
  api_key_set: boolean;
  api_key_hint: string | null;
}

interface TestResult {
  connected: boolean;
  latency_ms: number | null;
  workflow: { id: string; status: string; error?: string } | null;
}

const STATUS_LABELS: Record<string, string> = {
  connected: "已连接",
  active: "使用中",
  unknown: "未检测",
  disconnected: "已断开",
  error: "异常",
};

export function SettingsPage() {
  const location = useLocation();
  const backProjectId = (location.state as { fromProject?: string } | null)?.fromProject ?? lastProjectId();
  const queryClient = useQueryClient();
  const [results, setResults] = useState<Record<string, TestResult | { error: string }>>({});

  const {
    data: providers,
    isLoading,
    isError,
  } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: () => api.get<ProviderStatus[]>("/providers"),
    refetchInterval: 10_000,
  });

  const test = useMutation({
    mutationFn: () => api.post<TestResult>("/providers/comfyui/test"),
    onSuccess: (result) => setResults((r) => ({ ...r, comfyui_local: result })),
    onError: (error) =>
      setResults((r) => ({ ...r, comfyui_local: { error: error instanceof Error ? error.message : String(error) } })),
  });

  const refresh = () => void queryClient.invalidateQueries({ queryKey: queryKeys.providers });

  return (
    <div className="project-console">
      <main className="project-home-main">
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

        {isLoading && <div className="home-loading">正在读取设置…</div>}
        {isError && <div className="error-banner">设置读取失败，请确认 Studio Service 已启动。</div>}

        <LlmConfigCard />

        {!isLoading && (
          <div className="settings-list">
            {(providers ?? []).map((provider) => {
              const result = results[provider.id];
              return (
                <section key={provider.id} className="provider-card">
                  <div className="provider-card-head">
                    <span className={`provider-dot ${provider.status}`} />
                    <strong>{provider.name}</strong>
                    <span
                      className={`badge ${provider.status === "active" ? "warn" : provider.status === "connected" ? "ok" : "neutral"}`}
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
                    ) : (
                      <span className="muted small">内置 Provider · 随 Studio Service 运行</span>
                    )}
                    {result && <TestResultView result={result} />}
                  </div>
                </section>
              );
            })}
          </div>
        )}

        <div className="settings-note">
          <span className="field-label">当前生成服务</span>
          <p>
            生成任务按创建时选定的 Provider 执行；<code>STUDIO_IMAGE_PROVIDER</code> 决定默认值（mock / comfyui）。连接
            ComfyUI 后建议先「测试连接」确认健康检查与默认工作流预检通过。
          </p>
        </div>
      </main>
    </div>
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
      return api.post<{ connected: boolean; mode: string; latency_ms?: number | null; detail?: string; models_count?: number; sample_models?: string[]; error?: string }>(
        "/llm/test",
        body,
      );
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

  return (
    <section className="provider-card">
      <div className="provider-card-head">
        <Cpu size={16} />
        <strong>LLM 连接</strong>
        {data && (
          <span className={`badge ${mode === "openai" ? "warn" : "neutral"}`}>
            {mode === "openai" ? "openai · 真实模型" : "fake · 无 key"}
          </span>
        )}
      </div>

      {isLoading && <p className="muted small link-note">正在读取 LLM 配置…</p>}
      {isError && <div className="error-banner">LLM 配置读取失败，请确认 Studio Service 已启动。</div>}

      {!isLoading && data && (
        <div className="settings-llm-grid">
          <label className="field">
            <span className="field-label">模式</span>
            <select value={mode} onChange={(e) => setMode(e.target.value as LLMConfig["mode"])}>
              <option value="fake">fake（开发/测试，确定性规则，无需 Key）</option>
              <option value="openai">openai（真实 OpenAI 兼容端点）</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Base URL</span>
            <input
              value={baseUrl}
              placeholder="如 https://api.deepseek.com 或 http://127.0.0.1:11434/v1"
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">
              模型
              {modelOptions.length > 0 && (
                <button
                  type="button"
                  className="text-link small"
                  onClick={() => void queryClient.invalidateQueries({ queryKey: ["llm-models"] })}
                  title="从已保存的端点重新拉取模型列表"
                >
                  刷新列表
                </button>
              )}
            </span>
            <input
              value={model}
              list="llm-model-options"
              placeholder={modelsQuery.isError ? "如 deepseek-chat（列表拉取失败，可手输）" : "如 deepseek-chat / qwen2"}
              onChange={(e) => setModel(e.target.value)}
            />
            <datalist id="llm-model-options">
              {modelOptions.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>
          <label className="field">
            <span className="field-label">API Key {data.api_key_set && <span className="llm-key-hint">{data.api_key_hint}</span>}</span>
            <input
              type="password"
              value={apiKey}
              autoComplete="off"
              placeholder={data.api_key_set ? "已设置（留空保持不变）" : "留空则跳过"}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>
          <div className="settings-llm-actions">
            <button
              className="btn primary compact"
              disabled={save.isPending}
              onClick={() => save.mutate()}
              title="保存 LLM 连接配置并重建网关"
            >
              {save.isPending ? "保存中…" : "保存 LLM 配置"}
            </button>
            <button
              type="button"
              className="btn secondary compact"
              disabled={test.isPending}
              onClick={() => test.mutate()}
              title={mode === "openai" || baseUrl.trim() ? "探测该连接（GET /models，失败时降级最小 chat 探测）" : "fake 模式无需连接"}
            >
              {test.isPending ? "测试中…" : "测试连接"}
            </button>
            {saved && (
              <span className="test-result ok">
                <CheckCircle size={14} weight="fill" /> 已保存
              </span>
            )}
          </div>

          {test.data && (
            <div className={`test-result ${test.data.connected ? "ok" : "fail"}`} role="status">
              {test.data.connected ? <CheckCircle size={14} weight="fill" /> : <WarningCircle size={14} weight="fill" />}
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

          <p className="muted small link-note">
            fake 用于开发/测试（确定性输出，无需 Key）；openai 接入真实模型需提供 Base URL。保存后模型下拉自动拉取 /models；
            测试连接可对未保存的表单值先行探测。切换后立即生效，无需重启。
          </p>
        </div>
      )}

      {save.isError && <ApiErrorPanel error={save.error} />}
    </section>
  );
}
