import type { H3Event } from 'h3'
import type { ProjectUpdateBody, ProjectResponse } from '~/shared/types/projects'
import { djangoBase } from '~/server/utils/djangoBase'

/**
 * Server route (SSR) — Update Project by slug
 *
 * PATCH /api/projects/[slug]
 * Body: Partial<ProjectUpdateBody>
 * → Proxies to: {DJANGO_BASE_URL}/api/v1/projects/:slug/
 *
 * Notes:
 * - Forwards session cookies and CSRF header (if present) to support session-based auth during V1.
 * - Normalizes upstream failures into a 502 without leaking backend internals.
 */
export default defineEventHandler(async (event: H3Event): Promise<ProjectResponse> => {
  const base = djangoBase(event)

  const { slug } = getRouterParams(event) as { slug?: string }
  if (!slug) {
    throw createError({ statusCode: 400, statusMessage: 'Missing slug' })
  }

  const body = (await readBody(event)) as Partial<ProjectUpdateBody> | null
  if (!body || typeof body !== 'object') {
    throw createError({ statusCode: 400, statusMessage: 'Invalid body' })
  }

  // Forward only headers needed for session-based auth
  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const upstreamHeaders: Record<string, string> = { 'content-type': 'application/json' }
  if (reqHeaders.cookie) upstreamHeaders.cookie = reqHeaders.cookie
  if (reqHeaders['x-csrftoken']) upstreamHeaders['x-csrftoken'] = reqHeaders['x-csrftoken']

  try {
    const data = await $fetch<ProjectResponse>(`${base}/api/v1/projects/${encodeURIComponent(slug)}/`, {
      method: 'PATCH',
      headers: upstreamHeaders,
      body,
    })
    return data
  } catch (e: any) {
    throw createError({
      statusCode: 502,
      statusMessage: `Proxy error (project update): ${e?.message || String(e)}`,
    })
  }
})
