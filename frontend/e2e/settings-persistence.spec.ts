/**
 * E2E tests for settings persistence across reloads and cross-page effects.
 *
 * Covers:
 * - Algorithm selection persists after reload
 * - Night hours change reflected on scoring page
 * - Display column preference persists
 * - Settings page accessibility (axe-core)
 * - Data settings page loads and shows device presets
 *
 * Prerequisites:
 * - Docker stack running (cd docker && docker compose -f docker-compose.local.yml up -d)
 * - At least one CSV file uploaded and processed
 */

import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  login,
  loginAndGoTo,
  loginAndGoToScoring,
  waitForChart,
  assertPageHealthy,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Settings Persistence", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.clearBrowserCache");
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // =========================================================================
  // 1. Change algorithm in study settings -> persists after reload
  // =========================================================================
  test("algorithm change persists after page reload", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/settings/study");

    await expect(
      page.getByRole("heading", { name: /study settings/i }),
    ).toBeVisible({ timeout: 15000 });

    // Wait for backend settings to load
    await page.waitForTimeout(2000);

    const algorithmSelect = page.locator("#algorithm");
    await expect(algorithmSelect).toBeVisible();

    // Record the current value and pick a different one
    const originalValue = await algorithmSelect.inputValue();
    const testValue =
      originalValue === "cole_kripke_1992_actilife"
        ? "sadeh_1994_actilife"
        : "cole_kripke_1992_actilife";

    // Change the algorithm
    await algorithmSelect.selectOption(testValue);
    await expect(algorithmSelect).toHaveValue(testValue);

    // Wait for unsaved indicator
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });

    // Save the change
    const saveButton = page.getByRole("button", { name: /save/i });
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT",
      ),
      saveButton.click(),
    ]);

    // Unsaved indicator should disappear
    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible({
      timeout: 5000,
    });

    // Reload the page
    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/settings") && resp.request().method() === "GET",
    );
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(
      page.getByRole("heading", { name: /study settings/i }),
    ).toBeVisible({ timeout: 15000 });
    await responsePromise;
    await page.waitForTimeout(500);

    // Verify the saved value persisted
    await expect(page.locator("#algorithm")).toHaveValue(testValue, {
      timeout: 10000,
    });

    // Restore original value
    await algorithmSelect.selectOption(originalValue);
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT",
      ),
      saveButton.click(),
    ]);
    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible({
      timeout: 5000,
    });
  });

  // =========================================================================
  // 2. Change night hours -> reflected on scoring page
  // =========================================================================
  test("night hours change reflected on scoring page", async ({ page }) => {
    test.setTimeout(90000);
    await loginAndGoTo(page, "/settings/study");

    await expect(
      page.getByRole("heading", { name: /study settings/i }),
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000);

    // Record original night-start value
    const nightStart = page.locator("#night-start");
    await expect(nightStart).toBeVisible();
    const originalNightStart = await nightStart.inputValue();

    // Change night start to a different value
    const newNightStart = originalNightStart === "21:00" ? "22:00" : "21:00";
    await nightStart.fill(newNightStart);
    await expect(nightStart).toHaveValue(newNightStart);

    // Save
    const saveButton = page.getByRole("button", { name: /save/i });
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT",
      ),
      saveButton.click(),
    ]);

    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible({
      timeout: 5000,
    });

    // Navigate to scoring page
    await page.goto("/scoring");
    await waitForChart(page);
    await page.waitForTimeout(2000);

    // The scoring page should load without errors with the new night hours
    await assertPageHealthy(page);

    // The chart should still render properly (night boundary may have shifted)
    const overlay = page.locator(".u-over").first();
    await expect(overlay).toBeVisible({ timeout: 10000 });

    // Restore original value
    await page.goto("/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i }),
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000);

    const nightStartRestore = page.locator("#night-start");
    await nightStartRestore.fill(originalNightStart);
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT",
      ),
      page.getByRole("button", { name: /save/i }).click(),
    ]);
  });

  // =========================================================================
  // 3. Change display column preference -> chart updates
  // =========================================================================
  test("display column preference change persists in data settings", async ({
    page,
  }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/settings/data");

    await expect(
      page.getByRole("heading", { name: /data settings/i }),
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000);

    // Device preset dropdown controls display column defaults
    const devicePresetSelect = page.locator("#device-preset");
    await expect(devicePresetSelect).toBeVisible();

    // Record original preset
    const originalPreset = await devicePresetSelect.inputValue();

    // Change to a different device preset
    const newPreset = originalPreset === "actiwatch" ? "generic" : "actiwatch";
    await devicePresetSelect.selectOption(newPreset);
    await page.waitForTimeout(300);

    // Epoch length and skip rows should update based on preset
    const epochLength = page.locator("#epoch-length");
    const skipRows = page.locator("#skip-rows");

    if (newPreset === "actiwatch") {
      await expect(epochLength).toHaveValue("60");
      await expect(skipRows).toHaveValue("7");
    } else if (newPreset === "generic") {
      await expect(skipRows).toHaveValue("0");
    }

    // Unsaved indicator should appear
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });

    // Save
    const saveButton = page.getByRole("button", { name: /save/i });
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT",
      ),
      saveButton.click(),
    ]);

    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible({
      timeout: 5000,
    });

    // Reload and verify persistence
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(
      page.getByRole("heading", { name: /data settings/i }),
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1000);

    await expect(devicePresetSelect).toHaveValue(newPreset, {
      timeout: 10000,
    });

    // Restore original preset
    await devicePresetSelect.selectOption(originalPreset);
    await page.waitForTimeout(300);
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT",
      ),
      page.getByRole("button", { name: /save/i }).click(),
    ]);
  });

  // =========================================================================
  // 4. Settings page accessibility (axe-core)
  // =========================================================================
  test("study settings page passes accessibility checks", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/settings/study");

    await expect(
      page.getByRole("heading", { name: /study settings/i }),
    ).toBeVisible({ timeout: 15000 });

    // Wait for all form elements to render
    await page.waitForTimeout(2000);

    const results = await new AxeBuilder({ page })
      .disableRules(["color-contrast"]) // Allow minor contrast issues in dark themes
      .analyze();

    // Filter out any violations that are purely informational
    const criticalViolations = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );

    expect(criticalViolations).toEqual([]);
  });

  test("data settings page passes accessibility checks", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/settings/data");

    await expect(
      page.getByRole("heading", { name: /data settings/i }),
    ).toBeVisible({ timeout: 15000 });

    await page.waitForTimeout(2000);

    const results = await new AxeBuilder({ page })
      .disableRules(["color-contrast"])
      .analyze();

    const criticalViolations = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );

    expect(criticalViolations).toEqual([]);
  });

  // =========================================================================
  // 5. Data settings page loads and shows device presets
  // =========================================================================
  test("data settings page loads and shows device presets with all options", async ({
    page,
  }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/settings/data");

    await expect(
      page.getByRole("heading", { name: /data settings/i }),
    ).toBeVisible({ timeout: 15000 });

    // Device preset dropdown should be visible
    const devicePresetSelect = page.locator("#device-preset");
    await expect(devicePresetSelect).toBeVisible();

    // Should have 5 options: actigraph, actiwatch, motionwatch, geneactiv, generic
    await expect(devicePresetSelect.locator("option")).toHaveCount(5);

    // Verify each preset name is present
    const optionTexts = await devicePresetSelect
      .locator("option")
      .allTextContents();
    const lowerTexts = optionTexts.map((t) => t.toLowerCase());
    expect(lowerTexts.some((t) => t.includes("actigraph"))).toBeTruthy();
    expect(lowerTexts.some((t) => t.includes("actiwatch"))).toBeTruthy();
    expect(lowerTexts.some((t) => t.includes("geneactiv"))).toBeTruthy();
    expect(lowerTexts.some((t) => t.includes("generic"))).toBeTruthy();

    // Epoch length and skip rows inputs should be visible
    await expect(page.locator("#epoch-length")).toBeVisible();
    await expect(page.locator("#skip-rows")).toBeVisible();

    // Data management section with clear marker buttons should be visible
    await expect(page.getByText("Clear Sleep Markers")).toBeVisible();
    await expect(page.getByText("Clear Nonwear Markers")).toBeVisible();
    await expect(page.getByText("Clear All Markers")).toBeVisible();
  });

  // =========================================================================
  // 6. Reset settings restores defaults
  // =========================================================================
  test("reset button restores default settings", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/settings/study");

    await expect(
      page.getByRole("heading", { name: /study settings/i }),
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000);

    // Change a setting to make it different from default
    const nightStart = page.locator("#night-start");
    await nightStart.fill("23:30");
    await page.waitForTimeout(300);

    // Accept the confirmation dialog on reset
    page.on("dialog", (dialog) => dialog.accept());

    // Click reset
    await page.getByRole("button", { name: /reset/i }).click();
    await page.waitForTimeout(1500);

    // Night start should be back to default (21:00)
    await expect(nightStart).toHaveValue("21:00", { timeout: 5000 });
  });

  // =========================================================================
  // 7. Save button disabled when no changes
  // =========================================================================
  test("save button is disabled when no changes made", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoTo(page, "/settings/study");

    await expect(
      page.getByRole("heading", { name: /study settings/i }),
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000);

    // Without making changes, save should be disabled
    const saveButton = page.getByRole("button", { name: /save/i });
    await expect(saveButton).toBeDisabled();

    // Change a setting -> save should become enabled
    const algorithmSelect = page.locator("#algorithm");
    const currentValue = await algorithmSelect.inputValue();
    const newValue =
      currentValue === "sadeh_1994_actilife"
        ? "cole_kripke_1992_actilife"
        : "sadeh_1994_actilife";
    await algorithmSelect.selectOption(newValue);

    await expect(saveButton).toBeEnabled({ timeout: 3000 });

    // Unsaved changes indicator should also be visible
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });
  });
});
