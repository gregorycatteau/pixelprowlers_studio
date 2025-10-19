import type { H3Event } from 'h3'
import { getRequestHeaders, readBody, createError } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

/**
 * Proxy de connexion vers Django avec gestion explicite des cookies et CSRF.
 *
 * Objectifs sécurité/fonctionnels:
 * - Transmettre les cookies entrants au backend (header `cookie`)
 * - Propager les cookies de session renvoyés par Django (header `set-cookie`)
 * - Ajouter l'entête `X-CSRFToken` à partir de l'entête entrant ou du cookie `csrftoken`
 * - Garder `credentials: 'include'` pour les échanges d'identité côté serveur
 * - Relayer la réponse JSON telle quelle (ex: {"decision":"pending_2fa","fa_required":false})
 * - En cas d'erreur réseau/upstream, renvoyer un JSON clair au frontend
 */

// -- utilitaire: extraire le csrftoken depuis le header Cookie
function extractCsrfFromCookie(cookieHeader: string | undefined): string | null {
  if (!cookieHeader) return null
  // Recherche le cookie Django par défaut: csrftoken
  const match = cookieHeader.match(/(?:^|;\s*)csrftoken=([^;]+)/i)
  return match ? decodeURIComponent(match[1]) : null
}

// Assainit la valeur CSRF (FR): supprime des guillemets éventuels et espaces parasites
function sanitizeCsrf(v: string | undefined | null): string {
  const s = (v || '').trim()
  // Certains navigateurs/inspecteurs affichent les cookies entre guillemets
  return s.replace(/^"(.*)"$/, '$1')
}

export default defineEventHandler(async (event: H3Event) => {
  // Base Django issue de la config serveur (non falsifiable côté client)
  const base = djangoBase(event)
  const url = `${base}/api/auth/login/`

  // Récupère les entêtes de la requête entrante (incluant les cookies)
  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const incomingCookies = reqHeaders.cookie || ''
  // FR: mode "double-submit strict" — on privilégie la valeur du cookie csrftoken
  const cookieCsrf = extractCsrfFromCookie(incomingCookies) || ''
  const headerCsrf = (reqHeaders['x-csrftoken'] as string | undefined) || ''
  // Prefer explicit header (sent by client from latest cookie) then fallback to cookie
  const effectiveCsrf = sanitizeCsrf(headerCsrf || cookieCsrf || '')

  // Lit le corps JSON (identifiant/mot de passe)
  const body = (await readBody<Record<string, unknown>>(event).catch(() => ({}))) || {}

  try {
    // Débogage: émettre l'empreinte CSRF tôt pour qu'elle apparaisse aussi en cas d'erreur (403, etc.)
    try {
      const dbg = [
        cookieCsrf ? `c=${cookieCsrf.slice(0, 8)}` : 'c=-',
        headerCsrf ? `h=${headerCsrf.slice(0, 8)}` : 'h=-',
        effectiveCsrf ? `e=${effectiveCsrf.slice(0, 8)}` : 'e=-',
      ].join(';')
      event.node.res.setHeader('x-csrf-debug', dbg)
    } catch {}

    // Appel en "raw" pour récupérer également les entêtes de réponse (set-cookie)
    const upstream = await $fetch.raw(url, {
      method: 'POST',
      headers: {
        // Cookies & CSRF double-submit
        cookie: incomingCookies,
        'X-CSRFToken': effectiveCsrf,     // CSRF (depuis cookie si dispo)
        'content-type': 'application/json',
        // Ne PAS relayer Origin/Referer vers Django en dev: origine front (3000) ≠ backend (8000)
        // pour éviter un rejet CSRF par vérification d'origine.
        'X-Requested-With': 'XMLHttpRequest',
      },
      body,
      credentials: 'include',
    })

    // Propager les cookies de session renvoyés par Django
    const anyHeaders = upstream.headers as any

    // DEBUG contrôlé: expose des empreintes (tronquées) des valeurs CSRF manipulées
    // (Ne divulgue pas les valeurs complètes — uniquement 8 premiers caractères)
    try {
      const dbg = [
        cookieCsrf ? `c=${cookieCsrf.slice(0, 8)}` : 'c=-',
        headerCsrf ? `h=${headerCsrf.slice(0, 8)}` : 'h=-',
        effectiveCsrf ? `e=${effectiveCsrf.slice(0, 8)}` : 'e=-',
      ].join(';')
      event.node.res.setHeader('x-csrf-debug', dbg)
    } catch {}
    // Support undici (.getSetCookie) / node-fetch (.raw()['set-cookie']) / standard (.get('set-cookie'))
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

    // Relayer le JSON tel quel (décision d'auth côté backend)
    const data = await upstream.json().catch(async () => (upstream as any)._data ?? null)
    // Ajoute aussi une empreinte de corrélation si l’upstream l’a fournie
    try {
      const rid =
        upstream.headers.get('x-correlation-id') ||
        anyHeaders?.get?.('x-correlation-id') ||
        ''
      if (rid) {
        event.node.res.setHeader('x-correlation-id', rid)
      }
    } catch {}
    return data ?? { ok: true }
  } catch (e: any) {
    // En cas d'erreur, renvoyer un JSON exploitable côté UI
    const status = e?.response?.status || 502
    const statusText = e?.response?.statusText || 'Bad Gateway'
    const detail = e?.data || e?.message || 'Erreur proxy vers /api/auth/login/'
    throw createError({
      statusCode: status,
      statusMessage: statusText,
      data: {
        ok: false,
        error: 'proxy_login_failed',
        detail,
      },
    })
  }
})
