import type { H3Event } from 'h3'
import type { AgentsResponse, AgentSummary } from '~/shared/types/agents'

export default defineEventHandler(async (event: H3Event): Promise<AgentsResponse> => {
  const cfg = useRuntimeConfig(event)
  const base =
    cfg.public?.DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || 'http://localhost:8000'

  const headers = getRequestHeaders(event)

  try {
    // Le backend retourne { agents: [...] }
    const res = await $fetch<AgentsResponse>(`${base}/api/agents/`, {
      method: 'GET',
      headers: {
        // on forward les cookies de session (sessionid, csrftoken…)
        cookie: headers.cookie ?? '',
      },
    })
    return res
  } catch (e: any) {
    throw createError({
      statusCode: 502,
      statusMessage: `Proxy error (agents): ${e?.message || e}`,
    })
  }
})
