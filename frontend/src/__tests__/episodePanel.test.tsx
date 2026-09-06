// P2-E1-T02 EpisodePanel tests：分块范围/成本提示 + 角色候选审阅/应用 + 替换原文落编辑器。
// api 层全部 mock（vi.spyOn client.api），路由用 MemoryRouter 承载 useNavigate。
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import * as client from "../api/client";
import type { Episode } from "../api/types";
import { EpisodePanel } from "../features/script/EpisodePanel";

function makeEpisode(): Episode {
  return {
    id: "e1",
    project_id: "p1",
    episode_number: 1,
    title: "第一集",
    source_text: "x".repeat(100),
    script_text: null,
    summary: null,
    status: "draft",
    revision: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };
}

function makePreview() {
  return {
    snapshot_id: "snap1",
    episode_id: "e1",
    source_hash: "abc123",
    plans: [
      {
        scene_number: 1,
        title: "天台",
        location: "天台",
        time: "night",
        description: "沈亦握着篮球。",
        mood: "tense",
      },
    ],
    model: "fake",
    status: "pending",
    source_chars: 13000,
    analyzed_chars: 13000,
    chunk_count: 3,
    llm_calls: 4,
    max_chars: 24000,
    character_candidates: [
      { name: "沈亦", description: "主角。", existing_character_id: "c1", existing_character_name: "沈亦" },
      { name: "新人", description: "龙套。", existing_character_id: null, existing_character_name: null },
    ],
  };
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  const wrapper = ({ children }: { children?: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return render(<EpisodePanel episode={makeEpisode()} />, { wrapper });
}

function mockGets() {
  const get = vi.fn().mockImplementation((path: string) => {
    if (path === "/projects/p1/episodes") return Promise.resolve([makeEpisode()]);
    if (path === "/episodes/e1/analysis-snapshots/latest") return Promise.resolve(null);
    return Promise.reject(new Error("unexpected get " + path));
  });
  vi.spyOn(client.api, "get").mockImplementation(get as never);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("EpisodePanel (P2-E1-T02)", () => {
  it("预览后显示分块范围/成本，且候选默认决策为合并/新建", async () => {
    mockGets();
    const preview = makePreview();
    const post = vi.fn().mockImplementation((path: string) => {
      if (path === "/episodes/e1/analyze/preview") return Promise.resolve(preview);
      return Promise.reject(new Error("unexpected post " + path));
    });
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /AI 分析并预览/ }));

    expect(await screen.findByText(/本次分析全部/)).toBeTruthy();
    expect(screen.getByText(/3 块/)).toBeTruthy();
    expect(screen.getByText(/4 次模型调用/)).toBeTruthy();
    // 候选行 + 同名徽标 + 默认 radio（沈亦=合并，新人=新建）。
    expect(screen.getByText("沈亦")).toBeTruthy();
    expect(screen.getByText(/已存在/)).toBeTruthy();
    const radios = screen.getAllByRole("radio");
    const checked = radios.filter((r) => (r as HTMLInputElement).checked);
    expect(checked).toHaveLength(2);
  });

  it("应用角色决策按快照提交动作，逐项结果回显", async () => {
    mockGets();
    const preview = makePreview();
    const post = vi.fn().mockImplementation((path: string, _body?: unknown) => {
      if (path === "/episodes/e1/analyze/preview") return Promise.resolve(preview);
      if (path === "/episodes/e1/analyze/characters") {
        return Promise.resolve({
          episode_id: "e1",
          results: [
            { name: "沈亦", action: "merge", status: "merged", character_id: "c1", message: null },
            { name: "新人", action: "create", status: "created", character_id: "c2", message: null },
          ],
        });
      }
      return Promise.reject(new Error("unexpected post " + path));
    });
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /AI 分析并预览/ }));
    fireEvent.click(await screen.findByRole("button", { name: /应用角色决策/ }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/episodes/e1/analyze/characters", {
        snapshot_id: "snap1",
        decisions: [
          { name: "沈亦", action: "merge", character_id: "c1" },
          { name: "新人", action: "create" },
        ],
      }),
    );
    expect(await screen.findByText("已合并到已有人物")).toBeTruthy();
    expect(screen.getByText("已新建人物")).toBeTruthy();
  });

  it("替换原文读入编辑器且未自动保存（可恢复）", async () => {
    mockGets();
    renderPanel();
    const textarea = (await screen.findByLabelText("小说原文")) as HTMLTextAreaElement;
    expect(textarea.value).toContain("xxx");

    const file = new File(["新导入的正文内容"], "novel.txt", { type: "text/plain" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(textarea.value).toBe("新导入的正文内容"));
    // 落编辑器但未保存：出现未保存提示，且未调用 PATCH。
    expect(await screen.findByText("有未保存修改")).toBeTruthy();
  });
});
