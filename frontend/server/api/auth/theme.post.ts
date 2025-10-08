import type { H3Event } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

interface ThemePayload {
  hue: number
}
interface GenericOk {
  ok: boolean
  message?: string
}

/**
 * Extended handler:
 * - Default: POST /api/auth/theme (existing behavior)
 * - Also proxies (by action in body) to:
 *   - webauthnOptions  -> POST /api/auth/webauthn/options/
 *   - webauthnVerify   -> POST /api/auth/webauthn/verify/
 *   - nonce            -> GET  /api/auth/nonce/
 *   - nonceVerify      -> POST /api/auth/nonce/verify/
 *
 * This keeps backward compatibility for ThemeHuePicker while exposing auth utilities.
 */
type AuthAction = 'theme' | 'webauthnOptions' | 'webauthnVerify' | 'nonce' | 'nonceVerify'

async function handler(event: H3Event): Promise<Record<string, unknown>> {
  const base = djangoBase(event)
  const headers = getRequestHeaders(event) as Record<string, string | undefined>
  const cookies = headers.cookie || ''
  const body = (await readBody<any>(event)) || {}
  const action: AuthAction = (body?.action as AuthAction) || 'theme'

  let url = ''
  let method: 'GET' | 'POST' = 'POST'
  let upstreamBody: any = undefined

  switch (action) {
    case 'webauthnOptions': {
      url = `${base}/api/auth/webauthn/options/`
      method = 'POST'
      upstreamBody = { username: body?.username }
      break
    }
    case 'webauthnVerify': {
      url = `${base}/api/auth/webauthn/verify/`
      method = 'POST'
      upstreamBody = { credential: body?.credential, username: body?.username }
      break
    }
    case 'nonce': {
      url = `${base}/api/auth/nonce/`
      method = 'GET'
      break
    }
    case 'nonceVerify': {
      url = `${base}/api/auth/nonce/verify/`
      method = 'POST'
      upstreamBody = { nonce: body?.nonce, assertion: body?.assertion }
      break
    }
    case 'theme':
    default: {
      // Back-compat: theme update (original behavior)
      url = `${base}/api/auth/theme/`
      method = 'POST'
      upstreamBody = { hue: (body as ThemePayload)?.hue }
      break
    }
  }

  try {
    const res = await $fetch<Record<string, unknown>>(url, {
      method,
      headers: { cookie: cookies },
      ...(method === 'POST' ? { body: upstreamBody } : {}),
      credentials: 'include',
    })
    return res
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    const tag = action === 'theme' ? 'theme' : `auth:${action}`
    throw createError({ statusCode: 502, statusMessage: `Proxy error (${tag}): ${msg}` })
  }
}

export default defineEventHandler(handler)
