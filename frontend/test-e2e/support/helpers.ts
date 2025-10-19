import { execSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'
import { expect } from '@playwright/test'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const repoRoot = resolve(__dirname, '..', '..', '..')
const backendDir = resolve(repoRoot, 'backend')

export const ADMIN_USERNAME = process.env.E2E_SUPERUSER ?? 'dojo_admin'
export const ADMIN_PASSWORD = process.env.E2E_SUPERUSER_PASSWORD ?? 'dojo_admin_pass'

export function resetState(): void {
  execSync(
    'APP_ENV=dev DJANGO_SETTINGS_MODULE=studio_core.settings.dev poetry run python ../scripts/bootstrap_e2e.py',
    { cwd: backendDir, stdio: 'pipe' },
  )
}

export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/login')
  await page.locator('#username').fill(ADMIN_USERNAME)
  await page.locator('#password').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Continuer' }).click()
  await page.waitForURL('**/gate')
}

export async function completeGate(page: Page): Promise<void> {
  const absurdTextarea = page.locator('textarea')
  await expect(absurdTextarea).toBeVisible()
  await absurdTextarea.fill('la terre est plate')
  await page.getByRole('button', { name: 'Continuer' }).click()

  const ritualInput = page.locator('.input-text')
  await expect(ritualInput).toBeVisible()
  await ritualInput.fill("Bonjour Claire, moi c'est Dojo et on se tutoie.")
  await page.getByRole('button', { name: /Entrer dans le Studio/i }).click()

  await page.waitForURL('**/ask-agents')
}

export async function createConversation(page: Page, agentName = 'Claire'): Promise<string> {
  const agentButton = page
    .locator('.ask__agent-button')
    .filter({ hasText: new RegExp(agentName, 'i') })
    .first()
  await agentButton.click()
  await expect(agentButton).toHaveAttribute('aria-selected', 'true')

  await page.getByRole('button', { name: 'Ouvrir une conversation' }).click()
  await page.waitForURL('**/conversations/*')

  const url = new URL(page.url())
  const segments = url.pathname.split('/')
  return segments[segments.length - 1]
}

export async function sendConversationMessage(page: Page, message: string): Promise<void> {
  const textarea = page.locator('#conversation-message')
  await expect(textarea).toBeVisible()
  await textarea.fill(message)
  const sendButton = page.getByRole('button', { name: 'Envoyer' })
  const responsePromise = page.waitForResponse(
    (res) => res.url().includes('/api/messages/') && res.request().method() === 'POST',
  )
  await sendButton.click()
  await responsePromise
  await expect(page.locator('.conversation__message-body', { hasText: message })).toBeVisible()
}
