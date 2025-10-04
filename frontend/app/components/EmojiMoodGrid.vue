<template>
  <div class="grid-card">
    <h2 class="block-title">Synchronisation du ton</h2>
    <p class="block-sub">Sélectionnez ce qui vous ressemble aujourd’hui.</p>

    <div class="grid">
      <button
        v-for="(em, idx) in shuffled"
        :key="'em-' + idx"
        class="em"
        :class="{ 'em-active': isSelected(idx), 'em-disabled': isFull && !isSelected(idx) }"
        @click="toggle(idx)"
        type="button"
      >
        {{ em }}
      </button>
    </div>

    <div class="status">
      <span class="hint">Sélection : {{ selected.length }} / {{ max }}</span>
      <div class="chips">
        <span v-for="(i, k) in selected" :key="'chip-' + k" class="chip">
          {{ shuffled[i] }}
        </span>
      </div>
    </div>

    <div class="actions">
      <button class="btn-secondary" @click="reshuffle" type="button">Réorganiser</button>
      <button
        class="btn-primary"
        :disabled="busy || selected.length !== max"
        @click="confirm"
        type="button"
      >
        <span v-if="!busy">Continuer</span>
        <span v-else>Synchronisation…</span>
      </button>
    </div>

    <p v-if="msg" class="msg">{{ msg }}</p>
  </div>
</template>

<script setup lang="ts">
/**
 * Composant "grille d’émojis" avec sélection ordonnée de 4 items.
 * Sécurisé pour TS strict + "noUncheckedIndexedAccess": true.
 * - Mélange aléatoire à l’affichage (Fisher-Yates sécurisé via assertions non-null).
 * - On envoie au backend les indices (order) uniquement.
 */

import { ref, computed, onMounted } from 'vue'

const emit = defineEmits<{
  /** Événement de succès — renvoie les indices sélectionnés dans l’ordre */
  (e: 'ok', selection: number[]): void
}>()

const DEFAULT_EMOJIS = [
  '🦊',
  '🌊',
  '🌲',
  '🧊',
  '⚡',
  '🔥',
  '🌙',
  '☀️',
  '🌪️',
  '🌈',
  '🛰️',
  '🛠️',
  '🧭',
  '🎯',
  '🧪',
  '🧠',
  '🛡️',
  '📡',
  '⌛',
  '🧩',
  '🔭',
  '🧯',
  '🪐',
  '🦾',
  '🖤',
] as const

const props = withDefaults(
  defineProps<{
    /** Nombre maximum de sélections (ordre obligatoire) */
    max?: number
    /** Jeux d’émojis (optionnel, sinon fallback par défaut) */
    emojis?: string[]
  }>(),
  {
    max: 4,
    // On fournit un default béton → jamais undefined au runtime
    emojis: () => DEFAULT_EMOJIS.slice() as unknown as string[],
  },
)

/** Nombre max stabilisé (évite l’optionalité) */
const max = computed<number>(() => props.max ?? 4)

/** Source d’émojis (toujours un tableau défini) */
const source = computed<string[]>(() =>
  props.emojis && props.emojis.length > 0 ? props.emojis : DEFAULT_EMOJIS.slice(),
)

/** État local */
const shuffled = ref<string[]>([])
const selected = ref<number[]>([])
const busy = ref(false)
const msg = ref('')

/** Mélange Fisher–Yates avec assertions non-null (!) pour TS strict */
function shuffle<T>(arr: readonly T[]): T[] {
  const a = arr.slice()
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    // Avec "noUncheckedIndexedAccess", a[i] est T | undefined
    const tmp = a[i]! // ← assertion : i dans [0, length)
    a[i] = a[j]! // ← j dans [0, i], donc index valide
    a[j] = tmp
  }
  return a
}

function reshuffle() {
  // On ne permute que si rien n’est sélectionné (sinon on perturbe l’ordre)
  if (selected.value.length === 0) {
    shuffled.value = shuffle(source.value)
  }
}

function isSelected(idx: number) {
  return selected.value.includes(idx)
}

const isFull = computed<boolean>(() => selected.value.length >= max.value)

function toggle(idx: number) {
  msg.value = ''
  if (isSelected(idx)) {
    selected.value = selected.value.filter((i) => i !== idx)
    return
  }
  if (isFull.value) return
  selected.value.push(idx)
}

async function confirm() {
  if (selected.value.length !== max.value) return
  busy.value = true
  msg.value = ''
  try {
    // On envoie uniquement l’ordre d’indices (backend mappe vers son référentiel)
    const r = (await $fetch('/api/auth/profile', {
      method: 'POST',
      body: { order: selected.value },
      credentials: 'include',
    })) as { ok?: boolean }

    if (r?.ok) {
      emit('ok', [...selected.value])
    } else {
      msg.value = 'Profil non enregistré. Réessayez.'
    }
  } catch {
    msg.value = 'Temporairement indisponible.'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  // Premier mélange dès le mount
  shuffled.value = shuffle(source.value)
})
</script>

<style scoped>
@reference "@/assets/css/main.css";

.grid-card {
  @apply space-y-4 rounded-2xl p-6;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(139, 92, 246, 0.28);
}
.block-title {
  @apply text-lg font-semibold;
  color: #b0fff0;
}
.block-sub {
  @apply text-sm;
  color: #9dcdf7;
}

.grid {
  @apply grid gap-3;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}
.em {
  @apply flex h-12 items-center justify-center rounded-xl text-xl select-none;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #e6fff9;
  transition:
    transform 0.1s ease,
    box-shadow 0.15s ease,
    background 0.15s ease;
}
.em:hover {
  transform: translateY(-1px);
}
.em-active {
  background: rgba(0, 255, 204, 0.1);
  border-color: rgba(0, 255, 204, 0.35);
  box-shadow: 0 0 0 3px rgba(0, 255, 204, 0.15);
}
.em-disabled {
  opacity: 0.5;
  pointer-events: none;
}

.status {
  @apply flex items-center justify-between;
}
.hint {
  @apply text-sm;
  color: #9dcdf7;
}
.chips {
  @apply flex flex-wrap gap-2;
}
.chip {
  @apply rounded-lg px-2 py-1 text-sm;
  background: rgba(255, 255, 255, 0.06);
  color: #e6fff9;
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
