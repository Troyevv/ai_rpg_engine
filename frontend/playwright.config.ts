import { defineConfig, devices } from "@playwright/test";
import { readFileSync } from "node:fs";
const plan = process.env.E2E_PLAN ? JSON.parse(readFileSync(process.env.E2E_PLAN, 'utf8')) : null;
const baseURL = `http://127.0.0.1:${process.env.E2E_PORT || '8011'}`;
if (plan && (!Array.isArray(plan.files) || !plan.files.length)) throw new Error('Empty E2E selection');
export default defineConfig({
  testDir: "./e2e",
  testMatch: plan ? plan.files.map((file: string) => `**/${file}`) : '**/*.spec.ts',
  forbidOnly: !!process.env.CI,
  retries: 0,
  outputDir: process.env.E2E_OUTPUT || 'test-results',
  reporter: process.env.CI ? [
    ['line'], ['html', { open: 'never', outputFolder: process.env.E2E_HTML || 'playwright-report' }],
    ['junit', { outputFile: process.env.E2E_JUNIT || 'test-results/junit.xml' }],
    ['./ci-reporter.ts'],
  ] : [['list']],
  timeout: 60000,
  expect: { timeout: 12000 },
  workers: 1,
  use: {
    baseURL,
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_EXECUTABLE_PATH
      ? {
          executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
          args: ["--no-sandbox", "--disable-dev-shm-usage"],
        }
      : {},
  },
  webServer: {
    command: "python ../tests/e2e_server.py",
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"], defaultBrowserType: "chromium" },
    },
  ],
});
