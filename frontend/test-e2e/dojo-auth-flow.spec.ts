import { expect, test } from '@playwright/test'

import { completeGate, loginAsAdmin, resetState } from './support/helpers'

test.describe('Dojo auth flow', () => {
  test.beforeEach(() => {
    resetState()
  })

  test('login, gate validation, header user and logout', async ({ page }) => {
    await loginAsAdmin(page)
    await completeGate(page)

    await expect(page).toHaveURL(/\/ask-agents$/)
    await expect(page.locator('.px-header__user')).toHaveText(/dojo_admin/i)

    await page.getByRole('button', { name: /Déconnexion/i }).click()
    await page.waitForURL('**/login')
    await expect(page).toHaveURL(/\/login$/)
  })
})
