/**
 * Smoke tests for the sleep scoring web app.
 *
 * These tests verify core user flows end-to-end:
 *   1. Login and see file list
 *   2. Select file and navigate dates
 *   3. Activity plot renders with proper dimensions
 *   4. Auto-score places markers
 *   5. Save markers (dirty -> saved state)
 *   6. Export page loads with file checkboxes
 *
 * Prerequisites:
 *   - Docker stack running (cd docker && docker compose -f docker-compose.local.yml up -d)
 *   - At least one CSV file uploaded and processed
 *
 * Run: cd frontend && npx playwright test e2e/scoring-page.spec.ts
 */

import { test, expect } from "@playwright/test";
import {
  loginAndGoToScoring,
  loginAndGoTo,
  fileSelector,
  dateSelector,
  waitForChart,
  navigateToCleanDate,
  sleepMarkerCount,
} from "./helpers";

// ─────────────────────────────────────────────────────────────────────────────
// Serial suite: tests 2-5 depend on shared state (file selection -> scoring)
// ─────────────────────────────────────────────────────────────────────────────
test.describe.configure({ mode: "serial" });

test.describe("Scoring Page — Smoke Tests", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. Login and see file list
  // ═══════════════════════════════════════════════════════════════════════════
  test("login and see file list", async ({ page }) => {
    test.setTimeout(60_000);

    await loginAndGoToScoring(page);

    // The file selector dropdown should be visible and contain at least one
    // option whose text includes ".csv" (uploaded files).
    const fileSelect = fileSelector(page);
    await expect(fileSelect).toBeVisible({ timeout: 15_000 });

    const options = fileSelect.locator("option");
    const optionCount = await options.count();
    expect(optionCount).toBeGreaterThan(0);

    // At least one option should reference a CSV filename
    const csvOption = options.filter({ hasText: /\.csv/i }).first();
    await expect(csvOption).toBeAttached();
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. Select file and navigate dates
  // ═══════════════════════════════════════════════════════════════════════════
  test("select file and navigate dates", async ({ page }) => {
    test.setTimeout(60_000);

    await loginAndGoToScoring(page);

    // File selector should already have a file selected (first file auto-selected)
    const fileSelect = fileSelector(page);
    await expect(fileSelect).toBeVisible({ timeout: 15_000 });
    const initialFile = await fileSelect.inputValue();
    expect(initialFile).toBeTruthy();

    // Date selector should be visible once file is loaded
    const dateSelect = dateSelector(page);
    await expect(dateSelect).toBeVisible({ timeout: 15_000 });

    // Record the initial selected date text (e.g. "2025-07-31 (1/14)")
    const initialDateText =
      (await dateSelect.locator("option:checked").textContent()) ?? "";
    expect(initialDateText).toBeTruthy();

    // Navigate to next or previous date
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    const prevBtn = page.locator('[data-testid="prev-date-btn"]');
    await expect(nextBtn).toBeVisible({ timeout: 5_000 });
    await expect(prevBtn).toBeVisible({ timeout: 5_000 });

    if (await nextBtn.isEnabled()) {
      await nextBtn.click();
    } else if (await prevBtn.isEnabled()) {
      await prevBtn.click();
    } else {
      test.skip(true, "Only one date available; cannot validate date navigation");
    }

    // Wait for chart to re-render after date change
    await expect(page.locator(".u-over").first()).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(1_500);

    // Date text should have changed
    const newDateText =
      (await dateSelect.locator("option:checked").textContent()) ?? "";
    expect(newDateText).not.toBe(initialDateText);
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. Activity plot renders
  // ═══════════════════════════════════════════════════════════════════════════
  test("activity plot renders with non-zero dimensions", async ({ page }) => {
    test.setTimeout(60_000);

    await loginAndGoToScoring(page);

    // The uPlot container should be visible
    const uplotContainer = page.locator(".uplot");
    await expect(uplotContainer).toBeVisible({ timeout: 15_000 });

    // The canvas element inside uPlot should exist and have real dimensions
    const canvas = page.locator(".uplot canvas").first();
    await expect(canvas).toBeVisible({ timeout: 10_000 });

    const box = await canvas.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThan(400);
    expect(box!.height).toBeGreaterThan(200);

    // "No activity data" message should NOT be visible
    await expect(page.locator("text=No activity data")).toHaveCount(0);
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. Auto-score places markers
  // ═══════════════════════════════════════════════════════════════════════════
  test("auto-score places markers", async ({ page }) => {
    test.setTimeout(90_000);

    const overlay = await loginAndGoToScoring(page);

    // Navigate to a clean date (no existing markers) so auto-score has something to do
    await navigateToCleanDate(page);

    // Clear any remaining markers if navigateToCleanDate couldn't find a clean one
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (d) => d.accept());
      const clearBtn = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await clearBtn.click();
        await page.waitForTimeout(2_000);
      }
    }

    // Click the "Auto Sleep" button in the scoring toolbar
    const autoScoreBtn = page.locator("button").filter({ hasText: /Auto Sleep/ }).first();
    await expect(autoScoreBtn).toBeVisible({ timeout: 10_000 });

    // Skip if the button is disabled (e.g. no diary data)
    if (await autoScoreBtn.isDisabled()) {
      test.skip(true, "Auto-score button is disabled (possibly no diary data for this date)");
    }

    // Listen for the auto-score API response to confirm the request completed
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes("/auto-score") && resp.status() === 200,
      { timeout: 30_000 },
    );

    await autoScoreBtn.click();

    // Wait for the API response
    await responsePromise;

    // Auto-score may produce a review dialog — if so, accept the results
    const applyBtn = page.locator("button").filter({ hasText: /Apply|Accept|Confirm/ }).first();
    if (await applyBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await applyBtn.click();
      await page.waitForTimeout(1_000);
    }

    // At least one marker line or region should now appear in the DOM
    const markerLines = page.locator('[data-testid^="marker-line-sleep-"]');
    const markerRegions = page.locator('[data-testid^="marker-region-sleep-"]');

    // Wait a bit for markers to render
    await page.waitForTimeout(2_000);

    const lineCount = await markerLines.count();
    const regionCount = await markerRegions.count();

    // At least one marker element should be present (lines come in pairs: start + end)
    expect(lineCount + regionCount).toBeGreaterThan(0);
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. Save markers (dirty -> saved state)
  // ═══════════════════════════════════════════════════════════════════════════
  test("save markers after auto-scoring", async ({ page }) => {
    test.setTimeout(60_000);

    const overlay = await loginAndGoToScoring(page);

    // If we have markers from the previous test (serial mode), great.
    // Otherwise create one manually.
    let markerCount = await sleepMarkerCount(page);
    if (markerCount === 0) {
      // Create a marker by clicking twice on the plot overlay
      const box = await overlay.boundingBox();
      expect(box).toBeTruthy();
      await overlay.click({
        position: { x: box!.width * 0.25, y: box!.height / 2 },
        force: true,
      });
      await page.waitForTimeout(500);
      await overlay.click({
        position: { x: box!.width * 0.75, y: box!.height / 2 },
        force: true,
      });
      await page.waitForTimeout(1_500);
    }

    // After marker creation/modification, isDirty becomes true.
    // Auto-save fires after ~1s debounce. The "Saved" badge should appear.
    const savedBadge = page.getByText("Saved");
    await expect(savedBadge).toBeVisible({ timeout: 15_000 });

    // Verify no "Unsaved" or "Saving" indicators remain stuck
    await expect(page.getByText("Unsaved")).not.toBeVisible({ timeout: 3_000 });
    await expect(page.getByText("Saving")).not.toBeVisible({ timeout: 3_000 });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 6. Export page loads
  // ═══════════════════════════════════════════════════════════════════════════
  test("export page loads with file checkboxes", async ({ page }) => {
    test.setTimeout(60_000);

    await loginAndGoTo(page, "/export");

    // The "Export Data" heading should appear
    await expect(
      page.getByRole("heading", { name: /export data/i }),
    ).toBeVisible({ timeout: 15_000 });

    // The "Select Files" section should be present
    await expect(page.getByText("Select Files")).toBeVisible({ timeout: 10_000 });

    // File checkboxes (id starts with "file-") should exist, OR a "No files" message
    const fileCheckboxes = page.locator('input[type="checkbox"][id^="file-"]');
    const noFilesMsg = page.getByText("No files available");

    const checkboxCount = await fileCheckboxes.count();
    const hasNoFiles = await noFilesMsg.isVisible({ timeout: 3_000 }).catch(() => false);

    // Either we see file checkboxes or an explicit "no files" message
    expect(checkboxCount > 0 || hasNoFiles).toBeTruthy();

    // If files are present, verify they are real checkboxes that can be toggled
    if (checkboxCount > 0) {
      const firstCheckbox = fileCheckboxes.first();
      const wasChecked = await firstCheckbox.isChecked();
      await firstCheckbox.click();
      const nowChecked = await firstCheckbox.isChecked();
      expect(nowChecked).not.toBe(wasChecked);

      // Restore original state
      await firstCheckbox.click();
    }
  });
});
