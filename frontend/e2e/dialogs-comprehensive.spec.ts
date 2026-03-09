/**
 * Comprehensive E2E tests for dialog components on the scoring page:
 * - Color Legend dialog
 * - Keyboard Shortcuts dialog
 * - Popout Table dialog
 * - Clear All confirmation dialog (native browser confirm)
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
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Dialogs - Comprehensive", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // ==========================================================================
  // COLOR LEGEND DIALOG
  // ==========================================================================

  test("color legend opens on button click and shows 'Color Legend' heading", async ({ page }) => {
    await loginAndGoToScoring(page);

    const helpBtn = page.locator('[data-testid="color-legend-btn"]');
    await expect(helpBtn).toBeVisible({ timeout: 5000 });
    await helpBtn.click();

    const heading = page.getByRole("heading", { name: "Color Legend" });
    await expect(heading).toBeVisible({ timeout: 5000 });
  });

  test("color legend shows sleep marker color section", async ({ page }) => {
    await loginAndGoToScoring(page);

    await page.locator('[data-testid="color-legend-btn"]').click();
    await expect(page.getByRole("heading", { name: "Color Legend" })).toBeVisible({ timeout: 5000 });

    // The dialog should contain a "Sleep Markers" section heading
    await expect(page.getByText("Sleep Markers")).toBeVisible({ timeout: 3000 });
    // It should show marker types
    await expect(page.getByText("Onset Line")).toBeVisible();
    await expect(page.getByText("Offset Line")).toBeVisible();
  });

  test("color legend shows nonwear marker color section", async ({ page }) => {
    await loginAndGoToScoring(page);

    await page.locator('[data-testid="color-legend-btn"]').click();
    await expect(page.getByRole("heading", { name: "Color Legend" })).toBeVisible({ timeout: 5000 });

    await expect(page.getByText("Nonwear Markers")).toBeVisible({ timeout: 3000 });
    await expect(page.getByText("Manual Nonwear", { exact: true })).toBeVisible();
    await expect(page.getByText("Choi Nonwear", { exact: true })).toBeVisible();
  });

  test("color legend shows keyboard shortcuts section", async ({ page }) => {
    await loginAndGoToScoring(page);

    await page.locator('[data-testid="color-legend-btn"]').click();
    await expect(page.getByRole("heading", { name: "Color Legend" })).toBeVisible({ timeout: 5000 });

    // The color legend has a "Keyboard Shortcuts" section inside it
    await expect(page.getByText("Keyboard Shortcuts")).toBeVisible({ timeout: 3000 });
    await expect(page.getByText("Navigate dates")).toBeVisible();
    await expect(page.getByText("Delete selected marker").first()).toBeVisible();
  });

  test("color legend closes with Escape", async ({ page }) => {
    await loginAndGoToScoring(page);

    await page.locator('[data-testid="color-legend-btn"]').click();
    const heading = page.getByRole("heading", { name: "Color Legend" });
    await expect(heading).toBeVisible({ timeout: 5000 });

    await page.keyboard.press("Escape");

    await expect(heading).not.toBeVisible({ timeout: 5000 });
  });

  // ==========================================================================
  // KEYBOARD SHORTCUTS DIALOG
  // ==========================================================================

  test("keyboard shortcuts dialog opens and shows shortcut keys", async ({ page }) => {
    await loginAndGoToScoring(page);

    // The keyboard shortcuts button has a Keyboard icon and title="Keyboard shortcuts"
    const kbdBtn = page.locator('button[title="Keyboard shortcuts"]');
    await expect(kbdBtn).toBeVisible({ timeout: 5000 });
    await kbdBtn.click();

    const heading = page.getByRole("heading", { name: /Keyboard Shortcuts/ });
    await expect(heading).toBeVisible({ timeout: 5000 });

    // Should show actual key references
    await expect(page.getByText("Previous date")).toBeVisible({ timeout: 3000 });
    await expect(page.getByText("Next date")).toBeVisible();
    await expect(page.getByText("Delete selected marker").first()).toBeVisible();
  });

  test("keyboard shortcuts dialog has sections (Marker Placement, Navigation, etc.)", async ({ page }) => {
    await loginAndGoToScoring(page);

    await page.locator('button[title="Keyboard shortcuts"]').click();
    await expect(page.getByRole("heading", { name: /Keyboard Shortcuts/ })).toBeVisible({ timeout: 5000 });

    // Verify all four sections defined in SHORTCUT_SECTIONS
    await expect(page.getByText("Marker Placement")).toBeVisible({ timeout: 3000 });
    await expect(page.getByText("Marker Editing", { exact: true })).toBeVisible();
    await expect(page.getByText("Navigation", { exact: true })).toBeVisible();
    await expect(page.getByText("View & Controls")).toBeVisible();
  });

  test("keyboard shortcuts dialog closes with Escape", async ({ page }) => {
    await loginAndGoToScoring(page);

    await page.locator('button[title="Keyboard shortcuts"]').click();
    const heading = page.getByRole("heading", { name: /Keyboard Shortcuts/ });
    await expect(heading).toBeVisible({ timeout: 5000 });

    await page.keyboard.press("Escape");

    await expect(heading).not.toBeVisible({ timeout: 5000 });
  });

  // ==========================================================================
  // POPOUT TABLE DIALOG
  // ==========================================================================

  test("popout table dialog opens from onset table", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const popoutBtn = page.locator('button[title="Open full table"]').first();
    await expect(popoutBtn).toBeVisible({ timeout: 5000 });
    await popoutBtn.click();

    await expect(page.getByText("Full Day Activity Data")).toBeVisible({ timeout: 5000 });
  });

  test("popout table dialog shows data columns", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const popoutBtn = page.locator('button[title="Open full table"]').first();
    await expect(popoutBtn).toBeVisible({ timeout: 5000 });
    await popoutBtn.click();

    await expect(page.getByText("Full Day Activity Data")).toBeVisible({ timeout: 5000 });

    // Wait for data to load (table should appear after API response)
    await page.waitForTimeout(2000);

    // The popout table should show column headers
    const dialog = page.locator('[role="dialog"]');
    if (await dialog.isVisible({ timeout: 2000 })) {
      // Check for at least some expected columns from the table header
      await expect(dialog.getByRole("columnheader", { name: "#" })).toBeVisible({ timeout: 3000 });
      await expect(dialog.getByRole("columnheader", { name: "Time" })).toBeVisible();
      await expect(dialog.getByRole("columnheader", { name: "Axis Y" })).toBeVisible();
    }
  });

  test("popout table dialog closes with Escape", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const popoutBtn = page.locator('button[title="Open full table"]').first();
    await expect(popoutBtn).toBeVisible({ timeout: 5000 });
    await popoutBtn.click();

    const dialogTitle = page.getByText("Full Day Activity Data");
    await expect(dialogTitle).toBeVisible({ timeout: 5000 });

    await page.keyboard.press("Escape");
    await expect(dialogTitle).not.toBeVisible({ timeout: 5000 });
  });

  // ==========================================================================
  // CLEAR ALL CONFIRMATION DIALOG
  // ==========================================================================

  test("Clear All markers shows confirmation dialog (native confirm)", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Ensure a marker exists so Clear has something to do
    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay);
    const count = await sleepMarkerCount(page);
    expect(count).toBeGreaterThan(0);

    // Set up dialog handler BEFORE clicking Clear
    let dialogMessage = "";
    page.once("dialog", async (dialog) => {
      dialogMessage = dialog.message();
      await dialog.dismiss(); // Dismiss so markers are NOT cleared
    });

    // Click the Clear button (has Trash icon and text "Clear")
    const clearBtn = page.locator("button").filter({ hasText: "Clear" }).last();
    await clearBtn.click();

    // Verify the confirmation dialog was shown
    await page.waitForTimeout(500);
    expect(dialogMessage).toContain("Clear all markers");
  });

  test("dismissing Clear All confirmation keeps markers", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay);

    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThan(0);

    // Dismiss the dialog (cancel the clear)
    page.once("dialog", async (dialog) => {
      await dialog.dismiss();
    });

    const clearBtn = page.locator("button").filter({ hasText: "Clear" }).last();
    await clearBtn.click();
    await page.waitForTimeout(500);

    // Markers should still be there
    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBe(countBefore);
  });

  test("accepting Clear All confirmation removes all markers", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay);

    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThan(0);

    // Accept the dialog (confirm the clear)
    page.once("dialog", async (dialog) => {
      await dialog.accept();
    });

    const clearBtn = page.locator("button").filter({ hasText: "Clear" }).last();
    await clearBtn.click();
    await page.waitForTimeout(1000);

    // Markers should be gone
    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBe(0);
  });
});
