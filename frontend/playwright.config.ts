import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for PixelProwlers Studio (frontend).
 *
 * - Runs tests in ./test-e2e
 * - Retries once (retries = 1)
 * - Captures screenshots (only on failure) and videos (retain on failure)
 * - Produces JUnit + HTML reports and saves artifacts under test-results/
 *
 * Configure baseURL via env:
 *   PPW_BASE_URL=https://clients.local npm run test:e2e
 */
export default defineConfig({
  testDir: './test-e2e',
  /* Fail fast-ish, but retry once for flakiness tolerance */
  retries: 1,
  /* Default timeout per test (ms) */
  timeout: 30_000,
  expect: { timeout: 10_000 },

  /* CI-friendly reporters (list in logs, junit for CI, html for local inspection) */
  reporter: [
    ['list'],
    ['junit', { outputFile: 'reports/e2e.xml' }],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],

  /* Where to put screenshots, videos, traces */
  outputDir: 'test-results',

  /* Shared settings for all projects */
  use: {
    headless: true,
    baseURL: process.env.PPW_BASE_URL || 'http://localhost:3000',
    actionTimeout: 10_000,
    navigationTimeout: 20_000,

    /* Artifacts as requested */
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',

    /* Helpful defaults */
    ignoreHTTPSErrors: !!process.env.CI || false,
  },

  /* Run on Chromium by default; add Firefox/WebKit if desired */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Uncomment to run cross-browser
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],

  /* If you need to auto-start a server, define it here.
     For CI integration with existing harnesses, we leave this disabled. */
  // webServer: [
  //   {
  //     command: 'npm run dev',
  //     url: process.env.PPW_BASE_URL || 'http://localhost:3000',
  //     reuseExistingServer: !process.env.CI,
  //     timeout: 120_000,
  //   },
  // ],
})
