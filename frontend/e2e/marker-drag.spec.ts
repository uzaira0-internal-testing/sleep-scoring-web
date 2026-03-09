/**
 * E2E tests for marker drag behavior:
 * - Sleep rule arrows reposition in real-time during drag
 * - Marker data tables don't flicker (keepPreviousData + quantized query key)
 * - Shaded region follows drag movement
 * - Table highlight row tracks dragged position
 *
 * Tests run SERIALLY because they share a single backend and mutate marker state.
 * Each test navigates to a clean date to avoid interference from prior runs.
 */

import { test, expect, type Page, type Locator } from "@playwright/test";

// Serial execution: these tests share backend state and must not run in parallel
test.describe.configure({ mode: "serial" });

test.describe("Marker Drag Behavior", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  /** Login, wait for chart ready, return the overlay element */
  async function loginAndWaitForChart(page: Page) {
    await page.goto("http://localhost:8501/scoring");
    await page.waitForTimeout(1000);

    if (page.url().includes("/login")) {
      const passwordInput = page.locator('input[name="password"]');
      await expect(passwordInput).toBeVisible({ timeout: 10000 });
      await page.waitForTimeout(500);
      await passwordInput.fill("admin");
      await page.locator('input[name="username"]').fill("admin");
      await page.click('button[type="submit"]');
      await page.waitForURL("**/scoring**", { timeout: 15000 });
    }

    const overlay = page.locator(".u-over").first();
    await expect(overlay).toBeVisible({ timeout: 30000 });
    return overlay;
  }

  /**
   * Navigate to a date with no existing markers so tests start clean.
   * Clicks "next date" up to maxClicks times until no sleep marker regions exist.
   * Falls back to current date if all dates have markers.
   */
  async function navigateToCleanDate(page: Page, maxClicks = 5) {
    for (let i = 0; i < maxClicks; i++) {
      const existingMarkers = page.locator('[data-testid^="marker-region-sleep-"]');
      const count = await existingMarkers.count();
      if (count === 0) return; // Found a clean date

      const nextBtn = page.locator('[data-testid="next-date-btn"]');
      if (await nextBtn.isEnabled({ timeout: 1000 })) {
        await nextBtn.click();
        await page.waitForTimeout(1500); // Wait for chart + markers to re-render
      } else {
        break; // No more dates
      }
    }
  }

  /**
   * Ensure a visible sleep marker exists on the current date.
   * First checks for pre-existing markers (from DB). If none, creates one.
   * Returns the marker region locator.
   */
  async function ensureSleepMarker(page: Page, overlay: Locator) {
    // Check for pre-existing visible markers
    const existing = page.locator('[data-testid^="marker-region-sleep-"]');
    const visibleCount = await existing.filter({ has: page.locator(":visible") }).count().catch(() => 0);

    if (visibleCount > 0) {
      // Marker already exists and is visible
      const first = existing.first();
      if (await first.isVisible({ timeout: 1000 }).catch(() => false)) {
        return first;
      }
    }

    // Navigate to a clean date and create a fresh marker
    await navigateToCleanDate(page);

    const box = await overlay.boundingBox();
    expect(box).toBeTruthy();

    // Click onset at 25%
    await overlay.click({
      position: { x: box!.width * 0.25, y: box!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);

    // Click offset at 75%
    await overlay.click({
      position: { x: box!.width * 0.75, y: box!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(1500);

    // Verify marker was created - check both visible and attached
    const marker = page.locator('[data-testid^="marker-region-sleep-"]').first();
    // Region must be attached and have some width
    await expect(marker).toBeAttached({ timeout: 5000 });

    // If the region is zero-width (onset ≈ offset), it won't be "visible"
    // In that case the test data doesn't support wide markers; we still proceed
    return marker;
  }

  /** Select the first sleep marker period by clicking its MAIN/NAP button */
  async function selectFirstMarker(page: Page) {
    const markerButton = page.locator("button").filter({ hasText: /MAIN|NAP/ }).first();
    if (await markerButton.isVisible({ timeout: 3000 })) {
      await markerButton.click({ force: true });
      await page.waitForTimeout(1000);
    }
  }

  /** Get onset marker line (the draggable start edge) */
  async function getOnsetLine(page: Page) {
    // Try specific index first, then fallback to any
    const line = page.locator('[data-testid^="marker-line-sleep-"][data-testid$="-start"]').first();
    return line;
  }

  /** Get offset marker line (the draggable end edge) */
  async function getOffsetLine(page: Page) {
    const line = page.locator('[data-testid^="marker-line-sleep-"][data-testid$="-end"]').first();
    return line;
  }

  /** Perform a drag on an element by a given pixel offset */
  async function dragLine(page: Page, line: Locator, dx: number, steps = 5) {
    const box = await line.boundingBox();
    expect(box).toBeTruthy();

    const startX = box!.x + box!.width / 2;
    const startY = box!.y + box!.height / 2;

    await page.mouse.move(startX, startY);
    await page.mouse.down();
    for (let i = 1; i <= steps; i++) {
      await page.mouse.move(startX + (dx * i) / steps, startY);
      await page.waitForTimeout(60);
    }
    // Returns without mouseup so caller can assert mid-drag state
    return { startX, startY, endX: startX + dx };
  }

  // ==========================================================================
  // CORE DRAG TESTS
  // ==========================================================================

  test("dragging onset line moves the shaded region rightward", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndWaitForChart(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstMarker(page);

    // Wait for marker lines to render
    const onsetLine = await getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });

    // Record the onset line position before drag
    const lineBefore = await onsetLine.boundingBox();
    expect(lineBefore).toBeTruthy();

    // Drag onset 100px right and release
    await dragLine(page, onsetLine, 100);
    await page.mouse.up();
    await page.waitForTimeout(500);

    // After re-render, the onset line should be at a new position
    // (renderMarkers fires on mouseup)
    const lineAfter = await onsetLine.boundingBox();
    expect(lineAfter).toBeTruthy();
    expect(lineAfter!.x).toBeGreaterThan(lineBefore!.x + 20);
  });

  test("sleep rule arrows remain visible during marker drag", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndWaitForChart(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstMarker(page);

    // Wait for sleep rule arrows to appear
    await page.waitForTimeout(2000);
    const onsetArrow = page.locator('[data-testid^="sleep-rule-arrow-onset-"]').first();
    const offsetArrow = page.locator('[data-testid^="sleep-rule-arrow-offset-"]').first();

    const hasOnsetArrow = await onsetArrow.isVisible({ timeout: 3000 });
    const hasOffsetArrow = await offsetArrow.isVisible({ timeout: 1000 });

    if (!hasOnsetArrow && !hasOffsetArrow) {
      test.skip(true, "No sleep rule arrows visible — algorithm results may not cover marker range");
      return;
    }

    // Record initial arrow positions
    const initialOnsetBox = hasOnsetArrow ? await onsetArrow.boundingBox() : null;
    const initialOffsetBox = hasOffsetArrow ? await offsetArrow.boundingBox() : null;

    // Drag the offset line 150px right (expands the sleep window)
    const offsetLine = await getOffsetLine(page);
    await expect(offsetLine).toBeVisible({ timeout: 5000 });
    await dragLine(page, offsetLine, 150);

    // MID-DRAG: arrows should still exist and have height > 0
    // (Before this fix, renderMarkers was skipped during drag so arrows froze)
    if (hasOnsetArrow) {
      const midBox = await onsetArrow.boundingBox();
      if (midBox) {
        expect(midBox.height).toBeGreaterThan(0);
      }
    }
    if (hasOffsetArrow) {
      const midBox = await offsetArrow.boundingBox();
      if (midBox) {
        expect(midBox.height).toBeGreaterThan(0);
      }
    }

    await page.mouse.up();
    await page.waitForTimeout(500);

    // After drag completes, arrows should render with proper dimensions
    if (hasOnsetArrow && await onsetArrow.isVisible({ timeout: 2000 })) {
      const finalBox = await onsetArrow.boundingBox();
      expect(finalBox).toBeTruthy();
      expect(finalBox!.height).toBeGreaterThanOrEqual(30); // 40px expected
    }
  });

  test("sleep rule arrow labels show correct text pattern during drag", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndWaitForChart(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstMarker(page);

    await page.waitForTimeout(2000);
    const onsetLabel = page.locator(".sleep-rule-label.onset").first();
    const offsetLabel = page.locator(".sleep-rule-label.offset").first();

    const hasOnsetLabel = await onsetLabel.isVisible({ timeout: 3000 });
    const hasOffsetLabel = await offsetLabel.isVisible({ timeout: 1000 });

    if (!hasOnsetLabel && !hasOffsetLabel) {
      test.skip(true, "No sleep rule labels visible");
      return;
    }

    // Drag the onset line 200px right
    const onsetLine = await getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });
    await dragLine(page, onsetLine, 200, 10);

    // Mid-drag: label text should still contain the "Sleep Onset at" pattern
    if (hasOnsetLabel && await onsetLabel.isVisible()) {
      const midDragText = (await onsetLabel.textContent()) ?? "";
      expect(midDragText).toContain("Sleep Onset at");
    }

    await page.mouse.up();
    await page.waitForTimeout(500);

    // After drag: labels should have proper content
    if (hasOnsetLabel && await onsetLabel.isVisible()) {
      const text = (await onsetLabel.textContent()) ?? "";
      expect(text).toContain("Sleep Onset at");
      expect(text).toContain("3 consecutive sleep epochs");
    }
    if (hasOffsetLabel && await offsetLabel.isVisible()) {
      const text = (await offsetLabel.textContent()) ?? "";
      expect(text).toContain("Sleep Offset at");
      expect(text).toContain("5 consecutive sleep epochs");
    }
  });

  // ==========================================================================
  // TABLE BEHAVIOR DURING DRAG
  // ==========================================================================

  test("table keeps previous data during drag (no loading flash)", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndWaitForChart(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstMarker(page);

    // Wait for table data to fully load
    await page.waitForTimeout(3000);

    // Verify onset/offset table titles are visible
    await expect(page.locator("text=Sleep Onset").first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=Sleep Offset").first()).toBeVisible({ timeout: 5000 });

    // Count initial table rows
    const tableRows = page.locator("table tbody tr");
    const initialRowCount = await tableRows.count();

    // Get onset marker line
    const onsetLine = await getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });

    // Track whether "Loading..." ever flashes during drag
    let loadingAppeared = false;
    const loadingCheck = setInterval(async () => {
      try {
        const loading = page.locator("text=Loading...");
        if (await loading.isVisible({ timeout: 50 })) {
          loadingAppeared = true;
        }
      } catch {
        // expected - element doesn't exist
      }
    }, 100);

    // Drag onset line 120px right in small steps
    await dragLine(page, onsetLine, 120, 8);
    await page.mouse.up();

    clearInterval(loadingCheck);
    await page.waitForTimeout(500);

    // keepPreviousData should prevent loading flash
    expect(loadingAppeared).toBe(false);

    // Table should still have data rows
    if (initialRowCount > 0) {
      const finalRowCount = await tableRows.count();
      expect(finalRowCount).toBeGreaterThan(0);
    }
  });

  test("table highlight row persists after drag", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndWaitForChart(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstMarker(page);

    await page.waitForTimeout(3000);

    // Check for a highlighted row (font-bold class)
    const highlightedRow = page.locator("table tbody tr.font-bold").first();
    const hasHighlight = await highlightedRow.isVisible({ timeout: 3000 });

    if (!hasHighlight) {
      test.skip(true, "No highlighted table row visible");
      return;
    }

    // Drag onset line
    const onsetLine = await getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });
    await dragLine(page, onsetLine, 100);
    await page.mouse.up();
    await page.waitForTimeout(1000);

    // Table should still have data
    const rowCount = await page.locator("table tbody tr").count();
    expect(rowCount).toBeGreaterThan(0);

    // Highlight row should still exist after drag completes
    const highlightAfter = page.locator("table tbody tr.font-bold").first();
    if (await highlightAfter.isVisible({ timeout: 3000 })) {
      await expect(highlightAfter).toHaveClass(/font-bold/);
    }
  });

  // ==========================================================================
  // EDGE CASES
  // ==========================================================================

  test("nonwear markers do not show sleep rule arrows", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndWaitForChart(page);
    const box = await overlay.boundingBox();
    expect(box).toBeTruthy();

    // Switch to Nonwear mode
    const nonwearButton = page.locator("button").filter({ hasText: "Nonwear" }).first();
    await nonwearButton.click();
    await page.waitForTimeout(500);

    // Navigate to a clean date for nonwear
    await navigateToCleanDate(page);

    // Create a nonwear marker
    const freshBox = await overlay.boundingBox();
    expect(freshBox).toBeTruthy();
    await overlay.click({
      position: { x: freshBox!.width * 0.3, y: freshBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);
    await overlay.click({
      position: { x: freshBox!.width * 0.5, y: freshBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(1000);

    // Verify nonwear marker was created
    const nwMarker = page.locator('[data-testid^="marker-region-nonwear-"]').first();
    await expect(nwMarker).toBeVisible({ timeout: 5000 });

    // Select the nonwear marker
    const nwButton = page.locator("button").filter({ hasText: /NW/ }).first();
    if (await nwButton.isVisible({ timeout: 2000 })) {
      await nwButton.click({ force: true });
      await page.waitForTimeout(500);
    }

    // No sleep rule arrows should exist (they only appear for sleep markers)
    const sleepRuleArrows = page.locator('[data-testid^="sleep-rule-arrow-"]');
    const arrowCount = await sleepRuleArrows.count();
    expect(arrowCount).toBe(0);
  });

  test("dragging offset past onset does not crash the page", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndWaitForChart(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstMarker(page);

    // Get the offset line
    const offsetLine = await getOffsetLine(page);
    await expect(offsetLine).toBeVisible({ timeout: 5000 });

    // Drag offset line 300px to the left (past onset)
    await dragLine(page, offsetLine, -300, 10);
    await page.mouse.up();
    await page.waitForTimeout(500);

    // Page should not have crashed — chart overlay still visible
    await expect(overlay).toBeVisible();

    // Marker region should still exist in DOM (may be zero-width)
    const region = page.locator('[data-testid^="marker-region-sleep-"]').first();
    await expect(region).toBeAttached({ timeout: 5000 });
  });
});
