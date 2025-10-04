<script setup lang="ts">
/** Sélecteur d’agent — accessible + focus ring neon */
const props = defineProps<{
  agents: { slug: string; name: string }[]
  modelValue: string
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()
function onChange(e: Event) {
  emit('update:modelValue', (e.target as HTMLSelectElement).value)
}
</script>

<template>
  <div class="sel">
    <label class="sel-label">🎛️ Choisir un agent</label>
    <div class="sel-wrap">
      <select
        class="sel-input"
        :value="modelValue"
        @change="onChange"
        aria-label="Choisir un agent"
      >
        <option v-for="a in agents" :key="a.slug" :value="a.slug">{{ a.name }}</option>
      </select>
      <span class="sel-caret">▾</span>
    </div>
  </div>
</template>

<style scoped>
@reference "@/assets/css/main.css";

.sel {
  @apply space-y-2;
}
.sel-label {
  @apply block text-sm font-semibold text-slate-200;
}

.sel-wrap {
  @apply relative;
  filter: drop-shadow(0 0 6px rgba(16, 185, 129, 0.15));
}
.sel-input {
  @apply w-full appearance-none rounded-xl bg-black px-4 py-2.5 text-emerald-300;
  @apply border border-emerald-600/60 ring-0 outline-none focus:ring-2;
  --tw-ring-color: rgb(5 150 105 / 0.6); /* emerald-600 */
}
.sel-caret {
  @apply pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-emerald-400;
}
</style>
