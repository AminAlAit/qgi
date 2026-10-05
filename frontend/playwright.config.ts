import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E config for qgintelligence.com (#439).
 *
 * Test flow philosophy (agreed with Amin 2026-04-24):
 *   - Tests cover what we caught (regression guards) AND what currently
 *     works (happy-path invariants). The suite is a safety harness, not a
 *     list of past fires.
 *   - Test behavior + invariants, not implementation details. "Clicking
 *     Syria navigates to /countries/217" is durable. Exact CSS class
 *     presence is not.
 *   - Neighborhood coverage: when a fix lands, its spec also tests the
 *     adjacent working flows on the same page. The bug is the seed; the
 *     neighborhood comes along for free.
 *
 * Base URL priority:
 *   1. `PLAYWRIGHT_BASE_URL` env var — used in CI to target the Vercel
 *      preview URL (from `vercel-preview-url-step`).
 *   2. Default http://localhost:3000 — assumes `npm run dev` or
 *      `npm start` is running. `webServer` block below starts it
 *      automatically if not reachable.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  // #443: the synthetic/ subdir runs on a 15-min cron against
  // qgintelligence.com via .github/workflows/synthetic.yml. It must
  // NOT run as part of the regular pre-deploy e2e suite (those run
  // against localhost / preview URLs and the synthetic asserts would
  // fail or hit the wrong target). The synthetic workflow invokes
  // Playwright with an explicit `tests/e2e/synthetic` path that
  // overrides this ignore.
  testIgnore: ["**/synthetic/**"],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    // Avoid waiting forever on CSR pages; tests that intentionally wait
    // for hydration use explicit expect.toBeVisible() / waitFor.
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 5"] }, // 393x851 — covers the <md hamburger case (#427)
    },
  ],

  // Only start the local server when no PLAYWRIGHT_BASE_URL is set.
  // In CI against a Vercel preview URL, we skip this entirely.
  //
  // Mode selection (#452):
  //   - CI: `npm run start` (production build). Next 16 dev / Turbopack
  //     returns HTTP 200 for `notFound()` calls — production correctly
  //     returns 404. Country-slug-routing tests require the production
  //     behavior. The e2e.yml workflow does `npm run build` before this
  //     server starts, so the .next/ output is already on disk.
  //   - Local: `npm run dev` (faster iteration). Devs can also start
  //     `npm run dev` themselves first; playwright skips this block when
  //     a server is already on :3000.
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: process.env.CI ? "npm run start" : "npm run dev",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
