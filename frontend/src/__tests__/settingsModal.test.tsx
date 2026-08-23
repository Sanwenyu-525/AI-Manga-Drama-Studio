// P3 settings modal test: renders the form from the settings query and
// submits a PUT with the edited values. Mocks the api client (no network/backend).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectSettingsModal } from "../features/settings/ProjectSettingsModal";
import * as client from "../api/client";
import type { ProjectSettings } from "../api/types";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const settings: ProjectSettings = {
  project_id: "proj_1",
  language: "zh-CN",
  default_llm_provider: "openai",
  default_llm_model: "gpt-4o-mini",
  default_image_provider: "mock",
  default_image_model: null,
  default_video_provider: null,
  default_video_model: null,
  default_voice_provider: null,
  default_voice_model: null,
  default_image_workflow_id: "default_image_api",
  default_video_workflow_id: null,
  auto_retry: 1,
  max_retry_count: 3,
  auto_save: 1,
  continuity_enabled: 1,
  auto_activate_new_generation: 0,
  settings_json: null,
  updated_at: "2026-08-01T00:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ProjectSettingsModal", () => {
  it("renders the loaded settings into the form fields", async () => {
    const get = vi.fn().mockResolvedValue(settings);
    vi.spyOn(client.api, "get").mockImplementation(get);
    const { wrapper } = makeWrapper();
    render(<ProjectSettingsModal projectId="proj_1" open onClose={() => {}} />, { wrapper });
    await screen.findByDisplayValue("openai");
    expect(screen.getByDisplayValue("default_image_api")).toBeTruthy();
    expect(screen.getByText("生成行为")).toBeTruthy();
    expect(get).toHaveBeenCalledWith("/projects/proj_1/settings");
  });

  it("shows a loading state before settings arrive", () => {
    vi.spyOn(client.api, "get").mockReturnValue(new Promise(() => {}));
    const { wrapper } = makeWrapper();
    render(<ProjectSettingsModal projectId="proj_1" open onClose={() => {}} />, { wrapper });
    expect(screen.getByText("正在读取项目设置…")).toBeTruthy();
  });

  it("disables the save button until the form is dirty, then PUTs the update", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(settings);
    const put = vi.fn().mockResolvedValue({ ...settings, language: "ja" });
    vi.spyOn(client.api, "put").mockImplementation(put);
    const { wrapper } = makeWrapper();
    render(<ProjectSettingsModal projectId="proj_1" open onClose={() => {}} />, { wrapper });
    await screen.findByDisplayValue("openai");
    const saveBtn = screen.getByText("保存设置").closest("button")!;
    expect(saveBtn.disabled).toBe(true);
    fireEvent.change(screen.getByDisplayValue("zh-CN"), { target: { value: "ja" } });
    await waitFor(() => expect(screen.getByText("保存设置").closest("button")!.disabled).toBe(false));
    fireEvent.click(screen.getByText("保存设置").closest("button")!);
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    const [path, body] = put.mock.calls[0];
    expect(path).toBe("/projects/proj_1/settings");
    expect(body.language).toBe("ja");
    expect(body.auto_retry).toBe(1);
    expect(body.auto_save).toBe(1);
  });

  it("surfaces a backend save error via the error panel", async () => {
    vi.spyOn(client.api, "get").mockResolvedValue(settings);
    vi.spyOn(client.api, "put").mockRejectedValue(
      new client.ApiError(503, {
        error: { code: "SERVICE_UNAVAILABLE", message: "生成服务暂不可用", details: {} },
      }),
    );
    const { wrapper } = makeWrapper();
    render(<ProjectSettingsModal projectId="proj_1" open onClose={() => {}} />, { wrapper });
    await screen.findByDisplayValue("openai");
    fireEvent.change(screen.getByDisplayValue("zh-CN"), { target: { value: "en" } });
    await waitFor(() => expect(screen.getByText("保存设置").closest("button")!.disabled).toBe(false));
    fireEvent.click(screen.getByText("保存设置").closest("button")!);
    await screen.findByText("生成服务暂不可用");
  });
});
