import type { H3Event } from 'h3'
import { getRequestHeaders, createError } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

/**
 * Proxy CSRF robuste:
 * - Propage les cookies entrants (header `cookie`) pour les stratégies de rotation/refresh
 * - Passe `credentials: 'include'` pour laisser Django émettre le cookie CSRF
 * - Récupère et relaie les entêtes `set-cookie` vers le client
 * - Relaye le JSON tel quel (ex: { ok: true, csrf: "..." })
 * - En cas d'erreur, renvoie une structure JSON explicite
 */
export default defineEventHandler(async (event: H3Event) => {
  const base = djangoBase(event)
  const url = `${base}/api/auth/csrf/`

  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const incomingCookies = reqHeaders.cookie || ''

  try {
    const upstream = await $fetch.raw(url, {
      method: 'GET',
      headers: {
        cookie: incomingCookies,
      },
      credentials: 'include',
    })

    // Propagation Set-Cookie (csrftoken)
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
    const detail = e?.data || e?.message || 'Erreur proxy vers /api/auth/csrf/'
    throw createError({
      statusCode: status,
      statusMessage: statusText,
      data: {
        ok: false,
        error: 'proxy_csrf_failed',
        detail,
      },
    })
  }
})
