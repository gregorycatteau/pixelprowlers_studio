// app/composables/useNonce.ts
type NonceResponse = { ok?: boolean; nonce?: string }

export function useNonce() {
  const current = useState<string>('nonce:current', () => '')
  const pending = useState<Promise<void> | null>('nonce:pending', () => null)

  const setNonce = (value: string | undefined | null) => {
    if (value) {
      current.value = value
    }
  }

  const refresh = async () => {
    if (pending.value) {
      await pending.value
      return current.value
    }

    const nuxtApp = useNuxtApp()
    const promise = (async () => {
      try {
        const res = await nuxtApp.$fetch<NonceResponse>('/api/auth/nonce/', {
          method: 'POST',
        })
        if (res?.nonce) {
          setNonce(res.nonce)
        }
      } finally {
        pending.value = null
      }
    })()

    pending.value = promise
    await promise
    return current.value
  }

  const cycle = (headers: Headers | Record<string, string> | null | undefined) => {
    if (!headers) return
    let next: string | null = null
    if (headers instanceof Headers) {
      next = headers.get('X-New-Request-Nonce')
    } else if (typeof headers === 'object') {
      const key = Object.keys(headers).find((k) => k.toLowerCase() === 'x-new-request-nonce')
      if (key) next = (headers as Record<string, string>)[key]
    }
    if (next) setNonce(next)
  }

  const clear = () => {
    current.value = ''
  }

  return {
    get current() {
      return current.value
    },
    set current(value: string) {
      current.value = value
    },
    refresh,
    cycle,
    clear,
  }
}
