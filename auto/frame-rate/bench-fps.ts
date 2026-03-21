/**
 * Playwright-based frame rate benchmark.
 * Measures FPS during key interactions on the scoring page with real data.
 * Outputs METRIC fps_p10=XX (10th percentile — worst-case frames).
 *
 * Prerequisites:
 *   - Backend running at localhost:8500, frontend at localhost:8501
 *   - File id=378 assigned to user "benchuser" with password "DACAdminTest123"
 *
 * Usage: cd frontend && npx playwright test ../auto/frame-rate/bench-fps.ts --reporter=list
 */
import { test, expect, type Page } from "@playwright/test";

const SITE_PASSWORD = "DACAdminTest123";
const USERNAME = "benchuser";

// Inject rAF-based frame counter
const FPS_COLLECTOR = `
  window.__fps_frames = [];
  window.__fps_running = true;
  (function loop() {
    if (!window.__fps_running) return;
    window.__fps_frames.push(performance.now());
    requestAnimationFrame(loop);
  })();
`;

const FPS_STOP = `
  window.__fps_running = false;
  (() => {
    const frames = window.__fps_frames;
    if (frames.length < 2) return { fps_avg: 0, fps_p10: 0, fps_min: 0, frame_count: 0, dropped: 0 };
    const deltas = [];
    for (let i = 1; i < frames.length; i++) deltas.push(frames[i] - frames[i - 1]);
    deltas.sort((a, b) => a - b);
    const toFps = (ms) => ms > 0 ? 1000 / ms : 0;
    const avg = deltas.reduce((s, d) => s + d, 0) / deltas.length;
    const p90_delta = deltas[Math.floor(deltas.length * 0.9)];
    const max_delta = deltas[deltas.length - 1];
    return {
      fps_avg: Math.round(toFps(avg)),
      fps_p10: Math.round(toFps(p90_delta)),
      fps_min: Math.round(toFps(max_delta)),
      frame_count: frames.length,
      dropped: deltas.filter(d => d > 33.33).length,
    };
  })();
`;

async function login(page: Page) {
  await page.goto("http://localhost:8501");
  await page.waitForLoadState("networkidle");

  // Enter password if login page shown
  const passwordInput = page.locator('input[type="password"]');
  if (await passwordInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await passwordInput.fill(SITE_PASSWORD);
    const usernameInput = page.locator('input[name="username"], input[placeholder*="username" i]');
    if (await usernameInput.isVisible({ timeout: 1000 }).catch(() => false)) {
      await usernameInput.fill(USERNAME);
    }
    await page.locator('button[type="submit"]').click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
  }
}

async function navigateToScoringWithFile(page: Page) {
  await page.goto("http://localhost:8501/scoring");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1000);

  // Select the demo file if file selector is visible
  const fileSelect = page.locator('[data-testid="file-select"], select, [role="combobox"]').first();
  if (await fileSelect.isVisible({ timeout: 2000 }).catch(() => false)) {
    await fileSelect.click();
    // Look for the demo file option
    const option = page.locator('text=DEMO-001').first();
    if (await option.isVisible({ timeout: 2000 }).catch(() => false)) {
      await option.click();
    }
  }

  // Wait for chart to render
  await page.waitForTimeout(3000);
}

async function waitForChart(page: Page): Promise<{ x: number; y: number; width: number; height: number } | null> {
  const chart = page.locator(".uplot, canvas, [data-testid='activity-chart']").first();
  if (!(await chart.isVisible({ timeout: 5000 }).catch(() => false))) {
    return null;
  }
  const box = await chart.boundingBox();
  return box;
}

test.describe("FPS Benchmarks with Real Data", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("pan/drag across chart", async ({ page }) => {
    await navigateToScoringWithFile(page);
    const box = await waitForChart(page);
    if (!box) {
      console.log("METRIC drag_fps_p10=0");
      console.log("SKIP: No chart visible");
      return;
    }

    const startX = box.x + box.width * 0.2;
    const endX = box.x + box.width * 0.8;
    const y = box.y + box.height / 2;

    await page.evaluate(FPS_COLLECTOR);

    // Simulate slow drag across the chart
    await page.mouse.move(startX, y);
    await page.mouse.down();
    const steps = 60; // 60 frames of drag
    for (let i = 0; i <= steps; i++) {
      const x = startX + (endX - startX) * (i / steps);
      await page.mouse.move(x, y);
      await page.waitForTimeout(16); // ~60fps pacing
    }
    await page.mouse.up();
    await page.waitForTimeout(500);

    const result = await page.evaluate(FPS_STOP) as any;
    console.log(`METRIC drag_fps_avg=${result.fps_avg}`);
    console.log(`METRIC drag_fps_p10=${result.fps_p10}`);
    console.log(`METRIC drag_fps_min=${result.fps_min}`);
    console.log(`METRIC drag_dropped=${result.dropped}`);
    console.log(`METRIC drag_frames=${result.frame_count}`);
  });

  test("zoom in and out on chart", async ({ page }) => {
    await navigateToScoringWithFile(page);
    const box = await waitForChart(page);
    if (!box) {
      console.log("METRIC zoom_fps_p10=0");
      console.log("SKIP: No chart visible");
      return;
    }

    // Position mouse at center of chart
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.evaluate(FPS_COLLECTOR);

    // Rapid zoom in
    for (let i = 0; i < 15; i++) {
      await page.mouse.wheel(0, -120);
      await page.waitForTimeout(32);
    }
    // Rapid zoom out
    for (let i = 0; i < 15; i++) {
      await page.mouse.wheel(0, 120);
      await page.waitForTimeout(32);
    }
    await page.waitForTimeout(500);

    const result = await page.evaluate(FPS_STOP) as any;
    console.log(`METRIC zoom_fps_avg=${result.fps_avg}`);
    console.log(`METRIC zoom_fps_p10=${result.fps_p10}`);
    console.log(`METRIC zoom_fps_min=${result.fps_min}`);
    console.log(`METRIC zoom_dropped=${result.dropped}`);
    console.log(`METRIC zoom_frames=${result.frame_count}`);
  });

  test("rapid mouse movement over chart (hover)", async ({ page }) => {
    await navigateToScoringWithFile(page);
    const box = await waitForChart(page);
    if (!box) {
      console.log("METRIC hover_fps_p10=0");
      console.log("SKIP: No chart visible");
      return;
    }

    await page.evaluate(FPS_COLLECTOR);

    // Move mouse rapidly across chart (simulates cursor tracking)
    for (let i = 0; i < 100; i++) {
      const x = box.x + (box.width * (i / 100));
      const y = box.y + box.height / 2 + Math.sin(i * 0.3) * 30;
      await page.mouse.move(x, y);
      await page.waitForTimeout(8); // 125fps pacing
    }
    await page.waitForTimeout(500);

    const result = await page.evaluate(FPS_STOP) as any;
    console.log(`METRIC hover_fps_avg=${result.fps_avg}`);
    console.log(`METRIC hover_fps_p10=${result.fps_p10}`);
    console.log(`METRIC hover_fps_min=${result.fps_min}`);
    console.log(`METRIC hover_dropped=${result.dropped}`);
    console.log(`METRIC hover_frames=${result.frame_count}`);
  });

  test("page navigation between dates", async ({ page }) => {
    await navigateToScoringWithFile(page);

    await page.evaluate(FPS_COLLECTOR);

    // Click next/prev date buttons if available
    const nextBtn = page.locator('[data-testid="next-date"], button:has-text("Next"), [aria-label*="next" i]').first();
    if (await nextBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      for (let i = 0; i < 5; i++) {
        await nextBtn.click();
        await page.waitForTimeout(200);
      }
    }

    await page.waitForTimeout(500);
    const result = await page.evaluate(FPS_STOP) as any;
    console.log(`METRIC nav_fps_avg=${result.fps_avg}`);
    console.log(`METRIC nav_fps_p10=${result.fps_p10}`);
    console.log(`METRIC nav_fps_min=${result.fps_min}`);
    console.log(`METRIC nav_dropped=${result.dropped}`);
  });
});
