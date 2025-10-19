<template>
  <div class="px-table__wrapper" role="region" :aria-label="ariaLabel">
    <table class="px-table">
      <caption v-if="caption" class="px-table__caption">{{ caption }}</caption>
      <thead class="px-table__head">
        <slot name="head" />
      </thead>
      <tbody class="px-table__body">
        <slot />
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  caption?: string
  ariaLabel?: string
}>()
</script>

<style scoped>
@reference "@/assets/css/main.css";
.px-table__wrapper {
  @apply overflow-auto rounded-[var(--radius-md)] border border-color-border bg-color-surface;
}
.px-table {
  @apply min-w-full text-left;
  border-collapse: separate;
  border-spacing: 0;
}
.px-table__caption {
  @apply px-4 py-3 text-sm text-color-muted;
}
.px-table__head th {
  @apply bg-color-elev px-4 py-3 text-xs font-semibold uppercase tracking-wide text-color-text;
}
.px-table__body tr {
  @apply border-b border-color-border last:border-b-0;
}
.px-table__body td {
  @apply px-4 py-3 text-sm text-color-text;
}
.px-table__body tr:hover {
  @apply bg-color-elev;
}
</style>
