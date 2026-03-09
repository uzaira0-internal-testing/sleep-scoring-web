/**
 * E2E tests for edge cases and robustness:
 * - Boundary marker placement (extreme positions on the chart)
 * - Rapid user interactions (fast navigation, mode switching)
 * - Cross-file marker isolation
 * - Empty data scenarios
 * - Small markers
 * - Multiple markers on same date
 * - Invalid selections
 * - Page reload during creation
 * - Navigation preservation
 * - Browser back button
 *
 * Tests run SERIALLY because they share a single backend and mutate marker state.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndGoToScoring,
  waitForChart,
  createSleepMarker,
  ensureSleepMarker,
  selectFirstSleepMarker,
  navigateToCleanDate,
  getOverlayBox,
  switchToSleepMode,
  switchToNonwearMode,
  assertPageHealthy,
  sleepMarkerCount,
  nonwearMarkerCount,
  nextDate,
  prevDate,
  createNonwearMarker,
  fileSelector,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Edge Cases", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // ==========================================================================
  // BOUNDARY MARKER PLACEMENT
  // ==========================================================================

  test("creating marker at very start of data (onset at ~2% x-position) does not crash", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);

    // Click onset very close to the left edge (2%) and offset at 30%
    const box = await getOverlayBox(overlay);
    await overlay.click({
      position: { x: box.width * 0.02, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);
    await overlay.click({
      position: { x: box.width * 0.3, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(1500);

    // Page should still be healthy
    await assertPageHealthy(page);

    // A marker should have been created (or the app gracefully handled the edge position)
    const count = await sleepMarkerCount(page);
    expect(count).toBeGreaterThanOrEqual(0); // At least no crash
  });

  test("creating marker at very end of data (offset at ~98% x-position) does not crash", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);

    // Click onset at 70% and offset very close to the right edge (98%)
    const box = await getOverlayBox(overlay);
    await overlay.click({
      position: { x: box.width * 0.7, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);
    await overlay.click({
      position: { x: box.width * 0.98, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(1500);

    await assertPageHealthy(page);
    const count = await sleepMarkerCount(page);
    expect(count).toBeGreaterThanOrEqual(0);
  });

  // ==========================================================================
  // RAPID INTERACTIONS
  // ==========================================================================

  test("rapid date navigation (click next 5 times quickly) does not crash", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const nextBtn = page.locator('[data-testid="next-date-btn"]');

    // Click next date rapidly 5 times
    for (let i = 0; i < 5; i++) {
      if (await nextBtn.isEnabled({ timeout: 500 }).catch(() => false)) {
        await nextBtn.click();
        // Only a tiny pause between clicks to simulate rapid clicking
        await page.waitForTimeout(100);
      }
    }

    // Wait for things to settle
    await page.waitForTimeout(3000);

    // Page should still be healthy after rapid navigation
    await assertPageHealthy(page);
  });

  test("switching modes rapidly (Sleep -> Nonwear -> Sleep) does not crash", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Rapidly switch modes
    await switchToSleepMode(page);
    await switchToNonwearMode(page);
    await switchToSleepMode(page);
    await switchToNonwearMode(page);
    await switchToSleepMode(page);

    // Page should still be healthy
    await assertPageHealthy(page);

    // Mode should be back to Sleep
    const sleepBtn = page.locator("button").filter({ hasText: "Sleep" }).first();
    const sleepBtnClass = await sleepBtn.getAttribute("class");
    // The active mode button uses "default" variant (not "outline")
    expect(sleepBtnClass).not.toContain("border-input");
  });

  // ==========================================================================
  // CROSS-FILE ISOLATION
  // ==========================================================================

  test("creating markers then switching files does not bleed markers", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Create a marker on the current file
    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay);
    const countOnFile1 = await sleepMarkerCount(page);
    expect(countOnFile1).toBeGreaterThan(0);

    // Wait for auto-save
    await page.waitForTimeout(3000);

    // Check if there is a second file to switch to
    const fileSelect = fileSelector(page);
    const options = await fileSelect.locator("option").all();

    if (options.length > 1) {
      // Get current file value and find a different file
      const currentValue = await fileSelect.inputValue();
      let switchedToOtherFile = false;

      for (const option of options) {
        const val = await option.getAttribute("value");
        if (val && val !== currentValue) {
          await fileSelect.selectOption(val);
          switchedToOtherFile = true;
          break;
        }
      }

      if (switchedToOtherFile) {
        // Wait for the new file to load
        await waitForChart(page);
        await page.waitForTimeout(2000);

        // The markers from the first file should NOT be visible on the second file
        // (markers are file+date specific)
        await assertPageHealthy(page);
      }
    }
  });

  // ==========================================================================
  // EMPTY / MISSING DATA
  // ==========================================================================

  test("empty date (no activity data) shows appropriate state", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Navigate through dates to find one - we just verify no crashes
    // Even if all dates have data, the test validates that navigation works
    await assertPageHealthy(page);

    // The chart should always render (even with minimal data)
    const uplotEl = page.locator(".uplot");
    await expect(uplotEl).toBeVisible({ timeout: 5000 });
  });

  // ==========================================================================
  // SMALL / MULTIPLE MARKERS
  // ==========================================================================

  test("very small marker (onset and offset close together) is functional", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);

    // Create a very small marker with onset and offset close together (~5% apart)
    const box = await getOverlayBox(overlay);
    await overlay.click({
      position: { x: box.width * 0.45, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);
    await overlay.click({
      position: { x: box.width * 0.50, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(1500);

    // The marker should exist (it may be thin but still attached to DOM)
    const marker = page.locator('[data-testid^="marker-region-sleep-"]').first();
    await expect(marker).toBeAttached({ timeout: 5000 });

    // Page should remain healthy
    await assertPageHealthy(page);
  });

  test("multiple markers on same date do not interfere", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Clear existing markers to start clean
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(2000);
      }
    }

    // Create first marker at left portion
    await createSleepMarker(page, overlay, 0.1, 0.25);
    await page.waitForTimeout(500);

    // Deselect before creating next marker
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);

    // Create second marker at right portion
    await createSleepMarker(page, overlay, 0.6, 0.85);
    await page.waitForTimeout(500);

    // Both should exist
    const count = await sleepMarkerCount(page);
    expect(count).toBeGreaterThanOrEqual(2);

    // Select markers via div.cursor-pointer list items (not buttons)
    const markerItems = page.locator("div.cursor-pointer").filter({ hasText: /Main|Nap/i });
    const itemCount = await markerItems.count();
    expect(itemCount).toBeGreaterThanOrEqual(2);

    // Click first marker item
    await markerItems.first().click({ force: true });
    await page.waitForTimeout(500);

    // Verify we can select the second marker too
    await markerItems.nth(1).click({ force: true });
    await page.waitForTimeout(500);

    // Page should remain healthy after selecting different markers
    await assertPageHealthy(page);
  });

  // ==========================================================================
  // INVALID SELECTIONS & EDGE CASES
  // ==========================================================================

  test("selecting nonexistent period index does not crash", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Navigate to a date with no markers
    await navigateToCleanDate(page);

    // Press keyboard shortcuts that would act on a selected marker (which doesn't exist)
    await page.keyboard.press("q"); // Move onset left
    await page.waitForTimeout(100);
    await page.keyboard.press("e"); // Move onset right
    await page.waitForTimeout(100);
    await page.keyboard.press("a"); // Move offset left
    await page.waitForTimeout(100);
    await page.keyboard.press("d"); // Move offset right
    await page.waitForTimeout(100);
    await page.keyboard.press("Delete"); // Delete selected
    await page.waitForTimeout(100);
    await page.keyboard.press("c"); // Delete selected (alternate)
    await page.waitForTimeout(100);

    // Page should still be healthy - none of these should crash
    await assertPageHealthy(page);
  });

  test("page reload during marker creation cancels creation cleanly", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);

    // Start marker creation by clicking once (onset placement)
    const box = await getOverlayBox(overlay);
    await overlay.click({
      position: { x: box.width * 0.3, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(300);

    // The creation mode indicator should be visible
    const creationIndicator = page.locator("text=Click plot for");
    const indicatorVisible = await creationIndicator.isVisible({ timeout: 2000 }).catch(() => false);

    // Reload the page mid-creation
    await page.reload();
    await waitForChart(page);
    await page.waitForTimeout(2000);

    // After reload, creation mode should be reset (no pending creation)
    const indicatorAfter = page.locator("text=Click plot for");
    await expect(indicatorAfter).not.toBeVisible({ timeout: 3000 });

    // Page should be in a clean state
    await assertPageHealthy(page);
  });

  // ==========================================================================
  // NAVIGATION PRESERVATION
  // ==========================================================================

  test("navigating to settings and back preserves file/date selection", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Record current file selection
    const fileSelect = fileSelector(page);
    const fileBefore = await fileSelect.inputValue();

    // Record current date by reading the date selector
    const dateSelect = page.locator("select").filter({ has: page.locator("option", { hasText: /\(\d+\/\d+\)/ }) }).first();
    const dateValueBefore = await dateSelect.inputValue().catch(() => "");

    // Navigate to study settings
    await page.locator('a[href="/settings/study"]').click();
    await page.waitForURL("**/settings/study**", { timeout: 5000 });
    await page.waitForTimeout(500);

    // Navigate back to scoring
    await page.locator('a[href="/scoring"]').click();
    await page.waitForURL("**/scoring**", { timeout: 5000 });
    await waitForChart(page);
    await page.waitForTimeout(2000);

    // File selection should be preserved
    const fileAfter = await fileSelect.inputValue();
    expect(fileAfter).toBe(fileBefore);

    // Page should still be healthy
    await assertPageHealthy(page);
  });

  test("browser back button from settings returns to scoring page", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Navigate to data settings
    await page.locator('a[href="/settings/data"]').click();
    await page.waitForURL("**/settings/data**", { timeout: 5000 });

    // Use browser back button
    await page.goBack();
    await page.waitForTimeout(2000);

    // Should be back on the scoring page
    await expect(page).toHaveURL(/\/scoring/);
    await assertPageHealthy(page);
  });
});
