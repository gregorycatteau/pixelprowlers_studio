import type { H3Event } from 'h3'
import { getRequestHeaders, readBody, createError } from 'h3'
import { djangoBase } from '../../../../utils/djangoBase'

/**
 * Proxy de vérification E-OTP (email OTP) vers Django.
 * - Propage les cookies (session)
 * - Applique l'en-tête X-CSRFToken (double-submit)
 * - Relaye Set-Cookie de l'upstream (JWT/refresh)
 * - Renvoie le JSON tel quel, y compris Retry-After pour 429
 */

// -- utilitaire: extraire le csrftoken depuis le header Cookie
function extractCsrfFromCookie(cookieHeader: string | undefined): string | null {
  if (!cookieHeader) return null
  const match = cookieHeader.match(/(?:^|;\s*)csrftoken=([^;]+)/i)
  return match ? decodeURIComponent(match[1]) : null
}

// Assainit la valeur CSRF: supprime guillemets/espaces
function sanitizeCsrf(v: string | undefined | null): string {
  const s = (v || '').trim()
  return s.replace(/^"(.*)"$/, '$1')
}

export default defineEventHandler(async (event: H3Event) => {
  const base = djangoBase(event)
  const url = `${base}/api/auth/2fa/email/verify/`

  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const incomingCookies = reqHeaders.cookie || ''
  const cookieCsrf = extractCsrfFromCookie(incomingCookies) || ''
  const headerCsrf = (reqHeaders['x-csrftoken'] as string | undefined) || ''
  const effectiveCsrf = sanitizeCsrf(cookieCsrf || headerCsrf || '')

  const body = (await readBody<Record<string, unknown>>(event).catch(() => ({}))) || {}

  try {
    // Appel en "raw" pour récupérer entêtes (Set-Cookie, Retry-After)
    const upstream = await $fetch.raw(url, {
      method: 'POST',
      headers: {
        cookie: incomingCookies,
        'X-CSRFToken': effectiveCsrf,
        'content-type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body,
      credentials: 'include',
    })

    // Propage Set-Cookie
    const anyHeaders = upstream.headers as any
    const setCookies: string[] | string | undefined =
      anyHeaders?.getSetCookie?.() ||
      anyHeaders?.raw?.()?.['set-cookie'] ||
      upstream.headers.get('set-cookie') ||
      undefined

    if (Array.isArray(setCookies)) {
      event.node.res.setHeader('set-cookie', setCookies)
    } else if (typeof setCookies === 'string') {
      event.node.res.setHeader('set-cookie', setCookies)
    }

    // Propage Retry-After si présent
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
    const detail = e?.data || e?.message || 'Erreur proxy vers /api/auth/2fa/email/verify/'
    // Propage aussi Retry-After en cas d'erreur (ex: 429)
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
        error: 'proxy_eotp_verify_failed',
        detail,
      },
    })
  }
})
