/**
 * E2E regression tests for the Analysis page.
 *
 * Covers: page load, scoring progress display, file summary table,
 * file row navigation, aggregate metrics, and accessibility (axe-core).
 *
 * Tests run serially because they share backend state.
 */

import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { login, loginAndGoTo } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Analysis Page", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  });

  test("analysis page loads without error", async ({ page }) => {
    const jsErrors: string[] = [];
    page.on("pageerror", (error) => {
      jsErrors.push(error.message);
    });

    await login(page);
    await page.goto("/analysis");
    await page.waitForLoadState("networkidle");

    // The page heading should be visible
    await expect(page.locator("h1", { hasText: "Analysis" })).toBeVisible({ timeout: 15000 });

    // No critical JS errors should have been thrown during page load
    const criticalErrors = jsErrors.filter(
      (e) =>
        e.includes("Cannot access") ||
        e.includes("ReferenceError") ||
        e.includes("TypeError") ||
        e.includes("is not defined") ||
        e.includes("before initialization"),
    );
    expect(criticalErrors).toEqual([]);
  });

  test("scoring progress shows percentage", async ({ page }) => {
    await login(page);
    await page.goto("/analysis");
    await page.waitForLoadState("networkidle");

    // Wait for the Scoring Progress card to render
    const progressCard = page.locator("text=Scoring Progress").first();
    await expect(progressCard).toBeVisible({ timeout: 15000 });

    // The progress description should contain "X of Y dates scored" with a percentage,
    // e.g. "3 of 14 dates scored across 1 files (21%)"
    const progressDescription = page
      .locator("text=/\\d+ of \\d+ dates scored/")
      .first();
    await expect(progressDescription).toBeVisible({ timeout: 10000 });

    // Also verify a percentage is displayed somewhere in the progress area
    // The ProgressBar component renders "NN%" text
    const percentageText = page.locator("text=/\\d+%/").first();
    await expect(percentageText).toBeVisible({ timeout: 10000 });
  });

  test("file summary table populated", async ({ page }) => {
    await login(page);
    await page.goto("/analysis");
    await page.waitForLoadState("networkidle");

    // Wait for the File Summary card to render
    const fileSummaryTitle = page.locator("text=File Summary").first();
    await expect(fileSummaryTitle).toBeVisible({ timeout: 15000 });

    // The table should have a header row and at least one data row
    const table = page.locator("table").first();
    await expect(table).toBeVisible({ timeout: 10000 });

    // Verify header columns exist
    await expect(table.locator("th", { hasText: "Filename" })).toBeVisible();
    await expect(table.locator("th", { hasText: "Participant" })).toBeVisible();
    await expect(table.locator("th", { hasText: "Dates Scored" })).toBeVisible();
    await expect(table.locator("th", { hasText: "Progress" })).toBeVisible();

    // Verify at least one data row exists in tbody
    const rows = table.locator("tbody tr");
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test("click file row navigates to scoring page for that file", async ({ page }) => {
    await login(page);
    await page.goto("/analysis");
    await page.waitForLoadState("networkidle");

    // Wait for the table to populate
    const table = page.locator("table").first();
    await expect(table).toBeVisible({ timeout: 15000 });

    const firstRow = table.locator("tbody tr").first();
    await expect(firstRow).toBeVisible({ timeout: 10000 });

    // Get the filename from the first row for verification
    const filename = await firstRow.locator("td").first().textContent();
    expect(filename).toBeTruthy();

    // Click the row — it should navigate to the scoring page
    await firstRow.click();

    // Should navigate to /scoring
    await page.waitForURL("**/scoring**", { timeout: 15000 });
    expect(page.url()).toContain("/scoring");
  });

  test("metrics displayed", async ({ page }) => {
    await login(page);
    await page.goto("/analysis");
    await page.waitForLoadState("networkidle");

    // Wait for the Aggregate Metrics section to render
    const metricsHeading = page.locator("h2", { hasText: "Aggregate Metrics" });
    await expect(metricsHeading).toBeVisible({ timeout: 15000 });

    // Verify metric labels are present (from MetricCard components)
    // These correspond to TST, SE, WASO, SOL in the analysis page
    const expectedLabels = [
      "Mean Total Sleep Time",
      "Mean Sleep Efficiency",
      "Mean WASO",
      "Mean Sleep Onset Latency",
    ];

    for (const label of expectedLabels) {
      await expect(
        page.locator(`text=${label}`).first(),
      ).toBeVisible({ timeout: 10000 });
    }

    // Verify the period count cards are present
    await expect(
      page.locator("text=Total sleep periods").first(),
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator("text=Total nap periods").first(),
    ).toBeVisible({ timeout: 10000 });
  });

  test("analysis page passes accessibility checks", async ({ page }) => {
    await login(page);
    await page.goto("/analysis");
    await page.waitForLoadState("networkidle");

    // Wait for the page content to fully render before scanning
    await expect(page.locator("h1", { hasText: "Analysis" })).toBeVisible({ timeout: 15000 });

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
