/**
 * Comprehensive E2E tests for ALL keyboard shortcuts on the scoring page.
 *
 * Covers: date navigation (arrow keys), marker creation (click + Escape),
 * marker editing (Q/E/A/D), marker deletion (C/Delete), view toggle (Ctrl+4),
 * save (Ctrl+S), and the keyboard shortcuts help dialog.
 *
 * Tests run SERIALLY because they share a single backend and mutate marker state.
 */

import { test, expect, type Page } from "@playwright/test";
import {
  loginAndGoToScoring,
  ensureSleepMarker,
  selectFirstSleepMarker,
  navigateToCleanDate,
  createSleepMarker,
  getOverlayBox,
  switchToSleepMode,
  assertPageHealthy,
  sleepMarkerCount,
  getOnsetLine,
  getOffsetLine,
} from "./helpers";

// Serial execution: these tests share backend state and must not run in parallel.
test.describe.configure({ mode: "serial" });

test.describe("Keyboard Shortcuts - Comprehensive", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  /** Extract the "N/M" date counter text from the selected date dropdown option. */
  async function getDateCounter(page: Page): Promise<string> {
    // The date counter is embedded in the date selector dropdown option text like "(1/14)"
    const dateSelect = page.locator("select").filter({ has: page.locator("option:has-text('/')") }).first();
    await expect(dateSelect).toBeVisible({ timeout: 5000 });
    // Get the selected option's text which includes the (N/M) counter
    const selectedText = await dateSelect.locator("option:checked").textContent() ?? "";
    return selectedText;
  }

  /** Parse "N/M" into { current, total }. */
  function parseDateCounter(text: string): { current: number; total: number } {
    const match = text.match(/(\d+)\/(\d+)/);
    if (!match) return { current: 0, total: 0 };
    return { current: parseInt(match[1], 10), total: parseInt(match[2], 10) };
  }

  /** Navigate to the first date (index 0). */
  async function goToFirstDate(page: Page) {
    for (let i = 0; i < 20; i++) {
      const counter = await getDateCounter(page);
      const { current } = parseDateCounter(counter);
      if (current <= 1) break;
      await page.keyboard.press("ArrowLeft");
      await page.waitForTimeout(1000);
    }
  }

  /** Navigate to the last date. */
  async function goToLastDate(page: Page) {
    for (let i = 0; i < 30; i++) {
      const counter = await getDateCounter(page);
      const { current, total } = parseDateCounter(counter);
      if (current >= total) break;
      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(1000);
    }
  }

  // ===========================================================================
  // DATE NAVIGATION
  // ===========================================================================

  test("1. Right arrow key navigates to next date", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const initialCounter = await getDateCounter(page);
    const { current: initialNum } = parseDateCounter(initialCounter);

    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(1500);

    const newCounter = await getDateCounter(page);
    const { current: newNum } = parseDateCounter(newCounter);

    expect(newNum).toBe(initialNum + 1);
    await assertPageHealthy(page);
  });

  test("2. Left arrow key navigates to previous date", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // First go forward so we have room to go back
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(1500);
    const afterRight = await getDateCounter(page);
    const { current: afterRightNum } = parseDateCounter(afterRight);

    await page.keyboard.press("ArrowLeft");
    await page.waitForTimeout(1500);

    const afterLeft = await getDateCounter(page);
    const { current: afterLeftNum } = parseDateCounter(afterLeft);

    expect(afterLeftNum).toBe(afterRightNum - 1);
    await assertPageHealthy(page);
  });

  test("3. Multiple arrow key presses navigate multiple dates", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const initialCounter = await getDateCounter(page);
    const { current: initialNum, total } = parseDateCounter(initialCounter);

    // Press right arrow 3 times (if enough dates exist)
    const presses = Math.min(3, total - initialNum);
    for (let i = 0; i < presses; i++) {
      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(1000);
    }

    const newCounter = await getDateCounter(page);
    const { current: newNum } = parseDateCounter(newCounter);

    expect(newNum).toBe(initialNum + presses);
    await assertPageHealthy(page);
  });

  test("4. Arrow key at last date does nothing", async ({ page }) => {
    test.setTimeout(90000);
    await loginAndGoToScoring(page);
    await goToLastDate(page);

    const counterAtEnd = await getDateCounter(page);
    const { current: numAtEnd, total } = parseDateCounter(counterAtEnd);
    expect(numAtEnd).toBe(total);

    // Press right arrow - should stay at same date
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(1500);

    const counterAfter = await getDateCounter(page);
    expect(counterAfter).toBe(counterAtEnd);
    await assertPageHealthy(page);
  });

  test("5. Arrow key at first date does nothing", async ({ page }) => {
    test.setTimeout(90000);
    await loginAndGoToScoring(page);
    await goToFirstDate(page);

    const counterAtStart = await getDateCounter(page);
    const { current: numAtStart } = parseDateCounter(counterAtStart);
    expect(numAtStart).toBe(1);

    // Press left arrow - should stay at same date
    await page.keyboard.press("ArrowLeft");
    await page.waitForTimeout(1500);

    const counterAfter = await getDateCounter(page);
    expect(counterAfter).toBe(counterAtStart);
    await assertPageHealthy(page);
  });

  // ===========================================================================
  // MARKER CREATION
  // ===========================================================================

  test("6. Click plot once shows creation indicator", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);

    // Clear existing markers so click starts creation mode
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    const box = await getOverlayBox(overlay);
    await overlay.click({
      position: { x: box.width * 0.3, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);

    // After the first click, the creation indicator should appear
    // It says "Click plot for offset" when in placing_onset state
    const indicator = page.locator("text=/Click plot for/");
    await expect(indicator).toBeVisible({ timeout: 5000 });
    const text = await indicator.textContent();
    expect(text).toContain("offset");

    // Cancel to clean up
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  });

  test("7. Escape cancels marker creation", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);

    // Clear existing markers so clicks don't select existing markers
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    const beforeCount = await sleepMarkerCount(page);

    const box = await getOverlayBox(overlay);
    await overlay.click({
      position: { x: box.width * 0.3, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);

    // Verify indicator is visible
    const indicator = page.locator("text=/Click plot for/");
    await expect(indicator).toBeVisible({ timeout: 3000 });

    // Press Escape to cancel
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);

    // Indicator should be gone
    await expect(indicator).not.toBeVisible({ timeout: 3000 });

    // No new marker should have been created
    const afterCount = await sleepMarkerCount(page);
    expect(afterCount).toBe(beforeCount);
    await assertPageHealthy(page);
  });

  test("8. Right-click on plot cancels marker creation", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);

    // Clear existing markers so clicks start creation mode instead of selecting
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    const box = await getOverlayBox(overlay);
    // First click to start creation
    await overlay.click({
      position: { x: box.width * 0.3, y: box.height / 2 },
      force: true,
    });
    await page.waitForTimeout(500);

    const indicator = page.locator("text=/Click plot for/");
    await expect(indicator).toBeVisible({ timeout: 3000 });

    // Right-click to cancel
    await overlay.click({
      position: { x: box.width * 0.5, y: box.height / 2 },
      button: "right",
      force: true,
    });
    await page.waitForTimeout(500);

    // Indicator should be gone
    await expect(indicator).not.toBeVisible({ timeout: 3000 });
    await assertPageHealthy(page);
  });

  test("9. Second click completes marker creation", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);

    // Clear existing markers so clicks start creation mode
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(1500);
      }
    }

    const countBefore = await sleepMarkerCount(page);

    await createSleepMarker(page, overlay, 0.25, 0.75);

    // A new marker should exist
    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBeGreaterThan(countBefore);

    // Creation indicator should be gone
    const indicator = page.locator("text=/Click plot for/");
    await expect(indicator).not.toBeVisible({ timeout: 3000 });
    await assertPageHealthy(page);
  });

  // ===========================================================================
  // MARKER EDITING (Q/E/A/D)
  // ===========================================================================

  test("10. Q key moves onset line LEFT", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    const onsetLine = getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });

    const boxBefore = await onsetLine.boundingBox();
    expect(boxBefore).toBeTruthy();

    await page.keyboard.press("q");
    await page.waitForTimeout(500);

    const boxAfter = await onsetLine.boundingBox();
    expect(boxAfter).toBeTruthy();
    expect(boxAfter!.x).toBeLessThan(boxBefore!.x);
    await assertPageHealthy(page);
  });

  test("11. E key moves onset line RIGHT", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    const onsetLine = getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });

    const boxBefore = await onsetLine.boundingBox();
    expect(boxBefore).toBeTruthy();

    await page.keyboard.press("e");
    await page.waitForTimeout(500);

    const boxAfter = await onsetLine.boundingBox();
    expect(boxAfter).toBeTruthy();
    expect(boxAfter!.x).toBeGreaterThan(boxBefore!.x);
    await assertPageHealthy(page);
  });

  test("12. A key moves offset line LEFT", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    const offsetLine = getOffsetLine(page);
    await expect(offsetLine).toBeVisible({ timeout: 5000 });

    const boxBefore = await offsetLine.boundingBox();
    expect(boxBefore).toBeTruthy();

    await page.keyboard.press("a");
    await page.waitForTimeout(500);

    const boxAfter = await offsetLine.boundingBox();
    expect(boxAfter).toBeTruthy();
    expect(boxAfter!.x).toBeLessThan(boxBefore!.x);
    await assertPageHealthy(page);
  });

  test("13. D key moves offset line RIGHT", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    const offsetLine = getOffsetLine(page);
    await expect(offsetLine).toBeVisible({ timeout: 5000 });

    const boxBefore = await offsetLine.boundingBox();
    expect(boxBefore).toBeTruthy();

    await page.keyboard.press("d");
    await page.waitForTimeout(500);

    const boxAfter = await offsetLine.boundingBox();
    expect(boxAfter).toBeTruthy();
    expect(boxAfter!.x).toBeGreaterThan(boxBefore!.x);
    await assertPageHealthy(page);
  });

  test("14. Multiple Q presses accumulate (onset moves further left)", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    const onsetLine = getOnsetLine(page);
    await expect(onsetLine).toBeVisible({ timeout: 5000 });

    const boxInitial = await onsetLine.boundingBox();
    expect(boxInitial).toBeTruthy();

    // Press Q once
    await page.keyboard.press("q");
    await page.waitForTimeout(500);

    const boxAfterOne = await onsetLine.boundingBox();
    expect(boxAfterOne).toBeTruthy();
    expect(boxAfterOne!.x).toBeLessThan(boxInitial!.x);

    // Press Q two more times
    await page.keyboard.press("q");
    await page.waitForTimeout(300);
    await page.keyboard.press("q");
    await page.waitForTimeout(500);

    const boxAfterThree = await onsetLine.boundingBox();
    expect(boxAfterThree).toBeTruthy();

    // After 3 presses total, should be further left than after 1 press
    expect(boxAfterThree!.x).toBeLessThan(boxAfterOne!.x);
    await assertPageHealthy(page);
  });

  test("15. Q/E/A/D with no marker selected does nothing (no crash)", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);
    await switchToSleepMode(page);

    // Do NOT select any marker. Press all editing keys.
    await page.keyboard.press("q");
    await page.waitForTimeout(200);
    await page.keyboard.press("e");
    await page.waitForTimeout(200);
    await page.keyboard.press("a");
    await page.waitForTimeout(200);
    await page.keyboard.press("d");
    await page.waitForTimeout(200);

    // Page should still be fully functional
    await assertPageHealthy(page);

    // Verify the date counter is still visible (page did not break)
    const counter = await getDateCounter(page);
    expect(counter).toMatch(/\d+\/\d+/);
  });

  // ===========================================================================
  // MARKER DELETION
  // ===========================================================================

  test("16. C key with selected marker deletes it", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);
    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay, 0.25, 0.75);

    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThan(0);

    await selectFirstSleepMarker(page);

    await page.keyboard.press("c");
    await page.waitForTimeout(1000);

    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBeLessThan(countBefore);
    await assertPageHealthy(page);
  });

  test("17. Delete key with selected marker deletes it", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);
    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay, 0.25, 0.75);

    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThan(0);

    await selectFirstSleepMarker(page);

    await page.keyboard.press("Delete");
    await page.waitForTimeout(1000);

    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBeLessThan(countBefore);
    await assertPageHealthy(page);
  });

  test("18. C key with no marker selected does nothing", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);
    await ensureSleepMarker(page, overlay);

    // Do not select any marker
    const countBefore = await sleepMarkerCount(page);

    await page.keyboard.press("c");
    await page.waitForTimeout(500);

    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBe(countBefore);
    await assertPageHealthy(page);
  });

  // ===========================================================================
  // VIEW CONTROL
  // ===========================================================================

  test("19. Ctrl+4 toggles view mode from 24h to 48h", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Find the view mode select (the one near the "View:" label)
    const viewSelect = page.locator("select").filter({ hasText: /24h|48h/ }).first();
    await expect(viewSelect).toBeVisible({ timeout: 5000 });

    const initialValue = await viewSelect.inputValue();

    // Press Ctrl+4 to toggle
    await page.keyboard.press("Control+4");
    await page.waitForTimeout(1500);

    const newValue = await viewSelect.inputValue();

    if (initialValue === "24") {
      expect(newValue).toBe("48");
    } else {
      expect(newValue).toBe("24");
    }
    await assertPageHealthy(page);
  });

  test("20. Ctrl+4 again toggles back to original view", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const viewSelect = page.locator("select").filter({ hasText: /24h|48h/ }).first();
    await expect(viewSelect).toBeVisible({ timeout: 5000 });

    const initialValue = await viewSelect.inputValue();

    // Toggle once
    await page.keyboard.press("Control+4");
    await page.waitForTimeout(1500);

    const midValue = await viewSelect.inputValue();
    expect(midValue).not.toBe(initialValue);

    // Toggle again - should return to original
    await page.keyboard.press("Control+4");
    await page.waitForTimeout(1500);

    const finalValue = await viewSelect.inputValue();
    expect(finalValue).toBe(initialValue);
    await assertPageHealthy(page);
  });

  // ===========================================================================
  // SAVE
  // ===========================================================================

  test("21. Ctrl+S triggers save (save status indicator appears)", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);
    await switchToSleepMode(page);

    // Create a marker so there is something to save
    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay, 0.3, 0.7);

    // Wait for any auto-save to complete first
    await page.waitForTimeout(3000);

    // Modify the marker to make it dirty (move onset with Q)
    await selectFirstSleepMarker(page);
    await page.keyboard.press("q");
    await page.waitForTimeout(300);

    // Press Ctrl+S to force save
    await page.keyboard.press("Control+s");

    // The "Saving" indicator should appear (even briefly)
    // or transition to "Saved" status
    // We check for either "Saving" or "Saved" appearing within a short window
    const savingIndicator = page.locator("text=Saving");
    const savedIndicator = page.locator("text=Saved");

    // Wait for either indicator to appear
    await expect(
      savingIndicator.or(savedIndicator)
    ).toBeVisible({ timeout: 10000 });

    // Eventually the state should settle to "Saved"
    await expect(savedIndicator).toBeVisible({ timeout: 15000 });
    await assertPageHealthy(page);
  });

  // ===========================================================================
  // DIALOG
  // ===========================================================================

  test("22. Keyboard shortcuts dialog opens and closes with Escape", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Find the keyboard shortcuts button by its title attribute
    const shortcutsBtn = page.locator('button[title="Keyboard shortcuts"]');
    await expect(shortcutsBtn).toBeVisible({ timeout: 5000 });

    // Click to open the dialog
    await shortcutsBtn.click();
    await page.waitForTimeout(500);

    // Dialog should be visible with the title "Keyboard Shortcuts"
    const dialogTitle = page.getByRole("heading", { name: "Keyboard Shortcuts" });
    await expect(dialogTitle).toBeVisible({ timeout: 5000 });

    // Verify some shortcut descriptions are present
    await expect(page.getByText("Move onset/start LEFT 1 minute")).toBeVisible({ timeout: 3000 });
    await expect(page.getByText("Previous date")).toBeVisible({ timeout: 3000 });
    await expect(page.getByText("Delete selected marker").first()).toBeVisible({ timeout: 3000 });
    await expect(page.getByText("Toggle 24h / 48h view")).toBeVisible({ timeout: 3000 });
    await expect(page.getByText("Save markers")).toBeVisible({ timeout: 3000 });

    // Close with Escape
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);

    // Dialog should be gone
    await expect(dialogTitle).not.toBeVisible({ timeout: 5000 });
    await assertPageHealthy(page);
  });
});
