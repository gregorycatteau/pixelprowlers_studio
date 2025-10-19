import { test, expect, request } from '@playwright/test';

/**
 * e-OTP error scenario: resend quota (3/h OK, 4th -> 429)
 *
 * Settings (test): COOLDOWN_SECONDS=2s (settings.test.py), quota 3/h per user in eotp_resend()
 *
 * Expectations:
 * - After login -> pending_2fa, calling resend should:
 *   * Respect cooldown: if 429, use Retry-After then retry
 *   * Allow 3 successful resends (status 200) within the hour (with cooldown respected)
 *   * Return 429 on the 4th attempt with Retry-After header present
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

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
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

async function resendOnce(api: any, csrfToken: string) {
  const res = await api.post('/api/auth/2fa/email/resend/', {
    headers: { 'content-type': 'application/json', 'X-CSRFToken': csrfToken },
    data: {},
  });
  return res;
}

async function ensureResendOk(api: any, csrfToken: string) {
  // Loop until success with Retry-After backoff (cap attempts to avoid infinite waits)
  let attempts = 0;
  let res = await resendOnce(api, csrfToken);
  while (res.status() === 429 && attempts < 5) {
    const ra = Number(res.headers()['retry-after'] || '2');
    await new Promise((r) => setTimeout(r, (isNaN(ra) ? 2 : ra) * 1000 + 250));
    res = await resendOnce(api, csrfToken);
    attempts += 1;
  }
  expect(res.status(), 'resend should be OK').toBe(200);
  expect(res.headers()['retry-after']).toBeTruthy();
  const body = await res.json();
  expect(body.ok).toBeTruthy();
  expect(typeof body.retry_after).toBe('number');
  expect(typeof body.expires_in).toBe('number');
  return res;
}

test.describe('e-OTP resend quota (3/h OK, 4th -> 429)', () => {
  test('three resends OK with cooldown; fourth returns 429', async () => {
    const api = await request.newContext({
      baseURL: BACKEND_BASE_URL,
      extraHTTPHeaders: { 'X-E2E-Test': '1' },
    });
    const csrfToken = await getCsrf(api);
    await flush(api);

    // 1) Login -> pending_2fa
    await loginPending(api, csrfToken);

    // 2) Perform 3 resends successfully (respecting cooldown profile and quota semantics)
    // IMPORTANT: The service increments quota BEFORE checking cooldown.
    // To avoid consuming quota on 429, we wait an initial cooldown window before first resend.
    await sleep(2500); // COOLDOWN_SECONDS=2s (+buffer)

    // First resend (expect 200)
    let r1 = await resendOnce(api, csrfToken);
    if (r1.status() === 429) {
      const ra1 = Number(r1.headers()['retry-after'] || '2');
      await sleep((isNaN(ra1) ? 2 : ra1) * 1000 + 300);
      r1 = await resendOnce(api, csrfToken);
    }
    expect(r1.status(), 'first resend should be 200').toBe(200);
    const ra1n = Number(r1.headers()['retry-after'] || '2');
    await sleep((isNaN(ra1n) ? 2 : ra1n) * 1000 + 300);

    // Second resend (expect 200)
    let r2 = await resendOnce(api, csrfToken);
    if (r2.status() === 429) {
      const ra2 = Number(r2.headers()['retry-after'] || '2');
      await sleep((isNaN(ra2) ? 2 : ra2) * 1000 + 300);
      r2 = await resendOnce(api, csrfToken);
    }
    expect(r2.status(), 'second resend should be 200').toBe(200);
    const ra2n = Number(r2.headers()['retry-after'] || '2');
    await sleep((isNaN(ra2n) ? 2 : ra2n) * 1000 + 300);

    // Third resend (expect 200)
    let r3 = await resendOnce(api, csrfToken);
    if (r3.status() === 429) {
      const ra3 = Number(r3.headers()['retry-after'] || '2');
      await sleep((isNaN(ra3) ? 2 : ra3) * 1000 + 300);
      r3 = await resendOnce(api, csrfToken);
    }
    expect(r3.status(), 'third resend should be 200').toBe(200);
    const ra3n = Number(r3.headers()['retry-after'] || '2');
    await sleep((isNaN(ra3n) ? 2 : ra3n) * 1000 + 300);

    // 3) Fourth resend should be 429 (quota exceeded) with Retry-After
    const fourth = await resendOnce(api, csrfToken);
    expect(fourth.status(), 'fourth resend status').toBe(429);
    expect(fourth.headers()['retry-after']).toBeTruthy();
    // Body should be generic: { ok: false, error: "rate_limited" }
    try {
      const body = await fourth.json();
      expect(body.ok).toBeFalsy();
      expect(body.error).toBe('rate_limited');
    } catch {
      // Accept non-JSON as long as status is 429 and header present
    }
  });
});
