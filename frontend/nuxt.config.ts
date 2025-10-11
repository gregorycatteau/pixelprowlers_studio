// frontend/nuxt.config.ts
import tailwindcss from '@tailwindcss/vite'

const isProductionCsp = process.env.NODE_ENV === 'production' || process.env.APP_ENV === 'prod'

const prodCsp =
  "default-src 'self'; connect-src 'self' https:; img-src 'self' data: blob:; style-src 'self'; script-src 'self' 'strict-dynamic'; base-uri 'self'; frame-ancestors 'none'; report-uri /api/csp-report; report-to csp-endpoint"

const devCsp =
  "default-src 'self'; connect-src 'self' http://localhost:5173 http://localhost:3000 ws://localhost:5173 ws://localhost:3000 https:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; base-uri 'self'; frame-ancestors 'none'; report-uri /api/csp-report; report-to csp-endpoint"

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  // Nuxt 4 + app structure : ce chemin pointe bien vers app/assets/css/main.css
  css: ['~/assets/css/main.css'],

  components: [
    {
      path: '~/components/ui',
      pathPrefix: false,
    },
    '~/components',
  ],

  modules: ['@nuxtjs/device'],

  device: {
    defaultUserAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15',
  },

  // Tailwind v4 via plugin Vite
  vite: {
    plugins: [tailwindcss()],
  },
  nitro: {
    routeRules: {
      '/**': {
        headers: {
          'X-Frame-Options': 'DENY',
          'X-Content-Type-Options': 'nosniff',
          'Referrer-Policy': 'strict-origin-when-cross-origin',
          'Content-Security-Policy': isProductionCsp ? prodCsp : devCsp,
          'Report-To':
            '{"group":"csp-endpoint","max_age":10886400,"endpoints":[{"url":"/api/csp-report"}]}',
        },
      },
    },
  },
  runtimeConfig: {
    // Privé (côté serveur uniquement)
    DJANGO_BASE_URL: process.env.NUXT_DJANGO_BASE_URL || 'http://localhost:8000',
    // Public (exposé au client si besoin)
    public: {
      appEnv: process.env.APP_ENV || process.env.NUXT_PUBLIC_APP_ENV || 'dev',
      DJANGO_BASE_URL:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL ||
        process.env.NUXT_DJANGO_BASE_URL ||
        'http://localhost:8000',
      apiBase:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL ||
        process.env.NUXT_DJANGO_BASE_URL ||
        'http://localhost:8000',
      sentryDsn: process.env.NUXT_PUBLIC_SENTRY_DSN || '',
      sentrySampleRate: Number.parseFloat(process.env.NUXT_PUBLIC_SENTRY_SAMPLE_RATE || '0'),
      sentryEnvironment: process.env.NUXT_PUBLIC_SENTRY_ENVIRONMENT || '',
    },
  },
})
