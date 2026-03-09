/**
 * Shared Playwright e2e test helpers for the Sleep Scoring web app.
 * Import these in spec files to avoid duplicating login/setup/interaction code.
 */

import { expect, type Page, type Locator } from "@playwright/test";

async function loginIfNeeded(page: Page) {
  // Give router redirects a moment to settle (/scoring -> /login)
  await page.waitForTimeout(300);
  if (!page.url().includes("/login")) return;

  // Password can be optional depending on backend auth config
  const passwordInput = page.locator('input[name="password"]');
  if (await passwordInput.count() > 0) {
    await passwordInput.fill("admin");
  }

  await page.locator('input[name="username"]').fill("admin");
  await page.click('button[type="submit"]');
  await page.waitForURL("**/scoring**", { timeout: 15000 });
}

// =============================================================================
// AUTHENTICATION
// =============================================================================

/** Login and navigate to the scoring page, wait for chart to render */
export async function loginAndGoToScoring(page: Page): Promise<Locator> {
  await page.goto("/scoring");
  await loginIfNeeded(page);

  const overlay = page.locator(".u-over").first();
  await expect(overlay).toBeVisible({ timeout: 30000 });
  return overlay;
}

/** Login and navigate to any page */
export async function loginAndGoTo(page: Page, path: string) {
  await page.goto("/login");
  await loginIfNeeded(page);

  if (path !== "/scoring") {
    await page.goto(path);
    await page.waitForTimeout(500);
  }
}

/** Just login (don't wait for chart) */
export async function login(page: Page) {
  await page.goto("/login");
  await loginIfNeeded(page);
}

// =============================================================================
// CHART & OVERLAY
// =============================================================================

/** Wait for the uPlot chart to be ready */
export async function waitForChart(page: Page): Promise<Locator> {
  const overlay = page.locator(".u-over").first();
  await expect(overlay).toBeVisible({ timeout: 30000 });
  return overlay;
}

/** Get the chart overlay bounding box */
export async function getOverlayBox(overlay: Locator) {
  const box = await overlay.boundingBox();
  expect(box).toBeTruthy();
  return box!;
}

// =============================================================================
// DATE NAVIGATION
// =============================================================================

/** Click next date and wait for chart re-render */
export async function nextDate(page: Page) {
  await page.locator('[data-testid="next-date-btn"]').click();
  await page.waitForTimeout(1500);
}

/** Click prev date and wait for chart re-render */
export async function prevDate(page: Page) {
  await page.locator('[data-testid="prev-date-btn"]').click();
  await page.waitForTimeout(1500);
}

/** Get current date counter text from the date dropdown selected option (e.g. "✓ 2025-07-31 (1/14)") */
export async function getDateCounter(page: Page): Promise<string> {
  // The date counter is in the date selector dropdown's selected option text
  const dateSelect = page.locator("select").filter({ has: page.locator("option:has-text('/')") }).first();
  const selectedText = await dateSelect.locator("option:checked").textContent() ?? "";
  return selectedText;
}

/** Navigate to a date that has no sleep markers */
export async function navigateToCleanDate(page: Page, maxClicks = 8) {
  for (let i = 0; i < maxClicks; i++) {
    const count = await page.locator('[data-testid^="marker-region-sleep-"]').count();
    if (count === 0) return true;
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    if (await nextBtn.isEnabled({ timeout: 500 }).catch(() => false)) {
      await nextBtn.click();
      await page.waitForTimeout(1500);
    } else {
      break;
    }
  }
  return false;
}

// =============================================================================
// MARKER CREATION & SELECTION
// =============================================================================

/** Create a sleep marker by clicking at two x-positions on the overlay */
export async function createSleepMarker(
  page: Page,
  overlay: Locator,
  onsetPct = 0.25,
  offsetPct = 0.75,
) {
  const box = await getOverlayBox(overlay);
  await overlay.click({
    position: { x: box.width * onsetPct, y: box.height / 2 },
    force: true,
  });
  await page.waitForTimeout(500);
  await overlay.click({
    position: { x: box.width * offsetPct, y: box.height / 2 },
    force: true,
  });
  await page.waitForTimeout(1500);
}

/** Create a nonwear marker (switch mode, click twice, switch back) */
export async function createNonwearMarker(
  page: Page,
  overlay: Locator,
  startPct = 0.3,
  endPct = 0.5,
) {
  await page.locator("button").filter({ hasText: "Nonwear" }).first().click();
  await page.waitForTimeout(500);
  const box = await getOverlayBox(overlay);
  await overlay.click({
    position: { x: box.width * startPct, y: box.height / 2 },
    force: true,
  });
  await page.waitForTimeout(500);
  await overlay.click({
    position: { x: box.width * endPct, y: box.height / 2 },
    force: true,
  });
  await page.waitForTimeout(1500);
}

/** Ensure at least one visible sleep marker exists; creates one if needed */
export async function ensureSleepMarker(page: Page, overlay: Locator) {
  const existing = page.locator('[data-testid^="marker-region-sleep-"]').first();
  if (await existing.isVisible({ timeout: 2000 }).catch(() => false)) return;

  await navigateToCleanDate(page);
  await createSleepMarker(page, overlay);
}

/** Select the first sleep marker by clicking its list item (div.cursor-pointer with Main/Nap text) */
export async function selectFirstSleepMarker(page: Page) {
  // Marker items are div.cursor-pointer elements containing "Main" or "Nap" text
  const item = page.locator("div.cursor-pointer").filter({ hasText: /Main|Nap/i }).first();
  if (await item.isVisible({ timeout: 3000 })) {
    await item.click({ force: true });
    await page.waitForTimeout(1000);
  }
}

/** Select the first nonwear marker by clicking its list item (div.cursor-pointer with NW text) */
export async function selectFirstNonwearMarker(page: Page) {
  const item = page.locator("div.cursor-pointer").filter({ hasText: /NW \d+/ }).first();
  if (await item.isVisible({ timeout: 3000 })) {
    await item.click({ force: true });
    await page.waitForTimeout(1000);
  }
}

// =============================================================================
// MARKER LINES & DRAGGING
// =============================================================================

/** Get a sleep marker onset line */
export function getOnsetLine(page: Page) {
  return page.locator('[data-testid^="marker-line-sleep-"][data-testid$="-start"]').first();
}

/** Get a sleep marker offset line */
export function getOffsetLine(page: Page) {
  return page.locator('[data-testid^="marker-line-sleep-"][data-testid$="-end"]').first();
}

/** Drag a locator by dx pixels, returning mid-drag coords (mouse stays down) */
export async function dragElement(page: Page, el: Locator, dx: number, steps = 5) {
  const box = await el.boundingBox();
  expect(box).toBeTruthy();
  const sx = box!.x + box!.width / 2;
  const sy = box!.y + box!.height / 2;

  await page.mouse.move(sx, sy);
  await page.mouse.down();
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(sx + (dx * i) / steps, sy);
    await page.waitForTimeout(50);
  }
  return { startX: sx, startY: sy, endX: sx + dx };
}

// =============================================================================
// MODE & VIEW
// =============================================================================

/** Switch to Sleep mode (disables No Sleep first if active) */
export async function switchToSleepMode(page: Page) {
  // If "No Sleep" is active, the Sleep button is disabled — turn it off first
  const noSleepBtn = page.locator("button").filter({ hasText: /No Sleep/i }).first();
  if (await noSleepBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    // Check if No Sleep is active (bg-amber-600 class indicates active)
    const cls = (await noSleepBtn.getAttribute("class")) ?? "";
    if (cls.includes("bg-amber")) {
      await noSleepBtn.click();
      await page.waitForTimeout(300);
    }
  }

  const sleepBtn = page.locator("button").filter({ hasText: "Sleep" }).first();
  // Only click if not already the active mode (variant="default" vs "outline")
  if (await sleepBtn.isEnabled({ timeout: 1000 }).catch(() => false)) {
    const cls = (await sleepBtn.getAttribute("class")) ?? "";
    // If it has outline styling, it's not active — click to activate
    if (!cls.includes("bg-primary") || cls.includes("border-input")) {
      await sleepBtn.click();
      await page.waitForTimeout(300);
    }
  }
}

/** Switch to Nonwear mode */
export async function switchToNonwearMode(page: Page) {
  const btn = page.locator("button").filter({ hasText: "Nonwear" }).first();
  if (await btn.isEnabled({ timeout: 1000 }).catch(() => false)) {
    await btn.click();
    await page.waitForTimeout(300);
  }
}

/** Switch to No Sleep mode (accepts confirmation dialog if shown) */
export async function switchToNoSleepMode(page: Page) {
  page.once("dialog", (d) => d.accept());
  await page.locator("button").filter({ hasText: /No Sleep/i }).first().click();
  await page.waitForTimeout(500);
}

// =============================================================================
// SELECTORS & DROPDOWNS
// =============================================================================

/** Get file selector dropdown (first <select> on scoring page) */
export function fileSelector(page: Page) {
  return page.locator("select").filter({
    has: page.locator("option", { hasText: /\.csv/i }),
  }).first();
}

/** Get date selector dropdown (has options with date counter format like "(N/M)") */
export function dateSelector(page: Page) {
  // Date dropdown options contain "(N/M)" counter text - use this to disambiguate from other selects
  return page.locator("select").filter({ has: page.locator("option", { hasText: /\(\d+\/\d+\)/ }) }).first();
}

// =============================================================================
// COMMON ASSERTIONS
// =============================================================================

/** Assert that the page didn't crash (chart still visible) */
export async function assertPageHealthy(page: Page) {
  await expect(page.locator(".u-over").first()).toBeVisible({ timeout: 5000 });
}

/** Count sleep marker regions */
export async function sleepMarkerCount(page: Page): Promise<number> {
  return page.locator('[data-testid^="marker-region-sleep-"]').count();
}

/** Count nonwear marker regions */
export async function nonwearMarkerCount(page: Page): Promise<number> {
  return page.locator('[data-testid^="marker-region-nonwear-"]').count();
}
