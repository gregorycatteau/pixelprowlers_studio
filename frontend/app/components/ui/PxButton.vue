<template>
  <button
    :type="type"
    class="px-button"
    :class="`px-button--${variantClass}`"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    v-bind="$attrs"
  >
    <span v-if="loading" class="px-button__spinner" aria-hidden="true" />
    <span class="px-button__label">
      <slot />
    </span>
  </button>
</template>

<script setup lang="ts">
type Variant = 'primary' | 'ghost' | 'danger'

const props = withDefaults(
  defineProps<{
    type?: 'button' | 'submit' | 'reset'
    variant?: Variant
    loading?: boolean
    disabled?: boolean
  }>(),
  {
    type: 'button',
    variant: 'primary',
    loading: false,
    disabled: false,
  },
)

const variantClass = computed(() => props.variant)
</script>

<style scoped>
@reference "@/assets/css/main.css";
.px-button {
  @apply u-btn-base relative select-none transition active:scale-95;
}
.px-button--primary {
  @apply u-btn-primary;
}
.px-button--ghost {
  @apply u-btn-ghost;
}
.px-button--danger {
  @apply u-btn-base bg-color-danger text-white hover:brightness-110 focus-visible:u-focus-ring;
}
.px-button:disabled {
  @apply cursor-not-allowed opacity-60;
}
.px-button__spinner {
  @apply mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-transparent border-r-white;
}
.px-button__label {
  @apply whitespace-nowrap;
}
</style>
