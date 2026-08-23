// P6-T022/023/024 — Job queue UI in the bottom dock: list + status badges, expandable
// task detail, per-status control buttons, recovery markers for interrupted jobs, and
// the task-count summary. Mocks the api client by path.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GenerationQueue } from "../features/generation/GenerationQueue";
import type { JobRead, JobSummaryRead } from "../api/types";
import * as client from "../api/client";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

function summary(over: Partial<JobSummaryRead> & { id: string }): JobSummaryRead {
  return {
    project_id: "proj_1",
    name: "Scene 01 render",
    job_type: "scene_generation",
    scene_id: "sc_1",
    status: "queued",
    progress: 0,
    error_summary: null,
    task_count: 2,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...over,
  };
}

const running = summary({ id: "job_running", status: "running", progress: 40, name: "Running job" });
const paused = summary({ id: "job_paused", status: "paused", progress: 55, name: "Paused job" });
const interrupted = summary({ id: "job_interrupted", status: "interrupted", progress: 30, name: "Interrupted job" });
const queued = summary({ id: "job_queued", status: "queued", name: "Queued job" });

function detail(s: JobSummaryRead): JobRead {
  return {
    ...s,
    task_status_counts: { queued: 1, completed: 1 },
    tasks: [
      {
        id: "task_1",
        job_id: s.id,
        task_type: "image",
        target_type: "shot",
        target_id: "shot_a",
        shot_id: "shot_a",
        status: "completed",
        priority: 1,
        progress: 100,
        generation_id: "gen_a",
        error_message: null,
        created_at: "",
        updated_at: "",
      },
      {
        id: "task_2",
        job_id: s.id,
        task_type: "image",
        target_type: "shot",
        target_id: "shot_b",
        shot_id: "shot_b",
        status: "failed",
        priority: 1,
        progress: 0,
        generation_id: "gen_b",
        error_message: "provider timeout",
        created_at: "",
        updated_at: "",
      },
    ],
  };
}

function mockJobs(list: JobSummaryRead[]) {
  vi.spyOn(client.api, "get").mockImplementation((path: string) => {
    if (path === "/projects/proj_1/jobs") return Promise.resolve(list);
    const m = path.match(/^\/jobs\/(.+)$/);
    if (m) {
      const found = list.find((j) => j.id === m[1]);
      return Promise.resolve(detail(found ?? list[0]));
    }
    if (path === "/generations/recent") return Promise.resolve([]);
    return Promise.resolve([]);
  });
  vi.spyOn(client.api, "post").mockImplementation(() => Promise.resolve({}));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("GenerationQueue Jobs tab", () => {
  it("renders the job list with status badges and a count summary", async () => {
    mockJobs([running, queued, paused]);
    const { wrapper } = makeWrapper();
    render(<GenerationQueue projectId="proj_1" />, { wrapper });
    // switch to the jobs tab
    fireEvent.click(screen.getByText("任务"));
    expect(await screen.findByText(/Running job/)).toBeTruthy();
    expect(screen.getByText(/Queued job/)).toBeTruthy();
    expect(screen.getByText(/Paused job/)).toBeTruthy();
    // task-count summary (P6-T024): running + queued job counts
    expect(screen.getByText("进行中 1")).toBeTruthy();
    expect(screen.getByText("排队 1")).toBeTruthy();
  });

  it("expands a job into its task table and shows failed task error", async () => {
    mockJobs([running]);
    const { wrapper } = makeWrapper();
    render(<GenerationQueue projectId="proj_1" />, { wrapper });
    fireEvent.click(screen.getByText("任务"));
    const head = await screen.findByText(/Running job/);
    fireEvent.click(head);
    // detail fetch → task status badge + failed error message
    expect(await screen.findByText(/provider timeout/)).toBeTruthy();
    expect(screen.getByText("完成")).toBeTruthy();
    expect(screen.getByText(/失败/)).toBeTruthy();
  });

  it("enables Pause/Resume/Cancel/Retry by job status and calls the right endpoint", async () => {
    const postSpy = vi.spyOn(client.api, "post").mockImplementation(() => Promise.resolve({}));
    vi.spyOn(client.api, "get").mockImplementation((path: string) => {
      if (path === "/projects/proj_1/jobs") return Promise.resolve([running, paused, interrupted]);
      if (path === "/generations/recent") return Promise.resolve([]);
      if (path.startsWith("/jobs/")) return Promise.resolve(detail(running));
      return Promise.resolve([]);
    });
    const { wrapper } = makeWrapper();
    render(<GenerationQueue projectId="proj_1" />, { wrapper });
    fireEvent.click(screen.getByText("任务"));
    await screen.findByText(/Running job/);

    // Running job row exposes Pause + Cancel; clicking Cancel hits /jobs/job_running/cancel
    const runningRow = screen.getByText(/Running job/).closest(".job-row") as HTMLElement;
    const cancelBtn = within(runningRow).getAllByText("取消")[0];
    fireEvent.click(cancelBtn);
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/jobs/job_running/cancel"), { timeout: 3000 });
    postSpy.mockClear();

    // Paused job exposes highlighted Resume → /jobs/job_paused/resume
    const pausedRow = screen.getByText(/Paused job/).closest(".job-row") as HTMLElement;
    fireEvent.click(within(pausedRow).getByText("恢复"));
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/jobs/job_paused/resume"), { timeout: 3000 });
  });

  it("shows the interrupted recovery marker with a downloadable hint", async () => {
    vi.spyOn(client.api, "get").mockImplementation((path: string) => {
      if (path === "/projects/proj_1/jobs") return Promise.resolve([interrupted]);
      if (path === "/generations/recent") return Promise.resolve([]);
      return Promise.resolve([]);
    });
    vi.spyOn(client.api, "post").mockImplementation(() => Promise.resolve({}));
    const { wrapper } = makeWrapper();
    render(<GenerationQueue projectId="proj_1" />, { wrapper });
    fireEvent.click(screen.getByText("任务"));
    // interrupted → ⚠ recovery badge with "可恢复"
    expect(await screen.findByText(/已中断 · 可恢复/)).toBeTruthy();
    // recovery hint + highlighted Resume are offered in the actions row
    expect(screen.getByText(/暂停 · 可恢复/)).toBeTruthy();
    expect(screen.getByText("恢复")).toBeTruthy();
  });
});
