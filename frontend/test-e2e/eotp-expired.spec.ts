import { test, expect, request } from '@playwright/test';

/**
 * e-OTP error scenario: expired code then resend
 *
 * Settings (test): EOTP_TTL=5s, COOLDOWN_SECONDS=2s (set in settings.test.py)
 *
 * Expectations:
 * - After TTL passes, verify returns a generic failure (401/403) with { error: "invalid_code" } if JSON
 * - Resend after TTL (and beyond cooldown) returns 200 + Retry-After header + payload fields
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

test.describe('e-OTP expired -> generic failure, then resend OK', () => {
  test('OTP expires (TTL), verify fails, resend succeeds with Retry-After', async () => {
    const api = await request.newContext({
      baseURL: BACKEND_BASE_URL,
      extraHTTPHeaders: { 'X-E2E-Test': '1' },
    });
    const csrfToken = await getCsrf(api);
    await flush(api);

    // 1) Login -> pending_2fa
    const loginRes = await api.post('/api/auth/login/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { username: USERNAME, password: PASSWORD },
    });
    expect(loginRes.status(), 'login status').toBe(200);
    const loginBody = await loginRes.json();
    expect(loginBody.status, 'login response status').toBe('pending_2fa');

    // 2) Peek code
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

    // 3) Wait for TTL to expire (settings.test sets EOTP_TTL=5s)
    await new Promise((r) => setTimeout(r, 6000));

    // 4) Verify should fail generically (expired gets mapped to generic "invalid_code" 403)
    const verifyExpired = await api.post('/api/auth/2fa/email/verify/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: { code },
    });
    expect([401, 403]).toContain(verifyExpired.status());
    const expiredBodyText = await verifyExpired.text();
    try {
      const expiredBody = JSON.parse(expiredBodyText);
      expect(expiredBody.error).toBe('invalid_code');
    } catch {
      // accept generic non-JSON error as long as status is 401/403
    }

    // 5) Resend should be OK when beyond cooldown
    const resendRes = await api.post('/api/auth/2fa/email/resend/', {
      headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
      data: {},
    });
    // If cooldown still applies, allow a short wait then retry once
    let finalRes = resendRes;
    if (resendRes.status() === 429) {
      const ra = Number(resendRes.headers()['retry-after'] || '2');
      await new Promise((r) => setTimeout(r, (isNaN(ra) ? 2 : ra) * 1000 + 200));
      finalRes = await api.post('/api/auth/2fa/email/resend/', {
        headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
        data: {},
      });
    }

    expect(finalRes.status(), 'resend status').toBe(200);
    expect(finalRes.headers()['retry-after']).toBeTruthy();
    const finalBody = await finalRes.json();
    expect(finalBody.ok).toBeTruthy();
    expect(typeof finalBody.retry_after).toBe('number');
    expect(typeof finalBody.expires_in).toBe('number');
  });
});
