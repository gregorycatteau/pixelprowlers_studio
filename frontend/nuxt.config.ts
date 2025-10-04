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
  runtimeConfig: {
    // Privé (côté serveur uniquement)
    DJANGO_BASE_URL: process.env.NUXT_DJANGO_BASE_URL || 'http://localhost:8000',
    // Public (exposé au client si besoin)
    public: {
      DJANGO_BASE_URL: process.env.NUXT_DJANGO_BASE_URL || 'http://localhost:8000',
    },
  },
})
