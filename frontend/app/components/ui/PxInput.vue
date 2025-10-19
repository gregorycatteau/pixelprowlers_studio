<template>
  <div class="px-input">
    <label v-if="label" :for="controlId" class="px-input__label">{{ label }}</label>

    <component
      :is="isTextarea ? 'textarea' : 'input'"
      v-bind="attrs"
      :id="controlId"
      :rows="isTextarea ? rows : undefined"
      :class="['px-input__control', { 'px-input__control--error': Boolean(error) }]"
      :aria-describedby="describedBy"
      :aria-invalid="error ? 'true' : undefined"
    />

    <p v-if="hint" :id="hintId" class="px-input__hint">{{ hint }}</p>
    <p v-if="error" :id="errorId" class="px-input__error" role="alert">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    id?: string
    label?: string
    hint?: string
    error?: string
    textarea?: boolean
    rows?: number
  }>(),
  {
    id: undefined,
    label: undefined,
    hint: undefined,
    error: undefined,
    textarea: false,
    rows: 4,
  },
)

const attrs = useAttrs()
const generatedId = useId()

const isTextarea = computed(() => props.textarea)
const controlId = computed(
  () => props.id || (attrs.id as string | undefined) || `px-input-${generatedId}`,
)
const hintId = computed(() =>
  props.hint ? `${controlId.value}-hint` : undefined,
)
const errorId = computed(() =>
  props.error ? `${controlId.value}-error` : undefined,
)
const describedBy = computed(() => {
  const ids = []
  if (hintId.value) ids.push(hintId.value)
  if (errorId.value) ids.push(errorId.value)
  return ids.length ? ids.join(' ') : undefined
})

const rows = computed(() => props.rows)
</script>

<style scoped>
@reference "@/assets/css/main.css";
.px-input {
  @apply grid gap-1;
}
.px-input__label {
  @apply text-sm font-medium text-color-text;
}
.px-input__control {
  @apply w-full rounded-[var(--radius-md)] border border-color-border bg-color-surface px-3 py-2 text-sm transition focus-visible:u-focus-ring;
}
.px-input__control--error {
  @apply border-color-danger;
}
.px-input__hint {
  @apply text-xs text-color-muted;
}
.px-input__error {
  @apply text-xs text-color-danger;
}
</style>
