// frontend/test/shims/nuxt-imports.ts
// Shim des imports virtuels Nuxt pour l'exécution Vitest hors runtime Nuxt.
// Fournit des stubs minimalistes et PII-safe.

export const useRuntimeConfig = () => ({
  public: {
    appEnv: 'test',
    DJANGO_BASE_URL: 'http://localhost:8000',
    apiBase: 'http://localhost:8000',
    sentryDsn: '',
    sentrySampleRate: 0,
    sentryEnvironment: 'test',
  },
})

export const useCsrf = () => ({
  token: 'test-csrf',
  refresh: async () => undefined,
})
