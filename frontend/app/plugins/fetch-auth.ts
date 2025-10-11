// app/plugins/fetch-auth.ts
import { defineNuxtPlugin, navigateTo } from '#app'

const MUTATIVE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
const NONCE_URL_PATTERN = /\/api\/(gates|agents|conversations|messages)\b/

export default defineNuxtPlugin((nuxtApp) => {
  const auth = useAuth()
  const csrf = useCsrf()
  const nonce = useNonce()

  const client = $fetch.create({
    credentials: 'include',
    retry: 0,
    async onRequest({ request, options }) {
      options.credentials = 'include'

      const method = (options.method || 'GET').toString().toUpperCase()
      if (MUTATIVE_METHODS.has(method)) {
        const headers = new Headers(options.headers as HeadersInit | undefined)
        if (csrf.token) {
          headers.set('X-CSRFToken', csrf.token)
        }

        const target =
          typeof request === 'string'
            ? request
            : request instanceof Request
              ? request.url
              : ''
        if (target && NONCE_URL_PATTERN.test(target) && nonce.current) {
          headers.set('X-Request-Nonce', nonce.current)
        }

        headers.set('X-Requested-With', 'XMLHttpRequest')
        options.headers = Object.fromEntries(headers.entries())
      }
    },
    onResponse({ response }) {
      nonce.cycle(response.headers)
    },
    async onResponseError(context) {
      const { request, options, response } = context
      const status = response?.status ?? 0
      const data = (response as any)?._data as Record<string, any> | undefined
      const target =
        typeof request === 'string'
          ? request
          : request instanceof Request
            ? request.url
            : ''

      if (status === 401) {
        if (target.includes('/api/auth/login')) {
          throw context.error ?? new Error('Unauthorized')
        }
        auth.reset()
        if (process.client) {
          await navigateTo('/login')
        }
        return
      }

      if (status === 403 && data?.error === 'csrf_failed') {
        const retried = Boolean((options as any)._csrfRetried)
        if (!retried) {
          ;(options as any)._csrfRetried = true
          await csrf.refresh()
          return client(request, options)
        }
      }

      throw context.error ?? new Error(response?.statusText || 'Request failed')
    },
  })

  nuxtApp.provide('fetch', client)
})
