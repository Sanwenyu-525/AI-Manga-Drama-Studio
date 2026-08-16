// P6-T016/AssetBrowser endpoint switch - project-scoped asset listing (parallel
// backend task added GET /projects/{id}/assets -> {total, items} and GET /assets/{id}).
// The old client-side aggregation (tree + per-shot versions + masters) is dropped in
// favour of the server endpoint. A server "type" filter param narrows image/video;
// source groups (storyboard/character/location) refine client-side on source_type.
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { AssetListRead, AssetRead } from "../../api/types";

export type AssetSource = "storyboard" | "character" | "location";

export type AssetTypeFilter = "all" | "image" | "video";

export interface ProjectAssetEntry {
  id: string;
  mediaType: string;
  source: AssetSource;
  label: string;
  versionNumber: number | null;
  isActive: boolean;
  isMaster: boolean;
  createdAt: string;
  checksum: string | null;
}

export interface ProjectAssetLibrary {
  assets: ProjectAssetEntry[];
  total: number;
  isLoading: boolean;
}

export function useProjectAssetLibrary(projectId: string, typeFilter: AssetTypeFilter | null = null): ProjectAssetLibrary {
  const typeParam = typeFilter === "all" || typeFilter === null ? null : typeFilter;
  const path = typeParam ? "/projects/" + projectId + "/assets?type=" + typeParam : "/projects/" + projectId + "/assets";
  const query = useQuery({
    queryKey: queryKeys.projectAssets(projectId, typeParam),
    queryFn: () => api.get<AssetListRead>(path),
    enabled: Boolean(projectId),
  });

  const items = query.data?.items ?? [];
  const assets = items.map(toEntry);
  return { assets, total: query.data?.total ?? items.length, isLoading: query.isLoading };
}

function toEntry(asset: AssetRead): ProjectAssetEntry {
  const source = sourceFromType(asset.source_type);
  const isMaster = asset.source_type === "character_master" || asset.source_type === "location_master";
  return {
    id: asset.id,
    mediaType: asset.type,
    source,
    label: asset.name || assetLabel(asset.id, asset.type),
    versionNumber: asset.version_number,
    isActive: asset.status === "active" || asset.status === "ready",
    isMaster,
    createdAt: asset.created_at,
    checksum: asset.checksum,
  };
}

function sourceFromType(sourceType: string): AssetSource {
  if (sourceType === "character_master") return "character";
  if (sourceType === "location_master") return "location";
  return "storyboard";
}

function assetLabel(id: string, type: string): string {
  const kind = type === "video" ? "视频" : "图片";
  return kind + " " + id.slice(-6).toUpperCase();
}
