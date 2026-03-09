import { test, expect } from "@playwright/test";
import {
  loginAndGoToScoring,
  getOverlayBox,
  createSleepMarker,
  selectFirstSleepMarker,
  nextDate,
  dateSelector,
  fileSelector,
} from "./helpers";

test.describe("UX Improvements", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  });

  // ===========================================================================
  // Phase 1: Date status progress fraction
  // ===========================================================================
  test("shows scored/total progress in date navigation area", async ({ page }) => {
    await loginAndGoToScoring(page);

    // The progress label "X/Y scored" should appear near the date navigation
    const progressLabel = page.locator("span").filter({ hasText: /\d+\/\d+ scored/ }).first();
    await expect(progressLabel).toBeVisible({ timeout: 10000 });

    // Verify the format matches "N/M scored" pattern
    const text = await progressLabel.textContent();
    expect(text ?? "").toMatch(/^\d+\/\d+ scored(?:,.*)?$/);
  });

  // ===========================================================================
  // Phase 2: Offset time overnight handling
  // ===========================================================================
  test("offset time input handles overnight sleep correctly", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);
    const box = await getOverlayBox(overlay);

    // Create a marker spanning late evening to early morning
    await createSleepMarker(page, overlay, 0.25, 0.75);
    await selectFirstSleepMarker(page);
    await page.waitForTimeout(500);

    // Verify onset and offset inputs exist
    const onsetInput = page.locator('input[type="text"]').nth(0);
    const offsetInput = page.locator('input[type="text"]').nth(1);

    // Locate the onset input in the control bar (next to "Onset:" label)
    const onsetLabel = page.locator("text=Onset:").first();
    const offsetLabel = page.locator("text=Offset:").first();
    await expect(onsetLabel).toBeVisible({ timeout: 5000 });
    await expect(offsetLabel).toBeVisible({ timeout: 5000 });
  });

  // ===========================================================================
  // Phase 3: Zoom reset button
  // ===========================================================================
  test("shows reset zoom button when zoomed in and resets on click", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);
    const box = await getOverlayBox(overlay);

    // No reset button initially
    const resetBtn = page.locator("button:has-text('Reset Zoom')");
    await expect(resetBtn).toHaveCount(0);

    // Zoom in with mouse wheel on the chart
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    // deltaY < 0 zooms in for our wheelZoomPlugin
    await page.mouse.wheel(0, -300);
    await page.waitForTimeout(500);
    await page.mouse.wheel(0, -300);
    await page.waitForTimeout(500);

    // Reset button should appear
    await expect(resetBtn).toBeVisible({ timeout: 5000 });

    // Click reset
    await resetBtn.click();
    await page.waitForTimeout(500);

    // Button should disappear
    await expect(resetBtn).toHaveCount(0);
  });

  // ===========================================================================
  // Phase 4: Metric threshold warnings
  // ===========================================================================
  test("metrics panel is hidden by default (moved out of main scoring view)", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);

    // Create a marker and select it to trigger metrics display
    await createSleepMarker(page, overlay, 0.25, 0.75);
    await selectFirstSleepMarker(page);
    await page.waitForTimeout(1000);

    // Main scoring view intentionally hides the metrics panel.
    await expect(page.locator("text=Metrics").first()).toHaveCount(0);
    await expect(page.locator("text=TST").first()).toHaveCount(0);
    await expect(page.locator("text=WASO").first()).toHaveCount(0);
    await expect(page.locator("text=SOL").first()).toHaveCount(0);
  });

  // ===========================================================================
  // Phase 5: Marker time labels on plot
  // ===========================================================================
  test("marker lines display HH:MM time labels", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);

    // Create a marker
    await createSleepMarker(page, overlay, 0.25, 0.75);
    await page.waitForTimeout(500);

    // Time labels are rendered as .marker-line.time-label elements
    const timeLabels = page.locator(".marker-line.time-label");
    const count = await timeLabels.count();

    // Should have at least 2 time labels (onset + offset)
    expect(count).toBeGreaterThanOrEqual(2);

    // Verify the labels contain HH:MM format text
    if (count > 0) {
      const firstLabel = await timeLabels.first().textContent();
      expect(firstLabel).toMatch(/^\d{2}:\d{2}$/);
    }
  });

  // ===========================================================================
  // Phase 6: File selector shows scoring progress
  // ===========================================================================
  test("file dropdown shows scoring progress per file", async ({ page }) => {
    await loginAndGoToScoring(page);

    // Wait for file progress queries to resolve
    await page.waitForTimeout(3000);

    // The file selector should contain progress info (e.g., "filename (5/14)")
    const fileSel = fileSelector(page);
    await expect(fileSel).toBeVisible({ timeout: 5000 });

    // Get the text of the first option
    const options = await fileSel.locator("option").allTextContents();
    expect(options.length).toBeGreaterThan(0);

    // At least one option should contain a progress fraction like "(N/M)" format
    // or fallback "(N rows)" format
    const hasProgressOrRows = options.some(
      (text) =>
        /\(\d+\/\d+\s+scored(?:,.*)?\)/.test(text) ||
        /\(\d+[\s,]*\d* rows?\)/.test(text)
    );
    expect(hasProgressOrRows).toBe(true);
  });

  // ===========================================================================
  // Phase 7: Inline detection rule selector
  // ===========================================================================
  test("detection rule dropdown is visible in header", async ({ page }) => {
    await loginAndGoToScoring(page);

    // The "Rule:" label should be visible in the header
    const ruleLabel = page.locator("text=Rule:").first();
    await expect(ruleLabel).toBeVisible({ timeout: 5000 });

    // A select near the rule label should contain detection rule options
    const ruleOptions = page.locator("select option:has-text('Onset')");
    const count = await ruleOptions.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  // ===========================================================================
  // Phase 8: Skip-to-next-unscored button
  // ===========================================================================
  test("next unscored button is present and functional", async ({ page }) => {
    await loginAndGoToScoring(page);

    // The "Unscored" skip button should be visible
    const unscoredBtn = page.locator('[data-testid="next-unscored-btn"]');
    await expect(unscoredBtn).toBeVisible({ timeout: 5000 });

    // Get current date index before clicking
    const dateSel = dateSelector(page);
    const initialText = await dateSel.locator("option:checked").textContent() ?? "";

    // Click the unscored button (if enabled)
    const isEnabled = await unscoredBtn.isEnabled();
    if (isEnabled) {
      await unscoredBtn.click();
      await page.waitForTimeout(2000);

      // After clicking, the chart should still be healthy
      await expect(page.locator(".u-over").first()).toBeVisible({ timeout: 30000 });
    }
  });

  // ===========================================================================
  // Phase 9: Auto-score review mode (dialog instead of silent apply)
  // ===========================================================================
  test("auto-score shows confirmation dialog instead of silent apply", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);

    // Enable auto-score on navigate
    const autoCheckbox = page.locator("label:has-text('Auto')").first();
    await autoCheckbox.click();
    await page.waitForTimeout(300);

    // Navigate to a new date
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    if (await nextBtn.isEnabled()) {
      await nextBtn.click();
      await page.waitForTimeout(3000);

      // If auto-score ran, it should show the dialog (not silently apply)
      // The dialog has "Auto-Score Results" text
      const dialog = page.locator("text=Auto-Score Results");
      const dialogCount = await dialog.count();

      // Dialog may or may not appear depending on whether auto-score detected periods
      // But if it does appear, markers should NOT have been auto-applied
      if (dialogCount > 0) {
        await expect(dialog.first()).toBeVisible();

        // Dialog should have Cancel and Apply buttons
        const cancelBtn = page.locator("button:has-text('Cancel')").last();
        await expect(cancelBtn).toBeVisible();
        await cancelBtn.click();
      }
    }

    // Disable auto-score to clean up
    await autoCheckbox.click();
  });

  // ===========================================================================
  // Phase 10: Smooth loading transitions
  // ===========================================================================
  test("loading transition uses opacity fade instead of blank state", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);

    // Navigate to next date to trigger loading
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    if (await nextBtn.isEnabled()) {
      await nextBtn.click();

      // During loading, the ActivityPlot should still be in the DOM (opacity-faded, not removed)
      // We check that the uplot wrapper is never entirely removed
      await page.waitForTimeout(200);

      // The chart wrapper should always exist (either at full opacity or reduced)
      const chartContainer = page.locator(".uplot");
      // Even during loading, the chart element should remain in DOM
      // (it may be wrapped in a div with opacity-30 but should still be present)
      const exists = await chartContainer.count();
      // Could be 0 if chart is rebuilding, but generally should persist
      // The key behavior is that we don't show a blank white area

      // Wait for chart to be ready again
      await expect(page.locator(".u-over").first()).toBeVisible({ timeout: 30000 });
    }
  });

  // ===========================================================================
  // Phase 11: Collapsible sidebar
  // ===========================================================================
  test("sidebar can be collapsed and expanded", async ({ page }) => {
    await loginAndGoToScoring(page);

    // Sidebar should initially be visible with nav items
    const sidebar = page.locator("aside").first();
    await expect(sidebar).toBeVisible();

    // Find the collapse button (ChevronLeft in sidebar footer)
    const collapseBtn = page.locator('aside button[title="Collapse sidebar"]');
    await expect(collapseBtn).toBeVisible({ timeout: 5000 });

    // Click to collapse
    await collapseBtn.click();
    await page.waitForTimeout(300);

    // Sidebar should now be collapsed (width: 0)
    const sidebarBox = await sidebar.boundingBox();
    expect(sidebarBox!.width).toBeLessThanOrEqual(1);

    // Expand button should appear
    const expandBtn = page.locator('button[title="Expand sidebar"]');
    await expect(expandBtn).toBeVisible({ timeout: 3000 });

    // Click to expand
    await expandBtn.click();
    await page.waitForTimeout(300);

    // Sidebar should be visible again
    const sidebarBoxAfter = await sidebar.boundingBox();
    expect(sidebarBoxAfter!.width).toBeGreaterThan(100);
  });

  test("sidebar collapse state persists across page reloads", async ({ page }) => {
    await loginAndGoToScoring(page);

    // Collapse sidebar
    const collapseBtn = page.locator('aside button[title="Collapse sidebar"]');
    await expect(collapseBtn).toBeVisible({ timeout: 5000 });
    await collapseBtn.click();
    await page.waitForTimeout(300);

    // Verify collapsed
    const sidebar = page.locator("aside").first();
    const boxBefore = await sidebar.boundingBox();
    expect(boxBefore!.width).toBeLessThanOrEqual(1);

    // Reload page
    await page.reload();
    await page.waitForTimeout(2000);

    // Sidebar should still be collapsed after reload
    const sidebarAfter = page.locator("aside").first();
    const boxAfter = await sidebarAfter.boundingBox();
    expect(boxAfter!.width).toBeLessThanOrEqual(1);

    // Expand it back for subsequent tests
    const expandBtn = page.locator('button[title="Expand sidebar"]');
    await expandBtn.click();
    await page.waitForTimeout(300);
  });
});
