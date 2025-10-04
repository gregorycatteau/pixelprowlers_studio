import type { H3Event } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

interface ThemePayload {
  hue: number
}
interface GenericOk {
  ok: boolean
  message?: string
}

async function handler(event: H3Event): Promise<GenericOk> {
  const body = await readBody<ThemePayload>(event)
  const base = djangoBase(event)
  const headers = getRequestHeaders(event)

  try {
    const res = await $fetch<GenericOk>(`${base}/api/auth/theme/`, {
      method: 'POST',
      body,
      headers: { cookie: headers.cookie || '' },
      credentials: 'include',
    })
    return res
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    throw createError({ statusCode: 502, statusMessage: `Proxy error (theme): ${msg}` })
  }
}

export default defineEventHandler(handler)
