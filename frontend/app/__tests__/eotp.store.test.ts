/* @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock Nuxt composables imported via #imports
vi.mock('#imports', () => {
  return {
    useCsrf: () => ({
      token: 't',
      refresh: vi.fn().mockResolvedValue(undefined),
    }),
    useRuntimeConfig: () => ({
      public: { appEnv: 'test' },
    }),
  }
})

// Global $fetch mock helper
const setFetchResponse = (impl: (input: any, init?: any) => any) => {
  // @ts-expect-error define global
  globalThis.$fetch = impl
}

describe('useEotpStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // Clean session storage between tests
    try {
      sessionStorage.clear()
    } catch {}
  })

  afterEach(() => {
    vi.useRealTimers()
    // @ts-expect-error cleanup
    delete globalThis.$fetch
  })

  it('sets expiresAt from expires_in and computes ttlLeftSec', async () => {
    const { useEotpStore } = await import('../stores/useEotpStore')
    const store = useEotpStore()
    store.setExpiresInSeconds(60)
    expect(store.expiresAt).toBeGreaterThan(Date.now())
    const ttl = store.ttlLeftSec
    expect(ttl).toBeGreaterThan(0)
    expect(ttl).toBeLessThanOrEqual(60)
  })

  it('hydrates expiresAt from sessionStorage or fallback', async () => {
    const { useEotpStore } = await import('../stores/useEotpStore')
    const store = useEotpStore()

    // No value → fallback ~300s
    store.hydrateExpiresFromSession(300)
    let ttl = store.ttlLeftSec
    expect(ttl).toBeGreaterThan(200)

    // With a valid future timestamp
    const future = Date.now() + 90_000
    sessionStorage.setItem('eotp_expires_at', String(future))
    store.hydrateExpiresFromSession(300)
    ttl = store.ttlLeftSec
    expect(ttl).toBeGreaterThanOrEqual(80)
    expect(ttl).toBeLessThanOrEqual(90)
  })

  it('resend() reads retry_after and expires_in from success body', async () => {
    const { useEotpStore } = await import('../stores/useEotpStore')
    const store = useEotpStore()

    setFetchResponse(async () => {
      return { ok: true, retry_after: 25, expires_in: 180 }
    })

    const r = await store.resend()
    expect(r.ok).toBe(true)
    expect(store.retryAfterResend).toBe(25)
    expect(store.ttlLeftSec).toBeGreaterThanOrEqual(170)
  })

  it('resend() handles 429 and sets retryAfterResend from Retry-After header', async () => {
    const { useEotpStore } = await import('../stores/useEotpStore')
    const store = useEotpStore()

    const headers = new Headers({ 'Retry-After': '45' })
    const error: any = {
      response: {
        status: 429,
        headers,
      },
    }
    setFetchResponse(async () => {
      throw error
    })

    const r = await store.resend()
    expect(r.ok).toBe(false)
    expect(store.retryAfterResend).toBe(45)
    expect(store.lastError).toBe('rate_limited')
  })

  it('verify() handles 200 OK', async () => {
    const { useEotpStore } = await import('../stores/useEotpStore')
    const store = useEotpStore()

    setFetchResponse(async () => {
      return { ok: true }
    })

    const r = await store.verify('123456')
    expect(r.ok).toBe(true)
    expect(store.status).toBe('ok')
    expect(store.lastError).toBe('')
  })

  it('verify() handles 429 with Retry-After', async () => {
    const { useEotpStore } = await import('../stores/useEotpStore')
    const store = useEotpStore()

    const headers = new Headers({ 'Retry-After': '15' })
    const error: any = {
      response: {
        status: 429,
        headers,
      },
    }
    setFetchResponse(async () => {
      throw error
    })

    const r = await store.verify('123456')
    expect(r.ok).toBe(false)
    expect(r.status).toBe('rate_limited')
    expect(store.retryAfterVerify).toBe(15)
    expect(store.status).toBe('rate_limited')
    expect(store.lastError).toBe('rate_limited')
  })

  it('cooldown tick decrements both verify/resend timers', async () => {
    const { useEotpStore } = await import('../stores/useEotpStore')
    const store = useEotpStore()
    store.retryAfterVerify = 3
    store.retryAfterResend = 2
    store.decrementCooldownsTick()
    expect(store.retryAfterVerify).toBe(2)
    expect(store.retryAfterResend).toBe(1)
  })
})
