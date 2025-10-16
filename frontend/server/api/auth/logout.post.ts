import type { H3Event } from 'h3'
import { getRequestHeaders, createError } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

/**
 * Proxy de déconnexion vers Django avec gestion cookies + CSRF.
 *
 * Points clés (FR):
 * - Propage les cookies de session entrants (header `cookie`)
 * - Ajoute l'entête `X-CSRFToken` à partir de l'entête ou du cookie `csrftoken`
 * - Passe `credentials: 'include'` pour laisser Django invalider la session
 * - Relaye les entêtes `set-cookie` (ex: purge session côté client)
 * - En cas d'erreur upstream, renvoie un JSON clair
 */

// -- utilitaire: extraire le csrftoken depuis le header Cookie
function extractCsrfFromCookie(cookieHeader: string | undefined): string | null {
  if (!cookieHeader) return null
  const match = cookieHeader.match(/(?:^|;\s*)csrftoken=([^;]+)/i)
  return match ? decodeURIComponent(match[1]) : null
}

export default defineEventHandler(async (event: H3Event) => {
  const base = djangoBase(event)
  const url = `${base}/api/auth/logout/`

  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const incomingCookies = reqHeaders.cookie || ''
  const incomingCsrf = reqHeaders['x-csrftoken'] || extractCsrfFromCookie(incomingCookies) || ''

  try {
    const upstream = await $fetch.raw(url, {
      method: 'POST',
      headers: {
        cookie: incomingCookies,
        'x-csrftoken': incomingCsrf,
      },
      credentials: 'include',
    })

    // Propage Set-Cookie si le backend nettoie la session
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

    const data = await upstream.json().catch(async () => (upstream as any)._data ?? null)
    return data ?? { ok: true }
  } catch (e: any) {
    const status = e?.response?.status || 502
    const statusText = e?.response?.statusText || 'Bad Gateway'
    const detail = e?.data || e?.message || 'Erreur proxy vers /api/auth/logout/'
    throw createError({
      statusCode: status,
      statusMessage: statusText,
      data: {
        ok: false,
        error: 'proxy_logout_failed',
        detail,
      },
    })
  }
})
