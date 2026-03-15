import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for Sleep Scoring Web E2E tests.
 *
 * IMPORTANT: Docker must be running before running tests!
 * Run: cd docker && docker compose up -d
 *
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: "./e2e",
  // Tests share a single backend and mutate marker state — run one file at a time
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "html",

  use: {
    // Base URL - Docker dev frontend runs on 8501
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8501",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 5"] },
    },
    {
      name: "tablet",
      use: { viewport: { width: 768, height: 1024 } },
    },
  ],

  // No webServer - Docker must be started manually before running tests
  // Run: cd docker && docker compose up -d
});
