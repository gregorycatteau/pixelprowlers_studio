<template>
  <div class="layout-tablet">
    <slot />
  </div>
</template>

<script setup lang="ts">
// Device-only layout (tablet)
// Matches layoutKey = "tablet" (device-based selection in app.vue).
// Theme (dark/light) is applied globally via document classes in useUserTheme.
// Keep this layout minimal and deterministic to avoid SSR/CSR hydration mismatches.
</script>

<style scoped>
@reference "@/assets/css/main.css";

/* Tablet layout — minimal container with vertical flow.
   Theme-agnostic: rely on global .dark / [data-theme] toggled elsewhere. */
.layout-tablet {
  min-height: 100vh;
  display: flex;
  flex-direction: column;

  /* Provide comfortable gutters for tablet widths without relying on breakpoints here.
     Keep styling conservative to avoid rendering differences SSR/CSR. */
  padding-inline: 1.25rem; /* ~20px */
  padding-block: 0.75rem;  /* ~12px */
}
</style>
