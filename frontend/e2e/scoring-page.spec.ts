import { test, expect } from "@playwright/test";
import { loginAndGoToScoring, dateSelector, fileSelector } from "./helpers";

test.describe("Scoring Page", () => {
  test.beforeEach(async ({ page, context }) => {
    // Clear browser cache to ensure fresh bundles
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  });

  test("scoring page loads without JavaScript errors", async ({ page }) => {
    // Regression test: scoring.tsx had a TDZ error where dateStatusMap was used
    // before initialization (line 181 referenced a const defined at line 242).
    // This test ensures the page loads without any ReferenceError.
    const jsErrors: string[] = [];
    page.on("pageerror", (error) => {
      jsErrors.push(error.message);
    });

    await loginAndGoToScoring(page);

    // No JS errors should have been thrown during page load
    const criticalErrors = jsErrors.filter((e) =>
      e.includes("Cannot access") ||
      e.includes("ReferenceError") ||
      e.includes("is not defined") ||
      e.includes("before initialization")
    );
    expect(criticalErrors).toEqual([]);
  });

  test("displays activity plot with data", async ({ page }) => {
    // Login and wait for chart
    await loginAndGoToScoring(page);

    // Verify uPlot chart is rendered
    const uplotElement = page.locator(".uplot");
    await expect(uplotElement).toBeVisible();

    // Verify canvas exists and has proper dimensions
    const canvas = page.locator(".uplot canvas").first();
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThan(400);
    expect(box!.height).toBeGreaterThan(200);

    // Verify no "No activity data" message
    const noDataMessage = page.locator("text=No activity data");
    await expect(noDataMessage).toHaveCount(0);

    // Verify bottom panels are present - Sleep and Nonwear tabs with marker counts
    // These are div-based panel headers, not headings
    const sleepPanel = page.locator("text=Sleep").first();
    await expect(sleepPanel).toBeVisible({ timeout: 5000 });
    const nonwearPanel = page.locator("text=Nonwear").first();
    await expect(nonwearPanel).toBeVisible({ timeout: 5000 });

    // Verify file selector dropdown is present (first select is the file dropdown)
    const fileSelect = fileSelector(page);
    await expect(fileSelect).toBeVisible();
  });

  test("date navigation works", async ({ page }) => {
    // Login and wait for chart
    await loginAndGoToScoring(page);

    // Get initial date from the date dropdown selected option
    const dateSelect = dateSelector(page);
    await expect(dateSelect).toBeVisible({ timeout: 5000 });
    const initialCounter = await dateSelect.locator("option:checked").textContent() ?? "";

    // Click next date button using data-testid
    const nextButton = page.locator('[data-testid="next-date-btn"]');
    const prevButton = page.locator('[data-testid="prev-date-btn"]');
    await expect(nextButton).toBeVisible({ timeout: 5000 });
    await expect(prevButton).toBeVisible({ timeout: 5000 });
    if (await nextButton.isEnabled()) {
      await nextButton.click();
    } else if (await prevButton.isEnabled()) {
      await prevButton.click();
    } else {
      test.skip(true, "Only one date available; cannot validate date navigation");
    }

    // Wait for chart to re-render after date change
    await expect(page.locator(".u-over").first()).toBeVisible({ timeout: 30000 });
    await page.waitForTimeout(1500);

    // Verify date counter changed
    const newCounter = await dateSelect.locator("option:checked").textContent() ?? "";
    expect(newCounter).not.toBe(initialCounter);
  });

  test("file dropdown allows file switching", async ({ page }) => {
    // Login and wait for chart
    await loginAndGoToScoring(page);

    // Verify file dropdown is visible (first select is file dropdown)
    const fileSelect = fileSelector(page);
    await expect(fileSelect).toBeVisible({ timeout: 5000 });

    // Get initial selected value
    const initialValue = await fileSelect.inputValue();

    // Get all options
    const options = await fileSelect.locator("option").all();

    // If there are multiple files, try switching
    if (options.length > 1) {
      // Get the second option value
      const secondOptionValue = await options[1].getAttribute("value");
      if (secondOptionValue && secondOptionValue !== initialValue) {
        await fileSelect.selectOption(secondOptionValue);

        // Wait for chart to re-render after file change
        await expect(page.locator(".u-over").first()).toBeVisible({ timeout: 30000 });

        // Verify the selection changed
        const newValue = await fileSelect.inputValue();
        expect(newValue).toBe(secondOptionValue);
      }
    }
  });

  test("marker creation positions correctly on plot", async ({ page }) => {
    // Login and wait for chart
    const overlay = await loginAndGoToScoring(page);

    // Get initial overlay dimensions for click positioning
    const initialOverlayBox = await overlay.boundingBox();
    expect(initialOverlayBox).toBeTruthy();

    // Use the overlay's click method with position - handles scroll/viewport automatically
    // Click at 25% from left for onset (use force:true to click through existing markers)
    await overlay.click({
      position: { x: initialOverlayBox!.width * 0.25, y: initialOverlayBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);

    // Click at 75% from left for offset
    await overlay.click({
      position: { x: initialOverlayBox!.width * 0.75, y: initialOverlayBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);

    // Wait for marker region to appear (with specific data-testid)
    const markerRegion = page.locator('[data-testid^="marker-region-sleep-"]').first();

    // Wait for marker to be visible - it should render after state updates
    await expect(markerRegion).toBeVisible({ timeout: 5000 });

    // Get fresh bounding boxes AFTER marker is created (to account for any scrolling)
    const overlayBox = await overlay.boundingBox();
    const markerBox = await markerRegion.boundingBox();
    expect(overlayBox).toBeTruthy();
    expect(markerBox).toBeTruthy();

    // Verify marker is positioned within the plot overlay area (where data is drawn)
    // The marker should be within the overlay area (with small tolerance for rendering)
    expect(markerBox!.x).toBeGreaterThanOrEqual(overlayBox!.x - 10);
    expect(markerBox!.x + markerBox!.width).toBeLessThanOrEqual(
      overlayBox!.x + overlayBox!.width + 10
    );
    // Marker top should be at or near overlay top
    expect(markerBox!.y).toBeGreaterThanOrEqual(overlayBox!.y - 10);
    expect(markerBox!.y).toBeLessThan(overlayBox!.y + overlayBox!.height);
    // Marker should have meaningful height (similar to overlay)
    expect(markerBox!.height).toBeGreaterThan(overlayBox!.height * 0.8);
  });

  test("marker data table shows table titles when marker selected", async ({ page }) => {
    test.setTimeout(60000);

    // Login and wait for chart
    const overlay = await loginAndGoToScoring(page);
    const overlayBox = await overlay.boundingBox();
    expect(overlayBox).toBeTruthy();

    // Create a marker by clicking twice (use force:true to click through existing markers)
    await overlay.click({
      position: { x: overlayBox!.width * 0.25, y: overlayBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);
    await overlay.click({
      position: { x: overlayBox!.width * 0.75, y: overlayBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(1000);

    // Verify marker was created
    const markerRegions = page.locator('[data-testid^="marker-region-sleep-"]');
    await expect(markerRegions.first()).toBeVisible({ timeout: 5000 });

    // Newly created marker should be auto-selected and populate both tables.
    await page.waitForTimeout(1000);

    // Verify table titles appear when marker is selected
    const onsetTableTitle = page.locator("text=Sleep Onset");
    const offsetTableTitle = page.locator("text=Sleep Offset");
    await expect(onsetTableTitle.first()).toBeVisible({ timeout: 10000 });
    await expect(offsetTableTitle.first()).toBeVisible({ timeout: 10000 });
  });

  test("nonwear marker creation works", async ({ page }) => {
    test.setTimeout(60000);

    // Login and wait for chart
    const overlay = await loginAndGoToScoring(page);
    const overlayBox = await overlay.boundingBox();
    expect(overlayBox).toBeTruthy();

    // Switch to Nonwear mode by clicking the Nonwear mode button
    const nonwearModeButton = page.locator("button").filter({ hasText: "Nonwear" }).first();
    await nonwearModeButton.click();
    await page.waitForTimeout(500);

    // Create a nonwear marker by clicking twice
    await overlay.click({
      position: { x: overlayBox!.width * 0.3, y: overlayBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);
    await overlay.click({
      position: { x: overlayBox!.width * 0.5, y: overlayBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(1000);

    // Verify nonwear marker was created
    const markerRegions = page.locator('[data-testid^="marker-region-nonwear-"]');
    await expect(markerRegions.first()).toBeVisible({ timeout: 5000 });
  });

  test("markers persist after page reload", async ({ page }) => {
    test.setTimeout(60000);

    // Login and wait for chart
    const overlay = await loginAndGoToScoring(page);

    // Create a marker to ensure we have at least one
    const overlayBox = await overlay.boundingBox();
    expect(overlayBox).toBeTruthy();

    // Create a marker by clicking twice
    await overlay.click({
      position: { x: overlayBox!.width * 0.2, y: overlayBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);
    await overlay.click({
      position: { x: overlayBox!.width * 0.4, y: overlayBox!.height / 2 },
      force: true,
    });
    await page.waitForTimeout(3000); // Wait for auto-save

    // Verify at least one sleep marker region exists
    const sleepMarkers = page.locator('[data-testid^="marker-region-sleep-"]');
    const countBefore = await sleepMarkers.count();
    expect(countBefore).toBeGreaterThan(0);

    // Reload the page
    await page.reload();

    // Wait for the chart to be ready again
    await expect(page.locator(".u-over").first()).toBeVisible({ timeout: 30000 });

    // Wait for markers to load
    await page.waitForTimeout(3000);

    // Verify sleep markers were loaded from database
    const sleepMarkersAfter = page.locator('[data-testid^="marker-region-sleep-"]');
    const countAfter = await sleepMarkersAfter.count();
    expect(countAfter).toBeGreaterThan(0);
  });

  test("sleep rule arrows match desktop app style", async ({ page }) => {
    test.setTimeout(60000);

    // Login and wait for chart
    await loginAndGoToScoring(page);

    // Wait for markers and metrics to load
    await page.waitForTimeout(3000);

    // Check for sleep rule arrows (algorithm-detected onset/offset)
    const onsetArrow = page.locator('[data-testid^="sleep-rule-arrow-onset-"]');
    const offsetArrow = page.locator('[data-testid^="sleep-rule-arrow-offset-"]');

    const onsetCount = await onsetArrow.count();
    const offsetCount = await offsetArrow.count();
    console.log(`Sleep rule arrows - Onset: ${onsetCount}, Offset: ${offsetCount}`);

    // If arrows are present, verify their visual properties match desktop app
    if (onsetCount > 0) {
      const arrowEl = onsetArrow.first();
      await expect(arrowEl).toBeVisible();

      // Arrow should have meaningful size (40px total height = 25px tail + 15px head)
      const arrowBox = await arrowEl.boundingBox();
      expect(arrowBox).toBeTruthy();
      expect(arrowBox!.height).toBeGreaterThanOrEqual(30);
      expect(arrowBox!.width).toBeGreaterThanOrEqual(8);

      // Check label exists with "Sleep Onset at" text
      const onsetLabel = page.locator(".sleep-rule-label").filter({ hasText: /Sleep Onset at/ });
      if ((await onsetLabel.count()) > 0) {
        await expect(onsetLabel.first()).toBeVisible();
        const labelText = await onsetLabel.first().textContent();
        expect(labelText ?? "").toMatch(/3[-\s](minute rule applied|consecutive sleep epochs)/i);
      }
    }

    if (offsetCount > 0) {
      const arrowEl = offsetArrow.first();
      await expect(arrowEl).toBeVisible();

      // Check label exists with "Sleep Offset at" text
      const offsetLabel = page.locator(".sleep-rule-label").filter({ hasText: /Sleep Offset at/ });
      if ((await offsetLabel.count()) > 0) {
        await expect(offsetLabel.first()).toBeVisible();
        const labelText = await offsetLabel.first().textContent();
        expect(labelText ?? "").toMatch(/5[-\s](minute rule applied|consecutive (wake|sleep) epochs)/i);
      }
    }

  });

  test("navigation sidebar shows correct items", async ({ page }) => {
    // Login and wait for chart
    await loginAndGoToScoring(page);

    // Verify sidebar navigation items using href selectors for precision
    await expect(page.locator('a[href="/scoring"]')).toBeVisible();
    await expect(page.locator('a[href="/settings/study"]')).toBeVisible();
    await expect(page.locator('a[href="/settings/data"]')).toBeVisible();
    await expect(page.locator('a[href="/export"]')).toBeVisible();

    // Navigate to Study page
    await page.locator('a[href="/settings/study"]').click();
    await page.waitForURL("**/settings/study**", { timeout: 5000 });

    // Navigate to Data page
    await page.locator('a[href="/settings/data"]').click();
    await page.waitForURL("**/settings/data**", { timeout: 5000 });

    // Navigate back to Scoring
    await page.locator('a[href="/scoring"]').click();
    await page.waitForURL("**/scoring**", { timeout: 5000 });
  });
});
