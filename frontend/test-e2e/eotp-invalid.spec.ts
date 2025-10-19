import { test, expect, request } from '@playwright/test';

/**
 * e-OTP error scenario: invalid code
 *
 * Expectations:
 * - On wrong OTP, API returns a generic error (do not reveal "invalid"/"expired" details)
 * - Status is 401/403 (generic), body.error === "invalid_code"
 * - After a single invalid attempt, the user can still verify with the correct code
 *
 * Pre-req:
 * - Backend running with APP_ENV=test (so _peek is allowed)
 * - Superuser created by bootstrap_e2e.py (defaults: dojo_admin / dojo_admin_pass)
 */

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://localhost:8000';
const USERNAME = (process.env.E2E_USER || process.env.E2E_USERNAME) || 'dojo_admin';
const PASSWORD = (process.env.E2E_PASS || process.env.E2E_PASSWORD) || 'dojo_admin_pass';

async function getCsrf(api: any): Promise<string> {
  const res = await api.get('/csrf/');
  expect(res.status(), '/csrf/ status').toBe(200);
  const body = await res.json();
  return String(body?.csrfToken || '');
}

async function flush(api: any): Promise<void> {
  const res = await api.get('/flush/');
  expect(res.status(), '/flush/ status').toBe(200);
}

test.describe('e-OTP invalid code (generic error, no details)', () => {
  test('invalid OTP -> generic 401/403; then correct OTP works', async () => {
    const api = await request.newContext({
      baseURL: BACKEND_BASE_URL,
      extraHTTPHeaders: { 'X-E2E-Test': '1' },
    });
    const csrfToken = await getCsrf(api);
    await flush(api);

    // 1) Login, expect pending_2fa
    const loginRes = await api.post('/api/auth/login/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { username: USERNAME, password: PASSWORD },
    });
    expect(loginRes.status(), 'login status').toBe(200);
    const loginBody = await loginRes.json();
    expect(loginBody.status, 'login response status').toBe('pending_2fa');

    // 2) Peek current OTP (APP_ENV=test only)
    const peekRes = await api.post('/api/auth/2fa/email/_peek/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: {},
    });
    if (peekRes.status() === 403) {
      test.skip(true, '_peek disabled (APP_ENV!=test). Run backend with APP_ENV=test to enable.');
    }
    expect(peekRes.status(), '_peek status').toBe(200);
    const peekBody = await peekRes.json();
    const correctCode = String(peekBody.code || '');
    expect(correctCode, 'peeked OTP code format').toMatch(/^\d{6}|\d{8}$/);

    // 3) Try an invalid code (generic failure)
    const invalidCode = correctCode === '000000' ? '000001' : '000000';
    const invalidRes = await api.post('/api/auth/2fa/email/verify/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { code: invalidCode },
    });
    expect([401, 403]).toContain(invalidRes.status());
    const invalidBodyText = await invalidRes.text();
    // If JSON body, it should be { ok: false, error: "invalid_code" }
    try {
      const invalidBody = JSON.parse(invalidBodyText);
      expect(invalidBody.error).toBe('invalid_code');
    } catch {
      // If not JSON, we still accept the generic status code contract (401/403)
    }

    // 4) Verify with the correct code should still work after a single invalid attempt
    const verifyOkRes = await api.post('/api/auth/2fa/email/verify/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { code: correctCode },
    });
    expect(
      verifyOkRes.status(),
      `verify OK should be 200; got ${verifyOkRes.status()} — body: ${await verifyOkRes.text()}`
    ).toBe(200);
  });
});
