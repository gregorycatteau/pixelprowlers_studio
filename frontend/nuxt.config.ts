// frontend/nuxt.config.ts
import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  // Nuxt 4 + app structure : ce chemin pointe bien vers app/assets/css/main.css
  css: ['~/assets/css/main.css'],

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
          'Content-Security-Policy-Report-Only':
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' https://api.staging.pixelprowlers.io; base-uri 'self'; frame-ancestors 'none'; report-uri /api/csp-report",
        },
      },
    },
  },
  runtimeConfig: {
    // Privé (côté serveur uniquement)
    DJANGO_BASE_URL: process.env.NUXT_DJANGO_BASE_URL || 'http://localhost:8000',
    // Public (exposé au client si besoin)
    public: {
      DJANGO_BASE_URL: process.env.NUXT_DJANGO_BASE_URL || 'http://localhost:8000',
    },
  },
})
