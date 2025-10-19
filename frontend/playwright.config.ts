import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for PixelProwlers Studio (frontend).
 *
 * Goals for stable E2E on Kali:
 * - Clean projects (chromium, firefox, webkit)
 * - Deterministic artifacts (HTML report, traces, videos)
 * - webServer can start test stack (backend:8100, frontend:3100) or skip and attach to prestarted services
 *
 * Env:
 *   PPW_BASE_URL=http://127.0.0.1:3100
 *   PPW_BACKEND_HEALTH_URL=http://127.0.0.1:8100/ready/
 *   PW_SKIP_WEBSERVER=1   # if test stack is already running (e.g. via make test-env-up)
 */

const backendHealthUrl = process.env.PPW_BACKEND_HEALTH_URL || 'http://127.0.0.1:8100/ready/'
const frontendBaseUrl = process.env.PPW_BASE_URL || 'http://127.0.0.1:3100'

// When CI or explicitly requested, avoid respawning servers and rely on external infra.
const skipWebServer = process.env.PW_SKIP_WEBSERVER === '1' || false

const webServer = skipWebServer
  ? []
  : [
      {
        // Backend (Django) — test env on port 8100
        command: 'npm run dev:test:back',
        url: backendHealthUrl,
        reuseExistingServer: !process.env.CI,
        stdout: 'pipe',
        stderr: 'pipe',
        timeout: 180_000,
      },
      {
        // Frontend (Nuxt) — test env on port 3100
        command: 'npm run dev:test:front',
        url: frontendBaseUrl,
        reuseExistingServer: !process.env.CI,
        stdout: 'pipe',
        stderr: 'pipe',
        timeout: 180_000,
      },
    ]

export default defineConfig({
  testDir: './test-e2e',
  fullyParallel: false,

  // Retries for flakiness tolerance
  retries: process.env.CI ? 2 : 1,

  // Timeouts
  timeout: 30_000,
  expect: { timeout: 5_000 },

  // Reporters
  reporter: [
    ['list'],
    ['junit', { outputFile: 'reports/e2e.xml' }],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],

  // Artifacts
  outputDir: 'test-results',

  // Shared defaults
  use: {
    headless: true,
    baseURL: frontendBaseUrl,
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
    ignoreHTTPSErrors: !!process.env.CI || false,
  },

  // Cross-browser matrix
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],

  workers: process.env.CI ? 1 : undefined,

  // Either spawn and health-check the stack or attach to already-running services
  webServer,
})
