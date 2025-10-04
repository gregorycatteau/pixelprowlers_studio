<template>
  <section class="mx-auto max-w-3xl p-6 space-y-6">
    <header class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <NuxtLink to="/projects" class="text-sm text-blue-600 hover:underline">← Back</NuxtLink>
        <h1 class="text-2xl font-semibold">Project: {{ project?.name ?? slug }}</h1>
      </div>
      <button
        class="btn bg-red-600 hover:bg-red-700"
        @click="onDelete"
        :disabled="deleting || pending"
        title="Delete project"
      >
        Delete
      </button>
    </header>

    <div v-if="pending" class="text-gray-600">Loading…</div>
    <div v-else-if="loadError" class="text-red-700">
      Failed to load project: {{ loadError }}
    </div>
    <div v-else-if="!project" class="text-gray-600">
      Project not found.
    </div>

    <form v-else @submit.prevent="onSave" class="space-y-4 border rounded p-4">
      <div>
        <label class="block text-sm font-medium mb-1">Name</label>
        <input
          v-model="form.name"
          type="text"
          class="input"
          placeholder="Project name"
          :disabled="saving"
        />
      </div>

      <div>
        <label class="block text-sm font-medium mb-1">Description</label>
        <textarea
          v-model="form.description"
          class="input"
          placeholder="Short description (optional)"
          :disabled="saving"
        />
      </div>

      <div>
        <label class="block text-sm font-medium mb-1">Status</label>
        <select v-model="form.status" class="input" :disabled="saving">
          <option value="draft">draft</option>
          <option value="active">active</option>
          <option value="archived">archived</option>
        </select>
      </div>

      <div class="text-xs text-gray-500">
        <div><span class="font-medium">Updated:</span> {{ formatDate(project.updated_at) }}</div>
        <div><span class="font-medium">Created:</span> {{ formatDate(project.created_at) }}</div>
      </div>

      <div class="flex items-center gap-3">
        <button class="btn" :disabled="saving || pending">Save</button>
        <span v-if="err" class="text-red-600 text-sm">{{ err }}</span>
        <span v-if="ok" class="text-green-600 text-sm">Saved</span>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watchEffect } from 'vue'
import type { Project, ProjectUpdateBody } from '~/shared/types/projects'

const route = useRoute()
const slug = computed(() => route.params.slug as string)

const {
  data,
  pending,
  refresh,
  error: loadErr,
} = await useFetch<Project>(`/api/projects/${slug.value}`, { method: 'GET' })

const project = computed<Project | null>(() => data.value || null)
const loadError = computed(() => (loadErr.value ? (loadErr.value as any)?.statusMessage ?? 'Unknown error' : null))

const form = ref<ProjectUpdateBody>({
  name: '',
  description: '',
  status: 'draft',
})

watchEffect(() => {
  if (project.value) {
    form.value = {
      name: project.value.name,
      description: project.value.description,
      status: project.value.status,
    }
  }
})

const saving = ref(false)
const deleting = ref(false)
const err = ref<string | null>(null)
const ok = ref(false)

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const onSave = async () => {
  if (!slug.value) return
  err.value = null
  ok.value = false
  saving.value = true
  try {
    await $fetch(`/api/projects/${slug.value}`, {
      method: 'PATCH',
      body: form.value,
    })
    ok.value = true
    await refresh()
  } catch (e: any) {
    err.value = e?.statusMessage || 'Save failed'
  } finally {
    saving.value = false
  }
}

const onDelete = async () => {
  if (!slug.value) return
  if (!confirm('Are you sure you want to delete this project? This action cannot be undone.')) return
  deleting.value = true
  err.value = null
  try {
    await $fetch(`/api/projects/${slug.value}`, { method: 'DELETE' })
    await navigateTo('/projects')
  } catch (e: any) {
    err.value = e?.statusMessage || 'Delete failed'
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.input { @apply w-full border rounded px-2 py-1 outline-none focus:ring-2 focus:ring-blue-200; }
.btn { @apply inline-flex items-center px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50; }
</style>
