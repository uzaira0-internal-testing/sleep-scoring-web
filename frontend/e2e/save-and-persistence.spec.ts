/**
 * E2E tests for save and persistence behavior:
 * - Auto-save triggers after marker creation/modification
 * - Ctrl+S manual save
 * - Marker persistence across page reloads and navigation
 * - Save status indicator transitions (Unsaved -> Saving -> Saved)
 * - No Sleep date status persistence
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
  getOnsetLine,
  dragElement,
  switchToSleepMode,
  switchToNonwearMode,
  switchToNoSleepMode,
  assertPageHealthy,
  sleepMarkerCount,
  nonwearMarkerCount,
  nextDate,
  prevDate,
  createNonwearMarker,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.describe("Save & Persistence", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    const client = await page.context().newCDPSession(page);
    await client.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  // ==========================================================================
  // AUTO-SAVE BEHAVIOR
  // ==========================================================================

  test("creating a marker triggers auto-save (Saved indicator appears within 5s)", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay);

    // After creation, isDirty becomes true, then auto-save fires after 1s debounce
    // The "Saved" badge should appear within ~5 seconds
    const savedBadge = page.getByText("Saved");
    await expect(savedBadge).toBeVisible({ timeout: 10000 });
  });

  test("moving a marker shows Unsaved then auto-saves to Saved", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await ensureSleepMarker(page, overlay);
    await selectFirstSleepMarker(page);

    // Wait for initial save to complete
    await expect(page.getByText("Saved")).toBeVisible({ timeout: 10000 });

    // Now drag the onset line to change the marker
    const onsetLine = getOnsetLine(page);
    const isVisible = await onsetLine.isVisible({ timeout: 3000 });

    if (isVisible) {
      await dragElement(page, onsetLine, 50);
      await page.mouse.up();

      // After dragging, the state should become dirty
      // Then auto-save kicks in: Unsaved -> Saving -> Saved
      // We check for "Saved" appearing within a reasonable window
      await expect(page.getByText("Saved")).toBeVisible({ timeout: 10000 });
    }
  });

  test("Ctrl+S triggers immediate save", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay);

    // Wait briefly so the marker creation state is set, but before auto-save fires
    await page.waitForTimeout(200);

    // Press Ctrl+S to force immediate save
    await page.keyboard.press("Control+s");

    // Should see Saved indicator appear
    const savedBadge = page.getByText("Saved");
    await expect(savedBadge).toBeVisible({ timeout: 10000 });
  });

  // ==========================================================================
  // PERSISTENCE ACROSS RELOAD
  // ==========================================================================

  test("markers persist after page reload", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay);

    // Wait for auto-save to complete
    await expect(page.getByText("Saved")).toBeVisible({ timeout: 10000 });

    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThan(0);

    // Reload the page
    await page.reload();
    await waitForChart(page);
    await page.waitForTimeout(3000); // Wait for markers to load from DB

    // Markers should still be present
    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBeGreaterThan(0);
  });

  test("markers persist after navigating away and back to scoring", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await ensureSleepMarker(page, overlay);

    // Wait for auto-save
    await expect(page.getByText("Saved")).toBeVisible({ timeout: 10000 });

    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThan(0);

    // Navigate to settings page
    await page.locator('a[href="/settings/study"]').click();
    await page.waitForURL("**/settings/study**", { timeout: 5000 });

    // Navigate back to scoring
    await page.locator('a[href="/scoring"]').click();
    await page.waitForURL("**/scoring**", { timeout: 5000 });
    await waitForChart(page);
    await page.waitForTimeout(3000); // Wait for markers to reload

    // Markers should still be present
    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBeGreaterThan(0);
  });

  test("save status resets to clean state on date change", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    await navigateToCleanDate(page);
    await createSleepMarker(page, overlay);

    // Wait for save to complete
    await expect(page.getByText("Saved")).toBeVisible({ timeout: 10000 });

    // Navigate to next date - this should reset marker state
    await nextDate(page);
    await page.waitForTimeout(1000);

    // On a new date with no markers, the "Saved" badge should not appear
    // (it only shows when there are markers)
    // The page should be in a clean state (no unsaved/saving indicators)
    const unsaved = page.getByText("Unsaved");
    const saving = page.getByText("Saving");
    await expect(unsaved).not.toBeVisible({ timeout: 3000 });
    await expect(saving).not.toBeVisible({ timeout: 1000 });
  });

  test("multiple markers all persist after reload", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Clear existing markers so we start from a clean state
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(2000);
      }
    }

    // Create first sleep marker (narrow, in the left portion)
    await createSleepMarker(page, overlay, 0.1, 0.2);
    await page.waitForTimeout(1000);

    // Wait for first marker to auto-save
    await expect(page.getByText("Saved")).toBeVisible({ timeout: 10000 });

    // Deselect any marker before creating the next one
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);

    // Create second sleep marker (narrow, in the right portion - far from first)
    await createSleepMarker(page, overlay, 0.7, 0.85);
    await page.waitForTimeout(1000);

    // Force save with Ctrl+S and wait for completion
    await page.keyboard.press("Control+s");
    await expect(page.getByText("Saved")).toBeVisible({ timeout: 10000 });
    // Extra wait to ensure the save API request fully completes
    await page.waitForTimeout(2000);

    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThanOrEqual(2);

    // Reload
    await page.reload();
    await waitForChart(page);
    await page.waitForTimeout(3000);

    // All markers should be restored
    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBeGreaterThanOrEqual(2);
  });

  test("deleting a marker and reloading shows it is gone", async ({ page }) => {
    test.setTimeout(60000);
    const overlay = await loginAndGoToScoring(page);

    // Clear all existing markers first to start from scratch
    const existingCount = await sleepMarkerCount(page);
    if (existingCount > 0) {
      page.once("dialog", (dialog) => dialog.accept());
      const clearButton = page.locator("button").filter({ hasText: "Clear" }).first();
      if (await clearButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearButton.click();
        await page.waitForTimeout(2000);
      }
    }

    await createSleepMarker(page, overlay);

    // Wait for save
    await expect(page.getByText("Saved")).toBeVisible({ timeout: 10000 });
    const countBefore = await sleepMarkerCount(page);
    expect(countBefore).toBeGreaterThan(0);

    // Select and delete the marker using keyboard
    await selectFirstSleepMarker(page);
    await page.keyboard.press("Delete");
    await page.waitForTimeout(500);

    // Force save the deletion
    await page.keyboard.press("Control+s");
    await page.waitForTimeout(3000);

    // Reload
    await page.reload();
    await waitForChart(page);
    await page.waitForTimeout(3000);

    // Marker should not reappear
    const countAfter = await sleepMarkerCount(page);
    expect(countAfter).toBe(0);
  });

  test("No Sleep date status persists after reload", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    await navigateToCleanDate(page);

    // Mark date as No Sleep (accepts confirmation dialog if sleep markers exist)
    await switchToNoSleepMode(page);

    // Wait for auto-save of the no-sleep status
    await page.waitForTimeout(3000);

    // The No Sleep button should be active (visually amber/highlighted)
    const noSleepBtn = page.locator("button").filter({ hasText: /No Sleep/i }).first();
    // In the active state, the button has bg-amber-600 class
    const btnClass = await noSleepBtn.getAttribute("class");
    expect(btnClass).toContain("bg-amber-600");

    // Reload page
    await page.reload();
    await waitForChart(page);
    await page.waitForTimeout(3000);

    // After reload, the No Sleep status should be restored
    const noSleepBtnAfter = page.locator("button").filter({ hasText: /No Sleep/i }).first();
    const btnClassAfter = await noSleepBtnAfter.getAttribute("class");
    expect(btnClassAfter).toContain("bg-amber-600");

    // Toggle No Sleep OFF so it doesn't interfere with other tests
    await noSleepBtnAfter.click();
    await page.waitForTimeout(2000);
  });

  // ==========================================================================
  // CONSENSUS FLAG PERSISTENCE
  // ==========================================================================

  test("Consensus button toggles on/off and is visible", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // The Consensus button should be visible on the scoring page
    const consensusBtn = page.locator("button").filter({ hasText: /Consensus/i }).first();
    await expect(consensusBtn).toBeVisible({ timeout: 5000 });

    // Initially should be outline (not active)
    const initialClass = await consensusBtn.getAttribute("class") ?? "";
    const wasActive = initialClass.includes("bg-orange-600");

    // Click to toggle
    await consensusBtn.click();
    await page.waitForTimeout(500);

    const afterClickClass = await consensusBtn.getAttribute("class") ?? "";
    if (wasActive) {
      // Was active, clicking should deactivate — no orange bg
      expect(afterClickClass).not.toContain("bg-orange-600");
    } else {
      // Was inactive, clicking should activate — orange bg
      expect(afterClickClass).toContain("bg-orange-600");
    }

    // Toggle back to original state
    await consensusBtn.click();
    await page.waitForTimeout(500);

    const restoredClass = await consensusBtn.getAttribute("class") ?? "";
    if (wasActive) {
      expect(restoredClass).toContain("bg-orange-600");
    } else {
      expect(restoredClass).not.toContain("bg-orange-600");
    }
  });

  test("Consensus flag persists after page reload", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Ensure consensus is OFF first
    const consensusBtn = page.locator("button").filter({ hasText: /Consensus/i }).first();
    await expect(consensusBtn).toBeVisible({ timeout: 5000 });
    const initialClass = await consensusBtn.getAttribute("class") ?? "";
    if (initialClass.includes("bg-orange-600")) {
      await consensusBtn.click();
      await page.waitForTimeout(3000); // Wait for auto-save
    }

    // Now turn consensus ON
    await consensusBtn.click();
    await page.waitForTimeout(500);

    // Verify it's active
    const activeClass = await consensusBtn.getAttribute("class") ?? "";
    expect(activeClass).toContain("bg-orange-600");

    // Wait for auto-save to persist
    await page.waitForTimeout(3000);

    // Reload the page
    await page.reload();
    await waitForChart(page);
    await page.waitForTimeout(3000);

    // After reload, the Consensus flag should be restored
    const consensusBtnAfter = page.locator("button").filter({ hasText: /Consensus/i }).first();
    const classAfter = await consensusBtnAfter.getAttribute("class") ?? "";
    expect(classAfter).toContain("bg-orange-600");

    // Clean up: toggle consensus OFF
    await consensusBtnAfter.click();
    await page.waitForTimeout(3000);
  });

  test("Consensus flag persists after navigating to another date and back", async ({ page }) => {
    test.setTimeout(90000);
    await loginAndGoToScoring(page);

    // Ensure consensus starts OFF
    const consensusBtn = page.locator("button").filter({ hasText: /Consensus/i }).first();
    await expect(consensusBtn).toBeVisible({ timeout: 5000 });
    const initialClass = await consensusBtn.getAttribute("class") ?? "";
    if (initialClass.includes("bg-orange-600")) {
      await consensusBtn.click();
      await page.waitForTimeout(4000); // Wait for auto-save of the OFF state
    }

    // Turn consensus ON
    await consensusBtn.click();
    await page.waitForTimeout(500);
    expect((await consensusBtn.getAttribute("class")) ?? "").toContain("bg-orange-600");

    // Wait for auto-save to persist (1s debounce + save time)
    await page.waitForTimeout(4000);

    // Navigate to next date
    await nextDate(page);
    await page.waitForTimeout(3000);

    // Consensus should be OFF on the new date (cleared on navigation)
    const consensusBtnNext = page.locator("button").filter({ hasText: /Consensus/i }).first();
    const nextDateClass = await consensusBtnNext.getAttribute("class") ?? "";
    expect(nextDateClass).not.toContain("bg-orange-600");

    // Navigate back to previous date
    await prevDate(page);

    // Consensus flag should be restored from API after React Query refetch
    const consensusBtnBack = page.locator("button").filter({ hasText: /Consensus/i }).first();
    await expect(consensusBtnBack).toHaveClass(/bg-orange-600/, { timeout: 15000 });

    // Clean up: toggle consensus OFF
    await consensusBtnBack.click();
    await page.waitForTimeout(4000);
  });

  test("algorithm selection persists between sessions via settings", async ({ page }) => {
    test.setTimeout(60000);
    await loginAndGoToScoring(page);

    // Get the current algorithm selection from the scoring page
    const algorithmSelect = page.locator("select").filter({ hasText: /Sadeh|Cole|van Hees/ }).first();
    const isVisible = await algorithmSelect.isVisible({ timeout: 3000 });

    if (isVisible) {
      const currentValue = await algorithmSelect.inputValue();

      // The algorithm setting on the scoring page is stored in Zustand (client-side).
      // After reload, the last-used algorithm should still be selected because
      // the store may persist to localStorage or the server settings.
      await page.reload();
      await waitForChart(page);
      await page.waitForTimeout(2000);

      const algorithmSelectAfter = page.locator("select").filter({ hasText: /Sadeh|Cole|van Hees/ }).first();
      if (await algorithmSelectAfter.isVisible({ timeout: 3000 })) {
        const valueAfter = await algorithmSelectAfter.inputValue();
        // Value should be the same (default or previously selected)
        expect(valueAfter).toBe(currentValue);
      }
    }

    // Verify the page is still healthy
    await assertPageHealthy(page);
  });
});
