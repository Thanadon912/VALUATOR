import { defineConfig, devices } from "@playwright/test";

const isCI = Boolean(process.env.CI);
const allureReporter = [
  "allure-playwright",
  {
    resultsDir: process.env.ALLURE_RESULTS_DIR ?? "allure-results",
    categories: [
      {
        name: "Fixture / Mock Contract Drift",
        matchedStatuses: ["failed"],
        messageRegex: ".*strict mode violation.*",
      },
      {
        name: "Environment / Infrastructure",
        matchedStatuses: ["broken", "failed"],
        messageRegex: ".*(ERR_CONNECTION_REFUSED|ECONNREFUSED).*$",
      },
    ],
    environmentInfo: {
      Branch: process.env.GIT_BRANCH ?? "local",
      Commit: process.env.GIT_COMMIT ?? "uncommitted",
      "Node version": process.version,
      "Test runner": "Playwright",
      Environment: process.env.TEST_ENVIRONMENT ?? (isCI ? "ci" : "local"),
    },
  },
] as const;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: isCI ? 1 : undefined,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? "test-results",
  reporter: isCI
    ? [
        ["line"],
        ["junit", { outputFile: process.env.PLAYWRIGHT_JUNIT_OUTPUT ?? "test-results/e2e-junit.xml" }],
        ["html", { outputFolder: process.env.PLAYWRIGHT_HTML_OUTPUT ?? "playwright-report", open: "never" }],
        allureReporter,
      ]
    : [
        ["list"],
        ["junit", { outputFile: process.env.PLAYWRIGHT_JUNIT_OUTPUT ?? "test-results/e2e-junit.xml" }],
        ["html", { open: "never" }],
        allureReporter,
      ],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3200",
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    viewport: { width: 1440, height: 1100 },
  },
  projects: [
    {
      name: "chromium",
      testIgnore: "**/mobile/**/*.spec.ts",
      use: {
        browserName: "chromium",
        channel: process.env.E2E_BROWSER_CHANNEL || undefined,
      },
    },
    {
      name: "firefox",
      testIgnore: "**/mobile/**/*.spec.ts",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      testIgnore: "**/mobile/**/*.spec.ts",
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "mobile-android",
      testMatch: "**/mobile/**/*.spec.ts",
      use: {
        ...devices["Pixel 5"],
        browserName: "chromium",
        viewport: { width: 360, height: 800 },
      },
    },
    {
      name: "mobile-ios",
      testMatch: "**/mobile/**/*.spec.ts",
      use: {
        ...devices["iPhone 13"],
        browserName: "webkit",
        viewport: { width: 390, height: 844 },
      },
    },
  ],
});
