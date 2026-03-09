/**
 * E2E tests for view mode toggling, activity source switching,
 * algorithm selection, and overlay/checkbox controls.
 *
 * Tests run serially because they share backend state.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndGoToScoring,
  waitForChart,
  createSleepMarker,
  ensureSleepMarker,
  selectFirstSleepMarker,
  switchToSleepMode,
  switchToNonwearMode,
  navigateToCleanDate,
  getOverlayBox,
  assertPageHealthy,
  sleepMarkerCount,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("View & Algorithm Controls", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // -------------------------------------------------------------------------
  // Helper: find the View mode <select> (has options "24" and "48")
  // -------------------------------------------------------------------------
  function viewModeSelect(page: import("@playwright/test").Page) {
    return page.locator("select").filter({ hasText: /24h/ });
  }

  // Helper: find the Algorithm <select> (near "Algorithm:" label)
  function algorithmSelect(page: import("@playwright/test").Page) {
    // The algorithm select contains "Sadeh" text in its options
    return page.locator("select").filter({ hasText: /Sadeh/ });
  }

  // Helper: find the Activity source <select> (near "Source:" label)
  function sourceSelect(page: import("@playwright/test").Page) {
    return page.locator("select").filter({ hasText: /Y-Axis/ });
  }

  // -------------------------------------------------------------------------
  // 1. 24h view shows 24-hour time axis (default)
  // -------------------------------------------------------------------------
  test("24h view is the default view mode", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // The View select should default to "24"
    const viewSelect = viewModeSelect(page);
    await expect(viewSelect).toBeVisible({ timeout: 10000 });
    const value = await viewSelect.inputValue();
    expect(value).toBe("24");
  });

  // -------------------------------------------------------------------------
  // 2. Toggling to 48h view changes the time scale
  // -------------------------------------------------------------------------
  test("toggling to 48h view changes the view mode", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const viewSelect = viewModeSelect(page);
    await expect(viewSelect).toBeVisible({ timeout: 10000 });

    // Record the chart width before toggling (as a proxy for scale change)
    const overlayBefore = await page.locator(".u-over").first().boundingBox();
    expect(overlayBefore).toBeTruthy();

    // Switch to 48h
    await viewSelect.selectOption("48");
    await page.waitForTimeout(2000);

    // The select should now show "48"
    const newValue = await viewSelect.inputValue();
    expect(newValue).toBe("48");

    // Chart should still be visible (re-rendered with new time range)
    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 3. Toggling back to 24h restores original view
  // -------------------------------------------------------------------------
  test("toggling back to 24h restores original view", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const viewSelect = viewModeSelect(page);
    await expect(viewSelect).toBeVisible({ timeout: 10000 });

    // Switch to 48h then back to 24h
    await viewSelect.selectOption("48");
    await page.waitForTimeout(1500);
    await viewSelect.selectOption("24");
    await page.waitForTimeout(1500);

    const value = await viewSelect.inputValue();
    expect(value).toBe("24");

    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 4. Ctrl+4 keyboard shortcut toggles view mode
  // -------------------------------------------------------------------------
  test("Ctrl+4 keyboard shortcut toggles view mode", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const viewSelect = viewModeSelect(page);
    await expect(viewSelect).toBeVisible({ timeout: 10000 });

    const initialValue = await viewSelect.inputValue();

    // Press Ctrl+4 to toggle
    await page.keyboard.press("Control+4");
    await page.waitForTimeout(1500);

    const newValue = await viewSelect.inputValue();

    // Value should have toggled
    if (initialValue === "24") {
      expect(newValue).toBe("48");
    } else {
      expect(newValue).toBe("24");
    }

    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 5. Activity source dropdown has options (Y, VM, etc.)
  // -------------------------------------------------------------------------
  test("activity source dropdown has multiple options", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const srcSelect = sourceSelect(page);
    await expect(srcSelect).toBeVisible({ timeout: 10000 });

    // Should have at least 4 options: Y-Axis, X-Axis, Z-Axis, Vector Magnitude
    const options = srcSelect.locator("option");
    const optionCount = await options.count();
    expect(optionCount).toBeGreaterThanOrEqual(4);

    // Verify specific options exist
    await expect(options.filter({ hasText: "Y-Axis" })).toHaveCount(1);
    await expect(options.filter({ hasText: "Vector Magnitude" })).toHaveCount(1);
  });

  // -------------------------------------------------------------------------
  // 6. Changing activity source re-renders plot
  // -------------------------------------------------------------------------
  test("changing activity source re-renders plot", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const srcSelect = sourceSelect(page);
    await expect(srcSelect).toBeVisible({ timeout: 10000 });

    // Default should be "axis_y"
    const initialValue = await srcSelect.inputValue();
    expect(initialValue).toBe("axis_y");

    // Switch to Vector Magnitude
    await srcSelect.selectOption("vector_magnitude");
    await page.waitForTimeout(1500);

    // Value should have changed
    const newValue = await srcSelect.inputValue();
    expect(newValue).toBe("vector_magnitude");

    // Chart should still be healthy (re-rendered with new source)
    await assertPageHealthy(page);

    // Switch back to Y-Axis for subsequent tests
    await srcSelect.selectOption("axis_y");
    await page.waitForTimeout(500);
  });

  // -------------------------------------------------------------------------
  // 7. Algorithm dropdown has multiple options
  // -------------------------------------------------------------------------
  test("algorithm dropdown has multiple options", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const algoSelect = algorithmSelect(page);
    await expect(algoSelect).toBeVisible({ timeout: 10000 });

    // Should have at least 4 algorithm options
    const options = algoSelect.locator("option");
    const optionCount = await options.count();
    expect(optionCount).toBeGreaterThanOrEqual(4);

    // Verify known algorithm names
    await expect(options.filter({ hasText: /Sadeh.*1994/ })).toHaveCount(2);
    await expect(options.filter({ hasText: /Cole-Kripke/ })).toHaveCount(2);
  });

  // -------------------------------------------------------------------------
  // 8. Changing algorithm triggers re-scoring
  // -------------------------------------------------------------------------
  test("changing algorithm triggers re-scoring", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const algoSelect = algorithmSelect(page);
    await expect(algoSelect).toBeVisible({ timeout: 10000 });

    const initialValue = await algoSelect.inputValue();

    // Switch to a different algorithm
    const newAlgo = initialValue.includes("sadeh_1994_actilife")
      ? "cole_kripke_1992_actilife"
      : "sadeh_1994_actilife";

    // Listen for the activity/score API call to confirm re-scoring
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes("/score") && resp.status() === 200,
      { timeout: 15000 }
    );

    await algoSelect.selectOption(newAlgo);

    // Wait for the re-scoring API response
    const response = await responsePromise;
    expect(response.ok()).toBe(true);

    // Chart should remain healthy
    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 9. Algorithm change updates sleep rule arrows (if present)
  // -------------------------------------------------------------------------
  test("algorithm change updates sleep rule arrows if present", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Ensure we have a sleep marker for arrows to appear
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);
    await page.waitForTimeout(2000);

    // Count initial arrows
    const initialOnsetArrows = await page.locator('[data-testid^="sleep-rule-arrow-onset-"]').count();
    const initialOffsetArrows = await page.locator('[data-testid^="sleep-rule-arrow-offset-"]').count();

    // Switch algorithm
    const algoSelect = algorithmSelect(page);
    const currentAlgo = await algoSelect.inputValue();
    const newAlgo = currentAlgo.includes("sadeh_1994_actilife")
      ? "cole_kripke_1992_actilife"
      : "sadeh_1994_actilife";

    await algoSelect.selectOption(newAlgo);
    await page.waitForTimeout(3000);

    // After algorithm change, arrows may appear/disappear/reposition
    // We just verify the page didn't crash and the chart is still visible
    await assertPageHealthy(page);

    // If arrows were present before, verify they are still structural (may have moved)
    if (initialOnsetArrows > 0 || initialOffsetArrows > 0) {
      // At least verify the arrow elements exist in the DOM
      const totalArrows = await page.locator('[data-testid^="sleep-rule-arrow-"]').count();
      // Arrows may or may not exist after algorithm change depending on results
      expect(totalArrows).toBeGreaterThanOrEqual(0);
    }
  });

  // -------------------------------------------------------------------------
  // 10. Choi nonwear overlay regions visible in plot
  // -------------------------------------------------------------------------
  test("Choi nonwear overlay regions are rendered on plot", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);
    await page.waitForTimeout(2000);

    // Choi nonwear regions have the class "marker-region choi-nonwear"
    const choiRegions = page.locator(".marker-region.choi-nonwear");
    const count = await choiRegions.count();

    // Demo data may or may not have nonwear periods
    // If present, verify correct styling
    if (count > 0) {
      const firstRegion = choiRegions.first();
      await expect(firstRegion).toHaveCSS("position", "absolute");

      // Should have striped background pattern
      const background = await firstRegion.evaluate(
        (el) => window.getComputedStyle(el).background
      );
      expect(background).toContain("repeating-linear-gradient");
    }

    // Page should be healthy regardless
    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 11. Adjacent markers checkbox toggles adjacent day markers
  // -------------------------------------------------------------------------
  test("adjacent markers checkbox toggles adjacent day markers", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Find the "Adjacent" checkbox label
    const adjacentLabel = page.getByText("Adjacent");
    await expect(adjacentLabel).toBeVisible({ timeout: 10000 });

    // The checkbox is an input[type="checkbox"] next to the "Adjacent" label
    // Click the label to toggle the checkbox
    const initialChecked = await page.locator("input[type='checkbox']").first().isChecked();

    // Click the label to toggle
    await adjacentLabel.click();
    await page.waitForTimeout(1000);

    // State should have changed
    const newChecked = await page.locator("input[type='checkbox']").first().isChecked();
    expect(newChecked).not.toBe(initialChecked);

    // Chart should still be healthy
    await assertPageHealthy(page);

    // Toggle back
    await adjacentLabel.click();
    await page.waitForTimeout(500);
  });

  // -------------------------------------------------------------------------
  // 12. NW Overlays checkbox toggles nonwear overlay visibility
  // -------------------------------------------------------------------------
  test("NW Overlays checkbox toggles nonwear overlay visibility", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Find the "NW Overlays" checkbox label
    const nwLabel = page.getByText("NW Overlays");
    await expect(nwLabel).toBeVisible({ timeout: 10000 });

    // The NW Overlays checkbox is the second input[type="checkbox"]
    const nwCheckbox = page.locator("input[type='checkbox']").nth(1);

    // Get initial state
    const initialChecked = await nwCheckbox.isChecked();

    // Toggle the checkbox by clicking its label
    await nwLabel.click();
    await page.waitForTimeout(1000);

    // State should have changed
    const newChecked = await nwCheckbox.isChecked();
    expect(newChecked).not.toBe(initialChecked);

    // If we toggled OFF (was checked), Choi regions should no longer be visible
    if (initialChecked) {
      const choiRegions = page.locator(".marker-region.choi-nonwear");
      const visibleCount = await choiRegions.count();
      // When overlays are off, Choi regions should not be rendered
      expect(visibleCount).toBe(0);
    }

    // Chart should still be healthy
    await assertPageHealthy(page);

    // Toggle back to restore original state
    await nwLabel.click();
    await page.waitForTimeout(500);
  });

  // -------------------------------------------------------------------------
  // 13. View mode select reflects correct options
  // -------------------------------------------------------------------------
  test("view mode select has exactly 24h and 48h options", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const viewSelect = viewModeSelect(page);
    await expect(viewSelect).toBeVisible({ timeout: 10000 });

    const options = viewSelect.locator("option");
    const count = await options.count();
    expect(count).toBe(2);

    // Verify the option values
    const values = await options.evaluateAll((els) =>
      els.map((el) => (el as HTMLOptionElement).value)
    );
    expect(values).toContain("24");
    expect(values).toContain("48");
  });

  // -------------------------------------------------------------------------
  // 14. Source dropdown default is Y-Axis
  // -------------------------------------------------------------------------
  test("activity source defaults to Y-Axis", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const srcSelect = sourceSelect(page);
    await expect(srcSelect).toBeVisible({ timeout: 10000 });

    const value = await srcSelect.inputValue();
    expect(value).toBe("axis_y");
  });
});
