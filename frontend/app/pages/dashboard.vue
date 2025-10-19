<template>
  <section class="min-h-screen grid place-items-center px-6 py-10">
    <div class="w-full max-w-4xl space-y-8 rounded-2xl border border-slate-700/50 bg-slate-900/40 p-6 backdrop-blur">
      <header class="space-y-1">
        <h1 class="text-2xl md:text-3xl font-bold text-emerald-400">Tableau de bord (Clients)</h1>
        <p class="text-slate-300">
          Export sécurisé des codes de récupération — aucun jeton n’est manipulé côté client.
        </p>
      </header>

      <!-- Recovery codes input -->
      <section class="space-y-4">
        <h2 class="text-lg font-semibold text-cyan-300">Codes de récupération</h2>
        <p class="text-slate-300 text-sm">
          Collez ici vos codes de récupération (un par ligne), tels qu’ils vous ont été affichés à l’activation TOTP.
        </p>
        <textarea
          class="textarea"
          rows="6"
          placeholder="ABCD-1234&#10;EF56-7890&#10;…"
          v-model="codesText"
          aria-label="Codes de récupération, un code par ligne"
          :disabled="busy"
        />
        <p class="text-xs text-slate-400">
          Les codes ne sont jamais stockés côté serveur en clair. Ils sont vérifiés en mémoire et
          peuvent être empaquetés dans un zip chifré (AES‑256) ou chiffrés avec votre clé publique PGP.
        </p>
      </section>

      <!-- Export ZIP AES-256 -->
      <section class="space-y-4 rounded-xl border border-slate-700/60 p-4">
        <h3 class="text-base font-semibold text-emerald-300">Export ZIP AES‑256 (mot de passe requis)</h3>
        <div class="grid gap-2 md:grid-cols-[1fr_auto] md:items-end">
          <div class="grid gap-2">
            <label for="zip-pass" class="lbl">Mot de passe du ZIP (ne sera jamais stocké)</label>
            <input
              id="zip-pass"
              class="inp"
              type="password"
              v-model="zipPassword"
              :disabled="busy"
              minlength="8"
              placeholder="Mot de passe (≥ 8 caractères)"
              autocomplete="new-password"
            />
            <p class="text-xs text-slate-400">
              Conservez ce mot de passe, il sera nécessaire pour ouvrir l’archive.
            </p>
          </div>
          <button
            type="button"
            class="btn-primary md:justify-self-end"
            :disabled="busy || !canZip"
            @click="onExportZip"
          >
            <span v-if="!busy">Télécharger ZIP chiffré</span>
            <span v-else>Téléchargement…</span>
          </button>
        </div>
      </section>

      <!-- Export PGP (ASCII armored) -->
      <section class="space-y-4 rounded-xl border border-slate-700/60 p-4">
        <h3 class="text-base font-semibold text-sky-300">Export PGP (ASCII‑armored)</h3>
        <p class="text-slate-300 text-sm">
          Collez votre clé publique PGP (ASCII-armored). Le serveur renverra un message chifré
          contenant vos codes (aucun stockage en clair).
        </p>
        <textarea
          class="textarea"
          rows="6"
          placeholder="-----BEGIN PGP PUBLIC KEY BLOCK-----&#10;…&#10;-----END PGP PUBLIC KEY BLOCK-----"
          v-model="pgpPublicKey"
          aria-label="Clé publique PGP ASCII‑armored"
          :disabled="busy"
        />
        <div class="flex items-center justify-between gap-3">
          <small class="text-xs text-slate-400">
            Astuce: si vous utilisez un gestionnaire de clés, exportez la clé publique en ASCII‑armored.
          </small>
          <button type="button" class="btn-secondary" :disabled="busy || !canPgp" @click="onExportPgp">
            <span v-if="!busy">Télécharger .asc chifré</span>
            <span v-else>Préparation…</span>
          </button>
        </div>
      </section>

      <!-- Neutral status / errors -->
      <p v-if="msg" class="msg">{{ msg }}</p>

      <!-- Safety / privacy notes -->
      <footer class="rounded-xl border border-slate-700/60 p-4">
        <ul class="list-disc pl-6 space-y-1 text-slate-300 text-sm">
          <li>Aucun accès ou écriture de jetons en JS; seuls des cookies HttpOnly sont utilisés côté serveur.</li>
          <li>
            Le ZIP AES‑256 est chifré avec votre mot de passe (jamais stocké). Le fichier .asc PGP est
            chifré avec votre clé publique (ASCII‑armored).
          </li>
          <li>Les messages d’erreur restent neutres (pas de détails sensibles).</li>
        </ul>
      </footer>
    </div>
  </section>
</template>

<script setup lang="ts">
// SSR-first: aucune lecture/écriture de cookies en JS. On utilise uniquement des appels
// à des endpoints serveur (backend via origin Nuxt ou même site) et on déclenche
// des téléchargements en mémoire sans exposer des secrets côté client.

import { computed, ref } from 'vue'
import { useRuntimeConfig } from '#app'

// Inputs
const codesText = ref('')
const zipPassword = ref('')
const pgpPublicKey = ref('')

// State
const busy = ref(false)
const msg = ref('')

// Helpers
const codes = computed(() =>
  codesText.value
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter((s) => !!s),
)

const canZip = computed(() => codes.value.length > 0 && typeof zipPassword.value === 'string' && zipPassword.value.length >= 8)
const canPgp = computed(() => codes.value.length > 0 && /BEGIN PGP PUBLIC KEY/.test(pgpPublicKey.value))

// Runtime (dev note: DJANGO_BASE_URL est exposé en public mais utilisé ici uniquement pour construire la requête.
// Les cookies HttpOnly avec SameSite=Strict ne “fuient” pas cross-site; en local (localhost), c’est same‑site.)
const config = useRuntimeConfig()
const DJANGO_BASE_URL = (config.public as any).DJANGO_BASE_URL as string

async function onExportZip() {
  msg.value = ''
  if (!canZip.value) {
    msg.value = 'Paramètres incomplets. Réessayez.'
    return
  }
  busy.value = true
  try {
    // Appel direct à l’endpoint backend prévu:
    // POST /api/auth/totp/recovery/export/  (JSON → binaire ZIP)
    const res = await fetch(`${DJANGO_BASE_URL}/api/auth/totp/recovery/export/`, {
      method: 'POST',
      credentials: 'include', // cookies HttpOnly envoyés si même site
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        format: 'zip',
        codes: codes.value,
        password: zipPassword.value,
      }),
    })

    if (!res.ok) {
      msg.value = 'Export indisponible pour le moment.'
      return
    }

    const ct = res.headers.get('Content-Type') || ''
    if (!ct.includes('application/zip')) {
      msg.value = 'Réponse inattendue. Réessayez.'
      return
    }

    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'recovery-codes.zip'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    msg.value = 'Export indisponible pour le moment.'
  } finally {
    busy.value = false
  }
}

async function onExportPgp() {
  msg.value = ''
  if (!canPgp.value) {
    msg.value = 'Paramètres incomplets. Réessayez.'
    return
  }
  busy.value = true
  try {
    // POST /api/auth/totp/recovery/export/  (JSON → ASCII-armored PGP)
    const res = await fetch(`${DJANGO_BASE_URL}/api/auth/totp/recovery/export/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        format: 'pgp',
        codes: codes.value,
        pgp_public_key: pgpPublicKey.value,
      }),
    })

    if (!res.ok) {
      msg.value = 'Export PGP indisponible.'
      return
    }

    const text = await res.text()
    if (!/^-----BEGIN PGP MESSAGE-----/m.test(text)) {
      msg.value = 'Réponse inattendue. Réessayez.'
      return
    }

    const blob = new Blob([text], { type: 'application/pgp-encrypted' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'recovery-codes.asc'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    msg.value = 'Export PGP indisponible.'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
@reference "@/assets/css/main.css";

.textarea {
  @apply w-full rounded-lg bg-slate-800/70 border border-slate-600/50 px-3 py-2 text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500;
}
.inp {
  @apply w-full rounded-lg bg-slate-800/70 border border-slate-600/50 px-3 py-2 text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500;
}
.lbl {
  @apply text-sm text-slate-200;
}
.btn-primary {
  @apply rounded-lg px-4 py-2 font-semibold bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-60 disabled:cursor-not-allowed;
}
.btn-secondary {
  @apply rounded-lg px-4 py-2 font-medium bg-white/10 border border-white/20 text-slate-100 hover:bg-white/15 disabled:opacity-60 disabled:cursor-not-allowed;
}
.msg {
  @apply text-sm text-rose-300;
}
</style>
