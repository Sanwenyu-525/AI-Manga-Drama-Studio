// P6-T013/T014/T015 — EntityVersionBlock: the reusable version editor backing both
// the Character Library and Location Library. It lists a character/location's visual
// versions, lets the user import a reference image (multipart POST /assets/import),
// register it as a new version (stale by default) and promote any version to MASTER
// (POST .../versions/{id}/activate). The two entity kinds only differ in the API
// path shape, hence a tiny endpoint table below.
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Star, UploadSimple } from "@phosphor-icons/react";
import { api } from "../../api/client";
import { ApiErrorPanel } from "../../components/ApiErrorPanel";
import { queryKeys } from "../../api/queryKeys";
import type { AssetRead, CharacterVersion, LocationVersion } from "../../api/types";
import { deriveEntityVersionBadges, newestVersionId, type LibraryKind } from "./libraryBadges";

interface EntityVersionBlockProps {
  kind: LibraryKind;
  entityId: string;
  projectId: string;
}

// Endpoint path builders per entity kind (no backend changes — these routes exist).
const VERSION_LIST: Record<LibraryKind, string> = {
  character: "/characters/",
  location: "/locations/",
};

export function EntityVersionBlock({ kind, entityId, projectId }: EntityVersionBlockProps) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const base = VERSION_LIST[kind];
  const versionsKey =
    kind === "character" ? queryKeys.characterVersions(entityId) : queryKeys.locationVersions(entityId);

  const {
    data: versions,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: versionsKey,
    queryFn: () => api.get<LocationVersion[] | CharacterVersion[]>(`${base}${entityId}/versions`),
  });

  // 1) Import the chosen reference image as a project-scope asset (multipart).
  const importAsset = useMutation<AssetRead, Error, File>({
    mutationFn: async (file) => {
      const form = new FormData();
      form.append("file", file);
      form.append("asset_type", "image");
      form.append("purpose", kind === "character" ? "character_reference" : "location_reference");
      form.append("source_name", file.name);
      return api.upload<AssetRead>(`/projects/${projectId}/assets/import`, form);
    },
  });

  // 2) Register the imported asset as a new (stale) visual version.
  const createVersion = useMutation<LocationVersion | CharacterVersion, Error, string>({
    mutationFn: (assetId) => api.post(`${base}${entityId}/versions`, { asset_id: assetId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: versionsKey });
      setFileName(null);
      if (fileRef.current) fileRef.current.value = "";
    },
  });

  // 3) Promote a version to MASTER (explicit action).
  const activate = useMutation<LocationVersion | CharacterVersion, Error, string>({
    mutationFn: (versionId) => api.post(`${base}${entityId}/versions/${versionId}/activate`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: versionsKey });
    },
  });

  const uploading = importAsset.isPending || createVersion.isPending;
  const newestId = newestVersionId((versions ?? []) as LocationVersion[] | CharacterVersion[]);
  const mutateError = importAsset.error ?? createVersion.error;

  return (
    <div className="library-version-block">
      {isLoading && <span className="tree-muted-item">正在读取版本…</span>}
      {isError && error && <ApiErrorPanel error={error} />}

      {!isLoading && !isError && (
        <div className="version-card-list library-version-list">
          {(versions ?? []).length === 0 && (
            <span className="tree-muted-item">还没有视觉版本。上传参考图创建 v1。</span>
          )}
          {(versions ?? []).map((version) => {
            const badges = deriveEntityVersionBadges(version, newestId === version.id);
            return (
              <div key={version.id} className={`version-card library-version-row ${version.is_master ? "master" : ""}`}>
                <img src={`/api/v1/assets/${version.asset_id}/thumbnail`} alt={`V${version.version_number}`} />
                <span className="library-version-meta">
                  <strong>
                    V{version.version_number}
                    {version.name ? ` · ${version.name}` : ""}
                  </strong>
                  <small>{formatDate(version.created_at)}</small>
                </span>
                <span className="library-version-right">
                  {badges.map((badge) => (
                    <span key={badge.kind} className={`badge ${badge.tone}`}>
                      {badge.label}
                    </span>
                  ))}
                  {!version.is_master && (
                    <button
                      type="button"
                      className="btn primary tiny"
                      disabled={activate.isPending}
                      onClick={() => activate.mutate(version.id)}
                      title="把这个版本设为权威 MASTER"
                    >
                      <Star size={12} weight="fill" /> 设 MASTER
                    </button>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}

      <div className="library-import-row">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          style={{ display: "none" }}
          aria-hidden="true"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setFileName(file.name);
            importAsset.mutate(file, { onSuccess: (asset) => createVersion.mutate(asset.id) });
          }}
        />
        <button
          type="button"
          className="btn secondary tiny"
          disabled={uploading}
          onClick={() => fileRef.current?.click()}
          title="导入一张图片作为参考图并创建新版本"
        >
          <UploadSimple size={13} /> {uploading ? "上传中…" : "上传参考图 → 新版本"}
        </button>
        {fileName && <span className="tree-muted-item import-file-name">{fileName}</span>}
      </div>
      {mutateError && <ApiErrorPanel error={mutateError} />}
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
