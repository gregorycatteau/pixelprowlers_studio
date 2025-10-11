<template>
  <header class="px-header">
    <NuxtLink to="/" class="px-header__brand" aria-label="Accueil PixelProwlers Studio">
      <span class="px-header__brand-mark" aria-hidden="true">⧉</span>
      <span class="px-header__brand-name">PixelProwlers Studio</span>
    </NuxtLink>

    <nav class="px-header__nav" aria-label="Navigation principale">
      <NuxtLink
        v-for="link in navLinks"
        :key="link.to"
        :to="link.to"
        class="px-header__link"
        :aria-current="isActive(link.to) ? 'page' : undefined"
        :class="{
          'px-header__link--active': isActive(link.to),
        }"
      >
        {{ link.label }}
      </NuxtLink>
    </nav>

    <div v-if="isLogged" class="px-header__session">
      <span class="px-header__user" aria-live="polite">{{ userLabel }}</span>
      <button
        type="button"
        class="px-header__logout"
        :disabled="loggingOut"
        @click="onLogout"
      >
        {{ loggingOut ? 'Déconnexion…' : 'Déconnexion' }}
      </button>
    </div>

    <button
      type="button"
      class="px-header__theme-toggle"
      @click="toggleTheme"
      :aria-pressed="isDark"
    >
      <span class="px-header__theme-label">{{ isDark ? 'Mode sombre' : 'Mode clair' }}</span>
      <span class="px-header__theme-icon" aria-hidden="true">{{ isDark ? '☾' : '☀︎' }}</span>
    </button>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { navigateTo, useRoute } from '#imports'
import { useUserTheme } from '~/composables/useUserTheme'

const auth = useAuth()

const links = [
  { label: 'Dashboard', to: '/' },
  { label: 'Ask Agents', to: '/ask-agents', superuser: true },
]

const route = useRoute()
const { isDark, toggleTheme } = useUserTheme()

const isActive = (to: string) => route.path === to

const loggingOut = ref(false)
const isLogged = computed(() => auth.isAuthenticated.value)
const userLabel = computed(
  () => auth.user.value?.display_name || auth.user.value?.username || '',
)
const navLinks = computed(() =>
  links.filter((link) => !link.superuser || auth.isSuperuser.value),
)

const onLogout = async () => {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await auth.logout()
    await navigateTo('/login')
  } finally {
    loggingOut.value = false
  }
}
</script>

<style scoped>
@reference "@/assets/css/main.css";
.px-header {
  @apply flex items-center gap-4 px-4 py-3;
}
.px-header__brand {
  @apply flex items-center gap-2 text-lg font-semibold text-color-text transition hover:text-color-primary;
}
.px-header__brand-mark {
  @apply inline-flex h-7 w-7 items-center justify-center rounded-full bg-color-primary-soft text-sm;
}
.px-header__brand-name {
  @apply tracking-tight;
}
.px-header__nav {
  @apply hidden items-center gap-3 text-sm md:flex;
}
.px-header__link {
  @apply rounded-[var(--radius-sm)] px-3 py-2 text-color-muted transition hover:bg-color-elev hover:text-color-text focus-visible:u-focus-ring;
}
.px-header__link--active {
  @apply bg-color-primary-soft text-color-text;
}
.px-header__session {
  @apply ml-auto flex items-center gap-3 text-sm;
}
.px-header__user {
  @apply font-medium text-color-text;
}
.px-header__logout {
  @apply inline-flex items-center gap-2 rounded-full border border-color-border bg-transparent px-3 py-2 text-sm text-color-muted transition hover:bg-color-primary-soft hover:text-color-text focus-visible:u-focus-ring disabled:cursor-wait disabled:opacity-70;
}
.px-header__theme-toggle {
  @apply ml-3 inline-flex items-center gap-2 rounded-full border border-color-border bg-color-surface px-3 py-2 text-sm transition hover:bg-color-primary-soft focus-visible:u-focus-ring;
}
.px-header__theme-label {
  @apply sr-only md:not-sr-only;
}
.px-header__theme-icon {
  @apply text-base leading-none;
}
@media (min-width: var(--breakpoint-md)) {
  .px-header {
    @apply px-6;
  }
}
</style>
