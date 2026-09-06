// P6-T016/AssetBrowser endpoint switch - project-scoped asset listing (parallel
// backend task added GET /projects/{id}/assets -> {total, items} and GET /assets/{id}).
// The old client-side aggregation (tree + per-shot versions + masters) is dropped in
// favour of the server endpoint. A server "asset_type" filter param narrows image/video;
// source groups (storyboard/character/location) refine client-side on source_type.
//
// P2-E2-T02: cursor pagination via useInfiniteQuery (opaque next_cursor, keyset —
// no dup/loss on concurrent inserts) + Error state passthrough for the list view.
import { useInfiniteQuery } from "@tanstack/react-query";
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
  isError: boolean;
  error: Error | null;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  refetch: () => void;
}

const PAGE_SIZE = 50;

export function useProjectAssetLibrary(
  projectId: string,
  typeFilter: AssetTypeFilter | null = null,
): ProjectAssetLibrary {
  const typeParam = typeFilter === "all" || typeFilter === null ? null : typeFilter;
  // Contract: the backend filter query param is `asset_type` (api/assets.py) —
  // a `?type=` param is silently ignored by FastAPI and the filter never applies.
  const basePath = typeParam
    ? "/projects/" + projectId + "/assets?asset_type=" + typeParam + "&limit=" + PAGE_SIZE
    : "/projects/" + projectId + "/assets?limit=" + PAGE_SIZE;
  const query = useInfiniteQuery({
    queryKey: queryKeys.projectAssets(projectId, typeParam),
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      api.get<AssetListRead>(
        pageParam ? basePath + "&cursor=" + encodeURIComponent(pageParam) : basePath,
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(projectId),
  });

  const items = (query.data?.pages ?? []).flatMap((page) => page.items);
  const assets = items.map(toEntry);
  return {
    assets,
    total: query.data?.pages[0]?.total ?? items.length,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    fetchNextPage: () => void query.fetchNextPage(),
    refetch: () => void query.refetch(),
  };
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
