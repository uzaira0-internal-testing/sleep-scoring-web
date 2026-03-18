import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 60000,
  use: {
    baseURL: "http://localhost:8501",
    headless: true,
    viewport: { width: 1920, height: 1080 },
  },
});
