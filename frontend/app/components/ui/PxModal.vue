<template>
  <DialogRoot :open="isOpen" @update:open="onUpdate">
    <DialogTrigger v-if="$slots.trigger" as-child>
      <slot name="trigger" />
    </DialogTrigger>

    <DialogPortal>
      <DialogOverlay class="px-modal__overlay" />
      <DialogContent class="px-modal__content" :aria-describedby="contentDescribedBy">
        <header class="px-modal__header">
          <DialogTitle class="px-modal__title">{{ title }}</DialogTitle>
          <DialogDescription v-if="hasDescription" :id="descriptionId" class="px-modal__description">
            <slot name="description">
              {{ description }}
            </slot>
          </DialogDescription>
          <DialogClose class="px-modal__dismiss" aria-label="Fermer la fenêtre">
            <span aria-hidden="true">×</span>
          </DialogClose>
        </header>

        <section class="px-modal__body">
          <slot />
        </section>

        <footer v-if="$slots.footer" class="px-modal__footer">
          <slot name="footer" />
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from 'radix-vue'

const props = withDefaults(
  defineProps<{
    modelValue?: boolean
    title: string
    description?: string
  }>(),
  {
    modelValue: undefined,
    description: undefined,
  },
)

const slots = useSlots()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const internalOpen = ref(false)
const isControlled = computed(() => typeof props.modelValue === 'boolean')
const isOpen = computed({
  get: () => (isControlled.value ? Boolean(props.modelValue) : internalOpen.value),
  set: (value: boolean) => {
    if (!isControlled.value) {
      internalOpen.value = value
    }
    emit('update:modelValue', value)
  },
})

const descriptionBaseId = useId()
const descriptionId = computed(() => `px-modal-description-${descriptionBaseId}`)
const hasDescription = computed(() => Boolean(props.description || slots.description))
const contentDescribedBy = computed(() => (hasDescription.value ? descriptionId.value : undefined))

const onUpdate = (value: boolean) => {
  isOpen.value = value
}
</script>

<style scoped>
@reference "@/assets/css/main.css";
.px-modal__overlay {
  @apply fixed inset-0 bg-black/40 backdrop-blur-sm;
}
.px-modal__content {
  @apply fixed left-1/2 top-1/2 w-[min(90vw,480px)] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-lg)] bg-color-surface p-6 shadow-2xl focus:outline-none;
}
.px-modal__header {
  @apply relative flex flex-col gap-2;
}
.px-modal__title {
  @apply text-lg font-semibold text-color-text;
}
.px-modal__description {
  @apply text-sm text-color-muted;
}
.px-modal__dismiss {
  @apply absolute right-0 top-0 inline-flex h-8 w-8 items-center justify-center rounded-full text-lg text-color-muted transition hover:bg-color-elev hover:text-color-text focus-visible:u-focus-ring;
}
.px-modal__body {
  @apply mt-4 text-sm text-color-text;
}
.px-modal__footer {
  @apply mt-6 flex items-center justify-end gap-2;
}
</style>
