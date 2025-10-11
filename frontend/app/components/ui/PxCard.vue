<template>
  <section class="card">
    <header v-if="$slots.header" class="card-header">
      <slot name="header" />
    </header>
    <div class="card-body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="card-footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<script setup lang="ts"></script>

<style scoped>
@reference "@/assets/css/main.css";
.card {
  @apply u-card flex flex-col gap-3 px-4 py-4 md:px-6 md:py-6;
}
.card-header {
  @apply text-base font-semibold text-color-text;
}
.card-body {
  @apply text-sm text-muted;
}
.card-footer {
  @apply mt-auto pt-3 text-sm;
}
</style>
