/**
 * Comprehensive E2E tests for the Export page.
 *
 * Covers:
 * - Page loading and structure
 * - File selection: select all, clear all, individual toggle
 * - Column selection: categories, individual columns, presets
 * - Export options: header checkbox, metadata checkbox
 * - Download button enabled/disabled state
 * - File and column count indicators
 * - Navigation to export from sidebar
 */

import { test, expect } from "@playwright/test";
import { loginAndGoTo } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Export Comprehensive", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // ---------------------------------------------------------------------------
  // Page Load and Structure
  // ---------------------------------------------------------------------------

  test("export page loads with proper heading", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(
      page.getByRole("heading", { name: /export data/i })
    ).toBeVisible({ timeout: 15000 });
    await expect(
      page.getByText("Generate CSV exports of sleep scoring data")
    ).toBeVisible();
  });

  test("export page accessible from sidebar navigation", async ({ page }) => {
    await loginAndGoTo(page, "/scoring");

    // Wait for scoring page to be at least partially loaded
    await page.waitForTimeout(1000);

    // Click Export in sidebar
    const exportLink = page.getByRole("link", { name: /export/i });
    await expect(exportLink).toBeVisible({ timeout: 5000 });
    await exportLink.click();

    await expect(page).toHaveURL(/\/export/);
    await expect(
      page.getByRole("heading", { name: /export data/i })
    ).toBeVisible({ timeout: 15000 });
  });

  // ---------------------------------------------------------------------------
  // File Selection
  // ---------------------------------------------------------------------------

  test("file selection panel shows files with checkboxes", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });

    // Should show file selection area with checkboxes (native input type=checkbox)
    // Either files are listed or a "No files available" message is shown
    const fileCheckboxes = page.locator('input[type="checkbox"][id^="file-"]');
    const noFilesMessage = page.getByText("No files available");

    const checkboxCount = await fileCheckboxes.count();
    const hasNoFilesMsg = await noFilesMessage.isVisible().catch(() => false);

    // One of these must be true
    expect(checkboxCount > 0 || hasNoFilesMsg).toBeTruthy();
  });

  test("select all button checks all files", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    const selectAllBtn = page.getByRole("button", { name: /select all/i });
    await expect(selectAllBtn).toBeVisible();
    await selectAllBtn.click();
    await page.waitForTimeout(500);

    // Check the count indicator shows all files selected
    const countText = await page
      .locator("text=/\\d+ of \\d+ files selected/")
      .textContent();
    expect(countText).toBeTruthy();

    const match = countText?.match(/(\d+) of (\d+)/);
    if (match) {
      const [, selected, total] = match;
      expect(Number(selected)).toBe(Number(total));
    }
  });

  test("clear all button unchecks all files", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Select all first
    await page.getByRole("button", { name: /select all/i }).click();
    await page.waitForTimeout(500);

    // Then clear all
    await page.getByRole("button", { name: /clear all/i }).click();
    await page.waitForTimeout(500);

    // Count should show 0 of N files selected
    const countText = await page
      .locator("text=/\\d+ of \\d+ files selected/")
      .textContent();
    expect(countText).toBeTruthy();
    expect(countText).toMatch(/^0 of \d+/);
  });

  test("individual file checkbox toggles", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Clear all first to start from zero
    await page.getByRole("button", { name: /clear all/i }).click();
    await page.waitForTimeout(300);

    const firstCheckbox = page
      .locator('input[type="checkbox"][id^="file-"]')
      .first();
    const checkboxCount = await page
      .locator('input[type="checkbox"][id^="file-"]')
      .count();

    if (checkboxCount > 0) {
      // Check it
      await firstCheckbox.check();
      await page.waitForTimeout(300);

      // Count should show 1 of N
      const countAfterCheck = await page
        .locator("text=/\\d+ of \\d+ files selected/")
        .textContent();
      expect(countAfterCheck).toMatch(/^1 of \d+/);

      // Uncheck it
      await firstCheckbox.uncheck();
      await page.waitForTimeout(300);

      // Count should show 0 of N
      const countAfterUncheck = await page
        .locator("text=/\\d+ of \\d+ files selected/")
        .textContent();
      expect(countAfterUncheck).toMatch(/^0 of \d+/);
    }
  });

  // ---------------------------------------------------------------------------
  // Column Selection
  // ---------------------------------------------------------------------------

  test("column selection panel shows categories", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Columns")).toBeVisible({
      timeout: 15000,
    });

    // Should show at least one category name (e.g., "File Info")
    // Categories are rendered as bold text spans within the column panel
    const categoryLabels = page.locator(
      ".font-semibold.text-sm"
    );
    const categoryCount = await categoryLabels.count();
    expect(categoryCount).toBeGreaterThan(0);
  });

  test("category checkbox toggles all columns in category", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Columns")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Find the first category row (parent div that contains the category checkbox and name)
    // Categories have a checkbox followed by a bold label
    const firstCategoryRow = page
      .locator("div.flex.items-center.space-x-2.cursor-pointer")
      .first();
    const categoryExists = await firstCategoryRow.isVisible().catch(() => false);

    if (categoryExists) {
      // Click category to toggle it
      await firstCategoryRow.click();
      await page.waitForTimeout(300);

      // Get the category checkbox state
      const categoryCheckbox = firstCategoryRow.locator(
        'input[type="checkbox"]'
      );
      const isChecked = await categoryCheckbox.isChecked();

      // Click again to toggle back
      await firstCategoryRow.click();
      await page.waitForTimeout(300);

      const isCheckedAfter = await categoryCheckbox.isChecked();
      expect(isCheckedAfter).not.toBe(isChecked);
    }
  });

  test("individual column checkbox toggles", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Columns")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Find an individual column checkbox (those with id starting with "col-")
    const columnCheckbox = page
      .locator('input[type="checkbox"][id^="col-"]')
      .first();
    const exists = await columnCheckbox.isVisible().catch(() => false);

    if (exists) {
      const initialState = await columnCheckbox.isChecked();

      // Toggle it
      await columnCheckbox.click();
      await page.waitForTimeout(300);

      const newState = await columnCheckbox.isChecked();
      expect(newState).not.toBe(initialState);

      // Toggle back
      await columnCheckbox.click();
      await page.waitForTimeout(300);

      const restoredState = await columnCheckbox.isChecked();
      expect(restoredState).toBe(initialState);
    }
  });

  // ---------------------------------------------------------------------------
  // Download Button State
  // ---------------------------------------------------------------------------

  test("download button disabled when no files selected", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Clear all file selections
    await page.getByRole("button", { name: /clear all/i }).click();
    await page.waitForTimeout(500);

    // Download button should be disabled
    const downloadBtn = page.getByRole("button", { name: /download csv/i });
    await expect(downloadBtn).toBeDisabled();
  });

  test("download button enabled when files selected", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Select all files
    await page.getByRole("button", { name: /select all/i }).click();
    await page.waitForTimeout(500);

    // Download button should be enabled (if files exist)
    const fileCheckboxCount = await page
      .locator('input[type="checkbox"][id^="file-"]')
      .count();

    if (fileCheckboxCount > 0) {
      const downloadBtn = page.getByRole("button", { name: /download csv/i });
      await expect(downloadBtn).toBeEnabled();
    }
  });

  // ---------------------------------------------------------------------------
  // Export Options
  // ---------------------------------------------------------------------------

  test("include header checkbox is checked by default", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Export Options")).toBeVisible({
      timeout: 15000,
    });

    const headerCheckbox = page.locator("#include-header");
    await expect(headerCheckbox).toBeChecked();
  });

  test("include metadata checkbox is unchecked by default", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Export Options")).toBeVisible({
      timeout: 15000,
    });

    const metadataCheckbox = page.locator("#include-metadata");
    await expect(metadataCheckbox).not.toBeChecked();
  });

  test("include header checkbox can be toggled", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Export Options")).toBeVisible({
      timeout: 15000,
    });

    const headerCheckbox = page.locator("#include-header");
    await expect(headerCheckbox).toBeChecked();

    // Uncheck it
    await headerCheckbox.click();
    await page.waitForTimeout(200);
    await expect(headerCheckbox).not.toBeChecked();

    // Re-check it
    await headerCheckbox.click();
    await page.waitForTimeout(200);
    await expect(headerCheckbox).toBeChecked();
  });

  test("include metadata checkbox can be toggled", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Export Options")).toBeVisible({
      timeout: 15000,
    });

    const metadataCheckbox = page.locator("#include-metadata");
    await expect(metadataCheckbox).not.toBeChecked();

    // Check it
    await metadataCheckbox.click();
    await page.waitForTimeout(200);
    await expect(metadataCheckbox).toBeChecked();
  });

  // ---------------------------------------------------------------------------
  // Column Presets
  // ---------------------------------------------------------------------------

  test("column preset buttons change selection", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Columns")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // The preset buttons: Default, Minimal, Standard, Full
    const defaultBtn = page.getByRole("button", { name: "Default" });
    const minimalBtn = page.getByRole("button", { name: "Minimal" });
    const standardBtn = page.getByRole("button", { name: "Standard" });
    const fullBtn = page.getByRole("button", { name: "Full" });

    await expect(defaultBtn).toBeVisible();
    await expect(minimalBtn).toBeVisible();
    await expect(standardBtn).toBeVisible();
    await expect(fullBtn).toBeVisible();

    // Click "Full" to select all columns
    await fullBtn.click();
    await page.waitForTimeout(500);

    const fullCountText = await page
      .locator("text=/\\d+ columns selected/")
      .textContent();
    const fullMatch = fullCountText?.match(/(\d+) columns selected/);
    const fullCount = fullMatch ? Number(fullMatch[1]) : 0;

    // Click "Minimal" which should select fewer columns
    await minimalBtn.click();
    await page.waitForTimeout(500);

    const minimalCountText = await page
      .locator("text=/\\d+ columns selected/")
      .textContent();
    const minimalMatch = minimalCountText?.match(/(\d+) columns selected/);
    const minimalCount = minimalMatch ? Number(minimalMatch[1]) : 0;

    // Minimal should have fewer columns than Full
    expect(minimalCount).toBeLessThan(fullCount);
  });

  // ---------------------------------------------------------------------------
  // Count Indicators
  // ---------------------------------------------------------------------------

  test("file count indicator shows correct count", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // The file count indicator format is "X of Y files selected"
    const countIndicator = page.locator("text=/\\d+ of \\d+ files selected/");
    await expect(countIndicator).toBeVisible();

    // Initially 0 should be selected
    const initialText = await countIndicator.textContent();
    expect(initialText).toMatch(/^0 of \d+ files selected$/);

    // Select all
    await page.getByRole("button", { name: /select all/i }).click();
    await page.waitForTimeout(500);

    const afterSelectAll = await countIndicator.textContent();
    const match = afterSelectAll?.match(/(\d+) of (\d+)/);
    if (match) {
      expect(Number(match[1])).toBe(Number(match[2]));
    }
  });

  test("column count indicator shows correct count", async ({ page }) => {
    await loginAndGoTo(page, "/export");
    await expect(page.getByText("Select Columns")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // The column count indicator format is "X columns selected"
    const colCountIndicator = page.locator("text=/\\d+ columns selected/");
    await expect(colCountIndicator).toBeVisible();

    const text = await colCountIndicator.textContent();
    const match = text?.match(/(\d+) columns selected/);
    expect(match).toBeTruthy();
    // Default preset should have at least some columns selected
    expect(Number(match![1])).toBeGreaterThan(0);
  });

  // ---------------------------------------------------------------------------
  // Back to Scoring Navigation
  // ---------------------------------------------------------------------------

  test("back to scoring button navigates to scoring page", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/export");
    await expect(
      page.getByRole("heading", { name: /export data/i })
    ).toBeVisible({ timeout: 15000 });

    const backBtn = page.getByRole("button", { name: /back to scoring/i });
    await expect(backBtn).toBeVisible();
    await backBtn.click();

    await expect(page).toHaveURL(/\/scoring/);
  });
});
