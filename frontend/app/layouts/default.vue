<template>
  <div class="layout-default">
    <slot />
  </div>
</template>

<script setup lang="ts">
// Default Nuxt layout
// Provides a safe fallback layout to satisfy Nuxt's layout system and avoid warnings.
</script>

<style scoped>
@reference "@/assets/css/main.css";

.layout-default {
  @apply min-h-screen bg-color-bg text-color-text;
}
</style>
