import type { H3Event } from 'h3'
import { getRequestHeaders, createError } from 'h3'
import { djangoBase } from '../../../../utils/djangoBase'

/**
 * TEST-ONLY proxy: E-OTP peek (returns current OTP for E2E in APP_ENV=test)
 * Backends route: POST /api/auth/2fa/email/_peek/
 *
 * - Forwards cookies (session)
 * - Tries to propagate Retry-After if any
 * - Returns JSON { ok: true, code: "123456" } when available
 * - Should be guarded server-side by APP_ENV=test (backend enforces it)
 */
export default defineEventHandler(async (event: H3Event) => {
  const base = djangoBase(event)
  const url = `${base}/api/auth/2fa/email/_peek/`

  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const incomingCookies = reqHeaders.cookie || ''

  try {
    const upstream = await $fetch.raw(url, {
      method: 'POST',
      headers: {
        cookie: incomingCookies,
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'include',
    })

    // Propagate Retry-After if present
    const anyHeaders = upstream.headers as any
    const retryAfter =
      anyHeaders?.get?.('retry-after') || upstream.headers.get('retry-after') || undefined
    if (retryAfter) {
      event.node.res.setHeader('Retry-After', retryAfter)
    }

    const data = await upstream.json().catch(async () => (upstream as any)._data ?? null)
    return data ?? { ok: false, error: 'peek_unavailable' }
  } catch (e: any) {
    const status = e?.response?.status || 502
    const statusText = e?.response?.statusText || 'Bad Gateway'
    const detail = e?.data || e?.message || 'Erreur proxy vers /api/auth/2fa/email/_peek/'
    // Forward Retry-After if any
    try {
      const ra =
        e?.response?.headers?.get?.('Retry-After') ||
        e?.response?.headers?.get?.('retry-after') ||
        e?.response?.headers?.['retry-after']
      if (ra) {
        event.node.res.setHeader('Retry-After', String(ra))
      }
    } catch {}
    throw createError({
      statusCode: status,
      statusMessage: statusText,
      data: {
        ok: false,
        error: 'proxy_eotp_peek_failed',
        detail,
      },
    })
  }
})
