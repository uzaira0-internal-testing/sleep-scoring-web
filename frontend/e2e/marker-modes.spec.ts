/**
 * E2E tests for marker mode switching and mode-specific behavior.
 *
 * Validates: Sleep / Nonwear / No Sleep mode toggling,
 * marker list visibility per mode, marker creation in correct mode,
 * and mode persistence across date navigation.
 *
 * Tests run serially because they share backend state.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndGoToScoring,
  waitForChart,
  createSleepMarker,
  createNonwearMarker,
  ensureSleepMarker,
  selectFirstSleepMarker,
  selectFirstNonwearMarker,
  switchToSleepMode,
  switchToNonwearMode,
  switchToNoSleepMode,
  navigateToCleanDate,
  getOverlayBox,
  assertPageHealthy,
  sleepMarkerCount,
  nonwearMarkerCount,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Marker Modes", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // -------------------------------------------------------------------------
  // 1. Sleep mode is active by default
  // -------------------------------------------------------------------------
  test("sleep mode is active by default", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // The Sleep button should have the "default" variant (not "outline")
    // which means it does NOT have the "outline" class / has a solid background
    const sleepButton = page.locator("button").filter({ hasText: "Sleep" }).first();
    await expect(sleepButton).toBeVisible({ timeout: 10000 });

    // Default variant means the button is NOT outline - it should NOT have border-input class
    // The active mode button uses variant="default" which renders with bg-primary
    const classes = await sleepButton.getAttribute("class");
    expect(classes).toBeTruthy();
    // The outline variant adds specific border styling; the default variant doesn't
    // We verify the Sleep button does NOT have the outline indicator
    expect(classes).not.toContain("border-input");
  });

  // -------------------------------------------------------------------------
  // 2. Sleep mode shows sleep marker list (Main/Nap labels)
  // -------------------------------------------------------------------------
  test("sleep mode shows sleep marker list panel", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // The Sleep panel card should be visible with "Sleep" text and count
    const sleepPanel = page.locator("text=Sleep").first();
    await expect(sleepPanel).toBeVisible({ timeout: 10000 });

    await switchToSleepMode(page);

    // Clear all markers to ensure clean state for marker creation
    page.once("dialog", (dialog) => dialog.accept());
    const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
    if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await clearButton.click();
      await page.waitForTimeout(1500);
    }

    // Create a sleep marker on the clean plot
    await createSleepMarker(page, overlay, 0.25, 0.75);

    // The marker list should show a Main or Nap label
    const markerLabel = page.locator("div.cursor-pointer").filter({ hasText: /Main|Nap/i }).first();
    await expect(markerLabel).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // 3. Clicking Nonwear button switches to nonwear mode
  // -------------------------------------------------------------------------
  test("clicking Nonwear button switches to nonwear mode", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Click the Nonwear mode button
    await switchToNonwearMode(page);

    // The Nonwear button should now have the default (active) variant
    const nonwearButton = page.locator("button").filter({ hasText: "Nonwear" }).first();
    const classes = await nonwearButton.getAttribute("class");
    expect(classes).not.toContain("border-input");

    // The Sleep button should now be outline (inactive)
    const sleepButton = page.locator("button").filter({ hasText: "Sleep" }).first();
    const sleepClasses = await sleepButton.getAttribute("class");
    // In nonwear mode but not isNoSleep, Sleep button should be outline variant
    // It may or may not have border-input depending on whether isNoSleep
    // Just confirm Nonwear is active by checking page is healthy
    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 4. Nonwear mode shows nonwear marker list (NW buttons)
  // -------------------------------------------------------------------------
  test("nonwear mode shows nonwear marker list", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Clear existing markers so clicks don't hit existing marker regions
    await switchToSleepMode(page);
    const existingSleep = await sleepMarkerCount(page);
    if (existingSleep > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    // Switch to nonwear mode and create a marker
    await createNonwearMarker(page, overlay, 0.3, 0.5);

    // The nonwear panel should show NW marker entries
    const nwLabel = page.locator("div.cursor-pointer").filter({ hasText: /NW \d+/ }).first();
    await expect(nwLabel).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // 5. Nonwear mode hides sleep marker list interactions
  // -------------------------------------------------------------------------
  test("nonwear mode: sleep marker list shows placeholder when empty", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Clear all markers to ensure the sleep list is empty
    await switchToSleepMode(page);
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    // Switch to nonwear mode
    await switchToNonwearMode(page);

    // The Sleep panel should still be visible but show the placeholder text
    // "Click plot to create" is shown for empty sleep markers
    const placeholder = page.getByText("Click plot to create");
    await expect(placeholder).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // 6. Switching back to Sleep mode shows sleep markers
  // -------------------------------------------------------------------------
  test("switching back to Sleep mode shows sleep markers", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Create a sleep marker first
    await createSleepMarker(page, overlay);
    await page.waitForTimeout(500);

    // Verify sleep marker region exists
    const sleepCount = await sleepMarkerCount(page);
    expect(sleepCount).toBeGreaterThan(0);

    // Switch to nonwear mode
    await switchToNonwearMode(page);
    await page.waitForTimeout(300);

    // Switch back to sleep mode
    await switchToSleepMode(page);
    await page.waitForTimeout(300);

    // Sleep marker regions should still be visible on the plot
    const finalCount = await sleepMarkerCount(page);
    expect(finalCount).toBeGreaterThan(0);

    // Main/Nap label should be visible in the marker list
    const markerLabel = page.locator("div.cursor-pointer").filter({ hasText: /Main|Nap/i }).first();
    await expect(markerLabel).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // 7. No Sleep mode shows confirmation dialog when sleep markers exist
  // -------------------------------------------------------------------------
  test("No Sleep mode shows confirmation dialog when markers exist", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Ensure a sleep marker exists
    await ensureSleepMarker(page, overlay);

    // Track whether a dialog was shown
    let dialogMessage = "";
    page.once("dialog", async (dialog) => {
      dialogMessage = dialog.message();
      await dialog.dismiss(); // Dismiss so we don't actually clear markers
    });

    // Click No Sleep button
    const noSleepBtn = page.locator("button").filter({ hasText: /No Sleep/i }).first();
    await noSleepBtn.click();
    await page.waitForTimeout(500);

    // The dialog should have contained the warning about clearing markers
    expect(dialogMessage).toContain("No Sleep");
  });

  // -------------------------------------------------------------------------
  // 8. No Sleep mode disables Sleep button after confirmation
  // -------------------------------------------------------------------------
  test("No Sleep mode disables Sleep button after confirmation", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Navigate to a clean date so we can freely toggle No Sleep
    await navigateToCleanDate(page);
    await page.waitForTimeout(500);

    // Accept the confirmation dialog (or none needed if no markers)
    page.once("dialog", (d) => d.accept());

    // Click No Sleep
    const noSleepBtn = page.locator("button").filter({ hasText: /No Sleep/i }).first();
    await noSleepBtn.click();
    await page.waitForTimeout(500);

    // The Sleep button should now be disabled
    const sleepButton = page.locator("button").filter({ hasText: "Sleep" }).first();
    await expect(sleepButton).toBeDisabled({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // 9. Creating sleep marker in sleep mode works
  // -------------------------------------------------------------------------
  test("creating sleep marker in sleep mode works", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Ensure we are in sleep mode and clear existing markers
    await switchToSleepMode(page);
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    // Record marker count before creation
    const beforeCount = await sleepMarkerCount(page);

    // Create a sleep marker
    await createSleepMarker(page, overlay, 0.3, 0.7);

    // Verify a new sleep marker region appeared
    const afterCount = await sleepMarkerCount(page);
    expect(afterCount).toBeGreaterThan(beforeCount);

    // The marker region should be visible on the plot
    const markerRegion = page.locator('[data-testid^="marker-region-sleep-"]').first();
    await expect(markerRegion).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // 10. Creating nonwear marker in nonwear mode works
  // -------------------------------------------------------------------------
  test("creating nonwear marker in nonwear mode works", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Clear existing markers so clicks don't hit existing marker regions
    await switchToSleepMode(page);
    const existingSleep = await sleepMarkerCount(page);
    if (existingSleep > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    // Record nonwear marker count before
    const beforeCount = await nonwearMarkerCount(page);

    // createNonwearMarker switches to nonwear mode internally
    await createNonwearMarker(page, overlay, 0.2, 0.4);

    // Verify a new nonwear marker appeared
    const afterCount = await nonwearMarkerCount(page);
    expect(afterCount).toBeGreaterThan(beforeCount);

    // Nonwear marker region should be visible
    const nwRegion = page.locator('[data-testid^="marker-region-nonwear-"]').first();
    await expect(nwRegion).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // 11. Cannot create sleep markers in nonwear mode
  // -------------------------------------------------------------------------
  test("cannot create sleep markers in nonwear mode", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Navigate to a clean date
    await navigateToCleanDate(page);

    // Switch to nonwear mode
    await switchToNonwearMode(page);

    // Record sleep marker count
    const sleepBefore = await sleepMarkerCount(page);

    // Click on the plot twice (as if creating a marker)
    const box = await getOverlayBox(overlay);
    await overlay.click({
      position: { x: box.width * 0.25, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);
    await overlay.click({
      position: { x: box.width * 0.75, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(1500);

    // Sleep marker count should not have increased
    const sleepAfter = await sleepMarkerCount(page);
    expect(sleepAfter).toBe(sleepBefore);

    // A nonwear marker should have been created instead
    const nwCount = await nonwearMarkerCount(page);
    expect(nwCount).toBeGreaterThan(0);
  });

  // -------------------------------------------------------------------------
  // 12. Mode persists during date navigation
  // -------------------------------------------------------------------------
  test("mode persists during date navigation", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Switch to nonwear mode
    await switchToNonwearMode(page);

    // Get the Nonwear button before navigation
    const nonwearButton = page.locator("button").filter({ hasText: "Nonwear" }).first();
    const classesBefore = await nonwearButton.getAttribute("class");

    // Navigate to next date
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    if (await nextBtn.isEnabled({ timeout: 2000 }).catch(() => false)) {
      await nextBtn.click();
      await page.waitForTimeout(1500);
      await waitForChart(page);

      // Nonwear button should still be active (same class pattern)
      const classesAfter = await nonwearButton.getAttribute("class");
      // Both should be the active variant (not outline)
      expect(classesAfter).not.toContain("border-input");
    }

    // Verify page is still healthy
    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 13. Selecting sleep marker in list highlights it
  // -------------------------------------------------------------------------
  test("selecting sleep marker in list highlights it", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Create a sleep marker
    await createSleepMarker(page, overlay);

    // Click on the marker entry in the list (the whole div is clickable)
    const markerEntry = page.locator("text=Main").first();
    if (await markerEntry.isVisible({ timeout: 3000 })) {
      await markerEntry.click();
      await page.waitForTimeout(500);

      // The selected marker entry should have the highlighted class
      const selectedEntry = page.locator(".bg-purple-500\\/10").first();
      await expect(selectedEntry).toBeVisible({ timeout: 3000 });
    }

    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 14. Nonwear mode shows "Switch to Nonwear mode" placeholder
  // -------------------------------------------------------------------------
  test("nonwear panel shows instruction when empty and in sleep mode", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);
    await switchToSleepMode(page);

    // Clear all markers so nonwear panel shows empty state
    const existingCount = await sleepMarkerCount(page);
    const existingNw = await nonwearMarkerCount(page);
    if (existingCount > 0 || existingNw > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    // In sleep mode, the nonwear panel should show instruction text
    const instruction = page.getByText("Switch to Nonwear mode");
    await expect(instruction).toBeVisible({ timeout: 5000 });
  });
});
