// P6-T016 — project asset library aggregation hook.
//
// The backend exposes no GET /projects/{id}/assets listing endpoint, so this
// aggregates the project's media on the client from the read models that DO exist:
//   - /projects/{id}/tree         → episodes/scenes/shots (P2-T011)
//   - /shots/{id}/versions        → per-shot produced asset versions (ADR-001)
//   - character/location versions → MASTER reference images (P2-T007/T009)
//
// This is a documented limitation: the grid reflects only assets reachable from
// these read models (produced shot images + character/location masters). Directly
// imported standalone assets that are not referenced by any of the above are not
// enumerated until the backend ships a project-scoped asset listing endpoint.
import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { AssetVersionRead, Character, CharacterVersion, Location, LocationVersion, ProjectTreeRead } from "../../api/types";

export type AssetSource = "storyboard" | "character" | "location";

export interface ProjectAssetEntry {
  /** asset id (self-versioned, ADR-001) */
  id: string;
  /** media type from the version (image / video) */
  mediaType: string;
  /** where the asset is referenced from */
  source: AssetSource;
  /** human label of the owning frame, e.g. "EP01 · SC03 · SH005" or "角色 沈亦" */
  label: string;
  versionNumber: number;
  isActive: boolean;
  isMaster: boolean;
  createdAt: string;
  /** checksum, only known for character/location version assets (their DTO carries it) */
  checksum?: string | null;
}

export interface ProjectAssetLibrary {
  assets: ProjectAssetEntry[];
  isLoading: boolean;
}

export function useProjectAssetLibrary(projectId: string): ProjectAssetLibrary {
  // 1) Project navigation tree → shot ids (and the character/location reference lists).
  const treeQuery = useQuery({
    queryKey: queryKeys.projectTree(projectId),
    queryFn: () => api.get<ProjectTreeRead>(`/projects/${projectId}/tree`),
  });
  const charactersQuery = useQuery({
    queryKey: queryKeys.characters(projectId),
    queryFn: () => api.get<Character[]>(`/projects/${projectId}/characters`),
  });
  const locationsQuery = useQuery({
    queryKey: queryKeys.locations(projectId),
    queryFn: () => api.get<Location[]>(`/projects/${projectId}/locations`),
  });

  // 2) Per-shot ids flattened from the tree.
  const shots = useMemo(() => {
    const out: { shotId: string; episodeNumber: number; sceneNumber: number; shotNumber: number }[] = [];
    for (const ep of treeQuery.data?.episodes ?? []) {
      for (const sc of ep.scenes ?? []) {
        for (const sh of sc.shots ?? []) {
          out.push({ shotId: sh.id, episodeNumber: ep.episode_number, sceneNumber: sc.scene_number, shotNumber: sh.shot_number });
        }
      }
    }
    return out;
  }, [treeQuery.data]);

  // 3) Per-shot versions + character/location versions (MASTER references).
  const shotVersionQueries = useQueries({
    queries: shots.map((shot) => ({
      queryKey: ["versions", shot.shotId],
      queryFn: () => api.get<AssetVersionRead[]>(`/shots/${shot.shotId}/versions`),
      enabled: Boolean(shot.shotId),
    })),
  });
  const characterVersionQueries = useQueries({
    queries: (charactersQuery.data ?? []).map((c) => ({
      queryKey: queryKeys.characterVersions(c.id),
      queryFn: () => api.get<CharacterVersion[]>(`/characters/${c.id}/versions`),
      enabled: Boolean(c.id),
    })),
  });
  const locationVersionQueries = useQueries({
    queries: (locationsQuery.data ?? []).map((l) => ({
      queryKey: queryKeys.locationVersions(l.id),
      queryFn: () => api.get<LocationVersion[]>(`/locations/${l.id}/versions`),
      enabled: Boolean(l.id),
    })),
  });

  const assets = useMemo(() => {
    const entries: ProjectAssetEntry[] = [];
    const push = (e: Omit<ProjectAssetEntry, "createdAt"> & { createdAt?: string }) => {
      const withCreated: ProjectAssetEntry = {
        id: e.id,
        mediaType: e.mediaType,
        source: e.source,
        label: e.label,
        versionNumber: e.versionNumber,
        isActive: e.isActive,
        isMaster: e.isMaster,
        checksum: e.checksum,
        createdAt: e.createdAt ?? "",
      };
      entries.push(withCreated);
    };
    // shots → produced versions
    shots.forEach((shot, idx) => {
      const data = shotVersionQueries[idx]?.data;
      (data ?? []).forEach((v) => {
        const label = `EP${String(shot.episodeNumber).padStart(2, "0")} · SC${String(shot.sceneNumber).padStart(2, "0")} · SH${String(shot.shotNumber).padStart(3, "0")}`;
        push({ id: v.asset_id, mediaType: v.media_type, source: "storyboard", label, versionNumber: v.version_number, isActive: v.is_active, isMaster: false, createdAt: v.created_at });
      });
    });
    // character masters
    const chars = charactersQuery.data ?? [];
    characterVersionQueries.forEach((q, idx) => {
      const char = chars[idx];
      (q.data ?? []).forEach((v) => {
        if (!v.is_master) return;
        push({ id: v.asset_id, mediaType: "image", source: "character", label: `角色 · ${char?.name ?? v.name ?? "角色"}`, versionNumber: v.version_number, isActive: v.status === "active", isMaster: true, createdAt: v.created_at, checksum: v.checksum });
      });
    });
    // location masters
    const locs = locationsQuery.data ?? [];
    locationVersionQueries.forEach((q, idx) => {
      const loc = locs[idx];
      (q.data ?? []).forEach((v) => {
        if (!v.is_master) return;
        push({ id: v.asset_id, mediaType: "image", source: "location", label: `地点 · ${loc?.name ?? v.name ?? "地点"}`, versionNumber: v.version_number, isActive: v.status === "active", isMaster: true, createdAt: v.created_at, checksum: v.checksum });
      });
    });

    // de-duplicate by asset id (a master reference may also appear as a shot input)
    const seen = new Set<string>();
    const unique = entries.filter((e) => (seen.has(e.id) ? false : (seen.add(e.id), true)));
    unique.sort((a, b) => (a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0));
    return unique;
  }, [shots, shotVersionQueries, characterVersionQueries, locationVersionQueries, charactersQuery.data, locationsQuery.data]);

  const versionQueries = [...shotVersionQueries, ...characterVersionQueries, ...locationVersionQueries];
  const allPending = versionQueries.length > 0 && versionQueries.some((q) => q.isPending);
  return { assets, isLoading: treeQuery.isLoading || allPending };
}
