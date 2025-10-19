import { test, expect, request } from '@playwright/test';

/**
 * E2E e-OTP happy path (API-level) using _peek (APP_ENV=test):
 * - POST /api/auth/login/ with superuser credentials
 * - POST /api/auth/2fa/email/_peek/ to retrieve OTP (test-only)
 * - POST /api/auth/2fa/email/verify/ with retrieved code
 * - Assert 200 and pending -> consumed transition observable by verify OK and a reject on replay
 *
 * Requirements to run locally:
 * - Backend running with APP_ENV=test (so _peek is allowed)
 * - Superuser available (env provides credentials)
 * - Frontend Playwright environment (this spec uses direct API calls, not UI)
 *
 * Usage:
 *   BACKEND_BASE_URL=http://localhost:8000 \
 *   E2E_USERNAME=admin \
 *   E2E_PASSWORD=adminpassword \
 *   npx playwright test test-e2e/eotp-happy.spec.ts
 */

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://localhost:8000';
const USERNAME = (process.env.E2E_USER || process.env.E2E_USERNAME) || 'dojo_admin';
const PASSWORD = (process.env.E2E_PASS || process.env.E2E_PASSWORD) || 'dojo_admin_pass';

async function getCsrf(api: any): Promise<string> {
  const res = await api.get('/csrf/');
  if (res.status() !== 200) {
    throw new Error(`Failed to fetch CSRF token, status=${res.status()}`);
  }
  const body = await res.json();
  return String(body?.csrfToken || '');
}

test.describe('e-OTP happy path via _peek (APP_ENV=test)', () => {
  test('login -> pending_2fa -> peek code -> verify OK; replay rejected', async ({ request: _ }) => {
    const api = await request.newContext({
      baseURL: BACKEND_BASE_URL,
      extraHTTPHeaders: {
        'X-E2E-Test': '1',
      },
    });
    const csrfToken = await getCsrf(api);

    // 1) Login (expects 200 with status=pending_2fa for superuser)
    const loginRes = await api.post('/api/auth/login/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { username: USERNAME, password: PASSWORD },
    });
    expect(loginRes.status(), 'login status').toBe(200);
    const loginBody = await loginRes.json();
    expect(loginBody.status, 'login response status').toBe('pending_2fa');

    // 2) _peek — only allowed when APP_ENV=test
    const peekRes = await api.post('/api/auth/2fa/email/_peek/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: {},
    });
    if (peekRes.status() === 403) {
      test.skip(true, '_peek disabled (APP_ENV!=test). Run backend with APP_ENV=test to enable.');
    }
    expect(peekRes.status(), '_peek status').toBe(200);
    const peekBody = await peekRes.json();
    const code = String(peekBody.code || '');
    expect(code, 'OTP code').toMatch(/^\d{6}|\d{8}$/);

    // 3) verify OK
    const verifyOkRes = await api.post('/api/auth/2fa/email/verify/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { code },
    });
    expect(
      verifyOkRes.status(),
      `verify OK should be 200; got ${verifyOkRes.status()} — body: ${await verifyOkRes.text()}`
    ).toBe(200);

    // 4) replay should be rejected (consumed)
    const verifyReplayRes = await api.post('/api/auth/2fa/email/verify/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { code },
    });
    expect([401, 403]).toContain(verifyReplayRes.status());
  });

  test('resend returns Retry-After and payload fields', async ({ request: _ }) => {
    const api = await request.newContext({
      baseURL: BACKEND_BASE_URL,
      extraHTTPHeaders: { 'X-E2E-Test': '1' },
    });
    const csrfToken = await getCsrf(api);

    // Login to get pending_2fa
    const loginRes = await api.post('/api/auth/login/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { username: USERNAME, password: PASSWORD },
    });
    expect(loginRes.status()).toBe(200);

    // Cooldown may apply on immediate resend; still the spec asserts that 200 path returns Retry-After header
    const resendRes = await api.post('/api/auth/2fa/email/resend/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: {},
    });

    if (resendRes.status() === 429) {
      // If rate-limited, at least ensure Retry-After is present
      expect(resendRes.headers()['retry-after']).toBeTruthy();
    } else {
      expect(resendRes.status()).toBe(200);
      expect(resendRes.headers()['retry-after']).toBeTruthy();
      const body = await resendRes.json();
      expect(body.ok).toBeTruthy();
      expect(typeof body.retry_after).toBe('number');
      expect(typeof body.expires_in).toBe('number');
    }
  });
});
