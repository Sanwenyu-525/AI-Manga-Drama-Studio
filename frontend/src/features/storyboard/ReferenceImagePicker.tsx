// M1 + 自主迭代 03 前端闭环（P3 一致性预研 §5.2 + 场景一致性）：
// 生成前参考图可见、可控。自动模式解析 = 角色 MASTER（ShotCharacter→Character）
// + 场景地点 MASTER（Scene.location_id→Location），预览区分角色/地点。
//
// 三种模式（与后端 GenerationCreate.reference_asset_ids 语义一一对应）：
// - auto   缺省：ShotCharacter → 角色 MASTER + 场景地点 MASTER 自动解析（生成时不传该字段）
// - manual 手动：从项目图片资产自选（≤ MAX_REFERENCE_IMAGES 张，选择顺序 = 注入槽位顺序）
// - none   无  ：显式传空数组 —— 跳过参考图注入（调试纯 prompt 效果）
//
// Provider 能力感知：当前引擎（显式选择或系统默认）无 reference_image 能力时，
// 明确提示「生成时将忽略」——与 worker 的诚实降级行为对齐（不静默）。
import { useQuery } from "@tanstack/react-query";
import { ImagesSquare } from "@phosphor-icons/react";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { ProviderStatus, ShotReferenceRead } from "../../api/types";
import { assetUrl } from "../../lib/mediaUrl";
import { useProjectAssetLibrary } from "../assets/useProjectAssetLibrary";

export type ReferenceMode = "auto" | "manual" | "none";

export interface ReferenceChoice {
  mode: ReferenceMode;
  /** manual 模式下已选资产（选择顺序 = 注入槽位顺序）。 */
  assetIds: string[];
}

/** 与 worker MAX_REFERENCE_IMAGES（Z-Image Omni 三参考图上限）保持一致。 */
export const MAX_REFERENCE_IMAGES = 3;

const MODE_LABELS: Record<ReferenceMode, string> = {
  auto: "自动",
  manual: "手动",
  none: "无",
};

interface Props {
  shotId: string;
  projectId: string;
  /** 显式选择的引擎 id；undefined = 系统默认（/image/config 的 provider）。 */
  provider?: string;
  /** 已保存的镜头是否关联了出场角色（区分「未关联角色」与「角色无 MASTER」提示）。 */
  hasCastCharacters: boolean;
  value: ReferenceChoice;
  onChange: (next: ReferenceChoice) => void;
}

export function ReferenceImagePicker({ shotId, projectId, provider, hasCastCharacters, value, onChange }: Props) {
  const { data: refs } = useQuery({
    queryKey: queryKeys.shotReferences(shotId),
    queryFn: () => api.get<ShotReferenceRead[]>(`/shots/${shotId}/reference-images`),
  });
  const { data: providers } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: () => api.get<ProviderStatus[]>("/providers"),
  });
  const { data: imageConfig } = useQuery({
    queryKey: queryKeys.imageConfig,
    queryFn: () => api.get<{ provider: string }>("/image/config"),
  });
  const library = useProjectAssetLibrary(projectId, "image");

  const activeProvider = provider ?? imageConfig?.provider;
  const providerStatus = (providers ?? []).find((p) => p.id === activeProvider);
  // 未知 provider → undefined（不在此处警告，生成入口自会 422 fail-fast）
  const supportsReference = providerStatus
    ? providerStatus.capabilities?.reference_image === true
    : undefined;

  const refsCount = refs?.length ?? 0;
  const effectiveRefCount =
    value.mode === "manual" ? value.assetIds.length : value.mode === "none" ? 0 : refsCount;
  const showCapabilityWarn = supportsReference === false && effectiveRefCount > 0;

  const toggleAsset = (assetId: string) => {
    const selected = value.assetIds;
    if (selected.includes(assetId)) {
      onChange({ ...value, assetIds: selected.filter((id) => id !== assetId) });
    } else if (selected.length < MAX_REFERENCE_IMAGES) {
      onChange({ ...value, assetIds: [...selected, assetId] });
    }
    // 已满上限：忽略（禁用态已提示）
  };

  const switchMode = (mode: ReferenceMode) => {
    if (mode === value.mode) return;
    onChange({ mode, assetIds: mode === "manual" ? value.assetIds : [] });
  };

  return (
    <div className="reference-picker">
      <div className="reference-picker-head">
        <span className="field-label">
          <ImagesSquare size={14} /> 参考图（角色一致性）
        </span>
        <div className="reference-mode-row" role="group" aria-label="参考图模式">
          {(Object.keys(MODE_LABELS) as ReferenceMode[]).map((m) => (
            <button
              key={m}
              type="button"
              className={`reference-mode-btn ${value.mode === m ? "active" : ""}`}
              aria-pressed={value.mode === m}
              onClick={() => switchMode(m)}
            >
              {MODE_LABELS[m]}
            </button>
          ))}
        </div>
      </div>

      {value.mode === "auto" && (
        <div className="reference-body">
          {refsCount === 0 ? (
            <p className="reference-note">
              {hasCastCharacters
                ? "出场角色没有 MASTER 参考图版本 — 在活动栏「角色」页上传参考图并设为 MASTER 后，此处自动注入。"
                : "镜头未关联出场角色，场景也未绑定地点 — 在「角色/地点」勾选或绑定后，其 MASTER 参考图将自动注入。"}
            </p>
          ) : (
            <>
              <div className="reference-thumbs">
                {refs!.map((r) => {
                  const isLocation = r.location_id != null;
                  const label = isLocation ? r.location_name ?? "场景地点" : r.character_name ?? "角色";
                  return (
                    <figure
                      key={r.asset_id}
                      className={`reference-thumb ${isLocation ? "reference-thumb-location" : ""}`}
                      title={label}
                    >
                      <img src={assetUrl(r.asset_id, "thumbnail")} alt={label} />
                      <figcaption>
                        {isLocation && <span className="reference-kind-badge">场景</span>}
                        {label}
                      </figcaption>
                    </figure>
                  );
                })}
              </div>
              {refsCount > MAX_REFERENCE_IMAGES && (
                <p className="reference-note">
                  引擎最多注入前 {MAX_REFERENCE_IMAGES} 张（角色优先、地点兜底）— 如需指定请切换「手动」模式。
                </p>
              )}
            </>
          )}
        </div>
      )}

      {value.mode === "manual" && (
        <div className="reference-body">
          {library.isLoading ? (
            <p className="reference-note">正在加载项目图片资产…</p>
          ) : library.assets.length === 0 ? (
            <p className="reference-note">项目还没有图片资产。</p>
          ) : (
            <>
              <div className="reference-thumbs reference-thumbs-select">
                {library.assets.map((a) => {
                  const idx = value.assetIds.indexOf(a.id);
                  const full = idx === -1 && value.assetIds.length >= MAX_REFERENCE_IMAGES;
                  return (
                    <button
                      key={a.id}
                      type="button"
                      className={`reference-thumb reference-thumb-btn ${idx >= 0 ? "selected" : ""}`}
                      disabled={full}
                      title={full ? `最多选择 ${MAX_REFERENCE_IMAGES} 张` : a.label}
                      onClick={() => toggleAsset(a.id)}
                    >
                      <img src={assetUrl(a.id, "thumbnail")} alt={a.label} />
                      {idx >= 0 && <span className="reference-order">{idx + 1}</span>}
                      <span className="reference-thumb-caption">{a.label}</span>
                    </button>
                  );
                })}
              </div>
              <p className="reference-note">
                已选 {value.assetIds.length}/{MAX_REFERENCE_IMAGES} 张（编号 = 注入顺序）
              </p>
            </>
          )}
        </div>
      )}

      {value.mode === "none" && (
        <div className="reference-body">
          <p className="reference-note">本次生成不注入参考图（仅使用提示词）。</p>
        </div>
      )}

      {showCapabilityWarn && (
        <p className="reference-warn">
          当前引擎{providerStatus?.name ? `（${providerStatus.name}）` : ""}不支持参考图注入，生成时将忽略参考图
          — 可切换引擎为 ComfyUI 以启用一致性参考。
        </p>
      )}
    </div>
  );
}
