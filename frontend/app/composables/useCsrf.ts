// app/composables/useCsrf.ts
type CsrfResponse = { ok?: boolean; csrf?: string }

const COOKIE_NAME = 'csrftoken'

function readCookie(name: string): string {
  if (process.server) return ''
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

export function useCsrf() {
  const token = useState<string>('csrf:token', () => (process.client ? readCookie(COOKIE_NAME) : ''))
  const pending = useState<Promise<void> | null>('csrf:pending', () => null)

  const setToken = (value: string | undefined | null) => {
    if (value) {
      token.value = value
    }
  }

  const refresh = async () => {
    if (pending.value) {
      await pending.value
      return token.value
    }

    const nuxtApp = useNuxtApp()
    const promise = (async () => {
      try {
        const res = await nuxtApp.$fetch<CsrfResponse>('/api/auth/csrf/', {
          method: 'GET',
        })
        if (res?.csrf) {
          setToken(res.csrf)
        } else if (process.client) {
          setToken(readCookie(COOKIE_NAME))
        }
      } finally {
        pending.value = null
      }
    })()

    pending.value = promise
    await promise
    return token.value
  }

  return {
    get token() {
      return token.value
    },
    refresh,
  }
}
