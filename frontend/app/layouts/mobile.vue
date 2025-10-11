<template>
  <div class="layout-mobile">
    <slot />
  </div>
</template>

<script setup lang="ts">
// Device-only layout (mobile)
// Purpose: match layoutKey = "mobile" to avoid SSR/CSR hydration warnings.
// Styling is intentionally minimal and theme-agnostic. Theme (dark/light)
// is applied globally via document classes (see useUserTheme composable).
</script>

<style scoped>
@reference "@/assets/css/main.css";

/* Keep it simple and theme-agnostic; theme classes are applied globally */
.layout-mobile {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
</style>
