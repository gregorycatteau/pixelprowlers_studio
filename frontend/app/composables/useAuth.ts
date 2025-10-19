// app/composables/useAuth.ts

interface AuthUser {
  username: string
  display_name?: string | null
  is_superuser: boolean
  scopes?: string[]
}

interface GateState {
  ok: boolean
  ts: number | null
}

interface LoginResponse {
  ok?: boolean
  next?: string
  user?: AuthUser
}

interface MeResponse {
  ok?: boolean
  user?: AuthUser | null
  gate?: { ok?: boolean; ts?: number | null } | null
}

export function useAuth() {
  const user = useState<AuthUser | null>('auth:user', () => null)
  const gate = useState<GateState>('auth:gate', () => ({ ok: false, ts: null }))
  const hydrated = useState<boolean>('auth:hydrated', () => false)
  const loading = useState<boolean>('auth:loading', () => false)
  const csrf = useCsrf()
  const nonce = useNonce()
  const nuxtApp = useNuxtApp()

  const setUser = (next: AuthUser | null) => {
    user.value = next
  }

  const setGate = (next: GateState | null | undefined) => {
    if (next) {
      gate.value = { ok: Boolean(next.ok), ts: next.ts ?? null }
    } else {
      gate.value = { ok: false, ts: null }
    }
  }

  const reset = () => {
    setUser(null)
    setGate(null)
    hydrated.value = false
    nonce.clear()
  }

  const bootstrap = async () => {
    await csrf.refresh()
  }

  const fetchMe = async (force = false) => {
    if (!force && hydrated.value) {
      return user.value
    }

    loading.value = true
    try {
      const res = (await (nuxtApp as any).$fetch('/api/auth/me', {
        method: 'GET',
        credentials: 'include',
      })) as MeResponse
      if (res?.user && res.ok !== false) {
        setUser({
          username: res.user.username,
          display_name: res.user.display_name,
          is_superuser: Boolean(res.user.is_superuser),
          scopes: res.user.scopes,
        })
        setGate({ ok: Boolean(res.gate?.ok), ts: res.gate?.ts ?? null })
      } else {
        reset()
      }
    } catch (error) {
      reset()
      throw error
    } finally {
      hydrated.value = true
      loading.value = false
    }

    return user.value
  }

  const login = async (payload: { username: string; password: string }) => {
    await csrf.refresh()
    loading.value = true
    try {
      const res = (await (nuxtApp as any).$fetch('/api/auth/login', {
        method: 'POST',
        body: payload,
        credentials: 'include',
        headers: {
          // FR: double-submit cookie côté client → en-tête explicite pour fiabiliser le proxy
          'X-CSRFToken': csrf.token,
        },
      })) as LoginResponse
      if (res?.ok) {
        await fetchMe(true)
        nonce.clear()
      }
      return res
    } finally {
      loading.value = false
    }
  }

  const logout = async () => {
    try {
      await (nuxtApp as any).$fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'X-CSRFToken': csrf.token,
        },
      })
    } finally {
      reset()
      await csrf.refresh().catch(() => {})
    }
  }

  const ensureAuthenticated = async () => {
    try {
      await fetchMe()
    } catch {
      // Ignore, `fetchMe` already reset on failure
    }
    return Boolean(user.value)
  }

  return {
    user,
    gate,
    loading,
    hydrated,
    isAuthenticated: computed(() => Boolean(user.value)),
    isSuperuser: computed(() => Boolean(user.value?.is_superuser)),
    bootstrap,
    fetchMe,
    login,
    logout,
    reset,
    ensureAuthenticated,
    markGate(ok: boolean, ts: number | null = null) {
      gate.value = { ok, ts }
    },
  }
}
