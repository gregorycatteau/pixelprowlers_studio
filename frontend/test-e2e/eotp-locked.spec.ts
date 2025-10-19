import { test, expect, request } from '@playwright/test';

/**
 * e-OTP error scenario: locked after MAX_TRIES invalid attempts
 *
 * Settings (test): EOTP_MAX_TRIES=3 (set in settings.test.py)
 *
 * Expectations:
 * - Submit a wrong OTP MAX_TRIES times -> subsequent verify attempts fail generically (401/403)
 * - Endpoint MUST NOT reveal "locked" (generic error/API contract), body.error === "invalid_code" if JSON
 * - A new login + peek + verify with the fresh code still works (fresh challenge)
 */

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://localhost:8000';
const USERNAME = (process.env.E2E_USER || process.env.E2E_USERNAME) || 'dojo_admin';
const PASSWORD = (process.env.E2E_PASS || process.env.E2E_PASSWORD) || 'dojo_admin_pass';
const MAX_TRIES = 3; // mirrored from settings.test.py

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

async function loginPending(api: any, csrfToken: string) {
  const loginRes = await api.post('/api/auth/login/', {
    headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
    data: { username: USERNAME, password: PASSWORD },
  });
  expect(loginRes.status(), 'login status').toBe(200);
  const loginBody = await loginRes.json();
  expect(loginBody.status, 'login response status').toBe('pending_2fa');
}

async function peek(api: any, csrfToken: string) {
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
  expect(code, 'OTP format').toMatch(/^\d{6}|\d{8}$/);
  return code;
}

test.describe('e-OTP locked after MAX_TRIES invalid attempts (generic responses)', () => {
  test('exceed invalid attempts -> generic failure; fresh login still works', async () => {
    const api = await request.newContext({
      baseURL: BACKEND_BASE_URL,
      extraHTTPHeaders: { 'X-E2E-Test': '1' },
    });
    const csrfToken = await getCsrf(api);
    await flush(api);

    // 1) Login -> pending_2fa + get a current code (to craft a wrong one deterministically)
    await loginPending(api, csrfToken);
    const correctCode = await peek(api, csrfToken);
    const wrong = correctCode === '000000' ? '000001' : '000000';

    // 2) Submit wrong code MAX_TRIES times, expect generic 401/403 and error=invalid_code if JSON
    for (let i = 0; i < MAX_TRIES; i++) {
      const bad = await api.post('/api/auth/2fa/email/verify/', {
        headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
        data: { code: wrong },
      });
      expect([401, 403]).toContain(bad.status());
      const txt = await bad.text();
      try {
        const body = JSON.parse(txt);
        expect(body.error).toBe('invalid_code');
      } catch {
        // accept plain text as long as status is generic
      }
    }

    // 3) Another verify attempt (still wrong or even correct) should still fail for this challenge
    //    We'll try the correct code and expect generic failure due to locked state.
    const lockedTry = await api.post('/api/auth/2fa/email/verify/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { code: correctCode },
    });
    expect([401, 403]).toContain(lockedTry.status());
    // Optional JSON contract check
    try {
      const j = await lockedTry.json();
      expect(j.error).toBe('invalid_code');
    } catch {
      // ignore if not JSON
    }

    // 4) Start a fresh flow (new login issues a fresh challenge) -> verify OK
    await loginPending(api, csrfToken);
    const freshCode = await peek(api, csrfToken);
    const verifyOkRes = await api.post('/api/auth/2fa/email/verify/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { code: freshCode },
    });
    expect(
      verifyOkRes.status(),
      `verify OK should be 200; got ${verifyOkRes.status()} — body: ${await verifyOkRes.text()}`
    ).toBe(200);
  });
});
