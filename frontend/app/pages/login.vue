<template>
  <section class="login-wrap">
    <div class="login-card">
      <header class="header">
        <h1 class="title">Démarrer une session</h1>
        <p class="subtitle">Accédez à votre espace de travail</p>
      </header>

      <form class="form" @submit.prevent="onSubmit">
        <div class="field">
          <label class="label" for="username">Identifiant</label>
          <input
            id="username"
            v-model="username"
            class="input"
            type="text"
            autocomplete="username"
            required
            placeholder="ex : jdoe"
          />
        </div>

        <div class="field">
          <label class="label" for="password">Mot de passe</label>
          <input
            id="password"
            v-model="password"
            class="input"
            type="password"
            autocomplete="current-password"
            required
            placeholder="••••••••"
          />
        </div>

        <button class="btn-primary" :disabled="isDisabled">
          <span v-if="!submitting">Continuer</span>
          <span v-else>Ouverture…</span>
        </button>

        <p v-if="retryAfter > 0" class="hint">
          Réessayer dans {{ retryAfter }} s
        </p>
        <p v-if="errorMsg" class="error">
          {{ errorMsg }}
        </p>
      </form>
    </div>
    <NuxtPage />
    <PxToast v-model="toast.visible" :variant="toast.variant" :message="toast.message" />
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, computed } from 'vue'
import { navigateTo } from '#app'
import { useRoute } from '#imports'
import type { FetchError } from 'ofetch'

const auth = useAuth()
const csrf = useCsrf()
const route = useRoute()

const username = ref('')
const password = ref('')
const submitting = ref(false)
const errorMsg = ref('')
const retryAfter = ref(0)
let retryTimer: ReturnType<typeof setInterval> | null = null

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

const clearRetryTimer = () => {
  if (retryTimer) {
    clearInterval(retryTimer)
    retryTimer = null
  }
}

const startRetryCountdown = (seconds: number) => {
  clearRetryTimer()
  retryAfter.value = Math.max(1, Math.round(seconds))
  retryTimer = setInterval(() => {
    retryAfter.value -= 1
    if (retryAfter.value <= 0) {
      clearRetryTimer()
    }
  }, 1000)
}

const isDisabled = computed(() => {
  if (submitting.value) return true
  if (retryAfter.value > 0) return true
  return !username.value.trim() || !password.value.trim()
})

onMounted(async () => {
  await auth.bootstrap()
  if (!csrf.token) {
    await csrf.refresh()
  }
  if (route.query.forbidden) {
    errorMsg.value = 'Accès réservé aux administrateurs.'
  }
})

onBeforeUnmount(() => {
  clearRetryTimer()
})

const onSubmit = async () => {
  // Garde-fou UX: ne pas soumettre si champs vides / cooldown actif
  if (isDisabled.value) return
  submitting.value = true
  errorMsg.value = ''

  try {
    // Appel standard via le composable (POST /api/auth/login/)
    // Remarque: l'API peut renvoyer {decision:'pending_2fa', fa_required:boolean}
    if (process.client) {
      // Journalisation client pour diagnostic — supprimable en prod
      console.debug('[login] submit payload (masked)', {
        username: username.value.trim(),
        password_len: password.value.length,
      })
    }
    const res = await auth.login({
      username: username.value.trim(),
      password: password.value,
    })

    if (process.client) {
      console.debug('[login] response', res)
    }

    const anyRes = res as any

    // Cas 2FA différée: le backend indique une décision/état "pending_2fa"
    // Compat backend: accepte decision === 'pending_2fa' OU status === 'pending_2fa'
    if (anyRes?.decision === 'pending_2fa' || anyRes?.status === 'pending_2fa') {
      if (anyRes?.fa_required === true) {
        // 2FA requise: stocker l'expiration pour le compte à rebours et rediriger
        try {
          const expires = Number(anyRes?.eotp_expires_in)
          if (Number.isFinite(expires) && expires > 0) {
            const ts = Date.now() + Math.round(expires) * 1000
            sessionStorage.setItem('eotp_expires_at', String(ts))
          }
        } catch {}
        openToast('Vérification à deux facteurs requise.', 'info')
        await navigateTo('/login/2fa')
        return
      }
      // 2FA non requise: session considérée ouverte => aller au "gate"
      openToast('Session ouverte.', 'success')
      // Rafraîchir l’état utilisateur pour hydrater le store avant la redirection
      await auth.fetchMe(true).catch(() => {})
      await navigateTo('/gate')
      return
    }

    // Cas succès "classique" (contrat antérieur): ok === true
    if (res?.ok) {
      openToast('Session ouverte.', 'success')
      await auth.fetchMe(true).catch(() => {})
      await navigateTo('/gate')
      return
    }

    // Réponse inattendue (ni pending_2fa ni ok): feedback générique
    errorMsg.value = 'Réponse inattendue du serveur. Réessayez.'
  } catch (err) {
    if (process.client) {
      console.error('[login] submit error', err)
    }
    // Gestion des erreurs HTTP usuelles
    const error = err as FetchError<Record<string, unknown>>
    const status = error?.response?.status
    if (status === 401) {
      errorMsg.value = 'Identifiants invalides.'
    } else if (status === 429) {
      const retryHeader = error.response?.headers?.get?.('Retry-After')
      const seconds = retryHeader ? Number(retryHeader) : 30
      startRetryCountdown(Number.isFinite(seconds) ? seconds : 30)
      errorMsg.value = 'Trop de tentatives. Patientez avant de réessayer.'
    } else {
      errorMsg.value = 'Service indisponible. Réessayez plus tard.'
    }
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
@reference "@/assets/css/main.css";

.login-wrap {
  @apply flex min-h-screen w-full items-center justify-center px-6 py-16;
  background: radial-gradient(1200px 600px at 50% 0%, #0b1020 0%, #060810 60%, #04060c 100%);
}
.login-card {
  @apply w-full max-w-md rounded-2xl p-8;
  background: linear-gradient(180deg, rgba(20, 25, 40, 0.9), rgba(10, 14, 24, 0.9));
  border: 1px solid rgba(0, 255, 204, 0.18);
  box-shadow:
    0 10px 30px rgba(0, 255, 204, 0.06),
    inset 0 0 50px rgba(0, 50, 80, 0.1);
  backdrop-filter: blur(6px);
}
.header {
  @apply mb-6;
}
.title {
  @apply text-2xl font-semibold;
  letter-spacing: 0.02em;
  color: #b0fff0;
}
.subtitle {
  @apply text-sm;
  color: #7dd3fc;
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
}
.btn-primary {
  @apply mt-2 w-full rounded-lg px-5 py-2 font-semibold;
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
.btn-primary:hover:enabled {
  transform: translateY(-1px);
}
.hint {
  @apply text-xs text-color-muted;
}
.error {
  @apply mt-3 text-sm;
  color: #fda4af;
}
</style>
