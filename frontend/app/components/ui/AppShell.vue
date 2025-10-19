<template>
  <div class="app-shell">
    <header v-if="hasHeader" class="app-shell__header" role="banner">
      <slot name="header" />
    </header>

    <div v-if="hasToolbar" class="app-shell__toolbar" role="navigation">
      <slot name="toolbar" />
    </div>

    <main class="app-shell__content" role="main">
      <slot />
    </main>

    <footer v-if="hasFooter" class="app-shell__footer" role="contentinfo">
      <slot name="footer" />
    </footer>
  </div>
</template>

<script setup lang="ts">
const slots = useSlots()

const hasHeader = computed(() => Boolean(slots.header))
const hasToolbar = computed(() => Boolean(slots.toolbar))
const hasFooter = computed(() => Boolean(slots.footer))
</script>

<style scoped>
@reference "@/assets/css/main.css";
.app-shell {
  @apply u-grid-page bg-color-bg text-color-text;
}
.app-shell__header {
  @apply u-header;
}
.app-shell__toolbar {
  @apply border-b border-color-border bg-color-elev;
}
.app-shell__content {
  @apply bg-color-bg;
}
.app-shell__footer {
  @apply border-t border-color-border bg-color-surface text-color-muted text-sm;
}
</style>
