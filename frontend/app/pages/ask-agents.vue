<template>
  <AppShell>
    <template #header>
      <PxHeader />
    </template>

    <template #toolbar>
      <div class="ask-toolbar">
        <div class="ask-toolbar__group">
          <h1 class="ask-toolbar__title">Console agents IA</h1>
          <p class="ask-toolbar__subtitle">
            Choisis un agent certifié et ouvre une nouvelle conversation Dojo.
          </p>
        </div>
        <PxButton variant="ghost" class="ask-toolbar__action" @click="policyOpen = true">
          Politique d’usage
        </PxButton>
      </div>
    </template>

    <section class="ask">
      <aside class="ask__sidebar">
        <PxCard class="ask__card">
          <template #header>
            <div class="ask__card-header">
              <h2 class="ask__card-title">Agents disponibles</h2>
              <span class="ask__card-caption">{{ agents.length }} actifs</span>
            </div>
          </template>
          <ul class="ask__agent-list" role="tablist" aria-label="Sélection agent">
            <li v-for="agent in agents" :key="agent.slug" class="ask__agent-item">
              <button
                type="button"
                class="ask__agent-button"
                role="tab"
                :aria-selected="agent.slug === selectedSlug"
                @click="selectAgent(agent.slug)"
              >
                <span class="ask__agent-name">{{ agent.title }}</span>
                <span class="ask__agent-alias">{{ agent.slug }}</span>
              </button>
            </li>
          </ul>
        </PxCard>

        <PxCard v-if="selectedAgent" class="ask__card">
          <template #header>
            <div class="ask__card-header">
              <h2 class="ask__card-title">Détails agent</h2>
              <span class="ask__card-caption">{{ selectedAgent.slug }}</span>
            </div>
          </template>
          <p class="ask__description">{{ selectedAgent.description || 'Description indisponible.' }}</p>
          <div v-if="hasCapabilities" class="ask__capabilities">
            <h3 class="ask__capabilities-title">Capacités</h3>
            <ul class="ask__capabilities-list">
              <li v-for="cap in capabilityEntries" :key="cap.label" class="ask__capabilities-item">
                <span class="ask__capabilities-label">{{ cap.label }}</span>
                <span class="ask__capabilities-value">{{ cap.value }}</span>
              </li>
            </ul>
          </div>
        </PxCard>
      </aside>

      <section class="ask__content" aria-live="polite">
        <PxCard class="ask__card">
          <template #header>
            <h2 class="ask__card-title">Créer une conversation</h2>
          </template>
          <div class="ask-new">
            <p class="ask-new__hint">
              Chaque conversation est traçée et soumise aux politiques de sécurité. Utilise cette action
              pour engager une nouvelle session avec l’agent sélectionné.
            </p>
            <PxButton
              class="ask-new__button"
              :disabled="!selectedAgent || creating"
              :loading="creating"
              @click="createConversation"
            >
              Ouvrir une conversation
            </PxButton>
            <p class="ask-new__footer">Une fois créée, tu seras redirigé vers la page de messages.</p>
          </div>
        </PxCard>
      </section>
    </section>

    <template #footer>
      <div class="ask-footer">
        <p>Console logicielle : contrôle d’accès côté serveur, audit log structuré.</p>
      </div>
    </template>
  </AppShell>

  <PxModal v-model="policyOpen" title="Politique d’usage console agents">
    <p class="ask-policy">
      Chaque requête est tracée côté backend et soumise aux garde-fous de confidentialité. Les
      indisponibilités prolongées déclenchent une alerte SecOps.
    </p>
    <template #footer>
      <PxButton variant="ghost" @click="policyOpen = false">Compris</PxButton>
    </template>
  </PxModal>

  <PxToast v-model="toast.visible" :variant="toast.variant" :message="toast.message" />
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { navigateTo } from '#app'
import type { FetchError } from 'ofetch'

definePageMeta({
  middleware: ['dojo'],
})

type DojoAgent = {
  slug: string
  title: string
  description: string
  capabilities: Record<string, unknown>
  is_active: boolean
}

type ConversationCreateResponse = {
  id: string
  status: string
  agent: string
}

const nuxtApp = useNuxtApp()
const auth = useAuth()
const nonce = useNonce()

const agents = ref<DojoAgent[]>([])
const selectedSlug = ref('')
const policyOpen = ref(false)
const creating = ref(false)

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

const selectAgent = (slug: string) => {
  selectedSlug.value = slug
}

const selectedAgent = computed(() => agents.value.find((agent) => agent.slug === selectedSlug.value) || null)

const capabilityEntries = computed(() => {
  if (!selectedAgent.value) return [] as Array<{ label: string; value: string }>
  const caps = selectedAgent.value.capabilities || {}
  return Object.entries(caps).map(([key, value]) => ({
    label: key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))
})

const hasCapabilities = computed(() => capabilityEntries.value.length > 0)

const ensureNonce = async () => {
  if (!nonce.current) {
    await nonce.refresh()
  }
}

const loadAgents = async () => {
  try {
    const res = await nuxtApp.$fetch<DojoAgent[] | { results?: DojoAgent[] } | null>('/api/agents/', {
      method: 'GET',
    })
    const list = Array.isArray(res) ? res : res?.results ?? []
    agents.value = list
    selectedSlug.value = list.at(0)?.slug ?? ''
  } catch {
    openToast("Impossible de charger les agents.", 'danger')
  }
}

const requestWithNonce = async <T>(executor: () => Promise<T>): Promise<T> => {
  let retried = false
  for (;;) {
    try {
      return await executor()
    } catch (err) {
      const error = err as FetchError<{ error?: string }>
      const code = error?.response?._data?.error
      if (!retried && code && ['nonce_missing', 'nonce_invalid', 'nonce_expired', 'nonce_replay'].includes(code)) {
        retried = true
        await nonce.refresh()
        continue
      }
      throw err
    }
  }
}

const createConversation = async () => {
  if (!selectedAgent.value) {
    openToast('Sélectionne un agent pour démarrer.', 'warning')
    return
  }

  await ensureNonce()
  creating.value = true

  try {
    const payload = {
      agent: selectedAgent.value.slug,
      title: selectedAgent.value.title,
    }

    const res = await requestWithNonce(() =>
      nuxtApp.$fetch<ConversationCreateResponse>('/api/conversations/', {
        method: 'POST',
        body: payload,
      }),
    )

    openToast('Conversation créée.', 'success')
    await navigateTo(`/conversations/${res.id}`)
  } catch (err) {
    const error = err as FetchError<{ error?: string }>
    const code = error?.response?._data?.error
    if (code === 'conversation_archived') {
      openToast('Conversation indisponible.', 'warning')
    } else if (code) {
      openToast(`Erreur : ${code}`, 'danger')
    } else {
      openToast('Création impossible. Réessayez.', 'danger')
    }
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  await auth.fetchMe(true).catch(() => {})
  if (!auth.gate.value.ok) {
    await navigateTo('/gate')
    return
  }
  await ensureNonce()
  await loadAgents()
})
</script>

<style scoped>
@reference "@/assets/css/main.css";
.ask {
  @apply mx-auto grid max-w-6xl gap-6 px-4 py-8 md:grid-cols-[320px,1fr] md:px-8;
}
.ask__sidebar {
  @apply grid gap-4;
}
.ask__content {
  @apply grid gap-4;
}
.ask__card {
  @apply flex flex-col gap-4;
}
.ask__card-header {
  @apply flex items-center justify-between;
}
.ask__card-title {
  @apply text-base font-semibold text-color-text;
}
.ask__card-caption {
  @apply text-xs text-color-muted;
}
.ask__agent-list {
  @apply grid gap-2;
}
.ask__agent-item {
  @apply list-none;
}
.ask__agent-button {
  @apply flex w-full flex-col items-start gap-1 rounded-[var(--radius-md)] border border-color-border bg-color-bg px-3 py-3 text-left transition hover:bg-color-elev focus-visible:u-focus-ring;
}
.ask__agent-button[aria-selected='true'] {
  @apply border-color-primary bg-color-primary-soft text-color-text;
}
.ask__agent-name {
  @apply text-sm font-medium text-color-text;
}
.ask__agent-alias {
  @apply text-xs text-color-muted;
}
.ask__description {
  @apply text-sm text-color-text;
}
.ask__capabilities {
  @apply grid gap-2;
}
.ask__capabilities-title {
  @apply text-xs font-semibold uppercase tracking-wide text-color-muted;
}
.ask__capabilities-list {
  @apply grid gap-1;
}
.ask__capabilities-item {
  @apply flex items-center justify-between;
}
.ask__capabilities-label {
  @apply text-xs text-color-muted;
}
.ask__capabilities-value {
  @apply text-xs text-color-text;
}
.ask-new {
  @apply grid gap-3;
}
.ask-new__hint {
  @apply text-sm text-color-muted;
}
.ask-new__button {
  @apply w-full md:w-auto;
}
.ask-new__footer {
  @apply text-xs text-color-muted;
}
.ask-toolbar {
  @apply flex flex-col gap-4 px-4 py-4 md:flex-row md:items-center md:justify-between md:px-6;
}
.ask-toolbar__group {
  @apply grid gap-1;
}
.ask-toolbar__title {
  @apply text-xl font-semibold text-color-text;
}
.ask-toolbar__subtitle {
  @apply text-sm text-color-muted;
}
.ask-toolbar__action {
  @apply min-w-[140px];
}
.ask-footer {
  @apply flex items-center justify-center px-4 py-3 text-xs text-color-muted;
}
.ask-policy {
  @apply text-sm text-color-text;
}
</style>
