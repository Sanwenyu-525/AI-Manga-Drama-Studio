// M1 前端闭环 — ReferenceImagePicker：自动/手动/无三模式 + Provider 能力警告；
// generationSubmitErrorText：409 幂等门（同 shot+type 单飞行任务）友好文案。
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import * as client from "../api/client";
import {
  MAX_REFERENCE_IMAGES,
  ReferenceImagePicker,
  type ReferenceChoice,
} from "../features/storyboard/ReferenceImagePicker";
import { generationSubmitErrorText } from "../features/storyboard/ShotInspector";
import type { AssetListRead, ProviderStatus } from "../api/types";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

/** 受控组件的有状态测试壳：onChange 真实回流（记录每次上报值）。 */
function StatefulPicker({
  initial,
  calls,
  ...props
}: Omit<React.ComponentProps<typeof ReferenceImagePicker>, "value" | "onChange"> & {
  initial?: ReferenceChoice;
  calls?: ReferenceChoice[];
}) {
  const [value, setValue] = useState<ReferenceChoice>(initial ?? { mode: "auto", assetIds: [] });
  return (
    <ReferenceImagePicker
      {...props}
      value={value}
      onChange={(next) => {
        calls?.push(next);
        setValue(next);
      }}
    />
  );
}

const REFS = [
  { character_id: "char_1", character_name: "沈亦", version_id: "cv_1", asset_id: "ast_1" },
  { character_id: "char_2", character_name: "林晚", version_id: "cv_2", asset_id: "ast_2" },
];

const PROVIDERS: ProviderStatus[] = [
  { id: "mock", name: "Mock", type: "image", status: "ok", capabilities: { image_generation: true, reference_image: false } },
  { id: "comfyui", name: "ComfyUI", type: "image", status: "ok", capabilities: { image_generation: true, reference_image: true } },
];

const ASSET_LIBRARY: AssetListRead = {
  total: 4,
  items: [
    { id: "ast_1", type: "image", source_type: "character_master", name: "沈亦 MASTER", status: "active", version_number: 1, created_at: "" },
    { id: "ast_2", type: "image", source_type: "character_master", name: "林晚 MASTER", status: "active", version_number: 1, created_at: "" },
    { id: "ast_3", type: "image", source_type: "import", name: "ref_sheet.png", status: "ready", version_number: null, created_at: "" },
    { id: "ast_4", type: "image", source_type: "import", name: "extra.png", status: "ready", version_number: null, created_at: "" },
  ] as AssetListRead["items"],
};

function mockApi(overrides: Record<string, unknown> = {}) {
  const defaults: Record<string, unknown> = {
    "/shots/shot_1/reference-images": REFS,
    "/providers": PROVIDERS,
    "/image/config": { provider: "comfyui" },
    "/projects/proj_1/assets?asset_type=image&limit=50": ASSET_LIBRARY,
  };
  const table = { ...defaults, ...overrides };
  return vi.fn().mockImplementation((path: string) => {
    if (!(path in table)) throw new Error(`unexpected GET ${path}`);
    return Promise.resolve(table[path]);
  });
}

/** 渲染 StatefulPicker（onChange 真实回流 + 记录上报值）。 */
function renderPicker(
  overrides: Record<string, unknown> = {},
  initial: ReferenceChoice = { mode: "auto", assetIds: [] },
  props: Partial<React.ComponentProps<typeof ReferenceImagePicker>> = {},
) {
  const get = mockApi(overrides);
  vi.spyOn(client.api, "get").mockImplementation(get);
  const calls: ReferenceChoice[] = [];
  const { wrapper } = makeWrapper();
  const view = render(
    <StatefulPicker
      shotId="shot_1"
      projectId="proj_1"
      hasCastCharacters
      initial={initial}
      calls={calls}
      {...props}
    />,
    { wrapper },
  );
  return { get, calls, ...view };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ReferenceImagePicker（自动模式）", () => {
  it("展示自动解析的角色 MASTER 参考图（缩略图 + 角色名）", async () => {
    renderPicker();
    expect(await screen.findByText("沈亦")).toBeTruthy();
    expect(screen.getByText("林晚")).toBeTruthy();
    expect(screen.getAllByRole("img").length).toBe(2);
  });

  it("超出引擎上限时提示仅注入前 3 张", async () => {
    renderPicker({
      "/shots/shot_1/reference-images": [...REFS, { character_id: "c3", character_name: "甲", version_id: "v3", asset_id: "a3" }, { character_id: "c4", character_name: "乙", version_id: "v4", asset_id: "a4" }],
    });
    await screen.findByText("乙");
    expect(screen.getByText(new RegExp(`最多注入前 ${MAX_REFERENCE_IMAGES} 张`))).toBeTruthy();
  });

  it("无解析结果且已关联角色时，引导去角色库上传 MASTER", async () => {
    renderPicker({ "/shots/shot_1/reference-images": [] });
    expect(await screen.findByText(/MASTER 参考图版本/)).toBeTruthy();
  });

  it("无解析结果且未关联角色时，提示先勾选出场角色", async () => {
    const get = mockApi({ "/shots/shot_1/reference-images": [] });
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(
      <ReferenceImagePicker shotId="shot_1" projectId="proj_1" hasCastCharacters={false} value={{ mode: "auto", assetIds: [] }} onChange={() => {}} />,
      { wrapper },
    );
    expect(await screen.findByText(/未关联出场角色/)).toBeTruthy();
  });

  it("默认引擎无参考图能力且有参考图时给出警告；有能力的引擎不警告", async () => {
    // 默认引擎 = mock（无能力）
    renderPicker({ "/image/config": { provider: "mock" } });
    expect(await screen.findByText(/不支持参考图注入/)).toBeTruthy();
    cleanup();
    // 默认引擎 = comfyui（有能力）→ 无警告
    renderPicker({ "/image/config": { provider: "comfyui" } });
    await screen.findByText("沈亦");
    expect(screen.queryByText(/不支持参考图注入/)).toBeNull();
  });

  it("显式传入 provider 时以其能力为准（agnes 显式选择 → 警告）", async () => {
    const providers: ProviderStatus[] = [
      ...PROVIDERS,
      { id: "agnes", name: "Agnes", type: "image", status: "ok", capabilities: { image_generation: true, reference_image: false } },
    ];
    renderPicker({ "/providers": providers }, undefined, { provider: "agnes" });
    expect(await screen.findByText(/不支持参考图注入/)).toBeTruthy();
  });

  it("自动模式同时展示角色与场景地点参考图（地点带「场景」徽标）", async () => {
    const refs = [
      { character_id: "char_1", character_name: "沈亦", version_id: "cv_1", asset_id: "ast_1" },
      { location_id: "loc_1", location_name: "天台", version_id: "lv_1", asset_id: "ast_9" },
    ];
    renderPicker({ "/shots/shot_1/reference-images": refs });
    expect(await screen.findByText("沈亦")).toBeTruthy();
    expect(screen.getByText("场景")).toBeTruthy(); // 地点徽标
    expect(screen.getByText("天台")).toBeTruthy();
    const thumbs = screen.getAllByRole("img");
    expect(thumbs.length).toBe(2);
    // 地点缩略图带 distinct 类（场景一致性视觉区分）
    expect(thumbs[1].closest("figure")?.classList.contains("reference-thumb-location")).toBe(true);
  });

  it("仅场景绑定地点（无角色）时，自动模式展示地点参考图", async () => {
    const refs = [
      { location_id: "loc_2", location_name: "更衣室", version_id: "lv_2", asset_id: "ast_10" },
    ];
    renderPicker({ "/shots/shot_1/reference-images": refs }, undefined, { hasCastCharacters: false } as never);
    expect(await screen.findByText("更衣室")).toBeTruthy();
    expect(screen.getByText("场景")).toBeTruthy();
  });
});

describe("ReferenceImagePicker（手动 / 无模式）", () => {
  it("手动模式从项目图片资产选择，按点击顺序上报 assetIds，上限 3 张", async () => {
    const { calls } = renderPicker({}, { mode: "manual", assetIds: [] });
    // 等资产库加载
    const third = await screen.findByText("ref_sheet.png");
    expect(screen.getByText("沈亦 MASTER")).toBeTruthy();

    fireEvent.click(screen.getByText("沈亦 MASTER").closest("button")!);
    fireEvent.click(third.closest("button")!);
    fireEvent.click(screen.getByText("林晚 MASTER").closest("button")!);
    // 已满 3：第 4 个按钮禁用
    expect((screen.getByText("extra.png").closest("button") as HTMLButtonElement).disabled).toBe(true);

    expect(calls[calls.length - 1]).toEqual({ mode: "manual", assetIds: ["ast_1", "ast_3", "ast_2"] });
    expect(screen.getByText(new RegExp(`已选 3/${MAX_REFERENCE_IMAGES}`))).toBeTruthy();
  });

  it("手动模式取消选择后，被禁用的资产恢复可选", async () => {
    const { calls } = renderPicker({}, { mode: "manual", assetIds: ["ast_1", "ast_2", "ast_3"] });
    await screen.findByText("extra.png");
    expect((screen.getByText("extra.png").closest("button") as HTMLButtonElement).disabled).toBe(true);
    // 取消已选第 1 张 → 剩 2 张，extra.png 恢复可选
    fireEvent.click(screen.getByText("沈亦 MASTER").closest("button")!);
    expect(calls[calls.length - 1]).toEqual({ mode: "manual", assetIds: ["ast_2", "ast_3"] });
    expect((screen.getByText("extra.png").closest("button") as HTMLButtonElement).disabled).toBe(false);
  });

  it("切换到「无」模式：onChange 上报 mode=none（生成请求将显式传空数组）", async () => {
    const { calls } = renderPicker();
    await screen.findByText("沈亦");
    fireEvent.click(screen.getByRole("button", { name: "无" }));
    expect(calls[calls.length - 1]).toEqual({ mode: "none", assetIds: [] });
    expect(await screen.findByText(/不注入参考图/)).toBeTruthy();
  });

  it("手动模式选满 3 张时未选资产禁用，但已选资产仍可取消", async () => {
    renderPicker({}, { mode: "manual", assetIds: ["ast_1", "ast_2", "ast_3"] });
    await screen.findByText("extra.png");
    // 已选资产不会被禁用（可取消）
    expect((screen.getByText("沈亦 MASTER").closest("button") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("generationSubmitErrorText（409 幂等门）", () => {
  it("CONFLICT → 引导查看进行中任务，而非「生成失败」", () => {
    const err = new ApiError(409, { error: { code: "CONFLICT", message: "already queued", details: {} } });
    const text = generationSubmitErrorText(err);
    expect(text).toContain("进行中");
    expect(text).not.toContain("生成失败");
  });

  it("其他错误保持通用失败文案", () => {
    const err = new ApiError(500, { error: { code: "INTERNAL", message: "boom", details: {} } });
    expect(generationSubmitErrorText(err)).toContain("生成失败");
    expect(generationSubmitErrorText(new Error("network"))).toContain("生成失败");
  });
});
