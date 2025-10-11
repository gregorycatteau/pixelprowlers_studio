# 01 — Device/Layout SSR (S1) — Dojo Secure Access

But (S1)
- Stabiliser le rendu SSR/CSR des layouts (mobile / tablet / laptop) et du thème (dark / light).
- Supprimer le WARN Nuxt: “Your project has layouts but the <NuxtLayout /> component has not been used.”
- Garantir un fallback propre et documenter les bonnes pratiques afin d’éviter les glitches d’hydratation.

Portée
- Nuxt 4 + @nuxtjs/device
- Choix de layout via `<NuxtLayout :name="layoutKey">`
- Composable `useDeviceKind()` (wrapper autour de `useDevice()` du module device)
- Fallback `app/layouts/default.vue`
- Notes SSR pour cohérence UA et thème

---

## Décisions (S1)

1) Utiliser le module officiel `@nuxtjs/device` pour déterminer `isMobile`, `isTablet`, `isDesktop` côté SSR et client.
2) Forcer un `defaultUserAgent` côté SSR pour éviter les divergences de device entre SSR et client (clé pour éviter les warnings/hydration mismatches).
3) Piloter le layout via `NuxtLayout` (pas via un `<component :is="...">` custom).
4) Calculer un `layoutKey` déterministe en SSR et CSR: `<device-base>-<theme>`, avec un fallback “laptop-light”.
5) Fournir un layout `default.vue` minimaliste pour absorber les cas non prévus.

---

## Implantation

### 1) Nuxt config — Device + CSP (extrait)

- Module device activé
- UA par défaut pour SSR (utile en tests, CI, et dev)

```ts
// nuxt.config.ts (extrait pertinent)
export default defineNuxtConfig({
  modules: ['@nuxtjs/device'],
  device: {
    // UA SSR par défaut pour éviter divergences (à adapter si besoin)
    defaultUserAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15',
  },
})
```

### 2) Composable — useDeviceKind()

- Wrapper léger autour de `useDevice()` qui expose aussi un `isLaptop` cohérent
- Évite de réimplémenter la détection à la main

```ts
// app/composables/useDeviceKind.ts (existant)
export function useDeviceKind() {
  const nuxtApp = useNuxtApp()
  const device = nuxtApp.$device ?? useDevice()

  const isMobile = computed(() => Boolean(device.isMobile))
  const isTablet = computed(() => Boolean(device.isTablet))
  const isDesktop = computed(() => Boolean(device.isDesktop))
  const isLaptop = computed(() => {
    const desktop = Boolean(device.isDesktop)
    const tablet = Boolean(device.isTablet)
    const mobile = Boolean(device.isMobile)
    return desktop && !tablet && !mobile
  })

  return {
    device,
    isMobile,
    isTablet,
    isDesktop,
    isLaptop,
    isApple: computed(() => Boolean(device.isApple)),
    isAndroid: computed(() => Boolean(device.isAndroid)),
  }
}
```

### 3) app.vue — NuxtLayout + layoutKey

- Résout le warning Nuxt et centralise le choix du layout
- `layoutKey` dépend de l’appareil et du thème

```vue
<!-- app/app.vue (schéma d’implémentation) -->
<template>
  <NuxtLayout :name="layoutKey">
    <NuxtPage />
  </NuxtLayout>
</template>

<script setup lang="ts">
const { isMobile, isTablet, isLaptop } = useDeviceKind()
const { isDark } = useUserTheme() // composable projet pour thème (SSR-safe)

const layoutKey = computed(() => {
  // Base en fonction du device
  const base = isMobile.value ? 'mobile' : isTablet.value ? 'tablet' : isLaptop.value ? 'laptop' : 'laptop'
  // Thème
  return isDark.value ? `${base}-dark` : `${base}-light`
})
</script>
```

### 4) Fallback layout — default.vue

- En cas de clé non prévue (`:name` manquant), Nuxt utilisera `default`
- Doit rester simple, sans logique conditionnelle lourde

```vue
<!-- app/layouts/default.vue -->
<template>
  <div class="layout-default">
    <slot />
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
@reference "@/assets/css/main.css";
.layout-default {
  /* Fondement visuel minimal pour éviter flashs */
  min-height: 100vh;
}
</style>
```

---

## Bonnes pratiques SSR

1) UA par défaut côté SSR
- Le module `@nuxtjs/device` s’appuie sur l’UA. En dev/CI, l’UA peut varier.
- Définir `device.defaultUserAgent` évite des divergences SSR/CSR.

2) Éviter les lectures côté client dans des chemins SSR
- Ne pas lire `window`, `document` ou le viewport dans `app.vue`.
- Basculer par thème via un state SSR-safe (cookie, config serveur, ou lecture côté server middleware si nécessaire).

3) Layouts nominaux simples
- Nommez les layouts “mobile-dark”, “mobile-light”, “tablet-dark”, etc. pour refléter clairement les combinaisons.
- Évitez les layouts trop dynamiques: la clé doit rester stable au 1er paint.

4) Fallback obligatoire
- Garder `layouts/default.vue`.
- En cas de plugin, erreur, ou device imprévu, l’app rend `default` sans casser SSR.

5) Thème dark/light SSR
- `useUserTheme()` doit être SSR-safe (par ex. cookie `theme=dark|light` lu côté serveur).
- Idéalement, poser une classe `[data-theme="dark"]` au SSR pour éviter un “flash” au 1er tick client.

---

## Anti‑patterns (à éviter)

- Rendu layout via `<component :is="...">` en racine au lieu de `<NuxtLayout>`.
- Déduire le device via `window.innerWidth` au SSR (ça n’existe pas).
- Changer le layoutKey après hydratation sur des triggers non déterministes (ex: `setTimeout`).
- Modifier le DOM (classe thème) côté client sans avoir une valeur initiale cohérente côté SSR.

---

## Checklist de validation (S1)

- [ ] Plus de warning “<NuxtLayout />”.
- [ ] Le layout rendu côté SSR correspond au layout après hydratation (mobile/tablet/laptop).
- [ ] Thème dark/light stable (pas de flash ou swap au 1er tick).
- [ ] Fallback `default.vue` présent et minimal.

---

## Tests rapides

Local (dev)
- Démarrer: `npm run dev`
- Vérifier logs Nuxt: aucun warning `<NuxtLayout />`
- Simuler différents devices (User-Agent dans le navigateur ou outil dev)
- Tester basculement du thème (toggle si prévu) et recharger (SSR -> CSR cohérent)

Via curl (simple header check via proxy Caddy)
- `curl -I http://dev.localhost` → vérifier headers sécu (Caddy) + absence d’erreurs côté Nuxt
- `curl -A "<UA mobile>" http://dev.localhost` → vérifier rendu visuel côté UI

---

## Dépannage

- Problème: “Hydration mismatch” sporadique
  - Causes probables: device détecté différemment SSR/CSR, ou thème initial non aligné.
  - Actions:
    - Fixer `device.defaultUserAgent`.
    - S’assurer que `useUserTheme()` reflète une valeur SSR-safe (ex: cookie lu côté serveur).
    - Vérifier qu’aucun code client n’altère `layoutKey` de façon asynchrone après le 1er paint.

- Problème: Le layout ne change pas sur mobile
  - Vérifier l’UA simulé (module device s’appuie sur UA).
  - Vérifier le calcul `isLaptop` (desktop && !tablet && !mobile).
  - Valider l’import du composable `useDeviceKind()`.

- Problème: Alerte Nuxt `<NuxtLayout />` malgré tout
  - Confirmer que `NuxtLayout` est directement dans `app.vue` (et non masqué par un wrapper custom).
  - S’assurer que le layoutKey est une string simple (pas un composant ou une instance).

---

## Notes d’implémentation (équipe)

- La détection device sera à terme complétée par un “feature flag” permettant de geler le layout (utile en QA/perf).
- Le thème dark/light peut être fixé par utilisateur (préférence stockée) — s’assurer d’ignorer les PII (pas d’email ou de data sensible dans un cookie).
- Les pages sensibles (Dojo admins) bénéficient de cette stabilisation (moins de bruit visuel pendant les étapes d’auth/nonce).

---

## Historique — S1 Done (journal)

À compléter lors du “Done”:
- Fichiers modifiés clés (diff court)
- 2 commandes de test exécutées
- “Attacks simulated” (ici surtout robustesse SSR/CSR: force UA mobile, bascule thème, rechargement)

Exemple:
- Fichiers: `app/app.vue`, `app/layouts/default.vue`, `app/composables/useDeviceKind.ts`, `nuxt.config.ts`
- Tests:
  - `npm run dev` → pas de WARN `<NuxtLayout />`
  - `curl -A "Mobile Safari" http://dev.localhost` → rendu mobile stable
- Robustness simulated:
  - Changement de thème + refresh rapide: pas de flash / pas de swap de layout
