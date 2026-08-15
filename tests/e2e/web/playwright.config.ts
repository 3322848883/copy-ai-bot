import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  retries: 0, // 避免 retry 翻倍触发 /v1/auth/ 限流（10 次/分/IP）
  globalSetup: "./global-setup.ts",
  reporter: [["list"], ["html", { outputFolder: "../reports/playwright-report" }]],
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
});
