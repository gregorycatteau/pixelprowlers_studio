/* @vitest-environment jsdom */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TwoFA from '../pages/login/2fa.vue'
import { useEotpStore } from '../stores/useEotpStore'

// Mock navigateTo from Nuxt (#app)
vi.mock('#app', () => ({
  navigateTo: vi.fn().mockResolvedValue(undefined),
}))

describe('Page /login/2fa.vue (e‑OTP UI)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    // reset session storage used by store.hydrateExpiresFromSession
    try {
      sessionStorage.clear()
    } catch {}
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  const mountPage = () =>
    mount(TwoFA, {
      global: {
        stubs: {
          PxToast: true,
        },
      },
    })

  it('normalise la saisie (digits‑only, trim espaces/tirets)', async () => {
    const wrapper = mountPage()
    const input = wrapper.get('[data-testid="code"]') // unique champ
    await input.setValue('AB CD-12')
    // onCodeInput conserve seulement les chiffres
    expect((input.element as HTMLInputElement).value).toBe('12')
  })

  it('timer basé sur expires_at: décompte et état expiré à 0', async () => {
    const store = useEotpStore()
    // TTL = 3s
    store.setExpiresInSeconds(3)
    const wrapper = mountPage()
    const start = Date.now()

    // Avance de 2s → devrait afficher ~1s restant
    await vi.advanceTimersByTimeAsync(2000)
    vi.setSystemTime(new Date(start + 2000))
    await wrapper.vm.$nextTick()
    const ttlNode = wrapper.get('#ttl')
    expect(ttlNode.text()).toMatch(/encore\s+[0-3]/) // tolérance timing (délais setInterval)

    // Force l’expiration de manière déterministe (évite la dépendance à Date.now())
    store.expiresAt = Date.now() - 1000
    await wrapper.vm.$nextTick()
    expect(wrapper.get('#ttl').text().toLowerCase()).toContain('expiré')
  })

  it('resend: bouton désactivé pendant Retry‑After puis réactivé', async () => {
    const store = useEotpStore()
    store.retryAfterResend = 3
    const wrapper = mountPage()
    const btn = wrapper.get('[data-testid="btn-resend"]')

    expect((btn.element as HTMLButtonElement).disabled).toBe(true)

    // Le composant décrémente via setInterval(() => store.decrementCooldownsTick())
    vi.advanceTimersByTime(3000)
    await wrapper.vm.$nextTick()
    expect((btn.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('messages UI unifiés pour invalid/expired, spécifiques pour locked', async () => {
    const store = useEotpStore()
    const wrapper = mountPage()

    store.status = 'invalid'
    await wrapper.vm.$nextTick()
    expect(wrapper.get('#msg').text()).toContain('Code invalide')

    store.status = 'expired'
    await wrapper.vm.$nextTick()
    expect(wrapper.get('#msg').text()).toContain('Code invalide')

    store.status = 'locked'
    await wrapper.vm.$nextTick()
    expect(wrapper.get('#msg').text()).toMatch(/Trop de tentatives/i)
  })
})
