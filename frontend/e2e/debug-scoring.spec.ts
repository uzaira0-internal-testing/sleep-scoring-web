import { test } from "@playwright/test";

test("login then capture localStorage, then reload", async ({ page }) => {
  const msgs: string[] = [];
  page.on("console", msg => msgs.push(`[${msg.type()}] ${msg.text()}`));
  page.on("pageerror", err => msgs.push(`[PAGE_ERROR] ${err.message}\n${err.stack}`));

  // Login normally first
  await page.goto("http://localhost:80/sleep-scoring/");
  await page.waitForTimeout(2000);
  const connectBtn = page.locator('text=Connect to Server');
  if (await connectBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await connectBtn.click();
    await page.waitForTimeout(1000);
  }
  const pw = page.locator('input[type="password"]');
  if (await pw.isVisible({ timeout: 3000 }).catch(() => false)) {
    await pw.fill("DACAdminTest123");
    const name = page.locator('input[placeholder*="audit" i]');
    if (await name.isVisible({ timeout: 1000 }).catch(() => false)) {
      await name.fill("testuser");
    }
    await page.locator('button:has-text("Continue")').click();
    await page.waitForTimeout(5000);
  }

  console.log("=== STEP 1: After login, URL ===", page.url());
  await page.screenshot({ path: "/tmp/debug-step1.png" });

  // Capture localStorage
  const ls = await page.evaluate(() => {
    const entries: Record<string, string> = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)!;
      entries[key] = localStorage.getItem(key)!;
    }
    return entries;
  });
  console.log("=== LOCALSTORAGE KEYS ===", Object.keys(ls));
  for (const [k, v] of Object.entries(ls)) {
    console.log(`  ${k}: ${v.slice(0, 200)}`);
  }

  // Now reload the page — this is the path that triggers the bug
  console.log("=== RELOADING PAGE ===");
  await page.reload();
  await page.waitForTimeout(8000);

  console.log("=== STEP 2: After reload, URL ===", page.url());
  await page.screenshot({ path: "/tmp/debug-step2.png" });

  console.log("=== ALL MESSAGES ===");
  for (const m of msgs) console.log(m);
});
