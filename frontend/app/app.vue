<!-- frontend/app/app.vue -->
<script setup lang="ts">
/**
 * Shell global Nuxt 4 — full Tailwind v4.1, zéro style inline.
 * - Header + nav (link Accueil / Ask Agent)
 * - Contenu page via <NuxtPage />
 * - Accessibilité: <NuxtRouteAnnouncer />
 */
</script>

<template>
  <div class="app-shell">
    <a href="#main" class="skip-link">Aller au contenu</a>
    <header class="app-header">
      <div class="header-inner">
        <NuxtLink to="/" class="brand"> PixelProwlers Studio </NuxtLink>

        <nav class="main-nav" aria-label="Navigation principale">
          <NuxtLink to="/" class="nav-link" exact-active-class="is-active"> Accueil </NuxtLink>
          <NuxtLink to="/ask-agent" class="nav-link" exact-active-class="is-active">
            Ask Agent
          </NuxtLink>
        </nav>
      </div>
    </header>

    <main id="main" class="app-main">
      <NuxtPage />
    </main>

    <footer class="app-footer">
      <p class="foot-note">v0.1 • env: dev • budget LLM cap: 5 €/j</p>
    </footer>

    <NuxtRouteAnnouncer />
  </div>
</template>

<style scoped>
@reference "@/assets/css/main.css";

/* Conteneur global */
.app-shell {
  @apply flex min-h-screen flex-col;
}

/* Lien "skip to content" accessible */
.skip-link {
  @apply sr-only fixed top-2 left-2 z-50 rounded-md px-3 py-2 focus:not-sr-only;
  @apply bg-emerald-600 text-white;
}

/* Header */
.app-header {
  @apply sticky top-0 z-40 border-b border-emerald-700/30 bg-black backdrop-blur;
}
.header-inner {
  @apply mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6;
}
.brand {
  @apply text-lg font-bold text-emerald-400 transition hover:text-emerald-300 sm:text-xl;
}

/* Nav */
.main-nav {
  @apply flex items-center gap-4;
}
.nav-link {
  @apply rounded-md px-3 py-1 text-slate-200 transition hover:bg-emerald-900/20 hover:text-emerald-300;
}
.nav-link.is-active {
  @apply border border-emerald-700/40 bg-emerald-900/30 text-emerald-300;
}

/* Contenu */


/* Footer */
.app-footer {
  @apply border-t border-slate-700 bg-black;
}
.foot-note {
  @apply mx-auto max-w-6xl px-4 py-4 text-sm text-slate-400 sm:px-6;
}
</style>
