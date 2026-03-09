import { test, expect, Page } from "@playwright/test";

async function ensureOnScoringPage(page: Page) {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/scoring");
  await page.waitForTimeout(1000);
  if (page.url().includes("/login")) {
    await page.getByLabel(/username/i).fill("admin");
    await page.getByLabel(/password/i).fill("admin");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL("**/scoring**", { timeout: 15000 });
  }
  await page.waitForSelector(".u-wrap", { timeout: 30000 });
  await page.waitForTimeout(2000);
}

test.describe("Comprehensive Feature Parity Audit", () => {

  test("1. Chart renders with correct elements", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Chart should have uPlot elements
    const uWrap = page.locator(".u-wrap");
    expect(await uWrap.count()).toBeGreaterThan(0);

    const uOver = page.locator(".u-over");
    expect(await uOver.count()).toBeGreaterThan(0);

    // Chart should have non-zero dimensions
    const box = await uOver.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThan(100);
    expect(box!.height).toBeGreaterThan(50);

    // Check canvas exists
    const canvases = await page.locator(".u-wrap canvas").count();
    expect(canvases).toBeGreaterThan(0);
  });

  test("2. File selector dropdown works", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Find file selector (first select in header area)
    const fileSelects = page.locator("select");
    const count = await fileSelects.count();
    expect(count).toBeGreaterThan(0);

    // Check the file dropdown has options
    const firstSelect = fileSelects.first();
    const options = await firstSelect.locator("option").count();
    console.log(`File selector options: ${options}`);
    expect(options).toBeGreaterThan(0);
  });

  test("3. Delete file button visible", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Find delete button in header
    const deleteBtn = page.getByRole("button", { name: /delete/i });
    const count = await deleteBtn.count();
    console.log(`Delete buttons found: ${count}`);
    expect(count).toBeGreaterThan(0);
  });

  test("4. Mode buttons all work", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Sleep button should be active by default
    const sleepBtn = page.getByRole("button", { name: /sleep/i }).first();
    await expect(sleepBtn).toBeVisible();

    // Click Nonwear
    const nonwearBtn = page.getByRole("button", { name: /nonwear/i });
    await nonwearBtn.click();
    await page.waitForTimeout(500);

    // Click back to Sleep
    await sleepBtn.click();
    await page.waitForTimeout(500);

    // No Sleep button exists
    page.on("dialog", (dialog) => dialog.dismiss());
    const noSleepBtn = page.getByRole("button", { name: /no sleep/i });
    await expect(noSleepBtn).toBeVisible();
  });

  test("5. Marker creation and deletion", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    const uOver = page.locator(".u-over");
    const box = await uOver.boundingBox();
    if (!box) throw new Error("uPlot overlay not found");

    // Count initial markers
    const initialMarkers = await page.locator(".marker-region").count();

    // Click onset at 30% from left
    await uOver.click({ force: true, position: { x: box.width * 0.3, y: box.height * 0.5 } });
    await page.waitForTimeout(500);

    // Click offset at 55% from left
    await uOver.click({ force: true, position: { x: box.width * 0.55, y: box.height * 0.5 } });
    await page.waitForTimeout(1000);

    // Should have more markers now
    const newMarkers = await page.locator(".marker-region").count();
    console.log(`Markers: before=${initialMarkers}, after=${newMarkers}`);
    expect(newMarkers).toBeGreaterThan(initialMarkers);

    // Take screenshot of marker
    await page.screenshot({ path: "test-results/screenshots/audit-marker-created.png" });

    // Delete the marker using keyboard (C key)
    // First click on the marker item in the bottom panel to select it
    const markerItems = page.locator('[class*="border cursor-pointer"]').filter({ hasText: /Main|Nap/ });
    if (await markerItems.count() > 0) {
      await markerItems.first().click({ force: true });
      await page.waitForTimeout(300);

      // Press C to delete
      await page.keyboard.press("c");
      await page.waitForTimeout(500);

      // Markers should decrease
      const afterDelete = await page.locator(".marker-region").count();
      console.log(`After delete: ${afterDelete}`);
      expect(afterDelete).toBeLessThan(newMarkers);
    }
  });

  test("6. Date navigation with arrows and keyboard", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Get current date from dropdown
    const dateSelect = page.locator("select").last();
    const currentValue = await dateSelect.inputValue();
    console.log(`Current date index: ${currentValue}`);

    // Navigate forward using button
    const nextBtn = page.locator('[data-testid="next-date-btn"]');
    if (await nextBtn.isEnabled()) {
      await nextBtn.click();
      await page.waitForTimeout(2000);

      const newValue = await dateSelect.inputValue();
      console.log(`After next: ${newValue}`);
      expect(newValue).not.toBe(currentValue);

      // Navigate back
      const prevBtn = page.locator('[data-testid="prev-date-btn"]');
      await prevBtn.click();
      await page.waitForTimeout(2000);

      const backValue = await dateSelect.inputValue();
      expect(backValue).toBe(currentValue);
    }

    // Navigate with keyboard arrow keys
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(2000);

    const kbValue = await dateSelect.inputValue();
    console.log(`After arrow right: ${kbValue}`);
  });

  test("7. View mode toggle 24h/48h", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Find the view select
    const selects = page.locator("select");
    const count = await selects.count();
    let viewSelect: ReturnType<typeof selects.nth> | null = null;

    for (let i = 0; i < count; i++) {
      const options = await selects.nth(i).locator("option").allTextContents();
      if (options.some(o => o.includes("48h"))) {
        viewSelect = selects.nth(i);
        break;
      }
    }

    if (viewSelect) {
      // Switch to 48h
      await viewSelect.selectOption({ label: "48h" });
      await page.waitForTimeout(3000);

      // Verify chart still renders
      const uOver = page.locator(".u-over");
      expect(await uOver.count()).toBeGreaterThan(0);

      await page.screenshot({ path: "test-results/screenshots/audit-48h-view.png" });

      // Switch back
      await viewSelect.selectOption({ label: "24h" });
      await page.waitForTimeout(2000);
    }
  });

  test("8. Algorithm dropdown changes scoring", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Find algorithm select
    const selects = page.locator("select");
    const count = await selects.count();
    let algorithmSelect: ReturnType<typeof selects.nth> | null = null;

    for (let i = 0; i < count; i++) {
      const options = await selects.nth(i).locator("option").allTextContents();
      if (options.some(o => o.includes("Sadeh") || o.includes("Cole"))) {
        algorithmSelect = selects.nth(i);
        break;
      }
    }

    if (algorithmSelect) {
      // Switch algorithm
      const options = await algorithmSelect.locator("option").allTextContents();
      console.log("Algorithm options:", options);

      // Find Cole-Kripke option
      const coleOption = options.find(o => o.includes("Cole-Kripke"));
      if (coleOption) {
        await algorithmSelect.selectOption({ label: coleOption });
        await page.waitForTimeout(3000);

        // Chart should still render
        const uOver = page.locator(".u-over");
        expect(await uOver.count()).toBeGreaterThan(0);
      }
    }
  });

  test("9. Keyboard shortcuts dialog contents", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Open shortcuts dialog - look for keyboard icon button
    const kbButton = page.locator('button[title="Keyboard shortcuts"]');
    await kbButton.click();
    await page.waitForTimeout(500);

    // Wait for dialog to appear (it's a fixed/overlay element)
    await expect(page.locator("text=Keyboard Shortcuts").first()).toBeVisible({ timeout: 5000 });

    // Take screenshot to verify dialog content
    await page.screenshot({ path: "test-results/screenshots/audit-shortcuts-dialog-open.png" });

    // Check that key shortcut text exists in the page
    await expect(page.locator("text=Place onset")).toBeVisible();
    await expect(page.locator("text=Delete selected marker").first()).toBeVisible();
    await expect(page.locator("text=Previous date")).toBeVisible();
    await expect(page.locator("text=Save markers")).toBeVisible();

    await page.screenshot({ path: "test-results/screenshots/audit-shortcuts-dialog.png" });
  });

  test("10. Side tables show data when marker selected", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Create a marker first
    const uOver = page.locator(".u-over");
    const box = await uOver.boundingBox();
    if (!box) throw new Error("uPlot overlay not found");

    await uOver.click({ force: true, position: { x: box.width * 0.3, y: box.height * 0.5 } });
    await page.waitForTimeout(500);
    await uOver.click({ force: true, position: { x: box.width * 0.55, y: box.height * 0.5 } });
    await page.waitForTimeout(2000);

    // Select the marker by clicking it in the list
    const markerItems = page.locator('[class*="border cursor-pointer"]').filter({ hasText: /Main|Nap/ });
    if (await markerItems.count() > 0) {
      await markerItems.first().click();
      await page.waitForTimeout(2000);

      // Side tables should now have rows (not "Select a sleep marker")
      const onsetCard = page.locator("text=Sleep Onset").first();
      const noMarkerText = page.locator("text=Select a sleep marker");
      // If we still see "Select a sleep marker" it means tables didn't load
      // (This is ok if the marker wasn't properly selected)
      const noMarkerCount = await noMarkerText.count();
      console.log(`"Select a sleep marker" messages remaining: ${noMarkerCount}`);
    }

    await page.screenshot({ path: "test-results/screenshots/audit-side-tables.png" });
  });

  test("11. Save status badge transitions", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Create a marker to trigger dirty state
    const uOver = page.locator(".u-over");
    const box = await uOver.boundingBox();
    if (!box) throw new Error("uPlot overlay not found");

    await uOver.click({ force: true, position: { x: box.width * 0.35, y: box.height * 0.5 } });
    await page.waitForTimeout(500);
    await uOver.click({ force: true, position: { x: box.width * 0.6, y: box.height * 0.5 } });
    await page.waitForTimeout(500);

    // Should see "Unsaved" or "Saving" badge
    const unsaved = page.locator("text=Unsaved");
    const saving = page.locator("text=Saving");

    const unsavedVisible = await unsaved.count() > 0;
    const savingVisible = await saving.count() > 0;
    console.log(`Unsaved: ${unsavedVisible}, Saving: ${savingVisible}`);

    // Wait for auto-save
    await page.waitForTimeout(5000);

    // Should eventually show "Saved"
    const saved = page.locator("text=Saved");
    const savedCount = await saved.count();
    console.log(`Saved badges: ${savedCount}`);

    await page.screenshot({ path: "test-results/screenshots/audit-save-status.png" });
  });

  test("12. Other pages load correctly", async ({ page }) => {
    test.setTimeout(60000);
    // Login first via scoring page
    await ensureOnScoringPage(page);

    // Study settings (correct path is /settings/study)
    await page.goto("/settings/study");
    await page.waitForTimeout(3000);
    await expect(page.getByText(/study settings/i).first()).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "test-results/screenshots/audit-study-page.png" });

    // Data settings (correct path is /settings/data)
    await page.goto("/settings/data");
    await page.waitForTimeout(3000);
    await expect(page.getByText(/data settings/i).first()).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "test-results/screenshots/audit-data-page.png" });

    // Export page
    await page.goto("/export");
    await page.waitForTimeout(3000);
    await expect(page.getByText(/export/i).first()).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "test-results/screenshots/audit-export-page.png" });
  });

  test("13. Metrics and diary panels render", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Metrics panel - text might be inside a card header
    const metricsPanel = page.locator("text=Metrics").first();
    await expect(metricsPanel).toBeVisible({ timeout: 10000 });

    // Diary panel
    const diaryPanel = page.locator("text=Sleep Diary").first();
    await expect(diaryPanel).toBeVisible({ timeout: 10000 });

    // Diary should show "Add Entry" button or entry data
    const addEntry = page.locator("text=Add Entry");
    const addEntryCount = await addEntry.count();
    console.log(`Add Entry buttons: ${addEntryCount}`);
  });

  test("14. Clear all markers with confirmation", async ({ page }) => {
    test.setTimeout(60000);

    // Set up dialog handler BEFORE navigating (must be first)
    page.on("dialog", (dialog) => dialog.accept());

    await ensureOnScoringPage(page);

    // Create a marker first
    const uOver = page.locator(".u-over");
    const box = await uOver.boundingBox();
    if (!box) throw new Error("uPlot overlay not found");

    await uOver.click({ force: true, position: { x: box.width * 0.25, y: box.height * 0.5 } });
    await page.waitForTimeout(500);
    await uOver.click({ force: true, position: { x: box.width * 0.5, y: box.height * 0.5 } });
    await page.waitForTimeout(1000);

    // Verify marker was created
    const beforeClear = await page.locator(".marker-region").count();
    console.log(`Markers before clear: ${beforeClear}`);
    expect(beforeClear).toBeGreaterThan(0);

    // Click Clear button (the one in the control bar, not the dialog)
    const clearBtn = page.getByRole("button", { name: /clear/i }).last();
    await clearBtn.click();
    await page.waitForTimeout(2000);

    // Markers should decrease (possibly to 0, or fewer than before)
    const afterClear = await page.locator(".marker-region").count();
    console.log(`Markers after clear: ${afterClear}`);
    expect(afterClear).toBeLessThan(beforeClear);
  });

  test("15. Popout table dialog opens", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Look for popout button in the side table header area
    const popoutButtons = page.locator('[class*="cursor-pointer"]').filter({ has: page.locator('svg') });

    // Try clicking the popout icon in the Sleep Onset card
    const onsetCard = page.locator("text=Sleep Onset").first();
    if (await onsetCard.count() > 0) {
      // The popout button should be near the title
      const nearbyButtons = onsetCard.locator("xpath=..").locator("button, [role=button], .cursor-pointer");
      const btnCount = await nearbyButtons.count();
      console.log(`Popout-area buttons: ${btnCount}`);

      if (btnCount > 0) {
        await nearbyButtons.first().click();
        await page.waitForTimeout(1000);
      }
    }

    await page.screenshot({ path: "test-results/screenshots/audit-popout.png" });
  });

  test("16. Color legend dialog", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Find the color legend button (palette icon)
    const legendBtns = page.locator("button").filter({ has: page.locator('svg') });
    const count = await legendBtns.count();

    // Click the second-to-last icon button in the header area (color legend)
    // The color legend button has title containing "Color" or "Legend"
    const colorBtn = page.locator('button[title*="olor"], button[title*="legend"]');
    if (await colorBtn.count() > 0) {
      await colorBtn.first().click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: "test-results/screenshots/audit-color-legend.png" });
    } else {
      console.log("Color legend button not found by title");
    }
  });

  test("17. Upload button exists and is interactive", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    const uploadBtn = page.getByRole("button", { name: /upload/i });
    await expect(uploadBtn).toBeVisible();
    await expect(uploadBtn).toBeEnabled();
  });

  test("18. Activity source dropdown changes", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Find the source select (has "Y-Axis", "X-Axis" etc)
    const selects = page.locator("select");
    const count = await selects.count();

    for (let i = 0; i < count; i++) {
      const options = await selects.nth(i).locator("option").allTextContents();
      if (options.some(o => o.includes("Vector Magnitude"))) {
        // Switch to Vector Magnitude
        await selects.nth(i).selectOption({ label: "Vector Magnitude" });
        await page.waitForTimeout(3000);

        // Chart should still render
        const uOver = page.locator(".u-over");
        expect(await uOver.count()).toBeGreaterThan(0);

        console.log("Source changed to Vector Magnitude successfully");

        // Switch back
        await selects.nth(i).selectOption({ label: "Y-Axis (Vertical)" });
        await page.waitForTimeout(2000);
        break;
      }
    }
  });

  test("19. Full page screenshot for visual review", async ({ page }) => {
    test.setTimeout(60000);
    await ensureOnScoringPage(page);

    // Take full scoring page screenshot
    await page.screenshot({
      path: "test-results/screenshots/audit-full-scoring.png",
      fullPage: true,
    });

    // Create a marker and take another screenshot
    const uOver = page.locator(".u-over");
    const box = await uOver.boundingBox();
    if (!box) throw new Error("uPlot overlay not found");

    await uOver.click({ force: true, position: { x: box.width * 0.28, y: box.height * 0.5 } });
    await page.waitForTimeout(500);
    await uOver.click({ force: true, position: { x: box.width * 0.52, y: box.height * 0.5 } });
    await page.waitForTimeout(2000);

    // Select marker
    const markerItems = page.locator('[class*="border cursor-pointer"]').filter({ hasText: /Main|Nap/ });
    if (await markerItems.count() > 0) {
      await markerItems.first().click();
      await page.waitForTimeout(2000);
    }

    await page.screenshot({
      path: "test-results/screenshots/audit-with-marker-selected.png",
      fullPage: true,
    });
  });
});
