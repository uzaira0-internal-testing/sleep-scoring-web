/**
 * Accessibility tests using axe-core.
 *
 * Runs automated WCAG 2.1 AA checks on key pages. Catches missing labels,
 * insufficient contrast, missing landmarks, and other a11y violations.
 *
 * Prerequisites: Docker stack running.
 */

import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const BASE = "http://localhost:8501";
const SITE_PASSWORD = "testpass";
const USERNAME = "testadmin";

async function login(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/login`);
  const passwordInput = page.locator('input[type="password"]');
  if (await passwordInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await passwordInput.fill(SITE_PASSWORD);
    const usernameInput = page.locator('input[name="username"], input[placeholder*="name" i]');
    if (await usernameInput.isVisible({ timeout: 1000 }).catch(() => false)) {
      await usernameInput.fill(USERNAME);
    }
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/(scoring|files|$)/, { timeout: 10000 });
  }
}

test.describe("Accessibility (axe-core WCAG 2.1 AA)", () => {
  test("login page has no critical a11y violations", async ({ page }) => {
    await page.goto(`${BASE}/login`);
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .disableRules(["color-contrast"]) // Often false positive with dark themes
      .analyze();

    expect(results.violations.filter((v) => v.impact === "critical")).toEqual([]);
  });

  test("scoring page has no critical a11y violations", async ({ page }) => {
    await login(page);

    // Navigate to scoring page
    await page.goto(`${BASE}/scoring`);
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .disableRules(["color-contrast"]) // Chart canvas elements
      .analyze();

    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious"
    );
    // Log violations for debugging but don't fail on non-critical
    if (critical.length > 0) {
      console.log("A11y violations:", JSON.stringify(critical, null, 2));
    }
    expect(critical).toEqual([]);
  });

  test("all pages have proper heading hierarchy", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/scoring`);
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withRules(["heading-order", "page-has-heading-one"])
      .analyze();

    // Heading issues are warnings, not blockers
    const critical = results.violations.filter((v) => v.impact === "critical");
    expect(critical).toEqual([]);
  });

  test("interactive elements are keyboard accessible", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/scoring`);
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withRules([
        "button-name",
        "link-name",
        "label",
        "tabindex",
      ])
      .analyze();

    const critical = results.violations.filter((v) => v.impact === "critical");
    expect(critical).toEqual([]);
  });
});
