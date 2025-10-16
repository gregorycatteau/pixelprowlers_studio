# E-OTP 2FA (Email One-Time Password) — Overview

This document describes the minimal, robust Email-based 2FA flow for superusers after login. It covers the end-to-end flow, endpoints, environment variables, development vs production configuration, and manual validation.

## Flow

1) User logs in with email/username + password
- Backend validates credentials.
- If the user is superuser: returns status: "pending_2fa", fa_required: true, eotp_expires_in (seconds).
- Frontend stores eotp_expires_at = now + eotp_expires_in in sessionStorage and navigates to /login/2fa.

2) /login/2fa
- Renders a 6-digit code input, shows TTL countdown from eotp_expires_at.
- Verify:
  - POST /api/auth/2fa/email/verify with X-CSRFToken and credentials: 'include'.
  - On success: fetchMe(true) then navigate to /gate.
  - On failure: uniform error; if 429, respect Retry-After.
- Resend:
  - POST /api/auth/2fa/email/resend with X-CSRFToken and credentials: 'include'.
  - Enforces cooldown + quota; relays Retry-After. Updates eotp_expires_at if a new code/TTL is issued.

3) Gate
- Upon successful verification, user is redirected to /gate. Frontend reflects the authenticated session, using fetchMe(true).

## Endpoints (Backend, proxied by Nuxt server)

- Verify E-OTP
  - Django: POST /api/auth/2fa/email/verify/
  - Frontend server proxy: POST /api/auth/2fa/email/verify
  - Behavior:
    - CSRF protected (cookie + header double-submit).
    - Session-bound OTP verification (constant-time), one-time consumption, anti‑replay.
    - Rate-limit attempts within TTL; returns 429 with Retry-After for abuse.
    - On success: logs user in (session), issues JWT/refresh (cookies), clears pending_2fa.

- Resend E-OTP
  - Django: POST /api/auth/2fa/email/resend/
  - Frontend server proxy: POST /api/auth/2fa/email/resend
  - Behavior:
    - CSRF protected.
    - Cooldown and quota for resends; 429 with Retry-After when exceeded.
    - When regenerated, overwrites previous code hash, updates TTL.

- Login (stage 1)
  - Django: POST /api/auth/login/
  - Frontend server proxy: POST /api/auth/login
  - Response (superusers): { status: "pending_2fa", fa_required: true, eotp_expires_in }.

- Me/CSRF/logout
  - Me: GET /api/auth/me (proxy relays cookies)
  - CSRF: GET /api/auth/csrf (proxy relays Set-Cookie for csrftoken)
  - Logout: POST /api/auth/logout (requires X-CSRFToken)

## Env Vars

- EOTP_TTL_SECONDS (default: 300)
  - OTP validity duration.

- EOTP_RESEND_COOLDOWN_SECONDS (default: 90)
  - Minimum seconds between resends.

- EOTP_MAX_RESENDS (default: 3)
  - Maximum resend attempts within a TTL window.

- EOTP_VERIFY_MAX_ATTEMPTS (default: 5)
  - Maximum verification attempts per TTL window.

- EOTP_PEPPER (REQUIRED IN PROD)
  - Extra secret used to hash the OTP (HMAC-SHA256 fallback when Argon2 unavailable).
  - Do not commit this value; set via environment.

- EMAIL_BACKEND / DEFAULT_FROM_EMAIL (prod)
  - SMTP settings must be provided for real email delivery (see below).

- DEV / CI convenience:
  - APP_ENV != "prod" -> EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend by default (email printed to console).
  - DEBUG/EOTP_DEV_LOG enables log line: eotp.dev_issued user_id=... code=XXXXXX expires_in=...

## Development vs Production

- Development:
  - EMAIL_BACKEND prints emails to console to improve observability.
  - A dev log line with the 6-digit code is emitted (guarded by DEBUG or EOTP_DEV_LOG).
  - CSRF and cookies are still enforced; frontend proxies set credentials: 'include' and propagate Set‑Cookie.

- Production:
  - Configure SMTP.
    - EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
    - DEFAULT_FROM_EMAIL=no-reply@your-domain
    - EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS/SSL
  - Set EOTP_PEPPER (required) and do not log OTP values.
  - OTP hash uses Argon2 if argon2-cffi is installed; otherwise HMAC-SHA256 + pepper.
  - Cookies are HttpOnly, Secure, SameSite=Strict as applicable; headers (CSP/HSTS/etc.) remain unchanged.

## Security Points

- OTP not stored in cleartext, only hashed + peppered (Argon2 or HMAC-SHA256).
- Constant-time compare; one-time consumption.
- OTP state bound to {session_key, user_id} to prevent replay.
- CSRF enforced for verify/resend endpoints (double-submit cookie).
- Rate limits for verify and resend; 429 with Retry-After.
- Uniform error messages to avoid user enumeration.
- No PII or plaintext OTP in logs; dev-only log lines are strictly gated.

## Manual Validation Checklist

- Login as superuser:
  - Expect {status:"pending_2fa", fa_required:true, eotp_expires_in}.
  - Frontend redirects to /login/2fa and shows the form + countdown.
- Dev mode:
  - Backend console shows eotp.dev_issued ... code=XXXXXX.
  - Console email backend prints the email with the code.
- Verify:
  - Correct code -> redirected to /gate after auth.fetchMe(true).
  - Wrong code -> uniform error; after N tries -> 429 + Retry-After enforced and displayed on frontend.
- Resend:
  - Cooldown/quota enforced; 429 + Retry-After when exceeded.
  - TTL updated on new code; countdown updates accordingly.
- Logs/Headers:
  - No OTP/PII in production logs; cookies HttpOnly+Secure+SameSite, CSRF enforced.
  - Security headers (CSP/HSTS/etc.) unchanged.

## Troubleshooting

- 403/CSRF on verify/resend:
  - Ensure csrftoken cookie is present and X‑CSRFToken header is set (frontend proxies handle both).
  - In dev, fetch /api/auth/csrf to seed the cookie.

- No email in dev:
  - Console backend prints the email; check backend terminal logs.
  - For production, verify SMTP configuration variables.

- OTP not accepted:
  - Check TTL (expired codes are rejected).
  - Verify that session persists across login → /login/2fa → verify.
  - Ensure EOTP_PEPPER is consistent per environment (production only).
