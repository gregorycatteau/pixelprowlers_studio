// frontend/server/api/agents/[slug]/ask.post.ts
import type { EventHandler, H3Event } from 'h3'

type AskPostBody = {
  message: string
  temperature?: number
  max_tokens?: number
}

type AskResponse = {
  ok: boolean
  agent: string
  provider?: string
  model_uri?: string
  output?: string | Record<string, unknown>
  tokens_in?: number
  tokens_out?: number
  cost_eur?: number
  latency_ms?: number
  error?: string
  blocked_reason?: string
}

const handler: EventHandler = defineEventHandler(async (event: H3Event): Promise<AskResponse> => {
  // --- params ---
  const params = getRouterParams(event) as Record<string, string>
  const slug = params?.slug
  if (!slug) {
    throw createError({ statusCode: 400, statusMessage: 'Missing "slug" param' })
  }

  // --- body (validation légère) ---
  const rawBody = await readBody(event)
  const payload: AskPostBody = {
    message: (rawBody as any)?.message ?? '',
    temperature: (rawBody as any)?.temperature,
    max_tokens: (rawBody as any)?.max_tokens,
  }
  if (typeof payload.message !== 'string' || payload.message.trim().length === 0) {
    throw createError({ statusCode: 400, statusMessage: 'Missing/invalid "message" in body' })
  }

  // --- cible backend Django ---
  const cfg = useRuntimeConfig(event)
  const base =
    cfg.public?.DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || 'http://localhost:8000'

  // --- headers à forward ---
  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const upstreamHeaders: Record<string, string> = { 'content-type': 'application/json' }
  if (reqHeaders.cookie) upstreamHeaders.cookie = reqHeaders.cookie
  if (reqHeaders['x-csrftoken']) upstreamHeaders['x-csrftoken'] = reqHeaders['x-csrftoken']

  // --- appel upstream ---
  const res: AskResponse = await $fetch<AskResponse>(
    `${base}/api/agents/${encodeURIComponent(slug)}/ask`,
    { method: 'POST', headers: upstreamHeaders, body: payload },
  ).catch((e: any) => {
    throw createError({
      statusCode: 502,
      statusMessage: `Proxy error (ask:${slug}): ${e?.message || String(e)}`,
    })
  })

  return res
})

export default handler
