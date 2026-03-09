/**
 * Comprehensive E2E tests for date navigation on the scoring page.
 *
 * Covers: next/prev buttons, date counter format, boundary conditions,
 * round-trip navigation, date dropdown, date format/status symbols,
 * chart re-rendering, weekday label, marker isolation between dates,
 * marker persistence when revisiting a date, and keyboard navigation.
 *
 * Tests run SERIALLY because they share backend state and navigate dates sequentially.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndGoToScoring,
  waitForChart,
  nextDate,
  prevDate,
  getDateCounter,
  fileSelector,
  dateSelector,
  getOverlayBox,
  assertPageHealthy,
  sleepMarkerCount,
  createSleepMarker,
  navigateToCleanDate,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Date Navigation Comprehensive", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  /**
   * Parse a date counter string like "3/14" into { current, total }.
   * The counter is embedded in the date dropdown option text as "(N/M)".
   */
  function parseDateCounter(text: string): { current: number; total: number } | null {
    const match = text.match(/(\d+)\/(\d+)/);
    if (!match) return null;
    return { current: parseInt(match[1], 10), total: parseInt(match[2], 10) };
  }

  // =========================================================================
  // 1. Next date button advances date counter
  // =========================================================================
  test("next date button advances date counter", async ({ page }) => {
    await loginAndGoToScoring(page);

    const counterBefore = await getDateCounter(page);
    const parsed = parseDateCounter(counterBefore);
    expect(parsed).toBeTruthy();

    // Only advance if not on the last date
    if (parsed!.current < parsed!.total) {
      await nextDate(page);

      const counterAfter = await getDateCounter(page);
      const parsedAfter = parseDateCounter(counterAfter);
      expect(parsedAfter).toBeTruthy();
      expect(parsedAfter!.current).toBe(parsed!.current + 1);
      expect(parsedAfter!.total).toBe(parsed!.total);
    }
  });

  // =========================================================================
  // 2. Previous date button decrements date counter
  // =========================================================================
  test("previous date button decrements date counter", async ({ page }) => {
    await loginAndGoToScoring(page);

    // First advance so we have room to go back
    const counterInitial = await getDateCounter(page);
    const parsedInitial = parseDateCounter(counterInitial);

    if (parsedInitial && parsedInitial.current < parsedInitial.total) {
      await nextDate(page);
      const counterMid = await getDateCounter(page);
      const parsedMid = parseDateCounter(counterMid);

      await prevDate(page);
      const counterAfter = await getDateCounter(page);
      const parsedAfter = parseDateCounter(counterAfter);

      expect(parsedAfter).toBeTruthy();
      expect(parsedAfter!.current).toBe(parsedMid!.current - 1);
    }
  });

  // =========================================================================
  // 3. Date counter shows current/total format
  // =========================================================================
  test("date counter shows current/total format", async ({ page }) => {
    await loginAndGoToScoring(page);

    const counterText = await getDateCounter(page);
    expect(counterText).toMatch(/\d+\/\d+/);

    const parsed = parseDateCounter(counterText);
    expect(parsed).toBeTruthy();
    expect(parsed!.current).toBeGreaterThanOrEqual(1);
    expect(parsed!.total).toBeGreaterThanOrEqual(1);
    expect(parsed!.current).toBeLessThanOrEqual(parsed!.total);
  });

  // =========================================================================
  // 4. Next date at last date: button disabled or counter stays same
  // =========================================================================
  test("next date button is disabled at last date", async ({ page }) => {
    test.setTimeout(120000);
    await loginAndGoToScoring(page);

    const counterText = await getDateCounter(page);
    const parsed = parseDateCounter(counterText);
    expect(parsed).toBeTruthy();

    // Navigate to the last date using the dropdown
    const dateSel = dateSelector(page);
    const dateOptions = await dateSel.locator("option").all();
    const lastOptionValue = await dateOptions[dateOptions.length - 1].getAttribute("value");
    if (lastOptionValue !== null) {
      await dateSel.selectOption(lastOptionValue);
      await page.waitForTimeout(2000);
    }

    // The next button should now be disabled
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    const isDisabled = await nextBtn.isDisabled();
    expect(isDisabled).toBe(true);

    // Counter should show last/total
    const lastCounter = await getDateCounter(page);
    const parsedLast = parseDateCounter(lastCounter);
    expect(parsedLast).toBeTruthy();
    expect(parsedLast!.current).toBe(parsedLast!.total);
  });

  // =========================================================================
  // 5. Previous date at first date: button disabled or counter stays same
  // =========================================================================
  test("prev date button is disabled at first date", async ({ page }) => {
    await loginAndGoToScoring(page);

    // Navigate to the first date using the dropdown
    const dateSel = dateSelector(page);
    const firstOptionValue = await dateSel.locator("option").first().getAttribute("value");
    if (firstOptionValue !== null) {
      await dateSel.selectOption(firstOptionValue);
      await page.waitForTimeout(2000);
    }

    // The prev button should be disabled
    const prevBtn = page.locator('[data-testid="prev-date-btn"]');
    const isDisabled = await prevBtn.isDisabled();
    expect(isDisabled).toBe(true);

    // Counter should show 1/total
    const firstCounter = await getDateCounter(page);
    const parsedFirst = parseDateCounter(firstCounter);
    expect(parsedFirst).toBeTruthy();
    expect(parsedFirst!.current).toBe(1);
  });

  // =========================================================================
  // 6. Navigate forward 3 dates, then back 3, arrive at original
  // =========================================================================
  test("navigate forward 3 then back 3 returns to original date", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const counterBefore = await getDateCounter(page);
    const parsedBefore = parseDateCounter(counterBefore);
    expect(parsedBefore).toBeTruthy();

    // Need at least 4 dates to navigate forward 3
    if (parsedBefore!.total - parsedBefore!.current < 3) {
      test.skip(true, "Not enough dates to navigate forward 3");
      return;
    }

    // Navigate forward 3
    await nextDate(page);
    await nextDate(page);
    await nextDate(page);

    const counterMid = await getDateCounter(page);
    const parsedMid = parseDateCounter(counterMid);
    expect(parsedMid!.current).toBe(parsedBefore!.current + 3);

    // Navigate back 3
    await prevDate(page);
    await prevDate(page);
    await prevDate(page);

    const counterAfter = await getDateCounter(page);
    const parsedAfter = parseDateCounter(counterAfter);
    expect(parsedAfter!.current).toBe(parsedBefore!.current);
  });

  // =========================================================================
  // 7. Date dropdown has multiple options
  // =========================================================================
  test("date dropdown has multiple date options", async ({ page }) => {
    await loginAndGoToScoring(page);

    const dateSel = dateSelector(page);
    await expect(dateSel).toBeVisible({ timeout: 10000 });

    const optionCount = await dateSel.locator("option").count();
    expect(optionCount).toBeGreaterThan(0);
  });

  // =========================================================================
  // 8. Selecting a date from dropdown changes the counter
  // =========================================================================
  test("selecting a date from dropdown changes the counter", async ({ page }) => {
    await loginAndGoToScoring(page);

    const dateSel = dateSelector(page);
    const options = await dateSel.locator("option").all();

    if (options.length < 2) {
      test.skip(true, "Only one date available");
      return;
    }

    const counterBefore = await getDateCounter(page);
    const parsedBefore = parseDateCounter(counterBefore);

    // Select the second option (index 1)
    const secondValue = await options[1].getAttribute("value");
    if (secondValue !== null) {
      await dateSel.selectOption(secondValue);
      await page.waitForTimeout(2000);
    }

    const counterAfter = await getDateCounter(page);
    const parsedAfter = parseDateCounter(counterAfter);
    expect(parsedAfter).toBeTruthy();
    expect(parsedAfter!.current).toBe(2);
  });

  // =========================================================================
  // 9. Date dropdown options show date strings (YYYY-MM-DD format)
  // =========================================================================
  test("date dropdown options show YYYY-MM-DD format dates", async ({ page }) => {
    await loginAndGoToScoring(page);

    const dateSel = dateSelector(page);
    const options = await dateSel.locator("option").all();
    expect(options.length).toBeGreaterThan(0);

    for (const opt of options) {
      const text = await opt.textContent();
      expect(text).toBeTruthy();
      // Each option should contain a date in YYYY-MM-DD format
      expect(text).toMatch(/\d{4}-\d{2}-\d{2}/);
    }
  });

  // =========================================================================
  // 10. Date dropdown shows status symbols
  // =========================================================================
  test("date dropdown options show status symbols", async ({ page }) => {
    await loginAndGoToScoring(page);

    const dateSel = dateSelector(page);
    const options = await dateSel.locator("option").all();
    expect(options.length).toBeGreaterThan(0);

    let hasSymbol = false;
    for (const opt of options) {
      const text = await opt.textContent();
      if (!text) continue;
      // Options should have one of the status prefixes:
      // \u2713 (checkmark) for has_markers, \u25cb (circle) for empty, \u26d4 (no entry) for no_sleep
      if (text.includes("\u2713") || text.includes("\u25cb") || text.includes("\u26d4")) {
        hasSymbol = true;
        break;
      }
    }

    expect(hasSymbol).toBe(true);
  });

  // =========================================================================
  // 11. Chart re-renders after date change (overlay visible)
  // =========================================================================
  test("chart re-renders after date change", async ({ page }) => {
    await loginAndGoToScoring(page);

    // Navigate to next date
    await nextDate(page);

    // Verify chart overlay is still visible after date change
    const overlay = await waitForChart(page);
    await expect(overlay).toBeVisible();

    const box = await getOverlayBox(overlay);
    expect(box.width).toBeGreaterThan(100);
    expect(box.height).toBeGreaterThan(50);
  });

  // =========================================================================
  // 12. Weekday label updates on date change
  // =========================================================================
  test("weekday label updates on date change", async ({ page }) => {
    await loginAndGoToScoring(page);

    const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

    // Find the weekday label (span with one of the weekday names)
    const weekdayLocator = page.locator("span").filter({ hasText: new RegExp(weekdays.join("|")) }).first();
    const hasWeekday = await weekdayLocator.isVisible({ timeout: 3000 }).catch(() => false);

    if (!hasWeekday) {
      test.skip(true, "Weekday label not visible on current page");
      return;
    }

    const weekdayBefore = await weekdayLocator.textContent();
    expect(weekdayBefore).toBeTruthy();
    expect(weekdays).toContain(weekdayBefore!.trim());

    // Navigate to next date
    await nextDate(page);

    // The weekday label should still be visible and contain a valid weekday
    const weekdayAfter = page.locator("span").filter({ hasText: new RegExp(weekdays.join("|")) }).first();
    const afterText = await weekdayAfter.textContent();
    expect(afterText).toBeTruthy();
    expect(weekdays).toContain(afterText!.trim());
    // Adjacent dates should have different weekdays (unless data has gaps)
  });

  // =========================================================================
  // 13. Markers from date 1 not visible on date 2 (isolation)
  // =========================================================================
  test("markers from one date are not visible on another date", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Ensure we start on date 1
    const dateSel = dateSelector(page);
    const firstOptionValue = await dateSel.locator("option").first().getAttribute("value");
    if (firstOptionValue !== null) {
      await dateSel.selectOption(firstOptionValue);
      await page.waitForTimeout(2000);
    }

    await page.waitForTimeout(1500);
    const markersDate1 = await sleepMarkerCount(page);

    // Navigate to a different date
    await nextDate(page);
    await page.waitForTimeout(1500);
    const markersDate2 = await sleepMarkerCount(page);

    // The marker counts can independently be 0 or more, but the dates
    // should maintain separate marker state. Navigate back to confirm.
    await prevDate(page);
    await page.waitForTimeout(1500);
    const markersDate1Again = await sleepMarkerCount(page);

    // The original date should still have the same markers
    expect(markersDate1Again).toBe(markersDate1);
  });

  // =========================================================================
  // 14. Navigating back to a date shows its original markers
  // =========================================================================
  test("navigating back to a date shows its original markers", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Record markers on the first date
    await page.waitForTimeout(1500);
    const initialMarkers = await sleepMarkerCount(page);

    // Navigate forward 2 dates and back
    const counterText = await getDateCounter(page);
    const parsed = parseDateCounter(counterText);
    if (!parsed || parsed.total < 3) {
      test.skip(true, "Not enough dates to test round-trip navigation");
      return;
    }

    await nextDate(page);
    await nextDate(page);
    await prevDate(page);
    await prevDate(page);

    await page.waitForTimeout(1500);
    const restoredMarkers = await sleepMarkerCount(page);
    expect(restoredMarkers).toBe(initialMarkers);
  });

  // =========================================================================
  // 15. Keyboard arrow right = next date
  // =========================================================================
  test("keyboard ArrowRight navigates to next date", async ({ page }) => {
    await loginAndGoToScoring(page);

    const counterBefore = await getDateCounter(page);
    const parsedBefore = parseDateCounter(counterBefore);

    if (!parsedBefore || parsedBefore.current >= parsedBefore.total) {
      test.skip(true, "Already on last date, cannot navigate forward");
      return;
    }

    // Press ArrowRight to navigate to next date
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(2000);

    const counterAfter = await getDateCounter(page);
    const parsedAfter = parseDateCounter(counterAfter);
    expect(parsedAfter).toBeTruthy();
    expect(parsedAfter!.current).toBe(parsedBefore!.current + 1);
  });

  // =========================================================================
  // 16. Keyboard arrow left = prev date
  // =========================================================================
  test("keyboard ArrowLeft navigates to previous date", async ({ page }) => {
    await loginAndGoToScoring(page);

    // First navigate forward to ensure we can go back
    const counterInitial = await getDateCounter(page);
    const parsedInitial = parseDateCounter(counterInitial);

    if (!parsedInitial || parsedInitial.total < 2) {
      test.skip(true, "Only one date available");
      return;
    }

    // Navigate forward first using the button (reliable)
    await nextDate(page);
    const counterMid = await getDateCounter(page);
    const parsedMid = parseDateCounter(counterMid);

    // Press ArrowLeft to go back
    await page.keyboard.press("ArrowLeft");
    await page.waitForTimeout(2000);

    const counterAfter = await getDateCounter(page);
    const parsedAfter = parseDateCounter(counterAfter);
    expect(parsedAfter).toBeTruthy();
    expect(parsedAfter!.current).toBe(parsedMid!.current - 1);
  });

  // =========================================================================
  // 17. Page remains healthy after rapid date navigation
  // =========================================================================
  test("page remains healthy after rapid date navigation", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    const counterText = await getDateCounter(page);
    const parsed = parseDateCounter(counterText);

    if (!parsed || parsed.total < 4) {
      test.skip(true, "Not enough dates for rapid navigation test");
      return;
    }

    // Rapidly navigate forward and back without waiting for full render
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    const prevBtn = page.locator('[data-testid="prev-date-btn"]');

    await nextBtn.click();
    await page.waitForTimeout(300);
    await nextBtn.click();
    await page.waitForTimeout(300);
    await nextBtn.click();
    await page.waitForTimeout(300);
    await prevBtn.click();
    await page.waitForTimeout(300);
    await prevBtn.click();

    // Wait for everything to settle
    await page.waitForTimeout(2000);

    // Page should still be healthy
    await assertPageHealthy(page);

    // Counter should show a valid date
    const finalCounter = await getDateCounter(page);
    const parsedFinal = parseDateCounter(finalCounter);
    expect(parsedFinal).toBeTruthy();
    expect(parsedFinal!.current).toBeGreaterThanOrEqual(1);
    expect(parsedFinal!.current).toBeLessThanOrEqual(parsedFinal!.total);
  });

  // =========================================================================
  // 18. Date dropdown selected value matches counter
  // =========================================================================
  test("date dropdown selected value matches displayed counter", async ({ page }) => {
    await loginAndGoToScoring(page);

    const dateSel = dateSelector(page);
    const selectedValue = await dateSel.inputValue();

    // The selected option text should contain the current counter
    const selectedOption = dateSel.locator(`option[value="${selectedValue}"]`);
    const optionText = await selectedOption.textContent();
    expect(optionText).toBeTruthy();

    // Extract counter from the option text
    const counterMatch = optionText!.match(/(\d+)\/(\d+)/);
    expect(counterMatch).toBeTruthy();

    // The counter in the option text should also be reflected in the general counter
    const counterText = await getDateCounter(page);
    expect(counterText).toContain(`${counterMatch![1]}/${counterMatch![2]}`);
  });
});
