<template>
  <section class="min-h-screen grid place-items-center px-6 py-10">
    <div class="w-full max-w-3xl space-y-8 rounded-2xl border border-slate-700/50 bg-slate-900/40 p-6 backdrop-blur">
      <header class="space-y-1">
        <h1 class="text-2xl md:text-3xl font-bold text-emerald-400">Bienvenue</h1>
        <p class="text-slate-300">Authentification SSR-first — aucun jeton côté client.</p>
      </header>

      <!-- Realm switcher -->
      <div class="flex items-center gap-3">
        <button
          type="button"
          class="btn-tab"
          :class="mode === 'clients' ? 'btn-tab--active' : ''"
          @click="switchMode('clients')"
          :aria-pressed="mode === 'clients'"
        >
          Clients (TOTP)
        </button>
        <button
          type="button"
          class="btn-tab"
          :class="mode === 'dojo' ? 'btn-tab--active' : ''"
          @click="switchMode('dojo')"
          :aria-pressed="mode === 'dojo'"
        >
          Admins (Dojo · WebAuthn)
        </button>
      </div>

      <!-- Clients login (2 étapes avec TOTP) -->
      <form v-if="mode === 'clients'" class="space-y-6" @submit.prevent="onLoginClients">
        <fieldset class="space-y-4" :disabled="busy">
          <legend class="sr-only">Connexion Clients</legend>

          <div class="grid gap-2">
            <label class="lbl" for="email">Email</label>
            <input
              id="email"
              class="inp"
              type="email"
              autocomplete="email"
              v-model.trim="email"
              required
              inputmode="email"
            />
          </div>

          <div class="grid gap-2">
            <label class="lbl" for="password">Mot de passe</label>
            <input
              id="password"
              class="inp"
              type="password"
              autocomplete="current-password"
              v-model="password"
              required
              minlength="8"
            />
          </div>

          <!-- Turnstile (Cloudflare) — rendu client-only (SSR-safe) -->
          <ClientOnly>
            <div class="grid gap-2">
              <label class="lbl">Vérification anti‑bot (Turnstile)</label>
              <div ref="turnstileEl" />
              <p class="text-xs text-slate-400">
                Le widget Turnstile s’affiche côté client et produit un jeton temporaire transmis au serveur.
              </p>
            </div>
          </ClientOnly>

          <div class="flex items-center gap-3">
            <button type="submit" class="btn-primary" :disabled="busy">
              <span v-if="!busy && !pending2FA">Se connecter</span>
              <span v-else-if="!busy && pending2FA">Continuer (TOTP)</span>
              <span v-else>Un instant…</span>
            </button>
            <span class="text-sm text-slate-400" v-if="pending2FA">Étape 2FA requise</span>
          </div>

          <p v-if="msg" class="msg">{{ msg }}</p>
        </fieldset>

        <!-- Étape TOTP (pending_2fa) -->
        <div v-if="pending2FA" class="mt-6 space-y-4 rounded-xl border border-slate-700/60 p-4">
          <h2 class="text-lg font-semibold text-cyan-300">Validation TOTP</h2>

          <div class="grid gap-2">
            <label class="lbl" for="otp">Code à 6 chiffres</label>
            <input
              id="otp"
              class="inp"
              type="text"
              pattern="^[0-9]{6}$"
              inputmode="numeric"
              maxlength="6"
              v-model.trim="otp"
              placeholder="000000"
            />
          </div>

          <div class="flex items-center gap-3">
            <button type="button" class="btn-primary" :disabled="busy || !otpOk" @click="onTotpVerify">
              <span v-if="!busy">Vérifier</span>
              <span v-else>Vérification…</span>
            </button>

            <button
              type="button"
              class="btn-secondary"
              :disabled="busy"
              @click="onTotpBootstrap"
              v-if="!totpProvisioned"
            >
              Activer TOTP (si pas encore fait)
            </button>
          </div>

          <!-- Bootstrap TOTP (secret + otpauth URL) -->
          <div v-if="totpBootstrap" class="mt-4 space-y-2 rounded-lg border border-slate-700/60 p-3">
            <p class="text-slate-300">
              Scannez l’URL ci‑dessous dans votre app d’authentification (Google Authenticator, 1Password, etc.).
            </p>
            <div class="grid gap-1">
              <span class="text-xs text-slate-400">Secret</span>
              <code class="code">{{ totpBootstrap.secret }}</code>
            </div>
            <div class="grid gap-1">
              <span class="text-xs text-slate-400">otpauth URL</span>
              <code class="code break-all">{{ totpBootstrap.otpauth_url }}</code>
            </div>

            <div class="grid gap-2 mt-3">
              <label class="lbl" for="otp-activate">Entrez un code TOTP pour activer</label>
              <input
                id="otp-activate"
                class="inp"
                type="text"
                pattern="^[0-9]{6}$"
                inputmode="numeric"
                maxlength="6"
                v-model.trim="otpActivate"
                placeholder="000000"
              />
              <button
                type="button"
                class="btn-primary"
                :disabled="busy || !otpActivateOk"
                @click="onTotpActivate"
              >
                Activer
              </button>
            </div>

            <div v-if="recoveryCodes.length" class="mt-3 space-y-1">
              <p class="text-sm text-amber-200">Codes de récupération (à conserver en lieu sûr) :</p>
              <ul class="list-disc pl-6 text-slate-200">
                <li v-for="c in recoveryCodes" :key="c"><code class="code">{{ c }}</code></li>
              </ul>
              <p class="text-xs text-slate-400">
                Vous pourrez exporter ces codes en ZIP chiffré/PGP depuis le tableau de bord.
              </p>
            </div>
          </div>
        </div>
      </form>

      <!-- Dojo (Admins) — WebAuthn -->
      <form v-else class="space-y-6" @submit.prevent="onWebAuthn">
        <fieldset class="space-y-4" :disabled="busy">
          <legend class="sr-only">Connexion Admin (Dojo)</legend>

          <div class="grid gap-2">
            <label class="lbl" for="username">Identifiant (optionnel)</label>
            <input
              id="username"
              class="inp"
              type="text"
              autocomplete="username"
              v-model.trim="username"
              placeholder="ex: admin@acme.tld"
            />
            <p class="text-xs text-slate-400">
              L’accès Dojo peut exiger mTLS au niveau proxy + Passkey. Aucune donnée sensible n’est révélée ici.
            </p>
          </div>

          <div class="grid gap-2">
            <label class="lbl">Vérification Passkey (WebAuthn)</label>
            <button type="submit" class="btn-primary" :disabled="busy || !webauthnCapable">
              <span v-if="!busy">Continuer avec Passkey</span>
              <span v-else>Vérification…</span>
            </button>
            <p v-if="!webauthnCapable" class="text-sm text-amber-300">
              WebAuthn non disponible dans ce navigateur. Utilisez un appareil compatible.
            </p>
          </div>

          <p v-if="msg" class="msg">{{ msg }}</p>
        </fieldset>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
// SSR-first: on ne lit jamais document.cookie; tous les flux passent par des routes serveur Nuxt.
// Aucune persistance de jeton côté client (cookies HttpOnly uniquement).

import { computed, onMounted, ref } from 'vue'
import { useRouter, useRuntimeConfig } from '#app'

declare global {
  interface Window {
    turnstile?: any
  }
}

type Mode = 'clients' | 'dojo'

const router = useRouter()
const config = useRuntimeConfig()

// Realm UI
const mode = ref<Mode>('clients')
function switchMode(next: Mode) {
  msg.value = ''
  busy.value = false
  pending2FA.value = false
  totpBootstrap.value = null
  otp.value = ''
  otpActivate.value = ''
  recoveryCodes.value = []
  mode.value = next
  if (process.client && next === 'clients') {
    initTurnstile().catch(() => {})
  }
}

// Common state
const busy = ref(false)
const msg = ref('')
const webauthnCapable = ref(false)

// Turnstile (Cloudflare) — client-only token
const cfToken = ref<string>('') // token transmis au backend (/_fa/verify)
const turnstileEl = ref<HTMLElement | null>(null)

async function loadTurnstileScript(): Promise<void> {
  if (!process.client) return
  if (document.getElementById('cf-turnstile-script')) return
  await new Promise<void>((resolve, reject) => {
    const s = document.createElement('script')
    s.id = 'cf-turnstile-script'
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js'
    s.async = true
    s.defer = true
    s.onload = () => resolve()
    s.onerror = () => reject(new Error('turnstile script load failed'))
    document.head.appendChild(s)
  })
}

async function initTurnstile(): Promise<void> {
  if (!process.client) return
  const siteKey = (config.public as any)?.NUXT_PUBLIC_TURNSTILE_SITEKEY as string | undefined
  if (!siteKey || !turnstileEl.value) return
  await loadTurnstileScript()
  // Re-render widget each init to avoid stale instances
  try {
    turnstileEl.value.innerHTML = ''
    if (window?.turnstile) {
      window.turnstile.render(turnstileEl.value, {
        sitekey: siteKey,
        callback: (token: string) => {
          cfToken.value = token
        },
        'error-callback': () => {
          cfToken.value = ''
        },
        'expired-callback': () => {
          cfToken.value = ''
        },
      })
    }
  } catch {
    // keep UI functional even if widget fails
  }
}

// Clients (email+pwd → pending_2fa → totp)
const email = ref('')
const password = ref('')
const turnstileToken = ref('') // token externe (optionnel)
const pending2FA = ref(false)
const otp = ref('')
const otpActivate = ref('')
const totpBootstrap = ref<{ secret: string; otpauth_url: string } | null>(null)
const totpProvisioned = computed(() => !!totpBootstrap.value)
const otpOk = computed(() => /^[0-9]{6}$/.test(otp.value))
const otpActivateOk = computed(() => /^[0-9]{6}$/.test(otpActivate.value))
const recoveryCodes = ref<string[]>([])

// Dojo (WebAuthn)
const username = ref('')

// Utilities — base64url ↔ ArrayBuffer
function b64uToArrayBuffer(b64url: string): ArrayBuffer {
  const pad = (s: string) => s + '==='.slice((s.length + 3) % 4)
  const b64 = pad(b64url.replace(/-/g, '+').replace(/_/g, '/'))
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  return arr.buffer
}
function arrayBufferToB64u(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i] ?? 0)
  const b64 = btoa(bin)
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

// Mounted — feature detect
onMounted(async () => {
  webauthnCapable.value = !!(window?.PublicKeyCredential && navigator?.credentials)
  if (mode.value === 'clients') {
    await initTurnstile().catch(() => {})
  }
})

// Actions — Clients
async function onLoginClients() {
  busy.value = true
  msg.value = ''
  try {
    // Étape 1: login
    const res = (await $fetch('/api/auth/creds', {
      method: 'POST',
      body: {
        action: 'login',
        email: email.value,
        password: password.value,
        turnstile: cfToken.value || undefined,
      },
      credentials: 'include',
    })) as Record<string, unknown>

    const status = String(res?.status ?? '')
    if (status === 'pending_2fa') {
      pending2FA.value = true
      msg.value = 'Étape 2FA requise — saisissez votre TOTP.'
      return
    }

    // Par défaut, rester prudent
    msg.value = 'Connexion non finalisée. Réessayez.'
  } catch (e: any) {
    msg.value = 'Connexion non finalisée. Réessayez.'
  } finally {
    busy.value = false
  }
}

async function onTotpBootstrap() {
  busy.value = true
  msg.value = ''
  try {
    const res = (await $fetch('/api/auth/creds', {
      method: 'POST',
      body: { action: 'totpBootstrap' },
      credentials: 'include',
    })) as { ok?: boolean; secret?: string; otpauth_url?: string }

    if (res?.ok && res.secret && res.otpauth_url) {
      totpBootstrap.value = { secret: res.secret, otpauth_url: res.otpauth_url }
      msg.value = ''
    } else {
      msg.value = 'Initialisation TOTP indisponible.'
    }
  } catch {
    msg.value = 'Initialisation TOTP indisponible.'
  } finally {
    busy.value = false
  }
}

async function onTotpActivate() {
  if (!otpActivateOk.value) return
  busy.value = true
  msg.value = ''
  try {
    const res = (await $fetch('/api/auth/creds', {
      method: 'POST',
      body: { action: 'totpActivate', otp: otpActivate.value },
      credentials: 'include',
    })) as { ok?: boolean; recovery_codes?: string[] }

    if (res?.ok) {
      recoveryCodes.value = Array.isArray(res.recovery_codes) ? res.recovery_codes : []
      msg.value = 'TOTP activé. Saisissez un code pour vérifier et terminer la connexion.'
    } else {
      msg.value = 'Code invalide. Réessayez.'
    }
  } catch {
    msg.value = 'Activation TOTP indisponible.'
  } finally {
    busy.value = false
  }
}

async function onTotpVerify() {
  if (!otpOk.value) return
  busy.value = true
  msg.value = ''
  try {
    const res = (await $fetch('/api/auth/creds', {
      method: 'POST',
      body: { action: 'totpVerify', otp: otp.value, turnstile: cfToken.value || undefined },
      credentials: 'include',
    })) as { ok?: boolean }

    if (res?.ok) {
      // Le backend dépose des cookies HttpOnly (__Host-pp_refresh, __Host-pp_realm=C)
      // On laisse le middleware SSR router vers /dashboard; on force la navigation.
      await router.push('/dashboard')
      return
    }
    msg.value = 'Code incorrect. Réessayez.'
  } catch {
    msg.value = 'Vérification indisponible.'
  } finally {
    busy.value = false
  }
}

// Actions — Dojo (WebAuthn)
async function onWebAuthn() {
  if (!webauthnCapable.value) {
    msg.value = 'WebAuthn non disponible sur cet appareil.'
    return
  }
  busy.value = true
  msg.value = ''
  try {
    // 1) Options
    const optRes = (await $fetch('/api/auth/theme', {
      // On réutilise la route serveur étendue (back‑compat): action=webauthnOptions
      method: 'POST',
      body: { action: 'webauthnOptions', username: username.value || undefined },
      credentials: 'include',
    })) as { ok?: boolean; options?: any }

    if (!optRes?.ok || !optRes.options?.publicKey) {
      msg.value = 'Passkey indisponible. Réessayez.'
      return
    }

    const pubkey = optRes.options.publicKey
    // Décodage des champs binaire (challenge, allowCredentials[].id)
    const requestOptions: PublicKeyCredentialRequestOptions = {
      ...pubkey,
      challenge: typeof pubkey.challenge === 'string' ? b64uToArrayBuffer(pubkey.challenge) : pubkey.challenge,
      allowCredentials: Array.isArray(pubkey.allowCredentials)
        ? pubkey.allowCredentials.map((c: any) => ({
            ...c,
            id: typeof c.id === 'string' ? b64uToArrayBuffer(c.id) : c.id,
          }))
        : undefined,
      userVerification: 'required',
    }

    // 2) navigator.credentials.get
    const cred = (await navigator.credentials.get({
      publicKey: requestOptions,
    })) as PublicKeyCredential | null

    if (!cred) {
      msg.value = 'Vérification annulée.'
      return
    }

    const assertion = cred.response as AuthenticatorAssertionResponse
    const payload = {
      id: cred.id,
      type: cred.type,
      rawId: arrayBufferToB64u(cred.rawId),
      response: {
        clientDataJSON: arrayBufferToB64u(assertion.clientDataJSON),
        authenticatorData: arrayBufferToB64u(assertion.authenticatorData),
        signature: arrayBufferToB64u(assertion.signature),
        userHandle: assertion.userHandle ? arrayBufferToB64u(assertion.userHandle) : null,
      },
      clientExtensionResults: (cred as any).getClientExtensionResults?.() ?? {},
    }

    // 3) Vérification serveur
    const verifyRes = (await $fetch('/api/auth/theme', {
      method: 'POST',
      body: { action: 'webauthnVerify', credential: payload, username: username.value || undefined },
      credentials: 'include',
    })) as { ok?: boolean }

    if (verifyRes?.ok) {
      // Cookies HttpOnly déposés (__Host-pp_refresh, __Host-pp_realm=A). Rediriger vers console.
      await router.push('/console')
      return
    }

    msg.value = 'Vérification Passkey refusée.'
  } catch {
    msg.value = 'Vérification indisponible pour le moment.'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
@reference "@/assets/css/main.css";

/* Buttons */
.btn-primary {
  @apply rounded-lg px-4 py-2 font-semibold bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-60 disabled:cursor-not-allowed;
}
.btn-secondary {
  @apply rounded-lg px-4 py-2 font-medium bg-white/10 border border-white/20 text-slate-100 hover:bg-white/15 disabled:opacity-60 disabled:cursor-not-allowed;
}
.btn-tab {
  @apply rounded-lg px-3 py-1.5 font-medium text-sky-200 border border-sky-700/50 bg-slate-800/50 hover:bg-slate-800;
}
.btn-tab--active {
  @apply border-emerald-500 text-emerald-300 bg-slate-800;
}

/* Inputs / labels / messages */
.lbl {
  @apply text-sm text-slate-200;
}
.inp {
  @apply w-full rounded-lg bg-slate-800/70 border border-slate-600/50 px-3 py-2 text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500;
}
.msg {
  @apply text-sm text-rose-300;
}
.code {
  @apply inline-block rounded bg-slate-800/60 px-1.5 py-0.5 text-[13px] text-slate-100;
}
</style>
