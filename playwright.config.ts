import { defineConfig, devices } from "@playwright/test";

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
require("dotenv").config({ path: ".env" });

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: "./apps/web/playwright",
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Timeout for each test */
  timeout: 120000,
  /* Fail the test run after the first N failures */
  maxFailures: process.env.CI ? undefined : 10,
  /* Opt out of parallel tests on CI. */
  // workers: os.cpus().length,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }]],
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: "on-first-retry",
    screenshot: "only-on-failure", // Capture screenshots only on test failure
    video: "retain-on-failure", // Optionally record video on failure
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        permissions: ["clipboard-read", "clipboard-write"],
      },
      testMatch: "**/*.spec.ts",
    },

    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
      testMatch: "**/*.spec.ts",
    },

    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
      testMatch: "**/*.spec.ts",
    },

    /* Test against mobile viewports. */
    {
      name: "Mobile Chrome",
      use: {
        ...devices["Pixel 5"],
        permissions: ["clipboard-read", "clipboard-write"],
      },
      testMatch: "**/*.spec.ts",
    },
  ],
});
