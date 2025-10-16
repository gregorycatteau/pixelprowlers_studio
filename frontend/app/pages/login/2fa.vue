<template>
  <section class="eotp-wrap">
    <div class="eotp-card">
      <header class="header">
        <h1 class="title">Vérification à deux facteurs</h1>
        <p class="subtitle">Saisissez le code reçu par email</p>
      </header>

      <div class="info">
        <p v-if="ttlLeft > 0">Code valable encore {{ ttlLeft }} s</p>
        <p v-else>Le code a expiré. Renvoyez un nouveau code.</p>
      </div>

      <form class="form" @submit.prevent="onVerify">
        <div class="field">
          <label class="label" for="code">Code à 6 chiffres</label>
          <input
            id="code"
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
          <button class="btn-primary" type="submit" :disabled="verifyDisabled">
            <span v-if="verifyAfter <= 0 && !verifying">Valider</span>
            <span v-else-if="verifying">Vérification…</span>
            <span v-else>Réessayer dans {{ verifyAfter }} s</span>
          </button>

          <button class="btn-secondary" type="button" :disabled="resendDisabled" @click="onResend">
            <span v-if="resendAfter <= 0 && !resending">Renvoyer</span>
            <span v-else-if="resending">Envoi…</span>
            <span v-else>Renvoyer dans {{ resendAfter }} s</span>
          </button>
        </div>

        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
      </form>

      <footer class="foot">
        <button class="link" type="button" @click="goBack">← Revenir à la connexion</button>
      </footer>
    </div>

    <PxToast v-model="toast.visible" :variant="toast.variant" :message="toast.message" />
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, computed } from 'vue'
import { navigateTo } from '#app'
import type { FetchError } from 'ofetch'

const auth = useAuth()
const csrf = useCsrf()

const code = ref('')
const verifying = ref(false)
const resending = ref(false)
const errorMsg = ref('')

const verifyAfter = ref(0) // cooldown après 429 verify
const resendAfter = ref(0) // cooldown après resend

const expiresAt = ref<number | null>(null)
const ttlLeft = ref(0)
let ttlTimer: ReturnType<typeof setInterval> | null = null
let verifyTimer: ReturnType<typeof setInterval> | null = null
let resendTimer: ReturnType<typeof setInterval> | null = null

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
  // Conserver uniquement les chiffres, max 6
  code.value = (code.value || '').replace(/\D+/g, '').slice(0, 6)
}

const verifyDisabled = computed(() => {
  if (verifying.value) return true
  if (verifyAfter.value > 0) return true
  return code.value.length !== 6
})

const resendDisabled = computed(() => {
  return resending.value || resendAfter.value > 0
})

const tickTtl = () => {
  if (!expiresAt.value) {
    ttlLeft.value = 0
    return
  }
  const ms = expiresAt.value - Date.now()
  ttlLeft.value = Math.max(0, Math.floor(ms / 1000))
}

const startTimer = (kind: 'ttl' | 'verify' | 'resend') => {
  if (kind === 'ttl') {
    if (ttlTimer) clearInterval(ttlTimer)
    ttlTimer = setInterval(tickTtl, 1000)
  } else if (kind === 'verify') {
    if (verifyTimer) clearInterval(verifyTimer)
    verifyTimer = setInterval(() => {
      verifyAfter.value -= 1
      if (verifyAfter.value <= 0) {
        clearInterval(verifyTimer!)
        verifyTimer = null
      }
    }, 1000)
  } else {
    if (resendTimer) clearInterval(resendTimer)
    resendTimer = setInterval(() => {
      resendAfter.value -= 1
      if (resendAfter.value <= 0) {
        clearInterval(resendTimer!)
        resendTimer = null
      }
    }, 1000)
  }
}

onMounted(() => {
  // Hydrate expiration depuis sessionStorage (déposé au login)
  const raw = (sessionStorage.getItem('eotp_expires_at') || '').trim()
  const ts = Number(raw)
  if (Number.isFinite(ts) && ts > Date.now()) {
    expiresAt.value = ts
  } else {
    // fallback TTL 5 min
    expiresAt.value = Date.now() + 300_000
  }
  tickTtl()
  startTimer('ttl')
})

onBeforeUnmount(() => {
  if (ttlTimer) clearInterval(ttlTimer)
  if (verifyTimer) clearInterval(verifyTimer)
  if (resendTimer) clearInterval(resendTimer)
})

const onVerify = async () => {
  if (verifyDisabled.value) return
  verifying.value = true
  errorMsg.value = ''

  try {
    await csrf.refresh()
  } catch {}

  try {
    const res = await $fetch('/api/auth/2fa/email/verify', {
      method: 'POST',
      body: { code: code.value },
      credentials: 'include',
      headers: {
        'X-CSRFToken': csrf.token,
      },
    })

    // Succès → hydrater l'état, rediriger vers /gate
    openToast('2FA validée.', 'success')
    await auth.fetchMe(true).catch(() => {})
    await navigateTo('/gate')
  } catch (err) {
    const error = err as FetchError<Record<string, unknown>>
    const status = error?.response?.status
    if (status === 429) {
      // Respecter Retry-After pour l’utilisateur
      const ra = error.response?.headers?.get?.('Retry-After')
      const sec = ra ? Number(ra) : 30
      verifyAfter.value = Number.isFinite(sec) ? Math.max(1, Math.round(sec)) : 30
      startTimer('verify')
      errorMsg.value = 'Trop de tentatives. Patientez avant de réessayer.'
    } else if (status === 401 || status === 422) {
      errorMsg.value = 'Code invalide.'
    } else {
      errorMsg.value = 'Service indisponible. Réessayez.'
    }
  } finally {
    verifying.value = false
  }
}

const onResend = async () => {
  if (resendDisabled.value) return
  resending.value = true
  errorMsg.value = ''

  try {
    await csrf.refresh()
  } catch {}

  try {
    const res = (await $fetch('/api/auth/2fa/email/resend', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-CSRFToken': csrf.token,
      },
    })) as any

    // Mettre à jour le cooldown & TTL si fournis
    const ra = Number(res?.retry_after) || 90
    resendAfter.value = Math.max(1, Math.round(ra))
    startTimer('resend')

    const expIn = Number(res?.expires_in) || 300
    const nextTs = Date.now() + expIn * 1000
    sessionStorage.setItem('eotp_expires_at', String(nextTs))
    expiresAt.value = nextTs
    tickTtl()

    openToast('Code renvoyé.', 'info')
  } catch (err) {
    const error = err as FetchError<Record<string, unknown>>
    const status = error?.response?.status
    if (status === 429) {
      const ra =
        error.response?.headers?.get?.('Retry-After') ||
        (error as any)?.response?.headers?.['retry-after']
      const sec = ra ? Number(ra) : 60
      resendAfter.value = Number.isFinite(sec) ? Math.max(1, Math.round(sec)) : 60
      startTimer('resend')
      errorMsg.value = 'Trop de demandes. Patientez avant de réessayer.'
    } else {
      errorMsg.value = 'Envoi indisponible. Réessayez.'
    }
  } finally {
    resending.value = false
  }
}

const goBack = async () => {
  await navigateTo('/login')
}
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
