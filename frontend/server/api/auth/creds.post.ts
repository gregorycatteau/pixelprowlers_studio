// server/api/auth.post.ts (Nuxt 3 / Nitro) — Version corrigée TypeScript
import type { H3Event } from 'h3'
import { defineEventHandler, readBody, getRequestHeaders, createError } from 'h3'
import { $fetch } from 'ofetch'
import { djangoBase } from '../../utils/djangoBase'

/** Actions et payloads pris en charge par la route serveur Nuxt (proxy vers Django) */
type AuthAction =
  | 'login'
  | 'totpBootstrap'
  | 'totpActivate'
  | 'totpVerify'
  | 'webauthnOptions'
  | 'webauthnVerify'
  | 'nonce'
  | 'nonceVerify'

interface LoginPayload {
  action?: 'login'
  username?: string
  email?: string
  password: string
}
interface TotpBootstrapPayload { action: 'totpBootstrap' }
interface TotpActivatePayload { action: 'totpActivate'; otp: string }
interface TotpVerifyPayload { action: 'totpVerify'; otp: string }
interface WebAuthnOptionsPayload { action: 'webauthnOptions'; username?: string }
interface WebAuthnVerifyPayload { action: 'webauthnVerify'; credential: Record<string, unknown>; username?: string }
interface NonceGetPayload { action: 'nonce' }
interface NonceVerifyPayload { action: 'nonceVerify'; nonce: string; assertion?: Record<string, unknown> }

type RequestBody =
  | LoginPayload
  | TotpBootstrapPayload
  | TotpActivatePayload
  | TotpVerifyPayload
  | WebAuthnOptionsPayload
  | WebAuthnVerifyPayload
  | NonceGetPayload
  | NonceVerifyPayload

/** Réponse générique JSON (on passe‐through la réponse du backend) */
type ApiJson = Record<string, unknown>

/**
 * Handler typé pour router vers les endpoints d’auth Django
 *
 * Sécurité :
 * - On ne propage jamais de headers avec valeurs undefined (interdit par HeadersInit).
 * - On ajoute les tokens Turnstile uniquement s’ils existent.
 * - On forward explicitement le cookie pour coller à la session Django.
 */
async function handler(event: H3Event): Promise<ApiJson> {
  const body = (await readBody<RequestBody>(event)) || ({} as RequestBody)
  const base = djangoBase(event)

  // Récupération des headers entrants
  const inHeaders = getRequestHeaders(event) as Record<string, string | undefined>
  const cookies = inHeaders.cookie ?? ''

  // Token Turnstile : présent soit dans le body, soit dans certains headers
  const ts =
    (body as any)?.turnstile as string | undefined ||
    inHeaders['cf-turnstile-token'] ||
    inHeaders['x-turnstile-token']

  // Action courante
  const action: AuthAction = ((body as any).action as AuthAction) || 'login'

  // Préparation de la cible et du payload
  let url = ''
  let method: 'GET' | 'POST' = 'POST'
  let upstreamBody: Record<string, any> | null | undefined = undefined

  switch (action) {
    case 'login': {
      // Map legacy {username,password} -> {email,password}
      const email = (body as any).email || (body as any).username || ''
      url = `${base}/api/auth/login/`
      method = 'POST'
      upstreamBody = { email, password: (body as any).password }
      break
    }
    case 'totpBootstrap': {
      url = `${base}/api/auth/totp/bootstrap/`
      method = 'GET'
      break
    }
    case 'totpActivate': {
      url = `${base}/api/auth/totp/activate/`
      method = 'POST'
      upstreamBody = { otp: (body as any).otp }
      break
    }
    case 'totpVerify': {
      url = `${base}/api/auth/totp/verify/`
      method = 'POST'
      upstreamBody = { otp: (body as any).otp }
      break
    }
    case 'webauthnOptions': {
      url = `${base}/api/auth/webauthn/options/`
      method = 'POST'
      upstreamBody = { username: (body as any).username }
      break
    }
    case 'webauthnVerify': {
      url = `${base}/api/auth/webauthn/verify/`
      method = 'POST'
      upstreamBody = {
        credential: (body as any).credential,
        username: (body as any).username,
      }
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
      upstreamBody = {
        nonce: (body as any).nonce,
        assertion: (body as any).assertion,
      }
      break
    }
    default: {
      // Fallback: login
      const email = (body as any).email || (body as any).username || ''
      url = `${base}/api/auth/login/`
      method = 'POST'
      upstreamBody = { email, password: (body as any).password }
    }
  }

  // ---- IMPORTANT : construire des headers strictement string → string
  const headers: Record<string, string> = { cookie: cookies }
  if (ts) {
    headers['CF-Turnstile-Token'] = ts
    headers['X-Turnstile-Token'] = ts
  }

  try {
    const res = await $fetch<ApiJson>(url, {
      method,
      headers,
      ...(method === 'POST' ? { body: upstreamBody } : {}),
      // Note : `credentials` n’a pas d’effet côté serveur ofetch/Nitro ; on forward déjà le cookie explicitement.
    })
    return res
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    throw createError({
      statusCode: 502,
      statusMessage: `Proxy error (auth:${action}): ${msg}`,
    })
  }
}

export default defineEventHandler(handler)
