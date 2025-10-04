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

        <button class="btn-primary" :disabled="loading">
          <span v-if="!loading">Continuer</span>
          <span v-else>Ouverture…</span>
        </button>

        <p v-if="errorMsg" class="error">
          {{ errorMsg }}
        </p>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { navigateTo } from '#app'

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function onSubmit() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = (await $fetch('/api/auth/creds', {
      method: 'POST',
      body: { username: username.value, password: password.value },
      credentials: 'include',
    })) as { status?: string; next?: string[] }

    if (res?.status === 'pending') {
      // Chemin “normal” : on passe en préflight neutre
      await navigateTo('/preflight')
    } else {
      // Réponse générique
      errorMsg.value = 'Impossible d’ouvrir la session.'
    }
  } catch (e: any) {
    errorMsg.value = 'Impossible d’ouvrir la session.'
  } finally {
    loading.value = false
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
.btn-primary:hover {
  transform: translateY(-1px);
}
.error {
  @apply mt-3 text-sm;
  color: #fda4af;
}
</style>
