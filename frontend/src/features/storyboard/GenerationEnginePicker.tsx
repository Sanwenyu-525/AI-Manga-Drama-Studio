// P2-4 (Sprint 05): per-shot image engine picker (provider + workflow template).
//
// Lets the Storyboard Inspector explicitly choose which image engine drives a
// generation instead of always falling back to the runtime default. Both selects
// include a "default / auto" empty option so an untouched picker preserves the
// legacy behavior exactly (backend resolver + runtime image provider).
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type {
  ImageEngineChoice,
  ProviderStatus,
  WorkflowTemplateRead,
} from "../../api/types";

interface Props {
  value: ImageEngineChoice;
  onChange: (next: ImageEngineChoice) => void;
}

export function GenerationEnginePicker({ value, onChange }: Props) {
  const { data: providers } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: () => api.get<ProviderStatus[]>("/providers"),
  });
  const { data: workflows } = useQuery({
    queryKey: queryKeys.workflows,
    queryFn: () => api.get<WorkflowTemplateRead[]>("/workflows"),
  });

  const imageProviders = (providers ?? []).filter((p) => p.type === "image");
  const imageWorkflows = (workflows ?? []).filter((w) => {
    const t = w.workflow_type || "image";
    return t === "image" || t === "";
  });

  return (
    <div className="engine-picker">
      <label className="engine-picker-row">
        <span className="muted small">引擎</span>
        <select
          value={value.provider ?? ""}
          onChange={(e) => onChange({ ...value, provider: e.target.value || undefined })}
        >
          <option value="">使用默认</option>
          {imageProviders.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <label className="engine-picker-row">
        <span className="muted small">模板</span>
        <select
          value={value.workflow_id ?? ""}
          onChange={(e) => onChange({ ...value, workflow_id: e.target.value || undefined })}
        >
          <option value="">使用默认</option>
          {imageWorkflows.map((w) => {
            const wid = w.workflow_id ?? w.id;
            return (
              <option key={wid} value={wid}>
                {w.name ?? wid}
                {w.is_default ? "（默认）" : ""}
              </option>
            );
          })}
        </select>
      </label>
    </div>
  );
}