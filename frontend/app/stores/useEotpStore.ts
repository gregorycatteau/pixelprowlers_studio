/* frontend/app/stores/useEotpStore.ts */
import { defineStore } from 'pinia'
import type { FetchError } from 'ofetch'
import { useRuntimeConfig, useCsrf } from '#imports'

export type EotpStatus =
  | 'idle'
  | 'pending'
  | 'verifying'
  | 'ok'
  | 'invalid'
  | 'expired'
  | 'locked'
  | 'rate_limited'
  | 'error'

type VerifyResult = { ok: boolean; status: EotpStatus }
type ResendResult = { ok: boolean }

export const useEotpStore = defineStore('eotp', {
  state: () => ({
    status: 'idle' as EotpStatus,
    // Horodatage d’expiration côté front (ms, source = backend)
    expiresAt: null as number | null,
    // Cooldowns (sec)
    retryAfterVerify: 0,
    retryAfterResend: 0,
    // Tentatives restantes (si exposées plus tard)
    attemptsLeft: null as number | null,
    // Dernière erreur non sensible pour UI
    lastError: '' as '' | 'invalid' | 'expired' | 'locked' | 'rate_limited' | 'transport',
  }),
  getters: {
    ttlLeftSec(state): number {
      if (!state.expiresAt) return 0
      const ms = state.expiresAt - Date.now()
      return Math.max(0, Math.floor(ms / 1000))
    },
    cooldownActive(state): boolean {
      return state.retryAfterVerify > 0 || state.retryAfterResend > 0
    },
  },
  actions: {
    setExpiresInSeconds(expIn: number) {
      const ts = Date.now() + Math.max(0, Math.round(expIn)) * 1000
      this.expiresAt = ts
      try {
        // Mémoire session seulement (pas de localStorage persistant)
        sessionStorage.setItem('eotp_expires_at', String(ts))
      } catch {
        /* no-op */
      }
    },
    hydrateExpiresFromSession(fallbackSec = 300) {
      try {
        const raw = (sessionStorage.getItem('eotp_expires_at') || '').trim()
        const ts = Number(raw)
        if (Number.isFinite(ts) && ts > Date.now()) {
          this.expiresAt = ts
          return
        }
      } catch {
        /* ignore */
      }
      this.expiresAt = Date.now() + fallbackSec * 1000
    },
    decrementCooldownsTick() {
      if (this.retryAfterVerify > 0) this.retryAfterVerify = Math.max(0, this.retryAfterVerify - 1)
      if (this.retryAfterResend > 0) this.retryAfterResend = Math.max(0, this.retryAfterResend - 1)
    },
    async verify(code: string): Promise<VerifyResult> {
      const csrf = useCsrf()
      this.status = 'verifying'
      this.lastError = ''
      try {
        await csrf.refresh().catch(() => {})
        const res = await $fetch('/api/auth/2fa/email/verify/', {
          method: 'POST',
          body: { code: (code || '').toString() },
          credentials: 'include',
          headers: { 'X-CSRFToken': csrf.token },
        })
        // Succès: laisser la redirection à l’UI appelante
        this.status = 'ok'
        this.lastError = ''
        return { ok: true, status: 'ok' }
      } catch (err) {
        const error = err as FetchError<any>
        const status = error?.response?.status
        if (status === 429) {
          // Respecter Retry-After
          const raHeader =
            error.response?.headers?.get?.('Retry-After') ||
            (error as any)?.response?.headers?.['retry-after']
          const sec = raHeader ? Number(raHeader) : 30
          this.retryAfterVerify = Number.isFinite(sec) ? Math.max(1, Math.round(sec)) : 30
          this.status = 'rate_limited'
          this.lastError = 'rate_limited'
          return { ok: false, status: 'rate_limited' }
        }
        if (status === 401 || status === 422) {
          // UI affichera un message générique “Code invalide”
          this.status = 'invalid'
          this.lastError = 'invalid'
          return { ok: false, status: 'invalid' }
        }
        if (status === 403) {
          // Peut représenter expired (selon mapping backend)
          this.status = 'expired'
          this.lastError = 'expired'
          return { ok: false, status: 'expired' }
        }
        this.status = 'error'
        this.lastError = 'transport'
        return { ok: false, status: 'error' }
      }
    },
    async resend(): Promise<ResendResult> {
      const csrf = useCsrf()
      this.lastError = ''
      try {
        await csrf.refresh().catch(() => {})
        const body = (await $fetch('/api/auth/2fa/email/resend/', {
          method: 'POST',
          credentials: 'include',
          headers: { 'X-CSRFToken': csrf.token },
        })) as any
        // Corps attendu (S1/S2): { ok: true, retry_after: number, expires_in: number }
        const ra = Number(body?.retry_after)
        this.retryAfterResend = Number.isFinite(ra) ? Math.max(1, Math.round(ra)) : Math.max(1, 30)
        const expIn = Number(body?.expires_in)
        this.setExpiresInSeconds(Number.isFinite(expIn) ? expIn : 300)
        return { ok: true }
      } catch (err) {
        const error = err as FetchError<any>
        const status = error?.response?.status
        if (status === 429) {
          const raHeader =
            error.response?.headers?.get?.('Retry-After') ||
            (error as any)?.response?.headers?.['retry-after']
          const sec = raHeader ? Number(raHeader) : 60
          this.retryAfterResend = Number.isFinite(sec) ? Math.max(1, Math.round(sec)) : 60
          this.lastError = 'rate_limited'
          return { ok: false }
        }
        this.lastError = 'transport'
        return { ok: false }
      }
    },
    async fetchPeek(): Promise<{ ok: boolean; code?: string }> {
      // Dev/test uniquement
      const cfg = useRuntimeConfig()
      const env = (cfg.public?.appEnv || 'dev').toLowerCase()
      if (env !== 'test' && env !== 'dev') {
        return { ok: false }
      }
      try {
        const res = (await $fetch('/api/auth/2fa/email/_peek/', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        })) as any
        const code = String(res?.code || '')
        return { ok: !!code, code }
      } catch {
        return { ok: false }
      }
    },
  },
})
