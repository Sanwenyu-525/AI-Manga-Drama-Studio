// C2 一键成片 PipelineBar tests（api-event-contract §15.1）：
// idle→一键成片(run,202)→waiting_confirm→确认计划并出图(confirm)→running/images→排片并渲染(finalize)→completed；
// failed→从断点恢复(resume)。202 长任务经 useOperationPolling 轮询 GET /operations/{id} mock 驱动。
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { Episode, PipelineRead, ScenePlan } from "../api/types";
import { PipelineBar } from "../features/pipeline/PipelineBar";

function makeEpisode(): Episode {
  return {
    id: "e1",
    project_id: "p1",
    episode_number: 1,
    title: "第一集",
    source_text: "x",
    script_text: null,
    summary: null,
    status: "draft",
    revision: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };
}

function makePipeline(overrides: Partial<PipelineRead> = {}): PipelineRead {
  return {
    id: "p1",
    episode_id: "e1",
    project_id: "p1",
    status: "waiting_confirm",
    current_stage: null,
    stages: {
      analyze: "done",
      shots: "pending",
      images: "pending",
      timeline: "pending",
      render: "pending",
    },
    snapshot_id: "snap1",
    error_message: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function makePlans(): ScenePlan[] {
  return [
    {
      scene_number: 1,
      title: "天台",
      location: "天台",
      time: "night",
      description: "沈亦握着篮球。",
      mood: "tense",
    },
  ];
}

function completedOperation(opId: string, result: unknown) {
  return {
    id: opId,
    type: "pipeline_analysis",
    project_id: "p1",
    status: "completed" as const,
    result: result as Record<string, unknown> | null,
    error: null,
  };
}

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  const wrapper = ({ children }: { children?: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PipelineBar", () => {
  it("idle: 一键成片 runs analysis and surfaces reviewed plans (202 → waiting_confirm)", async () => {
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/episodes/e1/pipeline/latest") return Promise.resolve(null);
      if (path === "/operations/op-run") {
        return Promise.resolve(
          completedOperation("op-run", {
            pipeline: makePipeline(),
            plans: makePlans(),
            pending_shot_ids: [],
          }),
        );
      }
      return Promise.reject(new Error("unexpected get " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get as never);
    const post = vi.fn().mockResolvedValue({ operation_id: "op-run" });
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    const onShowPlans = vi.fn();
    const { wrapper } = makeWrapper();
    render(<PipelineBar episode={makeEpisode()} onShowPlans={onShowPlans} />, { wrapper });

    expect(await screen.findByRole("button", { name: /一键成片/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /一键成片/ }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/episodes/e1/pipeline/run"));
    await waitFor(() => expect(onShowPlans).toHaveBeenCalledWith(makePlans(), "snap1"));
    expect(await screen.findByText("分析完成，请确认场景计划后继续生产。")).toBeTruthy();
  });

  it("waiting_confirm: 确认计划并出图 queues shots + images", async () => {
    const pipeline = makePipeline();
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/episodes/e1/pipeline/latest") return Promise.resolve(pipeline);
      if (path === "/operations/op-confirm") {
        return Promise.resolve(
          completedOperation("op-confirm", {
            pipeline: makePipeline({
              status: "running",
              current_stage: "images",
              stages: {
                analyze: "done",
                shots: "done",
                images: "done",
                timeline: "pending",
                render: "pending",
              },
            }),
            plans: null,
            pending_shot_ids: ["s1", "s2"],
          }),
        );
      }
      return Promise.reject(new Error("unexpected get " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get as never);
    const post = vi.fn().mockResolvedValue({ operation_id: "op-confirm" });
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    const { wrapper } = makeWrapper();
    render(<PipelineBar episode={makeEpisode()} onShowPlans={vi.fn()} />, { wrapper });

    expect(await screen.findByRole("button", { name: /确认计划并出图/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /确认计划并出图/ }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/episodes/e1/pipeline/p1/confirm"),
    );
    expect(await screen.findByText("已提交 2 张图片生成，完成后可排片渲染。")).toBeTruthy();
  });

  it("running/images: 排片并渲染 finalizes (timeline + render queue)", async () => {
    const pipeline = makePipeline({
      status: "running",
      current_stage: "images",
      stages: {
        analyze: "done",
        shots: "done",
        images: "done",
        timeline: "pending",
        render: "pending",
      },
    });
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/episodes/e1/pipeline/latest") return Promise.resolve(pipeline);
      return Promise.reject(new Error("unexpected get " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get as never);
    const post = vi.fn().mockResolvedValue({
      pipeline: makePipeline({
        status: "completed",
        current_stage: null,
        stages: {
          analyze: "done",
          shots: "done",
          images: "done",
          timeline: "done",
          render: "done",
        },
      }),
      plans: null,
      pending_shot_ids: [],
    });
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    const { wrapper } = makeWrapper();
    render(<PipelineBar episode={makeEpisode()} onShowPlans={vi.fn()} />, { wrapper });

    expect(await screen.findByRole("button", { name: /排片并渲染/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /排片并渲染/ }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/episodes/e1/pipeline/p1/finalize"),
    );
    expect(await screen.findByText("成片完成：已排片并提交渲染。")).toBeTruthy();
  });

  it("failed: 从断点恢复 resumes from the first non-done stage", async () => {
    const pipeline = makePipeline({ status: "failed", error_message: "boom" });
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/episodes/e1/pipeline/latest") return Promise.resolve(pipeline);
      if (path === "/operations/op-resume") {
        return Promise.resolve(
          completedOperation("op-resume", {
            pipeline: makePipeline({ status: "completed" }),
            plans: null,
            pending_shot_ids: [],
          }),
        );
      }
      return Promise.reject(new Error("unexpected get " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get as never);
    const post = vi.fn().mockResolvedValue({ operation_id: "op-resume" });
    vi.spyOn(client.api, "post").mockImplementation(post as never);

    const { wrapper } = makeWrapper();
    render(<PipelineBar episode={makeEpisode()} onShowPlans={vi.fn()} />, { wrapper });

    expect(await screen.findByRole("button", { name: /从断点恢复/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /从断点恢复/ }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/episodes/e1/pipeline/p1/resume"));
  });

  it("completed: shows the stage checkmarks and an idle 一键成片 to restart", async () => {
    const pipeline = makePipeline({
      status: "completed",
      current_stage: null,
      stages: {
        analyze: "done",
        shots: "done",
        images: "done",
        timeline: "done",
        render: "done",
      },
    });
    const get = vi.fn().mockImplementation((path: string) => {
      if (path === "/episodes/e1/pipeline/latest") return Promise.resolve(pipeline);
      return Promise.reject(new Error("unexpected get " + path));
    });
    vi.spyOn(client.api, "get").mockImplementation(get as never);

    const { wrapper } = makeWrapper();
    render(<PipelineBar episode={makeEpisode()} onShowPlans={vi.fn()} />, { wrapper });

    expect(await screen.findByRole("button", { name: /一键成片/ })).toBeTruthy();
    expect(screen.getByText("分析")).toBeTruthy();
    expect(screen.getByText("分镜")).toBeTruthy();
    expect(screen.getByText("出图")).toBeTruthy();
    expect(screen.getByText("排片")).toBeTruthy();
    expect(screen.getByText("渲染")).toBeTruthy();
    // completed pipeline exposes no action buttons besides restart
    expect(screen.queryByRole("button", { name: /确认计划并出图/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /排片并渲染/ })).toBeNull();
  });
});
