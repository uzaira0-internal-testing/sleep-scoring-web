/**
 * Comprehensive E2E tests for the Settings pages (Study Settings and Data Settings).
 *
 * Covers:
 * - Study Settings: algorithm dropdown, sleep detection rule, night hours, filename patterns, save/reset
 * - Data Settings: device preset, epoch length, skip rows, marker clearing buttons, save
 * - Cross-page navigation between settings pages and scoring
 */

import { test, expect } from "@playwright/test";
import { loginAndGoTo } from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Settings Comprehensive", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // ---------------------------------------------------------------------------
  // Study Settings Page
  // ---------------------------------------------------------------------------

  test("study settings page loads with heading", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
  });

  test("algorithm dropdown has 4 options", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    const algorithmSelect = page.locator("#algorithm");
    await expect(algorithmSelect).toBeVisible();
    await expect(algorithmSelect.locator("option")).toHaveCount(4);
  });

  test("selecting algorithm shows unsaved indicator", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    // Wait for backend settings to load
    await page.waitForTimeout(1500);

    // No unsaved indicator initially
    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible();

    // Change the algorithm
    const algorithmSelect = page.locator("#algorithm");
    const currentValue = await algorithmSelect.inputValue();
    const newValue =
      currentValue === "sadeh_1994_actilife"
        ? "cole_kripke_1992_actilife"
        : "sadeh_1994_actilife";
    await algorithmSelect.selectOption(newValue);

    // Unsaved indicator should appear
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });
  });

  test("save button saves changes and clears unsaved indicator", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    // Change algorithm to trigger unsaved state
    const algorithmSelect = page.locator("#algorithm");
    const currentValue = await algorithmSelect.inputValue();
    const newValue =
      currentValue === "sadeh_1994_actilife"
        ? "cole_kripke_1992_actilife"
        : "sadeh_1994_actilife";
    await algorithmSelect.selectOption(newValue);
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });

    // Click save and wait for the PUT request to complete
    const saveButton = page.getByRole("button", { name: /save/i });
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT"
      ),
      saveButton.click(),
    ]);

    // Unsaved indicator should disappear
    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible({
      timeout: 5000,
    });
  });

  test("settings persist after page reload", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000);

    // Pick a specific value to save
    const algorithmSelect = page.locator("#algorithm");
    const originalValue = await algorithmSelect.inputValue();
    const testValue =
      originalValue === "cole_kripke_1992_actilife"
        ? "sadeh_1994_actilife"
        : "cole_kripke_1992_actilife";

    await algorithmSelect.selectOption(testValue);
    await expect(algorithmSelect).toHaveValue(testValue);

    // Save
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT"
      ),
      page.getByRole("button", { name: /save/i }).click(),
    ]);
    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible({
      timeout: 5000,
    });

    // Reload
    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/settings") &&
        resp.request().method() === "GET"
    );
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await responsePromise;
    await page.waitForTimeout(500);

    // Verify saved value persisted
    await expect(page.locator("#algorithm")).toHaveValue(testValue, {
      timeout: 10000,
    });
  });

  test("reset button shows confirmation dialog", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    // Listen for the dialog and dismiss it
    let dialogMessage = "";
    page.once("dialog", async (dialog) => {
      dialogMessage = dialog.message();
      await dialog.dismiss();
    });

    await page.getByRole("button", { name: /reset/i }).click();
    await page.waitForTimeout(500);

    expect(dialogMessage).toContain("Reset all settings to defaults");
  });

  test("accepting reset restores defaults", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    // Accept the confirmation dialog
    page.on("dialog", (dialog) => dialog.accept());

    await page.getByRole("button", { name: /reset/i }).click();
    await page.waitForTimeout(1500);

    // Defaults: night start is 21:00
    await expect(page.locator("#night-start")).toHaveValue("21:00", {
      timeout: 5000,
    });
  });

  test("night start time input accepts valid time", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    const nightStart = page.locator("#night-start");
    await expect(nightStart).toBeVisible();

    // Fill in a new time value
    await nightStart.fill("22:30");
    await expect(nightStart).toHaveValue("22:30");

    // Should trigger unsaved changes
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });
  });

  test("night end time input accepts valid time", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    const nightEnd = page.locator("#night-end");
    await expect(nightEnd).toBeVisible();

    await nightEnd.fill("08:00");
    await expect(nightEnd).toHaveValue("08:00");

    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });
  });

  test("filename patterns section shows test results", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    // Verify the filename patterns card is visible
    await expect(page.getByText("Filename Patterns")).toBeVisible();

    // Verify the test patterns card is visible
    await expect(page.getByText("Test Patterns")).toBeVisible();

    // Verify extraction results section is visible
    await expect(page.getByText("Extraction Results:")).toBeVisible();

    // Default test filename is "TECH-001_T1_20240115.csv" so results should show matches
    await expect(page.getByText("Participant ID:")).toBeVisible();
    await expect(page.getByText("Timepoint:")).toBeVisible();
    await expect(page.getByText("Group:")).toBeVisible();

    // The default patterns should produce matches (green text) for the default test filename
    await expect(page.locator("text=TECH-001")).toBeVisible();
    await expect(page.locator("text=T1")).toBeVisible();
    await expect(page.getByText("TECH", { exact: true })).toBeVisible();
  });

  test("changing test filename updates pattern results", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    const testFilenameInput = page.locator("#test-filename");
    await expect(testFilenameInput).toBeVisible();

    // Clear and type a new filename that matches the default patterns
    await testFilenameInput.fill("GNSM-042_T2_20250101.csv");
    await page.waitForTimeout(300);

    // Results should update to reflect the new filename
    await expect(page.locator("text=GNSM-042")).toBeVisible();
    await expect(page.locator("text=T2")).toBeVisible();
    await expect(page.getByText("GNSM", { exact: true })).toBeVisible();
  });

  test("sleep detection rule dropdown has 3 options", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    const detectionSelect = page.locator("#sleep-detection");
    await expect(detectionSelect).toBeVisible();
    await expect(detectionSelect.locator("option")).toHaveCount(3);
  });

  test("selecting sleep detection rule shows unsaved indicator", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible();

    const detectionSelect = page.locator("#sleep-detection");
    const currentValue = await detectionSelect.inputValue();
    // Pick a different option
    const allValues = await detectionSelect.locator("option").evaluateAll(
      (els) => els.map((el) => (el as HTMLOptionElement).value)
    );
    const newValue = allValues.find((v) => v !== currentValue) ?? allValues[0];
    await detectionSelect.selectOption(newValue);

    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });
  });

  test("id pattern input accepts value", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    const idPatternInput = page.locator("#id-pattern");
    await expect(idPatternInput).toBeVisible();

    await idPatternInput.fill("(\\d{3}-\\d{4})");
    await expect(idPatternInput).toHaveValue("(\\d{3}-\\d{4})");
  });

  test("timepoint pattern input accepts value", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    const tpInput = page.locator("#timepoint-pattern");
    await expect(tpInput).toBeVisible();

    await tpInput.fill("_(V\\d+)_");
    await expect(tpInput).toHaveValue("_(V\\d+)_");
  });

  test("group pattern input accepts value", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    const grpInput = page.locator("#group-pattern");
    await expect(grpInput).toBeVisible();

    await grpInput.fill("^(GRP\\d+)-");
    await expect(grpInput).toHaveValue("^(GRP\\d+)-");
  });

  test("save button is disabled when there are no changes", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    // Without making changes, save should be disabled
    const saveButton = page.getByRole("button", { name: /save/i });
    await expect(saveButton).toBeDisabled();
  });

  // ---------------------------------------------------------------------------
  // Data Settings Page
  // ---------------------------------------------------------------------------

  test("data settings page loads with heading", async ({ page }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });
  });

  test("device preset dropdown is visible with options", async ({ page }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });

    const devicePresetSelect = page.locator("#device-preset");
    await expect(devicePresetSelect).toBeVisible();

    // Should have 5 options: actigraph, actiwatch, motionwatch, geneactiv, generic
    await expect(devicePresetSelect.locator("option")).toHaveCount(5);
  });

  test("epoch length input accepts values", async ({ page }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });

    const epochInput = page.locator("#epoch-length");
    await expect(epochInput).toBeVisible();

    await epochInput.fill("30");
    await expect(epochInput).toHaveValue("30");
  });

  test("skip rows input accepts values", async ({ page }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });

    const skipRowsInput = page.locator("#skip-rows");
    await expect(skipRowsInput).toBeVisible();

    await skipRowsInput.fill("15");
    await expect(skipRowsInput).toHaveValue("15");
  });

  test("data settings save button works", async ({ page }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    // Change epoch length to trigger unsaved state
    const epochInput = page.locator("#epoch-length");
    await epochInput.fill("30");

    // Should show unsaved changes
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });

    // Save
    const saveButton = page.getByRole("button", { name: /save/i });
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT"
      ),
      saveButton.click(),
    ]);

    // Unsaved indicator should disappear
    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible({
      timeout: 5000,
    });
  });

  test("clear sleep markers button visible on data settings", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });

    // The "Clear Sleep Markers" button should be present in the Data Management section
    await expect(page.getByText("Clear Sleep Markers")).toBeVisible();
  });

  test("clear nonwear markers button visible on data settings", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });

    await expect(page.getByText("Clear Nonwear Markers")).toBeVisible();
  });

  test("clear all markers button visible on data settings", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });

    await expect(page.getByText("Clear All Markers")).toBeVisible();
  });

  test("device preset dropdown changes epoch and skip rows values", async ({
    page,
  }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    const devicePresetSelect = page.locator("#device-preset");

    // Select Actiwatch preset (epoch=60, skip=7)
    await devicePresetSelect.selectOption("actiwatch");
    await page.waitForTimeout(300);

    await expect(page.locator("#epoch-length")).toHaveValue("60");
    await expect(page.locator("#skip-rows")).toHaveValue("7");

    // Select Generic preset (epoch=60, skip=0)
    await devicePresetSelect.selectOption("generic");
    await page.waitForTimeout(300);

    await expect(page.locator("#skip-rows")).toHaveValue("0");
  });

  // ---------------------------------------------------------------------------
  // Cross-page Navigation
  // ---------------------------------------------------------------------------

  test("navigate from study to data settings", async ({ page }) => {
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });

    // Click on Data link in sidebar (sidebar shows "Data" + "Import settings")
    const dataSettingsLink = page.getByRole("link", { name: /data import/i });
    await expect(dataSettingsLink).toBeVisible();
    await dataSettingsLink.click();

    await expect(page).toHaveURL(/\/settings\/data/);
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 10000 });
  });

  test("navigate from data settings back to scoring", async ({ page }) => {
    await loginAndGoTo(page, "/settings/data");
    await expect(
      page.getByRole("heading", { name: /data settings/i })
    ).toBeVisible({ timeout: 15000 });

    // Click on Scoring link in sidebar
    const scoringLink = page.getByRole("link", { name: /scoring/i });
    await expect(scoringLink).toBeVisible();
    await scoringLink.click();

    await expect(page).toHaveURL(/\/scoring/);
  });
});
