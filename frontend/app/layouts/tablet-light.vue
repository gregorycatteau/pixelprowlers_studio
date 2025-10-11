<template>
  <div class="layout">
    <slot />
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
@reference "@/assets/css/main.css";
.layout {
  @apply min-h-screen bg-color-bg text-color-text;
}
</style>
