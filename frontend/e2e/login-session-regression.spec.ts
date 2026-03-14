import { test, expect } from "@playwright/test";

/**
 * Login & session persistence regression tests.
 *
 * These tests verify the authentication flow, session persistence across
 * navigation and page reloads, and that API calls include the expected
 * auth headers (X-Site-Password, X-Username).
 *
 * Prerequisites:
 *   - Docker stack running (`cd docker && docker compose -f docker-compose.local.yml up -d`)
 *   - Frontend at http://localhost:8501, backend at http://localhost:8500
 */

test.describe("Login & Session", () => {
  test.beforeEach(async ({ page, context }) => {
    // Clear all stored state so each test starts unauthenticated
    await context.clearCookies();
    await page.goto("/login");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  // -------------------------------------------------------------------------
  // 1. Unauthenticated redirect
  // -------------------------------------------------------------------------
  test("redirects unauthenticated user from /scoring to /login", async ({
    page,
  }) => {
    await page.goto("/scoring");
    // ProtectedRoute should redirect to /login when not authenticated
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });

  // -------------------------------------------------------------------------
  // 2. Successful login → redirect to /scoring
  // -------------------------------------------------------------------------
  test("successful login redirects to /scoring", async ({ page }) => {
    await page.goto("/login");
    // Wait for the login form to be ready (phase transitions from "loading")
    await page.waitForSelector('input[name="username"]', { timeout: 15_000 });

    // Fill in password if the field is visible (server has auth enabled)
    const passwordInput = page.locator('input[name="password"]');
    if ((await passwordInput.count()) > 0 && (await passwordInput.isVisible())) {
      await passwordInput.fill("admin");
    }

    // Fill username
    await page.locator('input[name="username"]').fill("admin");

    // Submit
    await page.locator('button[type="submit"]').click();

    // Should navigate to /scoring after login
    await expect(page).toHaveURL(/\/scoring/, { timeout: 15_000 });
  });

  // -------------------------------------------------------------------------
  // 3. Username displayed in sidebar after login
  // -------------------------------------------------------------------------
  test("username is displayed in sidebar after login", async ({ page }) => {
    await page.goto("/login");
    await page.waitForSelector('input[name="username"]', { timeout: 15_000 });

    const passwordInput = page.locator('input[name="password"]');
    if ((await passwordInput.count()) > 0 && (await passwordInput.isVisible())) {
      await passwordInput.fill("admin");
    }

    await page.locator('input[name="username"]').fill("TestUser");
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/scoring/, { timeout: 15_000 });

    // The layout sidebar shows the username — look for it in the page
    await expect(page.getByText("TestUser")).toBeVisible({ timeout: 10_000 });
  });

  // -------------------------------------------------------------------------
  // 4. Session persists across page reload
  // -------------------------------------------------------------------------
  test("session persists across page reload", async ({ page }) => {
    // Login first
    await page.goto("/login");
    await page.waitForSelector('input[name="username"]', { timeout: 15_000 });

    const passwordInput = page.locator('input[name="password"]');
    if ((await passwordInput.count()) > 0 && (await passwordInput.isVisible())) {
      await passwordInput.fill("admin");
    }

    await page.locator('input[name="username"]').fill("PersistUser");
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/scoring/, { timeout: 15_000 });

    // Reload the page
    await page.reload();

    // Should still be on /scoring (not redirected to /login)
    await expect(page).toHaveURL(/\/scoring/, { timeout: 15_000 });

    // Username should still be visible after reload
    await expect(page.getByText("PersistUser")).toBeVisible({ timeout: 10_000 });
  });

  // -------------------------------------------------------------------------
  // 5. Navigate scoring → analysis → scoring without re-login
  // -------------------------------------------------------------------------
  test("navigates between pages without re-login", async ({ page }) => {
    // Login
    await page.goto("/login");
    await page.waitForSelector('input[name="username"]', { timeout: 15_000 });

    const passwordInput = page.locator('input[name="password"]');
    if ((await passwordInput.count()) > 0 && (await passwordInput.isVisible())) {
      await passwordInput.fill("admin");
    }

    await page.locator('input[name="username"]').fill("NavUser");
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/scoring/, { timeout: 15_000 });

    // Navigate to /analysis via the sidebar link
    await page.getByRole("link", { name: /analysis/i }).click();
    await expect(page).toHaveURL(/\/analysis/, { timeout: 10_000 });
    // Should NOT be on /login
    await expect(page).not.toHaveURL(/\/login/);

    // Navigate back to /scoring via the sidebar link
    await page.getByRole("link", { name: /scoring/i }).click();
    await expect(page).toHaveURL(/\/scoring/, { timeout: 10_000 });
    await expect(page).not.toHaveURL(/\/login/);

    // Username persists throughout navigation
    await expect(page.getByText("NavUser")).toBeVisible({ timeout: 5_000 });
  });

  // -------------------------------------------------------------------------
  // 6. File selector shows files (not empty) after login
  // -------------------------------------------------------------------------
  test("file selector shows files after login", async ({ page }) => {
    // Login
    await page.goto("/login");
    await page.waitForSelector('input[name="username"]', { timeout: 15_000 });

    const passwordInput = page.locator('input[name="password"]');
    if ((await passwordInput.count()) > 0 && (await passwordInput.isVisible())) {
      await passwordInput.fill("admin");
    }

    await page.locator('input[name="username"]').fill("admin");
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/scoring/, { timeout: 15_000 });

    // Wait for the scoring page to fully load (chart or file selector)
    // The file selector is a <select> element containing <option> elements with .csv names
    const fileSelect = page
      .locator("select")
      .filter({ has: page.locator("option", { hasText: /\.csv/i }) })
      .first();

    // Wait for the file selector to appear and have options
    await expect(fileSelect).toBeVisible({ timeout: 30_000 });

    // Count options (excluding any placeholder "Select a file" option)
    const optionCount = await fileSelect.locator("option").count();
    // There should be at least one file option (the placeholder + at least 1 file)
    expect(optionCount).toBeGreaterThanOrEqual(1);
  });

  // -------------------------------------------------------------------------
  // 7. API calls include auth headers
  // -------------------------------------------------------------------------
  test("API calls include auth headers after login", async ({ page }) => {
    // Login
    await page.goto("/login");
    await page.waitForSelector('input[name="username"]', { timeout: 15_000 });

    const passwordInput = page.locator('input[name="password"]');
    if ((await passwordInput.count()) > 0 && (await passwordInput.isVisible())) {
      await passwordInput.fill("admin");
    }

    await page.locator('input[name="username"]').fill("HeaderTestUser");
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/scoring/, { timeout: 15_000 });

    // Set up request interception to capture API calls
    const capturedHeaders: Record<string, string>[] = [];

    page.on("request", (request) => {
      const url = request.url();
      // Capture headers from API calls to the backend (port 8500 or /api/ paths)
      if (url.includes("/api/") || url.includes(":8500")) {
        const headers = request.headers();
        capturedHeaders.push({
          url,
          "x-username": headers["x-username"] ?? "",
          "x-site-password": headers["x-site-password"] ?? "",
        });
      }
    });

    // Trigger an API call by reloading or navigating
    await page.reload();
    await page.waitForTimeout(3_000);

    // At least one API call should have been made
    expect(capturedHeaders.length).toBeGreaterThan(0);

    // All captured API requests should include the X-Username header
    for (const entry of capturedHeaders) {
      expect(entry["x-username"]).toBeTruthy();
      expect(entry["x-username"]).toBe("HeaderTestUser");
    }
  });
});
