<script setup lang="ts">
import { ref } from 'vue'
const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ (e: 'send', message: string): void }>()
const text = ref('')

function send() {
  const msg = text.value.trim()
  if (!msg || props.disabled) return
  emit('send', msg)
  text.value = ''
}
function onKey(e: KeyboardEvent) {
  // Enter -> envoyer ; Shift+Enter -> saut de ligne ; Ctrl/Cmd+Enter -> envoyer
  const ctrl = e.ctrlKey || e.metaKey
  if ((e.key === 'Enter' && !e.shiftKey) || (ctrl && e.key === 'Enter')) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="box">
    <textarea
      class="input"
      v-model="text"
      :disabled="disabled"
      placeholder="Tape ton message… (Enter pour envoyer • Shift+Enter = nouvelle ligne)"
      rows="3"
      @keydown="onKey"
    />
    <button class="btn" :disabled="disabled" @click="send">Envoyer</button>
  </div>
</template>

<style scoped>
@reference "@/assets/css/main.css";

.box {
  @apply flex items-start gap-3;
}
.input {
  @apply flex-1 rounded-xl bg-slate-950/70 px-4 py-3 text-slate-100;
  @apply border border-emerald-700/40 outline-none focus:ring-2;
  --tw-ring-color: rgb(16 185 129 / 0.6);
  resize: vertical;
}
.btn {
  @apply rounded-xl px-4 py-3 font-semibold transition;
  @apply bg-emerald-600 text-white hover:bg-emerald-500 active:bg-emerald-700;
  @apply shadow-[0_0_12px_rgba(16,185,129,0.35)];
  @apply disabled:cursor-not-allowed disabled:opacity-50;
}
</style>
