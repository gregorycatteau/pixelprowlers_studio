<template>
  <div class="layout-laptop">
    <header v-if="showHeader" class="laptop-header">
      <slot name="header" />
    </header>

    <main class="laptop-main">
      <slot />
    </main>

    <footer v-if="showFooter" class="laptop-footer">
      <slot name="footer" />
    </footer>
  </div>
</template>

<script setup lang="ts">
/**
 * Device-only layout (laptop)
 * Matches layoutKey = "laptop" (device-based selection in app.vue).
 * Theme (dark/light) is applied globally via document classes in useUserTheme.
 * Keep this layout minimal and deterministic to avoid SSR/CSR hydration mismatches.
 */
defineProps<{
  showHeader?: boolean
  showFooter?: boolean
}>()
</script>

<style scoped>
@reference "@/assets/css/main.css";

.layout-laptop {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* Optional header/footer slots with conservative spacing */
.laptop-header,
.laptop-footer {
  padding: 0.75rem 1rem;
}

/* Main grows to fill viewport height, centered column on wide screens */
.laptop-main {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  padding: 1rem;
}

@media (min-width: 1024px) {
  .laptop-main {
    padding: 1.5rem;
    max-width: 1200px;
    width: 100%;
    margin-inline: auto;
  }
}
</style>
