import { test, expect } from '@playwright/test'

/**
 * Basic availability test
 * - Loads the login page
 * - Verifies the main heading is rendered
 * - Provides quick signal that the Nuxt app and assets are served correctly
 */
test.describe('Availability', () => {
  test('login page renders with heading', async ({ page, baseURL }) => {
    const base = baseURL || 'http://127.0.0.1:3100'
    await page.goto(`${base}/login`, { waitUntil: 'networkidle' })

    const title = page.locator('h1.title')
    await expect(title).toHaveText(/Démarrer une session/i)

    // Optionally assert main form fields exist
    await expect(page.locator('#username')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    // Button is disabled until credentials are provided; visibility is enough for availability
    await expect(page.locator('button.btn-primary')).toBeVisible()
  })
})
