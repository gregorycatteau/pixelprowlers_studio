<template>
  <section class="pf-wrap">
    <div class="pf-card">
      <header class="header">
        <h1 class="title">Préparation de l’espace</h1>
        <p class="subtitle">Quelques réglages rapides.</p>
      </header>

      <div v-if="step === 0" class="block">
        <ThemeHuePicker :hue="202" @ok="onHueOk" />
      </div>

      <div v-else-if="step === 1" class="block">
        <EmojiMoodGrid @ok="onEmojiOk" />
      </div>

      <div v-else class="block">
        <p class="info">Configuration terminée. Ouverture de la console…</p>
        <button class="btn-primary" @click="goGate">Continuer</button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { navigateTo } from '#app'

const step = ref<0 | 1 | 2>(0)

function onHueOk(_hue: number) {
  step.value = 1
}
function onEmojiOk(_sel: number[]) {
  step.value = 2
}
async function goGate() {
  await navigateTo('/gate')
}
</script>

<style scoped>
@reference "@/assets/css/main.css";

.pf-wrap {
  @apply flex min-h-screen w-full items-center justify-center px-6 py-16;
  background: radial-gradient(1200px 600px at 50% 0%, #0b1020 0%, #060810 60%, #04060c 100%);
}
.pf-card {
  @apply w-full max-w-3xl space-y-6 rounded-2xl p-8;
  background: linear-gradient(180deg, rgba(20, 25, 40, 0.9), rgba(10, 14, 24, 0.9));
  border: 1px solid rgba(0, 255, 204, 0.18);
  box-shadow:
    0 10px 40px rgba(0, 255, 204, 0.06),
    inset 0 0 60px rgba(0, 50, 80, 0.1);
  backdrop-filter: blur(6px);
}
.header {
  @apply mb-2;
}
.title {
  @apply text-2xl font-semibold md:text-3xl;
  color: #b0fff0;
}
.subtitle {
  @apply text-sm;
  color: #7dd3fc;
}
.block {
  @apply space-y-4;
}
.info {
  @apply text-sm;
  color: #c2e9fb;
}
.btn-primary {
  @apply rounded-lg px-5 py-2 font-semibold;
  background: linear-gradient(90deg, #8b5cf6, #06b6d4);
  color: #f8faff;
}
</style>
