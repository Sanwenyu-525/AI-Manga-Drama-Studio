// Settings page (功能版): backend-backed provider management. The ComfyUI
// "test connection" button hits POST /providers/comfyui/test (health + workflow
// preflight); the mock provider is a built-in and reports no test endpoint.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle, Plug, WarningCircle, XCircle } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { ProviderStatus } from "../../api/types";
import { Link, useLocation } from "react-router-dom";

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
            <span className="eyebrow">SETTINGS</span>
            <h1>设置</h1>
            <p>生成服务与连接状态 · 真实反映 Studio Service 的 Provider 注册表</p>
          </div>
          <div className="row gap">
            {(location.state as { fromProject?: string } | null)?.fromProject ? (
              <Link
                to={`/projects/${(location.state as { fromProject: string }).fromProject}`}
                className="btn secondary compact"
              >
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
