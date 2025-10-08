<template>
  <section class="page">
    <header class="pageHeader">
      <h1 class="pageTitle">Projects</h1>
      <NuxtLink to="/" class="backLink">Back to Home</NuxtLink>
    </header>

    <!-- Create Project -->
    <form @submit.prevent="onCreate" class="formCard">
      <h2 class="formTitle">Create a new project</h2>

      <div class="field">
        <label class="label">Name</label>
        <input v-model="form.name" type="text" class="input" placeholder="Ex: Site Vitrine" required />
      </div>

      <div class="field">
        <label class="label">Description</label>
        <textarea v-model="form.description" class="input" placeholder="Optional short description" />
      </div>

      <div class="field">
        <label class="label">Status</label>
        <select v-model="form.status" class="input">
          <option value="draft">draft</option>
          <option value="active">active</option>
          <option value="archived">archived</option>
        </select>
      </div>

      <div class="formActions">
        <button class="btn" :disabled="creating">Create</button>
        <span v-if="err" class="statusError">{{ err }}</span>
        <span v-if="ok" class="statusOk">Created</span>
      </div>
    </form>

    <!-- List Projects -->
    <div class="listWrap">
      <div v-if="pending" class="loadingMessage">Loading projects…</div>
      <div v-else-if="fetchError" class="errorMessage">Failed to load: {{ fetchError }}</div>

      <ul v-else class="list">
        <li v-for="p in projects" :key="p.slug" class="listItem">
          <div class="itemLeft">
            <NuxtLink :to="`/projects/${p.slug}`" class="projectLink">
              {{ p.name }}
            </NuxtLink>
            <div class="projectMeta">
              Status: <span class="statusText">{{ p.status }}</span>
            </div>
          </div>
          <div class="itemRight">
            {{ formatDate(p.updated_at) }}
          </div>
        </li>
      </ul>

      <div v-if="!pending && projects.length === 0" class="emptyMessage">
        No projects yet.
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Project, ProjectCreateBody } from '~~/shared/types/projects'

/**
 * Charge la liste des projets depuis l’API SSR (Nitro) — méthode GET.
 * - Avantage sécu : pas de token exposé côté client.
 */
const {
  data,
  pending,
  refresh,
  error: loadErr,
} = await useFetch<Project[]>('/api/projects', { method: 'GET' })

/**
 * Liste des projets (toujours un tableau).
 */
const projects = computed<Project[]>(() => data.value || [])

/**
 * Message d’erreur lisible pour l’UI lors du chargement.
 */
const fetchError = computed(() =>
  loadErr.value ? (loadErr.value as any)?.statusMessage ?? 'Unknown error' : null
)

/**
 * Formulaire de création (modèle typé).
 */
const form = ref<ProjectCreateBody>({
  name: '',
  description: '',
  status: 'draft',
})

/** Indicateurs UI pour la création. */
const creating = ref(false)
const err = ref<string | null>(null)
const ok = ref(false)

/**
 * formatDate(iso: string): string
 * Formate une date ISO en chaîne lisible locale.
 * - Sécurisé par try/catch pour éviter de casser l’UI si iso est invalide.
 */
function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

/**
 * onCreate(): Promise<void>
 * Envoie la création de projet au backend via la route Nitro.
 * - Réinitialise le formulaire en cas de succès.
 * - Rafraîchit la liste (SSR fetch) pour refléter l’état serveur.
 * - Gestion d’erreur propre avec message utilisateur.
 */
const onCreate = async (): Promise<void> => {
  err.value = null
  ok.value = false
  creating.value = true
  try {
    await $fetch('/api/projects', {
      method: 'POST',
      body: form.value,
    })
    // Reset form
    form.value = { name: '', description: '', status: 'draft' }
    ok.value = true
    await refresh()
  } catch (e: any) {
    err.value = e?.statusMessage || 'Create failed'
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
@reference "@/assets/css/main.css";
/* --- Layout global --- */
.page {
  @apply mx-auto max-w-4xl p-6 space-y-6;
}

.pageHeader {
  @apply flex items-center justify-between;
}

.pageTitle {
  @apply text-2xl font-semibold;
}

.backLink {
  @apply text-sm text-blue-600 hover:underline;
}

/* --- Carte formulaire --- */
.formCard {
  @apply space-y-3 border rounded-md p-4;
}

.formTitle {
  @apply text-lg font-medium;
}

.field {
  @apply space-y-1;
}

.label {
  @apply block text-sm font-medium mb-1;
}

.input {
  @apply w-full border rounded px-3 py-2 outline-none focus:ring-2 focus:ring-blue-200;
}

.btn {
  @apply inline-flex items-center px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50;
}

.formActions {
  @apply flex items-center gap-3;
}

.statusError {
  @apply text-red-600 text-sm;
}

.statusOk {
  @apply text-green-600 text-sm;
}

/* --- Liste des projets --- */
.listWrap {
  @apply space-y-2;
}

.loadingMessage {
  @apply text-sm text-gray-600;
}

.errorMessage {
  @apply text-red-700;
}

.list {
  @apply divide-y;
}

.listItem {
  @apply py-3 flex items-center justify-between;
}

.itemLeft {
  @apply min-w-0;
}

.projectLink {
  @apply text-blue-600 hover:underline break-words;
}

.projectMeta {
  @apply text-xs text-gray-500 mt-0.5;
}

.statusText {
  @apply font-medium;
}

.itemRight {
  @apply text-xs text-gray-400 shrink-0 ml-3;
}

.emptyMessage {
  @apply text-sm text-gray-500;
}
</style>
