<template>
  <section class="min-h-screen grid place-items-center px-6 py-10">
    <div class="w-full max-w-3xl space-y-6 rounded-2xl border border-slate-700/50 bg-slate-900/40 p-6 backdrop-blur">
      <header class="space-y-1">
        <h1 class="text-2xl md:text-3xl font-bold text-emerald-400">Console Dojo</h1>
        <p class="text-slate-300">
          Signature de session via Passkey (WebAuthn) — aucun jeton manipulé côté client.
        </p>
      </header>

      <div class="space-y-4">
        <div class="grid gap-2">
          <span class="lbl">État</span>
          <p class="text-slate-200">
            <span v-if="signedAt">Signée à {{ signedAt }}</span>
            <span v-else>Non signée</span>
          </p>
        </div>

        <div class="grid gap-2">
          <span class="lbl">Action</span>
          <div class="flex items-center gap-3">
            <button class="btn-primary" :disabled="busy || !webauthnCapable" @click="onSign">
              <span v-if="!busy">Signer la session</span>
              <span v-else>Signature…</span>
            </button>
            <span v-if="!webauthnCapable" class="text-sm text-amber-300">
              WebAuthn non disponible dans ce navigateur.
            </span>
          </div>
        </div>

        <p v-if="msg" class="msg">{{ msg }}</p>

        <div class="mt-4 rounded-lg border border-slate-700/60 p-4 space-y-3">
          <p class="text-slate-300 text-sm">
            La signature utilise <span class="text-cyan-300">navigator.credentials.get</span> avec
            vérification utilisateur requise (UV=required). Aucun cookie n’est lu côté client; le
            serveur valide le nonce et trace l’événement.
          </p>
          <hr class="border-slate-700/60" />
          <div class="space-y-2">
            <p class="text-slate-300 text-sm">
              Mode Laby (antichambre) — illusions plausibles, sans effet réel. Accès aux artefacts canarisés:
            </p>
            <ul class="list-disc pl-6 text-slate-200 text-sm">
              <li><a href="/artifacts/.env" class="underline hover:text-emerald-300">.env (DNS token)</a></li>
              <li><a href="/artifacts/id_ed25519" class="underline hover:text-emerald-300">id_ed25519 (clé factice)</a></li>
              <li><a href="/artifacts/notes_admin.txt" class="underline hover:text-emerald-300">notes_admin.txt (URL token)</a></li>
            </ul>
            <div class="flex items-center gap-3">
              <button class="btn-secondary" :disabled="busy" @click="simulateLaby">Simuler une action</button>
              <span v-if="labyMsg" class="text-slate-300 text-sm">{{ labyMsg }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// Dojo Console — SSR-first, no token handling in JS.
// Flow:
//  1) GET nonce (via Nuxt server route proxy -> Django /api/auth/nonce/)
//  2) navigator.credentials.get (UV=required) with challenge = nonce
//  3) POST nonce/verify (proxy -> /api/auth/nonce/verify), includes assertion payload
// Notes: Backend ne réémet aucun secret au client; cookies HttpOnly gèrent la session.

import { onMounted, ref } from 'vue'

// UI state
const busy = ref(false)
const msg = ref('')
const signedAt = ref<string | null>(null)
const webauthnCapable = ref(false)
const labyMsg = ref('')

// base64url helpers
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
  for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i])
  const b64 = btoa(bin)
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

onMounted(() => {
  webauthnCapable.value = !!(window?.PublicKeyCredential && navigator?.credentials)
})

async function fetchNonce(): Promise<string | null> {
  try {
    // Nuxt server route extended (back-compat) → action 'nonce' (maps to GET /api/auth/nonce/)
    const res = (await $fetch('/api/auth/theme', {
      method: 'POST',
      credentials: 'include',
      body: { action: 'nonce' },
    })) as { ok?: boolean; nonce?: string }
    if (res?.ok && typeof res.nonce === 'string' && res.nonce.length > 0) {
      return res.nonce
    }
    return null
  } catch {
    return null
  }
}

async function postNonceVerify(nonce: string, assertion: any): Promise<boolean> {
  try {
    const res = (await $fetch('/api/auth/theme', {
      method: 'POST',
      credentials: 'include',
      body: { action: 'nonceVerify', nonce, assertion },
    })) as { ok?: boolean }
    return !!res?.ok
  } catch {
    return false
  }
}

async function onSign() {
  if (!webauthnCapable.value) {
    msg.value = 'WebAuthn indisponible sur cet appareil.'
    return
  }
  busy.value = true
  msg.value = ''
  try {
    // 1) Obtenir un nonce
    const nonce = await fetchNonce()
    if (!nonce) {
      msg.value = 'Nonce indisponible. Réessayez.'
      return
    }

    // 2) Construire des options d’assertion minimalistes avec UV=required
    const rpId = window.location.hostname
    const publicKey: PublicKeyCredentialRequestOptions = {
      challenge: b64uToArrayBuffer(nonce),
      userVerification: 'required',
      rpId,
      // allowCredentials: [] // optionnel; si absent, le navigateur choisit une credential valide pour ce RP
      timeout: 60_000,
    }

    const cred = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null
    if (!cred) {
      msg.value = 'Signature annulée.'
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

    // 3) Vérifier côté serveur
    const ok = await postNonceVerify(nonce, payload)
    if (!ok) {
      msg.value = 'Signature refusée ou expirée. Réessayez.'
      return
    }

    signedAt.value = new Date().toLocaleString()
    msg.value = ''
  } catch {
    msg.value = 'Signature indisponible pour le moment.'
  } finally {
    busy.value = false
  }
}
async function simulateLaby() {
  // Simule une latence réaliste et un succès neutre (aucun effet côté prod)
  labyMsg.value = ''
  busy.value = true
  await new Promise((r) => setTimeout(r, 600 + Math.floor(Math.random() * 400)))
  busy.value = false
  labyMsg.value = 'Opération réussie.'
  setTimeout(() => (labyMsg.value = ''), 2000)
}
</script>

<style scoped>
@reference "@/assets/css/main.css";

/* Labels, messages, buttons */
.lbl {
  @apply text-sm text-slate-200;
}
.msg {
  @apply text-sm text-rose-300;
}
.btn-primary {
  @apply rounded-lg px-4 py-2 font-semibold bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-60 disabled:cursor-not-allowed;
}
</style>
