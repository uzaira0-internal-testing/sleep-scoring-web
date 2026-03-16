/**
 * Deep E2E tests for the core scoring workflow — marker creation, selection,
 * dragging, deletion, undo/redo, No Sleep mode, autosave persistence, and
 * visual regression.
 *
 * Prerequisites:
 * - Docker stack running (cd docker && docker compose -f docker-compose.local.yml up -d)
 * - At least one CSV file uploaded and processed with multiple dates
 */

import { test, expect, type Locator } from "@playwright/test";
import {
  loginAndGoToScoring,
  waitForChart,
  createSleepMarker,
  createNonwearMarker,
  ensureSleepMarker,
  selectFirstSleepMarker,
  navigateToCleanDate,
  getOnsetLine,
  getOffsetLine,
  dragElement,
  switchToSleepMode,
  switchToNoSleepMode,
  assertPageHealthy,
  sleepMarkerCount,
  nonwearMarkerCount,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Marker Interactions", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.clearBrowserCache");
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // =========================================================================
  // 1. Create sleep marker via chart clicks -> marker appears in list
  // =========================================================================
  test("create sleep marker via chart clicks — marker appears in list", async ({
    page,
  }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await switchToSleepMode(page);

    const beforeCount = await sleepMarkerCount(page);

    await createSleepMarker(page, overlay, 0.25, 0.75);

    const afterCount = await sleepMarkerCount(page);
    expect(afterCount).toBe(beforeCount + 1);

    // Marker region visible on chart
    const region = page
      .locator('[data-testid^="marker-region-sleep-"]')
      .first();
    await expect(region).toBeVisible({ timeout: 5000 });

    // Marker entry visible in list (Main or Nap label)
    const markerLabel = page
      .locator("span.font-semibold")
      .filter({ hasText: /Main|Nap/ })
      .first();
    await expect(markerLabel).toBeVisible({ timeout: 5000 });

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 2. Create second sleep marker (NAP) -> both markers visible
  // =========================================================================
  test("create second sleep marker (NAP) — both markers visible", async ({
    page,
  }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await switchToSleepMode(page);

    // Clear any leftover markers
    const existing = await sleepMarkerCount(page);
    if (existing > 0) {
      page.once("dialog", (d) => d.accept());
      const clearBtn = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearBtn.click();
        await page.waitForTimeout(1500);
      }
    }

    // First marker in right half
    await createSleepMarker(page, overlay, 0.55, 0.85);
    const afterFirst = await sleepMarkerCount(page);
    expect(afterFirst).toBeGreaterThanOrEqual(1);

    // Deselect before creating second marker
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);

    // Second marker in left half (non-overlapping)
    await createSleepMarker(page, overlay, 0.1, 0.35);
    await page.waitForTimeout(1000);

    const afterSecond = await sleepMarkerCount(page);
    expect(afterSecond).toBeGreaterThanOrEqual(2);

    // Sleep panel header shows count
    const sleepHeader = page.locator("text=/Sleep \\(\\d+\\)/").first();
    await expect(sleepHeader).toBeVisible({ timeout: 3000 });

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 3. Create nonwear marker -> appears in nonwear section
  // =========================================================================
  test("create nonwear marker — appears in nonwear section", async ({
    page,
  }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);

    const beforeCount = await nonwearMarkerCount(page);

    await createNonwearMarker(page, overlay, 0.4, 0.6);

    const afterCount = await nonwearMarkerCount(page);
    expect(afterCount).toBe(beforeCount + 1);

    // Nonwear region visible on chart
    const nwRegion = page
      .locator('[data-testid^="marker-region-nonwear-"]')
      .first();
    await expect(nwRegion).toBeVisible({ timeout: 5000 });

    // NW label in list
    const nwLabel = page.locator("text=/NW \\d+/").first();
    await expect(nwLabel).toBeVisible({ timeout: 5000 });

    // Switch back to sleep mode for next tests
    await switchToSleepMode(page);
    await assertPageHealthy(page);
  });

  // =========================================================================
  // 4. Select marker -> marker highlighted in chart
  // =========================================================================
  test("select marker — marker highlighted with onset/offset lines", async ({
    page,
  }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);

    // Click the first marker item in the list
    const markerItem = page
      .locator("div.cursor-pointer")
      .filter({ has: page.locator("span.font-semibold") })
      .first();
    await markerItem.click({ force: true });
    await page.waitForTimeout(500);

    // Item should have selected styling (purple background)
    await expect(markerItem).toHaveClass(/bg-purple/, { timeout: 3000 });

    // Onset and offset lines should be visible on the chart
    const onsetLine = getOnsetLine(page);
    const offsetLine = getOffsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });
    await expect(offsetLine).toBeVisible({ timeout: 5000 });

    // Screenshot: marker selected with onset/offset lines visible
    await expect(page).toHaveScreenshot("marker-selected-with-lines.png", {
      maxDiffPixelRatio: 0.01,
    });

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 5. Drag onset line -> onset timestamp changes
  // =========================================================================
  test("drag onset line — onset position changes", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    const onsetLine = getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });

    const beforeBox = await onsetLine.boundingBox();
    expect(beforeBox).toBeTruthy();

    // Drag onset 80px right
    await dragElement(page, onsetLine, 80);
    await page.mouse.up();
    await page.waitForTimeout(500);

    const afterBox = await onsetLine.boundingBox();
    expect(afterBox).toBeTruthy();
    expect(afterBox!.x).toBeGreaterThan(beforeBox!.x + 20);

    // Screenshot: scoring page after dragging onset line
    await expect(page).toHaveScreenshot("marker-after-onset-drag.png", {
      maxDiffPixelRatio: 0.01,
    });

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 6. Drag offset line -> offset timestamp changes
  // =========================================================================
  test("drag offset line — offset position changes", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    const offsetLine = getOffsetLine(page);
    await expect(offsetLine).toBeVisible({ timeout: 5000 });

    const beforeBox = await offsetLine.boundingBox();
    expect(beforeBox).toBeTruthy();

    // Drag offset 80px left
    await dragElement(page, offsetLine, -80);
    await page.mouse.up();
    await page.waitForTimeout(500);

    const afterBox = await offsetLine.boundingBox();
    expect(afterBox).toBeTruthy();
    expect(afterBox!.x).toBeLessThan(beforeBox!.x - 20);

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 7. Delete marker -> marker removed from list and chart
  // =========================================================================
  test("delete marker — removed from list and chart", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await switchToSleepMode(page);

    // Create a fresh marker to delete
    await createSleepMarker(page, overlay, 0.3, 0.5);
    await page.waitForTimeout(500);

    const beforeCount = await sleepMarkerCount(page);
    expect(beforeCount).toBeGreaterThanOrEqual(1);

    // Newly created marker is auto-selected — onset line should be visible
    const onsetLine = getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });

    // Delete with keyboard
    await page.keyboard.press("Delete");
    await page.waitForTimeout(1000);

    const afterCount = await sleepMarkerCount(page);
    expect(afterCount).toBe(beforeCount - 1);

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 8. Undo after delete -> marker restored
  // =========================================================================
  test("Ctrl+Z after delete — marker restored", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await switchToSleepMode(page);

    // Create a marker, then delete it
    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay, 0.3, 0.6);
    await page.waitForTimeout(500);

    const countAfterCreate = await sleepMarkerCount(page);
    expect(countAfterCreate).toBeGreaterThanOrEqual(1);

    // Delete the selected marker
    await page.keyboard.press("Delete");
    await page.waitForTimeout(1000);

    const countAfterDelete = await sleepMarkerCount(page);
    expect(countAfterDelete).toBe(countAfterCreate - 1);

    // Undo the deletion
    await page.keyboard.press("Control+z");
    await page.waitForTimeout(1500);

    const countAfterUndo = await sleepMarkerCount(page);
    expect(countAfterUndo).toBe(countAfterCreate);

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 9. Redo after undo -> marker deleted again
  // =========================================================================
  test("Ctrl+Shift+Z after undo — marker deleted again", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await switchToSleepMode(page);

    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay, 0.3, 0.6);
    await page.waitForTimeout(500);

    const countAfterCreate = await sleepMarkerCount(page);
    expect(countAfterCreate).toBeGreaterThanOrEqual(1);

    // Delete
    await page.keyboard.press("Delete");
    await page.waitForTimeout(1000);

    const countAfterDelete = await sleepMarkerCount(page);
    expect(countAfterDelete).toBe(countAfterCreate - 1);

    // Undo
    await page.keyboard.press("Control+z");
    await page.waitForTimeout(1500);
    expect(await sleepMarkerCount(page)).toBe(countAfterCreate);

    // Redo (Ctrl+Shift+Z or Ctrl+Y)
    await page.keyboard.press("Control+Shift+z");
    await page.waitForTimeout(1500);

    const countAfterRedo = await sleepMarkerCount(page);
    expect(countAfterRedo).toBe(countAfterDelete);

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 10. Switch to No Sleep mode -> main sleep markers removed, NAPs preserved
  // =========================================================================
  test("No Sleep mode — main sleep markers removed, page healthy", async ({
    page,
  }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Navigate to a clean date, create a main sleep marker
    await navigateToCleanDate(page);
    await switchToSleepMode(page);
    await createSleepMarker(page, overlay, 0.3, 0.7);
    await page.waitForTimeout(500);

    const beforeCount = await sleepMarkerCount(page);
    expect(beforeCount).toBeGreaterThanOrEqual(1);

    // Activate No Sleep mode (accepts confirmation dialog)
    await switchToNoSleepMode(page);

    // After No Sleep activation, the Sleep button should be disabled
    const sleepButton = page
      .locator("button")
      .filter({ hasText: "Sleep" })
      .first();
    await expect(sleepButton).toBeDisabled({ timeout: 5000 });

    // Main sleep markers should be removed (count may be 0 or only NAPs remain)
    const afterCount = await sleepMarkerCount(page);
    expect(afterCount).toBeLessThan(beforeCount);

    await assertPageHealthy(page);

    // Toggle No Sleep OFF to restore normal mode for subsequent tests
    const noSleepBtn = page
      .locator("button")
      .filter({ hasText: /No Sleep/i })
      .first();
    await noSleepBtn.click();
    await page.waitForTimeout(1000);
  });

  // =========================================================================
  // 11. Create marker, reload page -> marker persists (autosave)
  // =========================================================================
  test("create marker, reload page — marker persists via autosave", async ({
    page,
  }) => {
    test.setTimeout(90000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await switchToSleepMode(page);

    await createSleepMarker(page, overlay, 0.3, 0.7);

    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThanOrEqual(1);

    // Wait for auto-save to complete
    const savedBadge = page.getByText("Saved");
    await expect(savedBadge).toBeVisible({ timeout: 10000 });

    // Extra wait to ensure save request is fully flushed
    await page.waitForTimeout(2000);

    // Full page reload
    await page.reload();
    await waitForChart(page);
    await page.waitForTimeout(3000);

    // Markers restored from backend
    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBe(countBefore);

    await assertPageHealthy(page);
  });

  // =========================================================================
  // 12. Visual regression: screenshot after creating markers
  // =========================================================================
  test("visual regression — scoring page with markers", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    // Wait for metrics / tables to load
    await page.waitForTimeout(3000);

    await expect(page).toHaveScreenshot("scoring-with-markers.png", {
      maxDiffPixels: 500,
      fullPage: false,
    });
  });
});
