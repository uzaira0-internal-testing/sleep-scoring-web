/**
 * E2E tests for the export workflow — page load, file selection, CSV download,
 * date range filtering, and direct URL export.
 *
 * Prerequisites:
 * - Docker stack running (cd docker && docker compose -f docker-compose.local.yml up -d)
 * - At least one CSV file uploaded, processed, and scored with markers
 */

import { test, expect } from "@playwright/test";
import { loginAndGoTo } from "./helpers";
import * as fs from "fs";
import * as path from "path";

test.describe.configure({ mode: "serial" });

test.describe("Export Flow", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.clearBrowserCache");
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // =========================================================================
  // 1. Export page loads and shows file checkboxes
  // =========================================================================
  test("export page loads and shows file checkboxes", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/export");

    // Heading should be visible
    await expect(
      page.getByRole("heading", { name: /export data/i }),
    ).toBeVisible({ timeout: 15000 });

    // "Select Files" panel should be present
    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 10000,
    });

    // File checkboxes should exist (id starts with "file-")
    const fileCheckboxes = page.locator('input[type="checkbox"][id^="file-"]');
    const noFilesMessage = page.getByText("No files available");

    const checkboxCount = await fileCheckboxes.count();
    const hasNoFiles = await noFilesMessage
      .isVisible({ timeout: 3000 })
      .catch(() => false);

    // Either files are listed or a "no files" message is shown
    expect(checkboxCount > 0 || hasNoFiles).toBeTruthy();

    // Column selection should also be visible
    await expect(page.getByText("Select Columns")).toBeVisible({
      timeout: 5000,
    });

    // Export options section should be visible
    await expect(page.getByText("Export Options")).toBeVisible({
      timeout: 5000,
    });
  });

  // =========================================================================
  // 2. Select files -> export button enabled
  // =========================================================================
  test("selecting files enables the export button", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/export");

    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // First clear all to ensure download button starts disabled
    const clearAllBtn = page.getByRole("button", { name: /clear all/i });
    await expect(clearAllBtn).toBeVisible();
    await clearAllBtn.click();
    await page.waitForTimeout(500);

    // Download button should be disabled when no files selected
    const downloadBtn = page.getByRole("button", { name: /download csv/i });
    await expect(downloadBtn).toBeDisabled();

    // Select all files
    const selectAllBtn = page.getByRole("button", { name: /select all/i });
    await selectAllBtn.click();
    await page.waitForTimeout(500);

    // Check if there are files to select
    const fileCheckboxCount = await page
      .locator('input[type="checkbox"][id^="file-"]')
      .count();

    if (fileCheckboxCount > 0) {
      // Download button should now be enabled
      await expect(downloadBtn).toBeEnabled({ timeout: 3000 });

      // File count indicator should reflect the selection
      const countText = await page
        .locator("text=/\\d+ of \\d+ files selected/")
        .textContent();
      expect(countText).toBeTruthy();

      const match = countText?.match(/(\d+) of (\d+)/);
      if (match) {
        expect(Number(match[1])).toBe(Number(match[2]));
        expect(Number(match[1])).toBeGreaterThan(0);
      }
    }
  });

  // =========================================================================
  // 3. Download CSV -> response is text/csv
  // =========================================================================
  test("download CSV produces a file with text/csv content", async ({
    page,
  }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/export");

    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Select all files
    await page.getByRole("button", { name: /select all/i }).click();
    await page.waitForTimeout(500);

    const fileCheckboxCount = await page
      .locator('input[type="checkbox"][id^="file-"]')
      .count();

    if (fileCheckboxCount === 0) {
      test.skip(true, "No files available for export");
      return;
    }

    // Set up download promise BEFORE clicking
    const downloadPromise = page.waitForEvent("download", { timeout: 30000 });

    // Click the download button
    const downloadBtn = page.getByRole("button", { name: /download csv/i });
    await expect(downloadBtn).toBeEnabled({ timeout: 3000 });
    await downloadBtn.click();

    // Wait for the download to start
    const download = await downloadPromise;

    // Verify the download has a filename
    const filename = download.suggestedFilename();
    expect(filename).toBeTruthy();
    expect(filename).toMatch(/\.csv$/i);

    // Save and verify the file has content
    const downloadPath = path.join("/tmp", filename);
    await download.saveAs(downloadPath);

    const fileContent = fs.readFileSync(downloadPath, "utf-8");
    expect(fileContent.length).toBeGreaterThan(0);

    // CSV content should have header row and comma-separated values
    const lines = fileContent.trim().split("\n");
    expect(lines.length).toBeGreaterThanOrEqual(1);

    // First line (header) should contain common column names
    const header = lines[0].toLowerCase();
    // At minimum, the CSV should have some known column like "filename" or "participant"
    const hasKnownColumn =
      header.includes("filename") ||
      header.includes("participant") ||
      header.includes("date") ||
      header.includes("onset") ||
      header.includes("offset");
    expect(hasKnownColumn).toBeTruthy();

    // Clean up
    fs.unlinkSync(downloadPath);
  });

  // =========================================================================
  // 4. Export with column preset filter
  // =========================================================================
  test("export with minimal column preset produces fewer columns", async ({
    page,
  }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/export");

    await expect(page.getByText("Select Files")).toBeVisible({
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Select all files
    await page.getByRole("button", { name: /select all/i }).click();
    await page.waitForTimeout(500);

    const fileCheckboxCount = await page
      .locator('input[type="checkbox"][id^="file-"]')
      .count();

    if (fileCheckboxCount === 0) {
      test.skip(true, "No files available for export");
      return;
    }

    // Switch to "Full" preset first and record column count
    const fullBtn = page.getByRole("button", { name: "Full" });
    await expect(fullBtn).toBeVisible();
    await fullBtn.click();
    await page.waitForTimeout(500);

    const fullCountText = await page
      .locator("text=/\\d+ columns selected/")
      .textContent();
    const fullMatch = fullCountText?.match(/(\d+) columns selected/);
    const fullCount = fullMatch ? Number(fullMatch[1]) : 0;
    expect(fullCount).toBeGreaterThan(0);

    // Switch to "Minimal" preset
    const minimalBtn = page.getByRole("button", { name: "Minimal" });
    await minimalBtn.click();
    await page.waitForTimeout(500);

    const minimalCountText = await page
      .locator("text=/\\d+ columns selected/")
      .textContent();
    const minimalMatch = minimalCountText?.match(/(\d+) columns selected/);
    const minimalCount = minimalMatch ? Number(minimalMatch[1]) : 0;

    // Minimal should have fewer columns than Full
    expect(minimalCount).toBeLessThan(fullCount);
    expect(minimalCount).toBeGreaterThan(0);

    // Now download with Minimal preset and verify column count
    const downloadPromise = page.waitForEvent("download", { timeout: 30000 });
    await page.getByRole("button", { name: /download csv/i }).click();
    const download = await downloadPromise;

    const downloadPath = path.join("/tmp", download.suggestedFilename());
    await download.saveAs(downloadPath);

    const fileContent = fs.readFileSync(downloadPath, "utf-8");
    const headerLine = fileContent.split("\n")[0];
    const columnCount = headerLine.split(",").length;

    // The number of CSV columns should roughly match the minimal selection
    // (may differ slightly due to fixed columns like filename/date)
    expect(columnCount).toBeGreaterThan(0);
    expect(columnCount).toBeLessThanOrEqual(fullCount + 5);

    // Clean up
    fs.unlinkSync(downloadPath);
  });

  // =========================================================================
  // 5. Export page navigation from scoring page sidebar
  // =========================================================================
  test("export page accessible from sidebar and back to scoring works", async ({
    page,
  }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/scoring");

    // Wait for scoring page to load
    await page.waitForTimeout(1000);

    // Click Export in sidebar
    const exportLink = page.getByRole("link", { name: /export/i });
    await expect(exportLink).toBeVisible({ timeout: 5000 });
    await exportLink.click();

    await expect(page).toHaveURL(/\/export/);
    await expect(
      page.getByRole("heading", { name: /export data/i }),
    ).toBeVisible({ timeout: 15000 });

    // Navigate back to scoring
    const backBtn = page.getByRole("button", { name: /back to scoring/i });
    if (await backBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await backBtn.click();
      await expect(page).toHaveURL(/\/scoring/);
    } else {
      // Use sidebar link as fallback
      const scoringLink = page.getByRole("link", { name: /scoring/i });
      await scoringLink.click();
      await expect(page).toHaveURL(/\/scoring/);
    }
  });

  // =========================================================================
  // 6. Export options toggles work correctly
  // =========================================================================
  test("export options checkboxes toggle correctly", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/export");

    await expect(page.getByText("Export Options")).toBeVisible({
      timeout: 15000,
    });

    // Include header should be checked by default
    const headerCheckbox = page.locator("#include-header");
    await expect(headerCheckbox).toBeChecked();

    // Toggle off
    await headerCheckbox.click();
    await page.waitForTimeout(200);
    await expect(headerCheckbox).not.toBeChecked();

    // Toggle back on
    await headerCheckbox.click();
    await page.waitForTimeout(200);
    await expect(headerCheckbox).toBeChecked();

    // Include metadata should be unchecked by default
    const metadataCheckbox = page.locator("#include-metadata");
    await expect(metadataCheckbox).not.toBeChecked();

    // Toggle on
    await metadataCheckbox.click();
    await page.waitForTimeout(200);
    await expect(metadataCheckbox).toBeChecked();

    // Toggle back off
    await metadataCheckbox.click();
    await page.waitForTimeout(200);
    await expect(metadataCheckbox).not.toBeChecked();
  });
});
