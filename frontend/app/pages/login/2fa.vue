<template>
  <section class="eotp-wrap">
    <div class="eotp-card">
      <header class="header">
        <h1 class="title">Vérification à deux facteurs</h1>
        <p class="subtitle">Saisissez le code reçu par email</p>
      </header>

      <div class="info" aria-live="polite">
        <p id="ttl" v-if="ttlDisplay > 0">Code valable encore {{ ttlDisplay }} s</p>
        <p id="ttl" v-else>Le code a expiré. Renvoyez un nouveau code.</p>
      </div>

      <form class="form" @submit.prevent="onVerify">
        <div class="field">
          <label class="label" for="code">Code à 6 chiffres</label>
          <input
            id="code"
            data-testid="code"
            v-model="code"
            class="input"
            type="text"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            placeholder="000000"
            @input="onCodeInput"
          />
        </div>

        <div class="actions">
          <button
            id="btn-verify"
            data-testid="btn-verify"
            class="btn-primary"
            type="submit"
            :disabled="verifyDisabled"
            @click="onVerifyClickBreadcrumb"
          >
            <span v-if="store.retryAfterVerify <= 0 && store.status !== 'verifying'">Valider</span>
            <span v-else-if="store.status === 'verifying'">Vérification…</span>
            <span v-else>Réessayer dans {{ store.retryAfterVerify }} s</span>
          </button>

          <button
            id="btn-resend"
            data-testid="btn-resend"
            class="btn-secondary"
            type="button"
            :disabled="resendDisabled"
            @click="onResend"
          >
            <span v-if="store.retryAfterResend <= 0">Renvoyer</span>
            <span v-else>Renvoyer dans {{ store.retryAfterResend }} s</span>
          </button>

          <!-- Dev/test only: helper _peek -->
          <button
            v-if="showPeek"
            class="btn-secondary"
            type="button"
            title="_peek (test only)"
            @click="onPeek"
          >
            _peek
          </button>
        </div>

        <p id="msg" data-testid="msg" v-if="uiMessage" class="error" aria-live="polite">
          {{ uiMessage }}
        </p>
      </form>

      <footer class="foot">
        <button class="link" type="button" @click="goBack">← Revenir à la connexion</button>
      </footer>
    </div>

    <PxToast v-model="toast.visible" :variant="toast.variant" :message="toast.message" />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRuntimeConfig, navigateTo } from '#imports'
import { useEotpStore } from '../../stores/useEotpStore'

const cfg = useRuntimeConfig()
const showPeek = computed(() => {
  const env = String(cfg.public?.appEnv || '').toLowerCase()
  return env === 'test'
})

const store = useEotpStore()

const code = ref('')
const tick = ref(0) // tick réactif pour rafraîchir l’affichage TTL
let intervalId: ReturnType<typeof setInterval> | null = null

const toast = reactive({
  visible: false,
  message: '',
  variant: 'info' as 'info' | 'success' | 'warning' | 'danger',
})

const openToast = (message: string, variant: 'info' | 'success' | 'warning' | 'danger' = 'info') => {
  toast.message = message
  toast.variant = variant
  toast.visible = true
}

const onCodeInput = () => {
  // Conserver uniquement les chiffres, max 6 (backend fait foi)
  code.value = (code.value || '').replace(/\D+/g, '').slice(0, 6)
}

const ttlDisplay = computed(() => {
  // Forcer recompute avec tick (Date.now() n’est pas réactif)
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  tick.value
  return store.ttlLeftSec
})

const verifyDisabled = computed(() => {
  if (store.status === 'verifying') return true
  if (store.retryAfterVerify > 0) return true
  return code.value.length !== 6
})

const resendDisabled = computed(() => {
  return store.retryAfterResend > 0
})

const uiMessage = computed(() => {
  // Messages génériques: invalid/expired → identiques
  if (store.status === 'invalid' || store.status === 'expired') {
    return 'Code invalide. Veuillez réessayer.'
  }
  if (store.status === 'locked') {
    return 'Trop de tentatives. Réessayez plus tard.'
  }
  if (store.status === 'rate_limited') {
    return 'Trop de demandes. Patientez avant de réessayer.'
  }
  if (store.status === 'error') {
    return 'Service indisponible. Réessayez.'
  }
  return ''
})

const onVerifyClickBreadcrumb = () => {
  try {
    // Breadcrumb non sensible si infra dispo (sentry/otel)
    // @ts-expect-error optional
    window?.__pxp_breadcrumb?.('eotp:verify_click')
  } catch {}
}

const onVerify = async () => {
  if (verifyDisabled.value) return
  const result = await store.verify(code.value)
  if (result.ok) {
    openToast('2FA validée.', 'success')
    try {
      // L’auth actualisée peut être gérée via composable/auth existant; on redirige ensuite
      await navigateTo('/gate')
    } catch {
      await navigateTo('/gate')
    }
  } else {
    try {
      // Breadcrumb non sensible
      // @ts-expect-error optional
      window?.__pxp_breadcrumb?.('eotp:error_displayed')
    } catch {}
  }
}

const onResend = async () => {
  try {
    // Breadcrumb non sensible
    // @ts-expect-error optional
    window?.__pxp_breadcrumb?.('eotp:resend_click')
  } catch {}

  const r = await store.resend()
  if (r.ok) {
    openToast('Code renvoyé.', 'info')
    code.value = ''
  } else {
    // Message géré via uiMessage selon status
  }
}

const onPeek = async () => {
  if (!showPeek.value) return
  const r = await store.fetchPeek()
  if (r.ok && r.code) {
    code.value = r.code
  }
}

const goBack = async () => {
  await navigateTo('/login')
}

onMounted(() => {
  store.hydrateExpiresFromSession(300)
  if (intervalId) clearInterval(intervalId)
  intervalId = setInterval(() => {
    store.decrementCooldownsTick()
    tick.value += 1
  }, 1000)
})

onBeforeUnmount(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>

<style scoped>
@reference "@/assets/css/main.css";

.eotp-wrap {
  @apply flex min-h-screen w-full items-center justify-center px-6 py-16;
  background: radial-gradient(1200px 600px at 50% 0%, #0b1020 0%, #060810 60%, #04060c 100%);
}
.eotp-card {
  @apply w-full max-w-md rounded-2xl p-8;
  background: linear-gradient(180deg, rgba(20, 25, 40, 0.9), rgba(10, 14, 24, 0.9));
  border: 1px solid rgba(0, 255, 204, 0.18);
  box-shadow:
    0 10px 30px rgba(0, 255, 204, 0.06),
    inset 0 0 50px rgba(0, 50, 80, 0.1);
  backdrop-filter: blur(6px);
}
.header {
  @apply mb-4;
}
.title {
  @apply text-2xl font-semibold;
  color: #b0fff0;
}
.subtitle {
  @apply text-sm;
  color: #7dd3fc;
}
.info {
  @apply mb-2 text-sm;
  color: #93c5fd;
}
.form {
  @apply space-y-4;
}
.field {
  @apply space-y-2;
}
.label {
  @apply text-sm;
  color: #c2e9fb;
}
.input {
  @apply w-full rounded-xl px-3 py-2;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(125, 211, 252, 0.22);
  color: #e6fff9;
  text-align: center;
  letter-spacing: 0.2em;
  font-size: 1.25rem;
}
.actions {
  @apply mt-2 flex items-center gap-3;
}
.btn-primary {
  @apply rounded-lg px-5 py-2 font-semibold;
  background: linear-gradient(90deg, #8b5cf6, #06b6d4);
  color: #f8faff;
}
.btn-secondary {
  @apply rounded-lg px-4 py-2 font-medium;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: #e2e8f0;
}
.error {
  @apply mt-2 text-sm;
  color: #fda4af;
}
.foot {
  @apply mt-4;
}
.link {
  color: #93c5fd;
  text-decoration: underline;
}
</style>
