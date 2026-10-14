import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 60000,
  globalSetup: "./e2e/setup.ts",
  globalTeardown: "./e2e/teardown.ts",
  use: {
    baseURL: "https://localhost:3010",
    ignoreHTTPSErrors: true,
    trace: "off",
    screenshot: "off",
  },
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
});
