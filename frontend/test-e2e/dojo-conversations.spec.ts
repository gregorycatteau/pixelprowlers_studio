import { expect, test } from '@playwright/test'

import {
  completeGate,
  createConversation,
  loginAsAdmin,
  resetState,
  sendConversationMessage,
} from './support/helpers'

test.describe.serial('Dojo conversations', () => {
  test.beforeEach(() => {
    resetState()
  })

  test('create conversation, send message and archive', async ({ page }) => {
    await loginAsAdmin(page)
    await completeGate(page)

    const conversationId = await createConversation(page)
    await expect(page).toHaveURL(new RegExp(`/conversations/${conversationId}`))

    const messageText = `Bonjour Dojo ${Date.now()}`
    await sendConversationMessage(page, messageText)

    // Archive the conversation via UI
    const archiveButton = page.getByRole('button', { name: /Archiver/i })
    await expect(archiveButton).toBeVisible()
    await archiveButton.click()

    await expect(page.locator('.conversation__status')).toHaveText(/Archivée/)
    await expect(page.getByRole('button', { name: 'Envoyer' })).toBeDisabled()
  })
})
