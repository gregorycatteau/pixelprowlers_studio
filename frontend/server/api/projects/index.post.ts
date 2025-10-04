import type { H3Event } from 'h3'
import type { ProjectCreateBody, ProjectResponse } from '~/shared/types/projects'
import { djangoBase } from '~/server/utils/djangoBase'

/**
 * Server route (SSR) — Create Project
 *
 * POST /api/projects
 * Body: { name: string, description?, status?, slug?, metadata? }
 * → Proxied to: {DJANGO_BASE_URL}/api/v1/projects/
 *
 * Notes:
 * - Forwards session cookies and CSRF header (if present) to support session-based auth during V1.
 * - Does not leak backend internals; normalizes errors as Nitro errors.
 */
export default defineEventHandler(async (event: H3Event): Promise<ProjectResponse> => {
  const base = djangoBase(event)

  // Forward only required headers (session cookies and CSRF if present)
  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const upstreamHeaders: Record<string, string> = { 'content-type': 'application/json' }
  if (reqHeaders.cookie) upstreamHeaders.cookie = reqHeaders.cookie
  if (reqHeaders['x-csrftoken']) upstreamHeaders['x-csrftoken'] = reqHeaders['x-csrftoken']

  // Basic validation (server-side) — backend performs strict validation as well
  const body = (await readBody(event)) as Partial<ProjectCreateBody>
  if (!body || typeof body.name !== 'string' || body.name.trim().length === 0) {
    throw createError({ statusCode: 400, statusMessage: 'Missing/invalid "name"' })
  }

  try {
    const data = await $fetch<ProjectResponse>(`${base}/api/v1/projects/`, {
      method: 'POST',
      headers: upstreamHeaders,
      body,
    })
    return data
  } catch (e: any) {
    // Normalize into a 502 to avoid leaking upstream internals
    throw createError({
      statusCode: 502,
      statusMessage: `Proxy error (create project): ${e?.message || String(e)}`,
    })
  }
})
