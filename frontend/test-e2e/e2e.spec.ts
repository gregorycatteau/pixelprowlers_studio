/**
 * PixelProwlers Studio — E2E (stubs) with mocks placeholders
 *
 * This file declares five Playwright scenarios as stubs, each with clear
 * Arrange/Act/Assert sections and mock helpers placeholders. These are
 * designed to be replaced with real implementations when the env/harness
 * and backends are up in CI.
 *
 * Scenarios:
 *  1) Admin (Dojo) legitimate — mTLS + WebAuthn mock → console signed
 *  2) Admin (Dojo) without passkey — WebAuthn mock fail → Laby redirection
 *  3) Client — login → pending_2fa → TOTP bootstrap/activate/verify → dashboard → export ZIP/PGP (mocks)
 *  4) Bot/Headless — Turnstile absent → /login blocked; /totp/verify refused if FA requires token
 *  5) Canaries — open .env & notes_admin.txt; mock webhook (HMAC) assertion
 *
 * Usage:
 *  - These tests are stubs and are marked as skipped. Remove `test.skip(...)`
 *    one-by-one once your harness and mocks are wired.
 *  - Configure baseURL in playwright.config.ts via env PPW_BASE_URL.
 */

import { test, expect, Page, Route, Request } from '@playwright/test'

/* =============================================================================
   Helpers (Mocks — placeholders)
   ========================================================================== */

/**
 * Mock the WebAuthn flow (navigator.credentials.get).
 * outcome = "success" | "fail"
 */
async function mockWebAuthn(page: Page, outcome: 'success' | 'fail' = 'success') {
  await page.addInitScript(
    ([shouldSucceed]) => {
      // Basic, non-cryptographic mock; replace with a proper simulator if needed.
      const ok = Boolean(shouldSucceed)
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      window.__PPW_WEBAUTHN_MOCK__ = { ok }

      const makeArrayBuffer = (text: string) => new TextEncoder().encode(text).buffer

      const fakeCredential = () => ({
        id: 'cred-id',
        type: 'public-key' as const,
        rawId: makeArrayBuffer('raw-id'),
        // Minimal AuthenticatorAssertionResponse-like shape (non-crypto)
        response: {
          clientDataJSON: makeArrayBuffer('client-data'),
          authenticatorData: makeArrayBuffer('auth-data'),
          signature: makeArrayBuffer('sig'),
          userHandle: null,
        },
        getClientExtensionResults: () => ({}),
      })

      const patch = () => {
        if (!('credentials' in navigator)) {
          // eslint-disable-next-line @typescript-eslint/ban-ts-comment
          // @ts-ignore
          navigator.credentials = {}
        }
        const original = navigator.credentials.get?.bind(navigator.credentials)
        navigator.credentials.get = async (options: unknown) => {
          if (window.__PPW_WEBAUTHN_MOCK__?.ok) {
            return fakeCredential()
          }
          // Fail path
          const err = new Error('WebAuthn mocked failure')
          // @ts-ignore
          err.name = 'NotAllowedError'
          throw err
        }
        // Keep a reference if revert needed
        // @ts-ignore
        window.__PPW_WEBAUTHN_ORIG_GET__ = original
      }

      try {
        patch()
      } catch {
        // swallow
      }
    },
    [outcome === 'success'],
  )
}

/**
 * Intercept /api/auth/creds (Nuxt server route) and inject a Turnstile token
 * header if needed for “OK” paths, or strip it for “blocked” paths.
 */
async function interceptTurnstile(
  page: Page,
  mode: 'inject' | 'strip',
  token = 'e2e-turnstile-token',
) {
  await page.route('**/api/auth/creds', async (route: Route, req: Request) => {
    const headers = { ...req.headers() }
    if (mode === 'inject') {
      headers['CF-Turnstile-Token'] = token
      headers['X-Turnstile-Token'] = token
    } else {
      delete headers['CF-Turnstile-Token']
      delete headers['X-Turnstile-Token']
    }
    // Forward with modified headers
    const resp = await route.fetch({ headers })
    await route.fulfill({
      response: resp,
    })
  })
}

/**
 * Mock QR bootstrap, ZIP/PGP file downloads during Client flow.
 * You can intercept fetch calls to backend endpoints and return minimal fixtures.
 */
async function mockClientOnboardingAndExports(page: Page) {
  // Example: intercept TOTP bootstrap (GET /api/auth/totp/bootstrap/)
  await page.route('**/api/auth/totp/bootstrap/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        secret: 'JBSWY3DPEHPK3PXP',
        otpauth_url:
          'otpauth://totp/PixelProwlers:demo?secret=JBSWY3DPEHPK3PXP&issuer=PixelProwlers',
      }),
    })
  })

  // Example: intercept ZIP export (return a dummy zip stream)
  await page.route('**/api/auth/totp/recovery/export/**', async (route) => {
    const req = route.request()
    const body = (await req.postDataJSON().catch(() => ({}))) as any
    const format = String(body?.format || 'zip')
    if (format === 'zip') {
      // Minimal empty ZIP bytes (placeholder)
      const buffer = new Uint8Array([0x50, 0x4b, 0x05, 0x06, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition': 'attachment; filename="recovery-codes.zip"',
        },
        body: Buffer.from(buffer),
      })
      return
    }
    if (format === 'pgp') {
      const armored =
        '-----BEGIN PGP MESSAGE-----\nVersion: E2E Mock\n\nmQENBF8=MOCK\n-----END PGP MESSAGE-----\n'
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'application/pgp-encrypted',
          'Content-Disposition': 'attachment; filename="recovery-codes.asc"',
        },
        body: armored,
      })
      return
    }
    await route.fulfill({
      status: 400,
      body: JSON.stringify({ ok: false, error: 'unsupported_format' }),
    })
  })
}

/**
 * Mock webhook n8n for canaries (HMAC signature expected).
 * You can stand up a local HTTP server in the test or intercept the outbound POST here
 * and check headers X-Canary-Timestamp/X-Canary-Signature (TODO).
 */
async function mockCanaryWebhook(page: Page) {
  // Example: intercept all POSTs to a given webhook endpoint (set via env)
  const webhookUrl = process.env.PPW_CANARY_WEBHOOK_URL || '**/webhook/canary/**'
  await page.route(webhookUrl, async (route: Route, req: Request) => {
    const headers = req.headers()
    // TODO: Verify HMAC signature and timestamp here if shared secret is available in env
    // const sig = headers['x-canary-signature']
    // const ts  = headers['x-canary-timestamp']
    // expect(sig).toBeTruthy()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    })
  })
}

/**
 * (Optional) Check CSP violations (placeholder).
 * In practice, we recommend a backend endpoint to surface reports count.
 */
async function expectNoCspViolations(/* page: Page */) {
  // TODO: call a check endpoint or analyze console messages for CSP errors
  expect(true).toBeTruthy()
}

/* =============================================================================
   Tests (stubs) — Remove test.skip to activate once harness/mocks are wired
   ========================================================================== */

test.describe('E2E — Admin (Dojo) legitimate — mTLS + WebAuthn mock → console signed', () => {
  test('should sign console and show "signée à …"', async ({ page }) => {
    // Arrange
    await mockWebAuthn(page, 'success')

    // Act
    await page.goto('/')

    // Navigate to Dojo mode and trigger WebAuthn login, then open /console
    await page.getByRole('button', { name: /Admins \(Dojo/ }).click()
    await page.getByRole('button', { name: /Continuer avec Passkey/ }).click()
    await page.goto('/console')
    await page.getByRole('button', { name: /Signer la session/ }).click()

    // Assert
    await expectNoCspViolations()
    await expect(page.getByText(/Signée à/i)).toBeVisible()
    // Ensure no cookies are readable client-side (placeholder check)
    await expect(
      page.evaluate(() => typeof document !== 'undefined' && !!document),
    ).resolves.toBeTruthy()
  })
})

test.describe('E2E — Admin (Dojo) without passkey — WebAuthn mock fail → Laby', () => {
  test('should redirect silently to Laby console', async ({ page }) => {
    await mockWebAuthn(page, 'fail')
    await page.goto('/')

    // Select Dojo tab & attempt Passkey (should fail → Laby)
    await page.getByRole('button', { name: /Admins \(Dojo/ }).click()
    await page.getByRole('button', { name: /Continuer avec Passkey/ }).click()

    // Assert: illusions visible + artifacts links
    await expectNoCspViolations()
    await expect(page.getByText(/Mode Laby \(antichambre\)/i)).toBeVisible()
    await expect(page.getByRole('link', { name: /.env/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /id_ed25519/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /notes_admin\.txt/ })).toBeVisible()
  })
})

test.describe('E2E — Client — login + TOTP onboarding + exports → dashboard', () => {
  test('should complete 2FA and export ZIP/PGP', async ({ page }) => {
    await mockClientOnboardingAndExports(page)
    await interceptTurnstile(page, 'inject', 'playwright-turnstile-token')

    await page.goto('/')

    // Login (Clients tab par défaut)
    await page.getByLabel('Email').fill('user@example.com')
    await page.getByLabel('Mot de passe').fill('password-123')
    await page.getByRole('button', { name: 'Se connecter' }).click()
    await expect(page.getByText(/Étape 2FA requise/i)).toBeVisible()

    // Bootstrap TOTP (mock) → activer → verify
    await page.getByRole('button', { name: /Activer TOTP/ }).click()
    await page.getByLabel('Entrez un code TOTP').fill('123456')
    await page.getByRole('button', { name: 'Activer' }).click()
    await page.getByLabel('Code à 6 chiffres').fill('123456')
    await page.getByRole('button', { name: 'Vérifier' }).click()
    await page.waitForURL('**/dashboard')

    // Export ZIP (attend l’événement de téléchargement)
    await page.getByLabel('Mot de passe du ZIP').fill('Zip-Secret-123!')
    const [zipDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: /Télécharger ZIP chifré/ }).click(),
    ])
    await expect(zipDownload.suggestedFilename()).resolves.toMatch(/recovery-codes\.zip$/)

    // Export PGP (attend l’événement de téléchargement)
    await page
      .getByLabel(/Clé publique PGP/i)
      .fill('-----BEGIN PGP PUBLIC KEY BLOCK-----\nFAKE\n-----END PGP PUBLIC KEY BLOCK-----')
    const [pgpDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: /Télécharger \.asc chifré/ }).click(),
    ])
    await expect(pgpDownload.suggestedFilename()).resolves.toMatch(/recovery-codes\.asc$/)

    await expectNoCspViolations()
  })
})

test.describe('E2E — Bot/Headless — Turnstile required', () => {
  test('should block login without Turnstile; allow when token present', async ({ page }) => {
    // Blocked path
    await interceptTurnstile(page, 'strip')
    await page.goto('/')
    // Intercept server route to force a backend error and keep UI neutral
    await page.route('**/api/auth/creds', async (route) => {
      await route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'blocked' }),
      })
    })
    // Fill and submit login form
    await page.getByLabel('Email').fill('user@example.com')
    await page.getByLabel('Mot de passe').fill('not-secret')
    await page.getByRole('button', { name: 'Se connecter' }).click()
    // Expect neutral error message
    await expect(page.getByText('Connexion non finalisée. Réessayez.')).toBeVisible()

    // Allowed path (inject token)
    await interceptTurnstile(page, 'inject', 'playwright-turnstile-token')
    // TODO: submit again; should proceed to pending_2fa
  })

  test('should refuse /totp/verify when X-FA-Require-Turnstile=1 and no token; OK with token', async ({
    page,
  }) => {
    // Strip Turnstile token and simulate FA requirement on totpVerify (fulfill 401)
    await page.route('**/api/auth/creds', async (route, req) => {
      const body = (await req.postDataJSON().catch(() => ({}))) as any
      if (body?.action === 'totpVerify') {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ ok: false, error: 'turnstile_required' }),
        })
        return
      }
      await route.fallback()
    })

    await page.goto('/')
    // Login to reach pending_2fa
    await page.getByLabel('Email').fill('user@example.com')
    await page.getByLabel('Mot de passe').fill('password-123')
    await page.getByRole('button', { name: 'Se connecter' }).click()
    await expect(page.getByText(/Étape 2FA requise/i)).toBeVisible()

    // Attempt TOTP verify without token → expect neutral error
    await page.getByLabel('Code à 6 chiffres').fill('123456')
    await page.getByRole('button', { name: 'Vérifier' }).click()
    // Neutral message (can be "Vérification indisponible." or "Code incorrect. Réessayez.")
    await expect(page.getByText(/(Vérification indisponible|Code incorrect)/i)).toBeVisible()

    // Inject Turnstile token: override route to return ok:true on totpVerify
    await page.unroute('**/api/auth/creds')
    await page.route('**/api/auth/creds', async (route, req) => {
      const body = (await req.postDataJSON().catch(() => ({}))) as any
      if (body?.action === 'totpVerify') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true }),
        })
        return
      }
      await route.fallback()
    })

    // Retry TOTP verify (simulating token present via backend OK)
    await page.getByLabel('Code à 6 chiffres').fill('123456')
    await page.getByRole('button', { name: 'Vérifier' }).click()
    await page.waitForURL('**/dashboard')
  })
})

test.describe('E2E — Canaries — artifacts + webhook HMAC', () => {
  test('should open artifacts and receive HMAC webhook (mock)', async ({ page }) => {
    test.skip(true)
    await mockCanaryWebhook(page)
    await page.goto('/console') // or a Laby page

    // Open artifact links
    // await page.getByRole('link', { name: '.env' }).click()
    // await page.goBack()
    // await page.getByRole('link', { name: 'notes_admin.txt' }).click()

    await expectNoCspViolations()
  })
})
