import { expect, test } from '@playwright/test'

import { completeGate, createConversation, loginAsAdmin, resetState } from './support/helpers'

async function getCsrfToken(page: import('@playwright/test').Page): Promise<string> {
  const cookies = await page.context().cookies()
  return cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? ''
}

test.describe.serial('Dojo security safeguards', () => {
  test.beforeEach(() => {
    resetState()
  })

  test('missing CSRF header is rejected with 403', async ({ page }) => {
    await loginAsAdmin(page)
    await completeGate(page)
    const conversationId = await createConversation(page)

    const status = await page.evaluate(async ({ conversationId: id }) => {
      const res = await fetch('/api/messages/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          conversation: id,
          content: 'Attempt without CSRF header',
        }),
      })
      return res.status
    }, { conversationId })

    expect(status).toBe(403)
  })

  test('nonce replay is blocked', async ({ page }) => {
    await loginAsAdmin(page)
    await completeGate(page)
    const conversationId = await createConversation(page)
    const csrfToken = await getCsrfToken(page)
    expect(csrfToken).not.toBe('')

    const replayResult = await page.evaluate(
      async ({ conversationId: id, token }) => {
        const getNonce = async () => {
          const res = await fetch('/api/auth/nonce/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': token },
          })
          const payload = await res.json()
          return payload.nonce as string
        }

        const postMessage = async (nonce: string, content: string) => {
          const res = await fetch('/api/messages/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': token,
              'X-Request-Nonce': nonce,
            },
            body: JSON.stringify({
              conversation: id,
              content,
            }),
          })
          const data = await res.json().catch(() => ({}))
          return {
            status: res.status,
            data,
            newNonce: res.headers.get('x-new-request-nonce'),
          }
        }

        const nonce = await getNonce()
        const first = await postMessage(nonce, 'Premier message via API')
        const second = await postMessage(nonce, 'Tentative de rejeu')
        return { first, second }
      },
      { conversationId, token: csrfToken },
    )

    expect(replayResult.first.status).toBe(201)
    expect(replayResult.first.newNonce).toBeTruthy()
    expect(replayResult.second.status).toBe(400)
    expect(replayResult.second.data?.error).toBe('nonce_replay')
  })

  test('gate rate-limit returns 429 after repeated failures', async ({ page }) => {
    await loginAsAdmin(page)

    const attemptButton = page.getByRole('button', { name: 'Continuer' })
    const textarea = page.locator('textarea')

    for (let attempt = 0; attempt < 6; attempt += 1) {
      await textarea.fill(`tentative invalide ${attempt}`)
      await attemptButton.click()
    }

    const feedback = page.locator('.feedback.ko')
    await expect(feedback).toContainText('Trop de requêtes')
    await expect(attemptButton).toBeDisabled()
  })
})
