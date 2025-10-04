<template>
  <div class="theme-card">
    <h2 class="block-title">Personnalisation rapide du thème</h2>
    <p class="block-sub">Ajustez la teinte pour votre confort visuel.</p>

    <div class="slider-wrap">
      <input
        class="slider"
        type="range"
        min="0"
        max="359"
        v-model.number="localHue"
        @input="onChange"
      />
      <div class="hue-readout">
        Teinte : <span class="mono">{{ localHue }}</span
        >°
      </div>
    </div>

    <div class="actions">
      <button class="btn-secondary" @click="randomize">Proposition aléatoire</button>
      <button class="btn-primary" @click="confirm" :disabled="busy">
        <span v-if="!busy">Continuer</span>
        <span v-else>Application…</span>
      </button>
    </div>

    <p v-if="msg" class="msg">{{ msg }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  (e: 'ok', hue: number): void
}>()

const props = withDefaults(
  defineProps<{
    hue?: number
  }>(),
  {
    hue: 202,
  },
)

const localHue = ref<number>(props.hue)
const busy = ref(false)
const msg = ref('')

function onChange() {
  msg.value = ''
}

function randomize() {
  localHue.value = Math.floor(Math.random() * 360)
}

async function confirm() {
  busy.value = true
  msg.value = ''
  try {
    // Appel API neutre
    const r = (await $fetch('/api/auth/theme', {
      method: 'POST',
      body: { hue: localHue.value },
      credentials: 'include',
    })) as { ok?: boolean }

    if (r?.ok) {
      emit('ok', localHue.value)
    } else {
      msg.value = 'Réglage non pris en compte. Réessayez.'
    }
  } catch {
    msg.value = 'Temporairement indisponible.'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
@reference "@/assets/css/main.css";

.theme-card {
  @apply space-y-4 rounded-2xl p-6;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(125, 211, 252, 0.2);
}
.block-title {
  @apply text-lg font-semibold;
  color: #b0fff0;
}
.block-sub {
  @apply text-sm;
  color: #9dcdf7;
}

.slider-wrap {
  @apply space-y-2;
}
/* Piste arc-en-ciel statique (pas d’inline style dynamique) */
.slider {
  @apply w-full;
  -webkit-appearance: none;
  height: 10px;
  border-radius: 9999px;
  outline: none;
  background: linear-gradient(
    90deg,
    #f00 0%,
    #ff0 17%,
    #0f0 33%,
    #0ff 50%,
    #00f 67%,
    #f0f 83%,
    #f00 100%
  );
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 9999px;
  background: #e6fff9;
  border: 2px solid #0ea5e9;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.25);
}
.slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 9999px;
  background: #e6fff9;
  border: 2px solid #0ea5e9;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.25);
}
.hue-readout {
  @apply text-sm;
  color: #c2e9fb;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.actions {
  @apply flex items-center gap-3;
}
.btn-primary {
  @apply rounded-lg px-4 py-2 font-semibold;
  background: linear-gradient(90deg, #8b5cf6, #06b6d4);
  color: #f8faff;
}
.btn-secondary {
  @apply rounded-lg px-4 py-2 font-medium;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: #e2e8f0;
}
.msg {
  @apply text-sm;
  color: #fda4af;
}
</style>
