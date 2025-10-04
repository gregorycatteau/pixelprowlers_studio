import type { H3Event } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

/** Payload attendu côté Django */
interface CredsPayload {
  username: string
  password: string
}

/** Réponse normalisée renvoyée par Django */
interface CredsResponse {
  status: 'pending' | 'ok' | 'blocked' | 'error'
  next?: string[] // ex: ['theme','profile']
  message?: string // optionnel, neutre
}

/** Handler typé pour éviter tout any implicite */
async function handler(event: H3Event): Promise<CredsResponse> {
  const body = await readBody<CredsPayload>(event)
  const base = djangoBase(event)
  const headers = getRequestHeaders(event)

  try {
    const res = await $fetch<CredsResponse>(`${base}/api/auth/creds/`, {
      method: 'POST',
      body,
      headers: { cookie: headers.cookie || '' },
      credentials: 'include',
    })
    return res
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    throw createError({ statusCode: 502, statusMessage: `Proxy error (creds): ${msg}` })
  }
}

export default defineEventHandler(handler)
