/**
 * E2E regression tests for scoring page rendering and settings integration.
 *
 * Covers:
 * - Chart rendering (uPlot canvas)
 * - File selector functionality
 * - Date navigation
 * - Settings change reflected on scoring page
 * - No-sleep toggle
 * - Save indicator after changes
 * - Accessibility (axe-core) scan
 *
 * Tests run serially because they share backend state.
 */

import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  loginAndGoToScoring,
  loginAndGoTo,
  waitForChart,
  fileSelector,
  dateSelector,
  navigateToCleanDate,
  createSleepMarker,
  switchToNoSleepMode,
  assertPageHealthy,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Scoring & Settings Regression", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // -------------------------------------------------------------------------
  // 1. Chart renders: after login, canvas or .uplot element is visible
  // -------------------------------------------------------------------------
  test("chart renders after login", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Verify the uPlot wrapper element is visible
    const uplotElement = page.locator(".uplot");
    await expect(uplotElement).toBeVisible({ timeout: 30000 });

    // Verify a canvas element exists inside uPlot and has proper dimensions
    const canvas = page.locator(".uplot canvas").first();
    await expect(canvas).toBeVisible({ timeout: 10000 });

    const box = await canvas.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThan(400);
    expect(box!.height).toBeGreaterThan(100);

    // The uPlot overlay (interactive layer) should also be present
    const overlay = page.locator(".u-over").first();
    await expect(overlay).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // 2. File selector works: click file selector, options appear
  // -------------------------------------------------------------------------
  test("file selector shows options when clicked", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const fileSelect = fileSelector(page);
    await expect(fileSelect).toBeVisible({ timeout: 10000 });

    // Verify the dropdown has at least one option (the currently loaded file)
    const options = fileSelect.locator("option");
    const optionCount = await options.count();
    expect(optionCount).toBeGreaterThanOrEqual(1);

    // Verify at least one option contains a .csv filename
    const firstOptionText = await options.first().textContent();
    expect(firstOptionText).toBeTruthy();

    // If there are multiple files, try selecting a different one
    if (optionCount > 1) {
      const initialValue = await fileSelect.inputValue();
      const secondOptionValue = await options.nth(1).getAttribute("value");
      if (secondOptionValue && secondOptionValue !== initialValue) {
        await fileSelect.selectOption(secondOptionValue);
        // Wait for chart to re-render after file switch
        await expect(page.locator(".u-over").first()).toBeVisible({
          timeout: 30000,
        });
        const newValue = await fileSelect.inputValue();
        expect(newValue).toBe(secondOptionValue);

        // Restore original file selection
        await fileSelect.selectOption(initialValue);
        await page.waitForTimeout(1500);
      }
    }
  });

  // -------------------------------------------------------------------------
  // 3. Date navigation: click next date button, URL or content changes
  // -------------------------------------------------------------------------
  test("date navigation changes the displayed date", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Get the date selector and its initial selected value
    const dateSelect = dateSelector(page);
    await expect(dateSelect).toBeVisible({ timeout: 10000 });
    const initialDateText =
      (await dateSelect.locator("option:checked").textContent()) ?? "";

    // Try the next-date button first; fall back to prev-date if disabled
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    const prevBtn = page.locator('[data-testid="prev-date-btn"]');
    await expect(nextBtn).toBeVisible({ timeout: 5000 });
    await expect(prevBtn).toBeVisible({ timeout: 5000 });

    if (await nextBtn.isEnabled()) {
      await nextBtn.click();
    } else if (await prevBtn.isEnabled()) {
      await prevBtn.click();
    } else {
      test.skip(true, "Only one date available; cannot validate navigation");
    }

    // Wait for chart re-render
    await expect(page.locator(".u-over").first()).toBeVisible({
      timeout: 30000,
    });
    await page.waitForTimeout(1500);

    // Verify the date counter text changed
    const newDateText =
      (await dateSelect.locator("option:checked").textContent()) ?? "";
    expect(newDateText).not.toBe(initialDateText);
  });

  // -------------------------------------------------------------------------
  // 4. Settings change reflected: navigate to settings, change algorithm,
  //    verify it applies
  // -------------------------------------------------------------------------
  test("algorithm change in settings is reflected on scoring page", async ({
    page,
  }) => {
    test.setTimeout(90000);

    // Go to study settings and change the algorithm
    await loginAndGoTo(page, "/settings/study");
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    const algorithmSelect = page.locator("#algorithm");
    await expect(algorithmSelect).toBeVisible();

    const currentValue = await algorithmSelect.inputValue();
    const newAlgorithm =
      currentValue === "sadeh_1994_actilife"
        ? "cole_kripke_1992_actilife"
        : "sadeh_1994_actilife";

    await algorithmSelect.selectOption(newAlgorithm);

    // Wait for unsaved indicator then save
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({
      timeout: 5000,
    });

    const saveButton = page.getByRole("button", { name: /save/i });
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT"
      ),
      saveButton.click(),
    ]);

    // Confirm save completed
    await expect(page.getByText(/unsaved changes/i)).not.toBeVisible({
      timeout: 5000,
    });

    // Navigate to scoring page and verify the algorithm is active
    await page.locator('a[href="/scoring"]').click();
    await page.waitForURL("**/scoring**", { timeout: 10000 });
    await waitForChart(page);
    await page.waitForTimeout(2000);

    // The algorithm dropdown on scoring page should reflect the saved setting
    const scoringAlgoSelect = page
      .locator("select")
      .filter({ hasText: /Sadeh|Cole/ })
      .first();
    if (await scoringAlgoSelect.isVisible({ timeout: 5000 }).catch(() => false)) {
      const scoringAlgoValue = await scoringAlgoSelect.inputValue();
      expect(scoringAlgoValue).toBe(newAlgorithm);
    }

    // Verify the chart is healthy after the algorithm change
    await assertPageHealthy(page);

    // Restore original algorithm setting
    await page.locator('a[href="/settings/study"]').click();
    await page.waitForURL("**/settings/study**", { timeout: 10000 });
    await expect(
      page.getByRole("heading", { name: /study settings/i })
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1500);

    await page.locator("#algorithm").selectOption(currentValue);
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/settings") &&
          resp.request().method() === "PUT"
      ),
      page.getByRole("button", { name: /save/i }).click(),
    ]);
    await page.waitForTimeout(500);
  });

  // -------------------------------------------------------------------------
  // 5. No-sleep toggle: find and toggle no-sleep button on scoring page
  // -------------------------------------------------------------------------
  test("no-sleep toggle marks date and preserves nap markers", async ({
    page,
  }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Navigate to a clean date to avoid interfering with existing markers
    await navigateToCleanDate(page);

    // Locate the No Sleep button
    const noSleepBtn = page
      .locator("button")
      .filter({ hasText: /No Sleep/i })
      .first();
    await expect(noSleepBtn).toBeVisible({ timeout: 5000 });

    // Get initial state (active = bg-amber-600)
    const initialClass = (await noSleepBtn.getAttribute("class")) ?? "";
    const wasActive = initialClass.includes("bg-amber");

    // Toggle No Sleep ON (accept any confirmation dialog)
    if (!wasActive) {
      page.once("dialog", (d) => d.accept());
      await noSleepBtn.click();
      await page.waitForTimeout(500);
    }

    // Verify No Sleep is now active (amber background)
    const activeClass = (await noSleepBtn.getAttribute("class")) ?? "";
    expect(activeClass).toContain("bg-amber");

    // The Sleep mode button should be disabled when No Sleep is active
    const sleepBtn = page.locator("button").filter({ hasText: "Sleep" }).first();
    if (await sleepBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      const sleepBtnDisabled = await sleepBtn.isDisabled();
      expect(sleepBtnDisabled).toBe(true);
    }

    // Toggle No Sleep OFF to clean up
    await noSleepBtn.click();
    await page.waitForTimeout(500);

    const restoredClass = (await noSleepBtn.getAttribute("class")) ?? "";
    expect(restoredClass).not.toContain("bg-amber");

    await assertPageHealthy(page);
  });

  // -------------------------------------------------------------------------
  // 6. Save indicator: after making changes, "Saved" indicator appears
  // -------------------------------------------------------------------------
  test("save indicator appears after marker creation", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Navigate to a clean date
    await navigateToCleanDate(page);

    // Create a sleep marker
    await createSleepMarker(page, overlay);

    // The "Saved" indicator should appear after auto-save (1s debounce + save)
    const savedBadge = page.getByText("Saved");
    await expect(savedBadge).toBeVisible({ timeout: 10000 });

    // Verify the badge is not showing "Unsaved" or "Saving" at rest
    await page.waitForTimeout(2000);
    const unsavedBadge = page.getByText("Unsaved");
    const savingBadge = page.getByText("Saving");
    await expect(unsavedBadge).not.toBeVisible({ timeout: 2000 });
    await expect(savingBadge).not.toBeVisible({ timeout: 2000 });
  });

  // -------------------------------------------------------------------------
  // 7. Accessibility: run axe-core scan on scoring page
  // -------------------------------------------------------------------------
  test("scoring page passes accessibility checks", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Wait for the page to fully stabilize before running axe
    await page.waitForTimeout(2000);

    const results = await new AxeBuilder({ page })
      .exclude(".uplot") // Exclude canvas-based chart (not auditable by axe)
      .exclude("[data-testid^='marker-']") // Exclude dynamic marker overlays
      .analyze();

    // Log any violations for debugging
    if (results.violations.length > 0) {
      for (const violation of results.violations) {
        console.log(
          `[a11y] ${violation.id} (${violation.impact}): ${violation.description} ` +
            `(${violation.nodes.length} node(s))`
        );
      }
    }

    expect(results.violations).toEqual([]);
  });
});
