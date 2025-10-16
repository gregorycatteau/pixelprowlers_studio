import type { H3Event } from 'h3'
import { getRequestHeaders, createError } from 'h3'
import { djangoBase } from '../../../../utils/djangoBase'

/**
 * Proxy de renvoi E-OTP (email OTP) vers Django.
 * - Propage cookies de session
 * - Applique X-CSRFToken (double-submit via cookie si présent)
 * - Propage Retry-After en cas de 429
 * - Relaye le JSON tel quel
 */

// -- utilitaire: extraire le csrftoken depuis le header Cookie
function extractCsrfFromCookie(cookieHeader: string | undefined): string | null {
  if (!cookieHeader) return null
  const match = cookieHeader.match(/(?:^|;\s*)csrftoken=([^;]+)/i)
  return match ? decodeURIComponent(match[1]) : null
}

// Assainit la valeur CSRF
function sanitizeCsrf(v: string | undefined | null): string {
  const s = (v || '').trim()
  return s.replace(/^"(.*)"$/, '$1')
}

export default defineEventHandler(async (event: H3Event) => {
  const base = djangoBase(event)
  const url = `${base}/api/auth/2fa/email/resend/`

  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const incomingCookies = reqHeaders.cookie || ''
  const cookieCsrf = extractCsrfFromCookie(incomingCookies) || ''
  const headerCsrf = (reqHeaders['x-csrftoken'] as string | undefined) || ''
  const effectiveCsrf = sanitizeCsrf(cookieCsrf || headerCsrf || '')

  try {
    const upstream = await $fetch.raw(url, {
      method: 'POST',
      headers: {
        cookie: incomingCookies,
        'X-CSRFToken': effectiveCsrf,
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'include',
    })

    const anyHeaders = upstream.headers as any
    const retryAfter =
      anyHeaders?.get?.('retry-after') || upstream.headers.get('retry-after') || undefined
    if (retryAfter) {
      event.node.res.setHeader('Retry-After', retryAfter)
    }

    const data = await upstream.json().catch(async () => (upstream as any)._data ?? null)
    return data ?? { ok: true }
  } catch (e: any) {
    const status = e?.response?.status || 502
    const statusText = e?.response?.statusText || 'Bad Gateway'
    const detail = e?.data || e?.message || 'Erreur proxy vers /api/auth/2fa/email/resend/'
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
        error: 'proxy_eotp_resend_failed',
        detail,
      },
    })
  }
})
