<template>
  <section class="mx-auto max-w-4xl p-6 space-y-6">
    <header class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Projects</h1>
      <NuxtLink to="/" class="text-sm text-blue-600 hover:underline">Back to Home</NuxtLink>
    </header>

    <!-- Create Project -->
    <form @submit.prevent="onCreate" class="space-y-3 border rounded p-4">
      <h2 class="text-lg font-medium">Create a new project</h2>

      <div>
        <label class="block text-sm font-medium mb-1">Name</label>
        <input v-model="form.name" type="text" class="input" placeholder="Ex: Site Vitrine" required />
      </div>

      <div>
        <label class="block text-sm font-medium mb-1">Description</label>
        <textarea v-model="form.description" class="input" placeholder="Optional short description" />
      </div>

      <div>
        <label class="block text-sm font-medium mb-1">Status</label>
        <select v-model="form.status" class="input">
          <option value="draft">draft</option>
          <option value="active">active</option>
          <option value="archived">archived</option>
        </select>
      </div>

      <div class="flex items-center gap-3">
        <button class="btn" :disabled="creating">Create</button>
        <span v-if="err" class="text-red-600 text-sm">{{ err }}</span>
        <span v-if="ok" class="text-green-600 text-sm">Created</span>
      </div>
    </form>

    <!-- List Projects -->
    <div class="space-y-2">
      <div v-if="pending">Loading projects…</div>
      <div v-else-if="fetchError" class="text-red-700">Failed to load: {{ fetchError }}</div>
      <ul v-else class="divide-y">
        <li v-for="p in projects" :key="p.slug" class="py-3 flex items-center justify-between">
          <div class="min-w-0">
            <NuxtLink :to="`/projects/${p.slug}`" class="text-blue-600 hover:underline break-words">
              {{ p.name }}
            </NuxtLink>
            <div class="text-xs text-gray-500 mt-0.5">
              Status: <span class="font-medium">{{ p.status }}</span>
            </div>
          </div>
          <div class="text-xs text-gray-400 shrink-0 ml-3">
            {{ formatDate(p.updated_at) }}
          </div>
        </li>
      </ul>
      <div v-if="!pending && projects.length === 0" class="text-sm text-gray-500">No projects yet.</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Project, ProjectCreateBody } from '~/shared/types/projects'

const {
  data,
  pending,
  refresh,
  error: loadErr,
} = await useFetch<Project[]>('/api/projects', { method: 'GET' })

const projects = computed<Project[]>(() => data.value || [])
const fetchError = computed(() => loadErr.value ? (loadErr.value as any)?.statusMessage ?? 'Unknown error' : null)

const form = ref<ProjectCreateBody>({
  name: '',
  description: '',
  status: 'draft',
})

const creating = ref(false)
const err = ref<string | null>(null)
const ok = ref(false)

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const onCreate = async () => {
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
.input { @apply w-full border rounded px-2 py-1 outline-none focus:ring-2 focus:ring-blue-200; }
.btn { @apply inline-flex items-center px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50; }
</style>
