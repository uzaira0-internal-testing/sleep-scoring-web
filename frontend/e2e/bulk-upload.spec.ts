import { test, expect } from "@playwright/test";
import { loginAndGoTo } from "./helpers";
import * as fs from "fs";
import * as path from "path";

const CSV_ROOT =
  "W:\\Projects\\TECH Study\\Data\\Accelerometer Data\\Duplicate for Sleep Scoring\\60s csv Files";

function collectCsvFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectCsvFiles(full));
    } else if (entry.name.startsWith("P1-") && entry.name.endsWith(".csv")) {
      results.push(full);
    }
  }
  return results;
}

test("bulk upload all CSVs from 60s csv folder", async ({ page }) => {
  // 239 files across 5 scorer folders, ~1MB each
  test.setTimeout(1_800_000); // 30 minutes

  const filePaths = collectCsvFiles(CSV_ROOT);
  console.log(`Found ${filePaths.length} CSV files to upload`);
  expect(filePaths.length).toBeGreaterThan(0);

  // Login and go to data settings
  await loginAndGoTo(page, "/settings/data");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1000);

  // Enable "Replace existing" toggle if available
  const replaceSwitch = page.locator('button[role="switch"]').first();
  if (await replaceSwitch.isVisible({ timeout: 3000 }).catch(() => false)) {
    const checked = await replaceSwitch.getAttribute("aria-checked");
    if (checked !== "true") {
      await replaceSwitch.click();
      await page.waitForTimeout(300);
    }
  }

  // Set all files on the hidden multi-file input
  // This is the first input[type="file"][multiple] — the "Upload Files" button's input
  const fileInput = page.locator('input[type="file"][multiple]').first();
  await expect(fileInput).toBeAttached();

  console.log(`Setting ${filePaths.length} files on input...`);
  await fileInput.setInputFiles(filePaths);

  // The UI uploads files sequentially, showing "Uploading X/N: filename" progress
  // Wait for the progress text to appear first
  await page.waitForFunction(
    () => document.body.textContent?.includes("Uploading"),
    { timeout: 30_000 },
  );
  console.log("Upload started...");

  // Now wait for all uploads to finish (progress text disappears)
  await page.waitForFunction(
    () => !document.body.textContent?.includes("Uploading"),
    { timeout: 540_000 },
  );
  console.log("Upload finished!");

  await page.waitForTimeout(2000);

  // Log the result
  const bodyText = await page.textContent("body");
  const uploadedMatch = bodyText?.match(/Uploaded (\d+)/);
  const failedMatch = bodyText?.match(/(\d+) failed/);
  console.log(`Result: Uploaded=${uploadedMatch?.[1] ?? "?"}, Failed=${failedMatch?.[1] ?? "0"}`);

  // Verify at least some files uploaded successfully
  if (uploadedMatch) {
    expect(Number(uploadedMatch[1])).toBeGreaterThan(0);
  }

  // Navigate to scoring and verify files exist
  await page.goto("/scoring");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2000);

  const fileSelect = page.locator("select").first();
  if (await fileSelect.isVisible({ timeout: 5000 }).catch(() => false)) {
    const options = await fileSelect.locator("option").count();
    console.log(`File selector has ${options} options after upload`);
    expect(options).toBeGreaterThan(0);
  }
});
