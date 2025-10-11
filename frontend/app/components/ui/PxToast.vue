<template>
  <transition name="px-toast-fade">
    <div
      v-if="visible"
      class="px-toast"
      :class="`px-toast--${variant}`"
      role="status"
      aria-live="polite"
    >
      <div class="px-toast__content">
        <slot>{{ message }}</slot>
      </div>
      <button type="button" class="px-toast__close" @click="dismiss" aria-label="Fermer la notification">
        ×
      </button>
    </div>
  </transition>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue?: boolean
    message?: string
    variant?: 'info' | 'success' | 'warning' | 'danger'
    duration?: number
  }>(),
  {
    modelValue: undefined,
    message: undefined,
    variant: 'info',
    duration: 5000,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const timer = ref<ReturnType<typeof setTimeout> | null>(null)
const internalVisible = ref(false)
const isControlled = computed(() => typeof props.modelValue === 'boolean')

const visible = computed({
  get: () => (isControlled.value ? Boolean(props.modelValue) : internalVisible.value),
  set: (value: boolean) => {
    if (!isControlled.value) {
      internalVisible.value = value
    }
    emit('update:modelValue', value)
  },
})

const runtimeWindow = typeof window !== 'undefined' ? window : null

const clearTimer = () => {
  if (timer.value && runtimeWindow) {
    runtimeWindow.clearTimeout(timer.value)
    timer.value = null
  }
}

const startTimer = () => {
  clearTimer()
  if (!props.duration || !runtimeWindow) return
  timer.value = runtimeWindow.setTimeout(() => {
    visible.value = false
  }, props.duration)
}

watch(
  () => visible.value,
  (open) => {
    if (open) startTimer()
    else clearTimer()
  },
  { immediate: true },
)

const dismiss = () => {
  visible.value = false
}
onBeforeUnmount(clearTimer)
</script>

<style scoped>
@reference "@/assets/css/main.css";
.px-toast {
  @apply fixed right-4 top-4 flex items-start gap-3 rounded-[var(--radius-md)] border border-color-border bg-color-surface px-4 py-3 shadow-lg;
}
.px-toast--success {
  @apply border-color-success;
}
.px-toast--warning {
  @apply border-color-warning;
}
.px-toast--danger {
  @apply border-color-danger;
}
.px-toast__content {
  @apply text-sm text-color-text;
}
.px-toast__close {
  @apply ml-auto inline-flex h-6 w-6 items-center justify-center rounded-full text-sm text-color-muted transition hover:bg-color-elev hover:text-color-text focus-visible:u-focus-ring;
}
.px-toast-fade-enter-active,
.px-toast-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.px-toast-fade-enter-from,
.px-toast-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
