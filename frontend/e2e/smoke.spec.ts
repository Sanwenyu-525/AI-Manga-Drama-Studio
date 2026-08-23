import { test, expect } from "@playwright/test";

// TASK-019 — E2E 冒烟：主路径一条（fake/mock 模式，无 GPU / 真实模型）。
//
// 走「新建项目 → 进入 Studio Shell」并断言关键 UI 收敛。用空白项目模式避开
// 小说导入/分析（分析依赖 LLM 编排，由后端 fake 覆盖，且属于后续扩展范围）。
// 核心目标：验证真实浏览器下 React 渲染 + Vite→后端 proxy + Query 数据取回链路。

const PROJECT_NAME = `E2E冒烟_${Date.now()}`;

test.describe("Studio 主路径冒烟", () => {
  test("新建空白项目并进入 Studio Shell", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(String(err)));

    // ---- 1. 打开新建项目页 ----
    await page.goto("/projects/new");
    await expect(page.locator(".new-project-page")).toBeVisible({ timeout: 15_000 });

    // ---- 2. 填名称 + 选"空白项目" ----
    const nameInput = page.locator('.project-form-column input[value], input[type="text"]').first();
    await nameInput.fill(PROJECT_NAME);
    await page.locator(".start-mode-card", { hasText: "空白项目" }).click();

    // ---- 3. 创建项目 → 进入 Studio Shell ----
    await page.locator("button.btn.primary", { hasText: "创建项目" }).click();

    // 导航到 /projects/:id/script（LegacyEpisodeRoute workspace=script）
    await page.waitForURL(/\/projects\/[^/]+(\/script)?$/, { timeout: 30_000 });

    // Shell 关键区域可见
    await expect(page.locator(".app-shell")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".explorer")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator(".top-bar")).toBeVisible({ timeout: 10_000 });

    // ---- 4. 无页面级横向滚动（R2 冒烟回归）----
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow, "Shell 不应产生页面级横向滚动").toBe(false);

    // ---- 5. 无前端运行时错误 ----
    expect(errors.filter((e) => !e.includes("net::ERR") && !e.includes("favicon"))).toEqual([]);
  });

  test("项目首页可读取到刚创建的项目", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".project-home-main")).toBeVisible({ timeout: 15_000 });

    // 名称出现在列表（可能需等 Query 取回）
    await expect(page.getByText(PROJECT_NAME).first()).toBeVisible({ timeout: 20_000 });
  });
});
