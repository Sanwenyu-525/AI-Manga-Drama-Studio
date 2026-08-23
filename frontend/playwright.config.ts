import { defineConfig, devices } from "@playwright/test";

// TASK-019 — E2E 冒烟配置。
//
// 运行主路径（fake/mock 模式，CI 无需 GPU/真实模型）：
//   1. 启动后端 FastAPI（STUDIO_LLM_MODE=fake, STUDIO_IMAGE_PROVIDER=mock 已为默认，
//      显式声明以表达"不需要真实外部依赖"）。
//   2. 启动前端 Vite（经 proxy 把 /api → 后端 17820）。
//   3. 用已缓存的 chromium 冒烟断言主路径 UI 收敛。
//
// 本地运行：cd frontend && npx playwright test --config=playwright.config.ts
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  fullyParallel: false, // 每个 server 只配一个项目主页冒烟，串行避免真实 DB 竞态
  workers: 1,
  outputDir: "./e2e-results",
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:17821",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "uv run uvicorn app.main:app --host 127.0.0.1 --port 17820",
      cwd: "../backend",
      url: "http://127.0.0.1:17820/api/v1/health",
      reuseExistingServer: false,
      timeout: 90_000,
      env: {
        STUDIO_LLM_MODE: "fake",
        STUDIO_IMAGE_PROVIDER: "mock",
        STUDIO_RENDER_PROVIDER: "mock",
      },
    },
    {
      command: "npm run dev",
      cwd: ".",
      url: "http://127.0.0.1:17821",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
