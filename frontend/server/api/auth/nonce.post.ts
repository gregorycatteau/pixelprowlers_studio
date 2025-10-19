// frontend/server/api/auth/nonce.post.ts
import type { H3Event } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

type NonceResponse = {
  ok: boolean
  nonce: string
  expires_in: number
}

export default defineEventHandler(async (event: H3Event) => {
  const base = djangoBase(event)

  const reqHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const upstreamHeaders: Record<string, string> = { 'content-type': 'application/json' }
  if (reqHeaders.cookie) upstreamHeaders.cookie = reqHeaders.cookie
  if (reqHeaders['x-csrftoken']) upstreamHeaders['x-csrftoken'] = reqHeaders['x-csrftoken']

  const res = await $fetch<NonceResponse>(`${base}/api/auth/nonce/`, {
    method: 'POST',
    headers: upstreamHeaders,
    // no body needed
  }).catch((e: any) => {
    throw createError({
      statusCode: 502,
      statusMessage: `Proxy error (nonce): ${e?.message || String(e)}`,
    })
  })

  return res
})
