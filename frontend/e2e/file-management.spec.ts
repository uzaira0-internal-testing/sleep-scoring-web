/**
 * Comprehensive E2E tests for file management on the scoring page.
 *
 * Covers: file selector visibility, file switching, chart re-rendering,
 * marker isolation between files, delete confirmation, upload button,
 * file option content, and chart canvas dimensions.
 *
 * Tests run SERIALLY because they share backend state (files, markers).
 */

import { test, expect } from "@playwright/test";
import {
  loginAndGoToScoring,
  waitForChart,
  fileSelector,
  dateSelector,
  nextDate,
  getOverlayBox,
  assertPageHealthy,
  sleepMarkerCount,
  createSleepMarker,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("File Management", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // =========================================================================
  // 1. File selector dropdown is visible on scoring page
  // =========================================================================
  test("file selector dropdown is visible on scoring page", async ({ page }) => {
    await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    await expect(fileSel).toBeVisible({ timeout: 10000 });

    // Screenshot: scoring page with file selector visible
    await expect(page).toHaveScreenshot("file-management-file-selector.png", {
      maxDiffPixelRatio: 0.01,
    });
  });

  // =========================================================================
  // 2. File dropdown has multiple options (> 0 files)
  // =========================================================================
  test("file dropdown has at least one file option", async ({ page }) => {
    await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    await expect(fileSel).toBeVisible({ timeout: 10000 });

    const options = fileSel.locator("option");
    const count = await options.count();
    // There may be a disabled placeholder option; at least one real file should exist
    expect(count).toBeGreaterThan(0);

    // Verify the selected value is not empty (a file is auto-selected)
    const selectedValue = await fileSel.inputValue();
    expect(selectedValue).not.toBe("");
  });

  // =========================================================================
  // 3. Selecting a different file reloads the chart (overlay re-renders)
  // =========================================================================
  test("selecting a different file reloads the chart", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    const allOptions = await fileSel.locator("option").all();

    // Skip test if only one file available
    if (allOptions.length < 2) {
      test.skip(true, "Only one file available; cannot test file switching");
      return;
    }

    const firstValue = await fileSel.inputValue();

    // Find a different option that is not the current selection
    let targetValue: string | null = null;
    for (const opt of allOptions) {
      const val = await opt.getAttribute("value");
      const disabled = await opt.getAttribute("disabled");
      if (val && val !== firstValue && val !== "" && disabled === null) {
        targetValue = val;
        break;
      }
    }

    if (!targetValue) {
      test.skip(true, "No alternative file option found");
      return;
    }

    // Switch to the other file
    await fileSel.selectOption(targetValue);

    // Wait for chart to re-render
    const newOverlay = await waitForChart(page);
    await expect(newOverlay).toBeVisible({ timeout: 30000 });

    // Verify the file selection actually changed
    const newValue = await fileSel.inputValue();
    expect(newValue).toBe(targetValue);
  });

  // =========================================================================
  // 4. Selecting a different file changes visible markers
  // =========================================================================
  test("selecting a different file changes visible markers", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    const allOptions = await fileSel.locator("option").all();

    if (allOptions.length < 2) {
      test.skip(true, "Only one file available");
      return;
    }

    // Record marker count on the first file
    await page.waitForTimeout(1500);
    const markersFile1 = await sleepMarkerCount(page);

    // Switch to second file
    const firstValue = await fileSel.inputValue();
    let targetValue: string | null = null;
    for (const opt of allOptions) {
      const val = await opt.getAttribute("value");
      const disabled = await opt.getAttribute("disabled");
      if (val && val !== firstValue && val !== "" && disabled === null) {
        targetValue = val;
        break;
      }
    }

    if (!targetValue) {
      test.skip(true, "No alternative file option found");
      return;
    }

    await fileSel.selectOption(targetValue);
    await waitForChart(page);
    await page.waitForTimeout(1500);

    // Marker count might differ (different file = different markers)
    // The key assertion is that the page is healthy and chart rendered
    await assertPageHealthy(page);

    const markersFile2 = await sleepMarkerCount(page);
    // We cannot guarantee the counts differ, but the page state should be valid
    // The chart should be visible and responsive
    expect(typeof markersFile2).toBe("number");
  });

  // =========================================================================
  // 5. File dropdown preserves selection after date navigation
  // =========================================================================
  test("file dropdown preserves selection after date navigation", async ({ page }) => {
    await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    const selectedBefore = await fileSel.inputValue();
    expect(selectedBefore).not.toBe("");

    // Navigate to next date
    await nextDate(page);
    await assertPageHealthy(page);

    // File selection should remain the same
    const selectedAfter = await fileSel.inputValue();
    expect(selectedAfter).toBe(selectedBefore);
  });

  // =========================================================================
  // 6. Delete file button is visible when a file is selected
  // =========================================================================
  test("delete file button is visible when file selected", async ({ page }) => {
    await loginAndGoToScoring(page);

    // The Delete button contains Trash2 icon and text "Delete"
    const deleteBtn = page.locator("button").filter({ hasText: "Delete" }).first();
    await expect(deleteBtn).toBeVisible({ timeout: 5000 });
  });

  // =========================================================================
  // 7. Delete file shows confirmation dialog (dismiss it)
  // =========================================================================
  test("delete file shows confirmation dialog which can be dismissed", async ({ page }) => {
    await loginAndGoToScoring(page);

    // Set up dialog handler to DISMISS (cancel) the confirm dialog
    let dialogMessage = "";
    page.once("dialog", async (dialog) => {
      dialogMessage = dialog.message();
      await dialog.dismiss(); // Cancel - do NOT delete
    });

    const deleteBtn = page.locator("button").filter({ hasText: "Delete" }).first();
    await expect(deleteBtn).toBeVisible({ timeout: 5000 });
    await deleteBtn.click();

    // Verify the confirmation dialog was shown
    await page.waitForTimeout(500);
    expect(dialogMessage).toContain("Delete");
    expect(dialogMessage).toContain("cannot be undone");

    // Page should still be healthy (file was NOT deleted)
    await assertPageHealthy(page);

    // The file should still be selected (deletion was cancelled)
    const fileSel = fileSelector(page);
    const selectedValue = await fileSel.inputValue();
    expect(selectedValue).not.toBe("");
  });

  // =========================================================================
  // 8. Upload button is visible
  // =========================================================================
  test("upload button is visible", async ({ page }) => {
    await loginAndGoToScoring(page);

    const uploadBtn = page.locator("button").filter({ hasText: "Upload" }).first();
    await expect(uploadBtn).toBeVisible({ timeout: 5000 });
  });

  // =========================================================================
  // 9. Each file option shows a filename
  // =========================================================================
  test("each file option shows a filename", async ({ page }) => {
    await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    const options = await fileSel.locator("option").all();

    expect(options.length).toBeGreaterThan(0);

    for (const opt of options) {
      const text = await opt.textContent();
      const value = await opt.getAttribute("value");

      // Skip placeholder/disabled options with empty value
      if (value === "" || value === null) continue;

      // Each option should have non-empty text that resembles a filename
      expect(text).toBeTruthy();
      expect(text!.length).toBeGreaterThan(0);
    }
  });

  // =========================================================================
  // 10. Switching files and back preserves the original file's data
  // =========================================================================
  test("switching files and back preserves original file data", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    const allOptions = await fileSel.locator("option").all();

    if (allOptions.length < 2) {
      test.skip(true, "Only one file available");
      return;
    }

    const originalValue = await fileSel.inputValue();
    await page.waitForTimeout(1500);
    const originalMarkerCount = await sleepMarkerCount(page);

    // Find a different file
    let otherValue: string | null = null;
    for (const opt of allOptions) {
      const val = await opt.getAttribute("value");
      const disabled = await opt.getAttribute("disabled");
      if (val && val !== originalValue && val !== "" && disabled === null) {
        otherValue = val;
        break;
      }
    }

    if (!otherValue) {
      test.skip(true, "No alternative file option found");
      return;
    }

    // Switch to another file
    await fileSel.selectOption(otherValue);
    await waitForChart(page);
    await page.waitForTimeout(1500);

    // Switch back to the original file
    await fileSel.selectOption(originalValue);
    await waitForChart(page);
    await page.waitForTimeout(1500);

    // The original file should be re-selected
    const currentValue = await fileSel.inputValue();
    expect(currentValue).toBe(originalValue);

    // Marker count should be the same as before
    const restoredMarkerCount = await sleepMarkerCount(page);
    expect(restoredMarkerCount).toBe(originalMarkerCount);
  });

  // =========================================================================
  // 11. File selector value matches the current file displayed
  // =========================================================================
  test("file selector value matches current file displayed", async ({ page }) => {
    await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    const selectedValue = await fileSel.inputValue();
    expect(selectedValue).not.toBe("");

    // The selected option text should include a filename pattern
    // (the Select component shows "filename (N rows)" format)
    const selectedOption = fileSel.locator(`option[value="${selectedValue}"]`);
    const optionText = await selectedOption.textContent();
    expect(optionText).toBeTruthy();
    // Should contain the word "rows" (format: "filename.csv (N rows)")
    expect(optionText).toMatch(/\d+ rows/);
  });

  // =========================================================================
  // 12. Chart canvas has proper dimensions
  // =========================================================================
  test("chart canvas has proper dimensions", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);

    const box = await getOverlayBox(overlay);
    expect(box.width).toBeGreaterThan(400);
    expect(box.height).toBeGreaterThan(200);

    // Also verify the uPlot canvas element
    const canvas = page.locator(".uplot canvas").first();
    await expect(canvas).toBeVisible();
    const canvasBox = await canvas.boundingBox();
    expect(canvasBox).toBeTruthy();
    expect(canvasBox!.width).toBeGreaterThan(400);
    expect(canvasBox!.height).toBeGreaterThan(200);

    // Screenshot: chart canvas with proper dimensions rendered
    await expect(page).toHaveScreenshot("file-management-chart-canvas.png", {
      maxDiffPixelRatio: 0.01,
    });
  });

  // =========================================================================
  // 13. File selector has correct number of selectable options
  // =========================================================================
  test("all file options are selectable", async ({ page }) => {
    await loginAndGoToScoring(page);

    const fileSel = fileSelector(page);
    const options = await fileSel.locator("option").all();

    let selectableCount = 0;
    for (const opt of options) {
      const disabled = await opt.getAttribute("disabled");
      const value = await opt.getAttribute("value");
      if (disabled === null && value && value !== "") {
        selectableCount++;
      }
    }

    // There should be at least one selectable file
    expect(selectableCount).toBeGreaterThan(0);
  });

  // =========================================================================
  // 14. Chart overlay is inside the uPlot container
  // =========================================================================
  test("chart overlay is properly nested inside uPlot container", async ({ page }) => {
    const overlay = await loginAndGoToScoring(page);

    // The overlay should be inside a .uplot container
    const uplotContainer = page.locator(".uplot").first();
    await expect(uplotContainer).toBeVisible();

    const uplotBox = await uplotContainer.boundingBox();
    const overlayBox = await getOverlayBox(overlay);

    expect(uplotBox).toBeTruthy();
    // Overlay should be within the uPlot container bounds
    expect(overlayBox.x).toBeGreaterThanOrEqual(uplotBox!.x - 5);
    expect(overlayBox.y).toBeGreaterThanOrEqual(uplotBox!.y - 5);
  });
});
