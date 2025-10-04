import type { H3Event } from 'h3'
import { djangoBase } from '~/server/utils/djangoBase'

/**
 * Server route (SSR) — Delete Project by slug
 *
 * DELETE /api/projects/[slug]
 * → Proxies to: {DJANGO_BASE_URL}/api/v1/projects/:slug/
 *
 * Notes:
 * - Forwards session cookies and CSRF header (if present) to support session-based auth during V1.
 * - Normalizes upstream failures into a 502 without leaking backend internals.
 */
export default defineEventHandler(async (event: H3Event) => {
  const base = djangoBase(event)

  const { slug } = getRouterParams(event) as { slug?: string }
  if (!slug) {
    throw createError({ statusCode: 400, statusMessage: 'Missing slug' })
  }

  // Forward only headers needed for session-based auth
  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const upstreamHeaders: Record<string, string> = {}
  if (reqHeaders.cookie) upstreamHeaders.cookie = reqHeaders.cookie
  if (reqHeaders['x-csrftoken']) upstreamHeaders['x-csrftoken'] = reqHeaders['x-csrftoken']

  try {
    await $fetch<void>(`${base}/api/v1/projects/${encodeURIComponent(slug)}/`, {
      method: 'DELETE',
      headers: upstreamHeaders,
    })
    return { ok: true }
  } catch (e: any) {
    throw createError({
      statusCode: 502,
      statusMessage: `Proxy error (project delete): ${e?.message || String(e)}`,
    })
  }
})
