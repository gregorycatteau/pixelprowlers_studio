import type { H3Event } from 'h3'
import type { ProjectsResponse } from '~~/shared/types/projects'
import { djangoBase } from '~~/server/utils/djangoBase'

/**
 * Server route (SSR) — List Projects
 *
 * Proxies the Django API v1 endpoint using the server runtime config and
 * forwards the session cookies (and CSRF header if present).
 *
 * GET /server/api/projects
 * → GET {DJANGO_BASE_URL}/api/v1/projects/
 */
export default defineEventHandler(async (event: H3Event): Promise<ProjectsResponse> => {
  const base = djangoBase(event)
  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>

  // Only forward the minimal set of headers needed for session-based auth.
  const upstreamHeaders: Record<string, string> = {}
  if (reqHeaders.cookie) upstreamHeaders.cookie = reqHeaders.cookie
  if (reqHeaders['x-csrftoken']) upstreamHeaders['x-csrftoken'] = reqHeaders['x-csrftoken']

  try {
    const data = await $fetch<ProjectsResponse>(`${base}/api/v1/projects/`, {
      method: 'GET',
      headers: upstreamHeaders,
    })
    return data
  } catch (e: any) {
    // Normalize error into a Nitro error (do not leak backend internals)
    throw createError({
      statusCode: 502,
      statusMessage: `Proxy error (projects list): ${e?.message || String(e)}`,
    })
  }
})
