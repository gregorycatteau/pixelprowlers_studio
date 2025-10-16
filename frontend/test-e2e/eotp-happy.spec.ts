import { test, expect } from '@playwright/test'

/**
 * E-OTP happy path (dev/test only)
 * - Logs in with superuser credentials (E2E_USER/E2E_PASS)
 * - Waits for redirect to /login/2fa
 * - Retrieves OTP via test-only endpoint (/api/auth/2fa/email/_peek) through the Nuxt proxy
 * - Submits the OTP and expects redirect to /gate
 *
 * Notes:
 * - Backend must run in APP_ENV=test and expose the peek endpoint (guarded server-side).
 * - Frontend Nuxt dev must be reachable at PPW_BASE_URL (defaults to http://127.0.0.1:3100).
 * - This test is skipped automatically if E2E credentials are not provided.
 */
test.describe('E-OTP (happy path, test only)', () => {
  const USER = process.env.E2E_USER || ''
  const PASS = process.env.E2E_PASS || ''

  test.skip(!USER || !PASS, 'E2E_USER/E2E_PASS must be provided to run this test')

  test('login -> pending_2fa -> /login/2fa -> peek OTP -> /gate', async ({ page, baseURL }) => {
    const base = baseURL || 'http://127.0.0.1:3100'

    // Open login page
    await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
    await expect(page.locator('h1.title')).toHaveText(/Démarrer une session/i)

    // Fill credentials and submit
    await page.fill('#username', USER)
    await page.fill('#password', PASS)
    await page.click('button.btn-primary')

    // Wait for 2FA screen
    await page.waitForURL('**/login/2fa*', { timeout: 20_000 })
    await expect(page.locator('h1.title')).toHaveText(/Vérification à deux facteurs/i)
    await expect(page.locator('#code')).toBeVisible()

    // Get OTP via test-only endpoint using page context fetch (preserves cookies)
    const peek = await page.evaluate(async () => {
      try {
        const res = await fetch('/api/auth/2fa/email/_peek', {
          method: 'POST',
          credentials: 'include',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
        const data = await res.json()
        return data
      } catch (e) {
        return { ok: false, error: String(e) }
      }
    })

    test.skip(!peek?.ok || !peek?.code, `Peek unavailable: ${peek?.error || 'no code'}`)
    const code = String(peek.code || '')

    // Submit OTP
    await page.fill('#code', code)
    await page.click('button.btn-primary')

    // Expect redirect to /gate and header rendered
    await page.waitForURL('**/gate*', { timeout: 20_000 })
    await expect(page.locator('h1.title')).toHaveText(/Console — nouvelle session/i)
  })
})
