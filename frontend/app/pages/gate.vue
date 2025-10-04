<template>
  <section class="gate-container">
    <div class="gate-card">
      <header class="header">
        <h1 class="title">Console — nouvelle session</h1>
        <p class="subtitle">
          <span v-if="step === 1">Initialisation de session</span>
          <span v-else>Validation de session</span>
        </p>
      </header>

      <!-- ÉTAPE 1 (ne révèle rien) -->
      <div v-if="step === 1" class="step">
        <p class="hint">Décrivez brièvement votre objectif ou collez l’instruction à exécuter.</p>

        <textarea
          v-model="absurdText"
          class="input-area"
          rows="3"
          placeholder="Ex : générer un rapport, lancer une analyse, préparer des actions…"
        ></textarea>

        <div class="actions">
          <button
            class="btn-primary"
            :disabled="loading || !absurdText.trim()"
            @click="submitAbsurdity"
          >
            <span v-if="!loading">Continuer</span>
            <span v-else>Traitement…</span>
          </button>
        </div>

        <p v-if="feedback" :class="['feedback', feedbackOk ? 'ok' : 'ko']">
          {{ feedback }}
        </p>
      </div>

      <!-- ÉTAPE 2 (ne révèle rien) -->
      <div v-else class="step">
        <div class="prompt-box">
          {{ challengePrompt || 'Agent prêt — saisissez votre requête.' }}
        </div>

        <input v-model="ritualText" class="input-text" placeholder="Répondre…" autocomplete="off" />

        <div class="actions">
          <button class="btn-secondary" :disabled="loading" @click="backToStep1">← Revenir</button>
          <button
            class="btn-primary"
            :disabled="loading || !ritualText.trim()"
            @click="submitRitual"
          >
            <span v-if="!loading">Entrer dans le Studio</span>
            <span v-else>Vérification…</span>
          </button>
        </div>

        <p v-if="feedback" :class="['feedback', feedbackOk ? 'ok' : 'ko']">
          {{ feedback }}
        </p>
      </div>

      <footer class="foot-note">
        <p>
          Conseil : assurez-vous d’être connecté. Accès admin :
          <a class="link" href="http://localhost:8000/pp-admin/" target="_blank" rel="noopener"
            >/pp-admin/</a
          >
        </p>
      </footer>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { navigateTo } from '#app'

type AbsurdityResp = { ok: boolean; score?: number; reason?: string; fails?: number }
type InitResp = { ok: boolean; prompt: string }
type VerifyResp = { ok: boolean }

const step = ref<1 | 2>(1)
const loading = ref(false)
const absurdText = ref('')
const ritualText = ref('')

const challengePrompt = ref('')

const feedback = ref('')
const feedbackOk = ref(false)

function setFeedback(msg: string, ok = false) {
  feedback.value = msg
  feedbackOk.value = ok
  // Feedback discret (pas de détails d’échec)
  setTimeout(() => (feedback.value = ''), 3500)
}

/**
 * Wrapper $fetch sans générique direct (évite TypedInternalResponse).
 * On caste après l’appel.
 */
async function postJSON<T = unknown>(url: string, body: any): Promise<T> {
  const res = await $fetch(url, {
    method: 'POST' as const,
    body,
    credentials: 'include' as const,
  })
  return res as T
}

async function submitAbsurdity() {
  loading.value = true
  try {
    // Étape silencieuse : on ne révèle pas la nature du check
    const res = await postJSON<AbsurdityResp>('/api/gates/absurdity-check', {
      text: absurdText.value,
    })
    if (res.ok) {
      setFeedback('Ok.', true)
      // On enchaîne discrètement avec l’initialisation du “prompt”
      await initChallenge()
      step.value = 2
    } else {
      // Message générique (pas d’indices)
      setFeedback('Commande non reconnue. Reformulez en une phrase courte.')
    }
  } catch (e: any) {
    setFeedback('Temporairement indisponible. Réessayez.')
  } finally {
    loading.value = false
  }
}

async function initChallenge() {
  try {
    const res = await postJSON<InitResp>('/api/gates/challenge-init', { agent: 'Claire' })
    if (res.ok) {
      challengePrompt.value = res.prompt
    }
  } catch {
    // silencieux
  }
}

async function submitRitual() {
  loading.value = true
  try {
    const res = await postJSON<VerifyResp>('/api/gates/challenge-verify', {
      agent: 'Claire',
      response: ritualText.value,
    })
    if (res.ok) {
      setFeedback('Session prête.', true)
      setTimeout(() => navigateTo('/ask-agent'), 200)
    } else {
      // Ne rien dévoiler :
      setFeedback('Réponse non reconnue.')
    }
  } catch {
    setFeedback('Temporairement indisponible. Réessayez.')
  } finally {
    loading.value = false
  }
}

function backToStep1() {
  step.value = 1
  ritualText.value = ''
}

onMounted(async () => {
  // “Réveil” de session (pas d’erreur visible)
  try {
    await $fetch('/api/accounts/whoami', { method: 'GET', credentials: 'include' })
  } catch {
    /* noop */
  }
})
</script>

<style scoped>
@reference "@/assets/css/main.css";

/* Fond neutre, sombre, lisible (contraste fort) */
.gate-container {
  @apply flex min-h-screen w-full items-center justify-center px-6 py-16;
  background: radial-gradient(1200px 600px at 50% 0%, #0b1020 0%, #060810 60%, #04060c 100%);
}

/* Carte premium “apple-cyberpunk” */
.gate-card {
  @apply w-full max-w-3xl rounded-2xl p-8;
  background: linear-gradient(180deg, rgba(20, 25, 40, 0.9), rgba(10, 14, 24, 0.9));
  border: 1px solid rgba(0, 255, 204, 0.18);
  box-shadow:
    0 10px 40px rgba(0, 255, 204, 0.07),
    inset 0 0 60px rgba(0, 50, 80, 0.12);
  backdrop-filter: blur(6px);
}

.header {
  @apply mb-4;
}

.title {
  @apply mb-1 text-3xl font-semibold md:text-4xl;
  letter-spacing: 0.02em;
  color: #b0fff0;
  text-shadow: 0 0 10px rgba(0, 255, 204, 0.2);
}

.subtitle {
  @apply text-sm;
  color: #7dd3fc;
}

.step {
  @apply mt-6 space-y-4;
}

.hint {
  @apply text-base;
  color: #c2e9fb;
}

.input-area {
  @apply w-full resize-none rounded-xl p-4;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(125, 211, 252, 0.22);
  color: #e6fff9;
}

.input-text {
  @apply w-full rounded-xl p-3;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(139, 92, 246, 0.32);
  color: #e6fff9;
}

.prompt-box {
  @apply mb-2 rounded-xl p-4;
  background: rgba(0, 255, 204, 0.05);
  border: 1px dashed rgba(0, 255, 204, 0.28);
  color: #b0fff0;
}

.actions {
  @apply flex items-center gap-3;
}

.btn-primary {
  @apply rounded-lg px-5 py-2 font-semibold;
  background: linear-gradient(90deg, #8b5cf6, #06b6d4);
  color: #f8faff;
  box-shadow: 0 10px 24px rgba(139, 92, 246, 0.18);
  transition:
    transform 0.15s ease,
    opacity 0.15s ease;
}
.btn-primary:disabled {
  opacity: 0.6;
}
.btn-primary:hover {
  transform: translateY(-1px);
}

.btn-secondary {
  @apply rounded-lg px-4 py-2 font-medium;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: #e2e8f0;
}

.feedback {
  @apply mt-1 text-sm;
}
.feedback.ok {
  color: #34d399;
}
.feedback.ko {
  color: #fda4af;
}

.foot-note {
  @apply mt-6 text-xs opacity-80;
  color: #9fb8ff;
}
.link {
  color: #93c5fd;
  text-decoration: underline;
}
</style>
