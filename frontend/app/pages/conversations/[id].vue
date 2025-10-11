<template>
  <AppShell>
    <template #header>
      <PxHeader />
    </template>

    <section class="conversation">
      <PxCard class="conversation__card">
        <template #header>
          <div class="conversation__heading">
            <div class="conversation__titles">
              <h1 class="conversation__title">
                {{ conversation?.title || 'Conversation Dojo' }}
              </h1>
              <p class="conversation__subtitle">
                Agent&nbsp;: <span class="conversation__agent">{{ agentLabel }}</span>
              </p>
            </div>
            <span class="conversation__status" :data-variant="statusVariant">
              {{ statusLabel }}
            </span>
          </div>
        </template>

        <div class="conversation__meta">
          <span>
            Créée le <strong>{{ createdAtLabel }}</strong>
          </span>
          <span>
            Messages <strong>{{ messages.length }}</strong>
          </span>
        </div>

        <div v-if="conversation?.status !== 'archived'" class="conversation__actions">
          <PxButton variant="ghost" :loading="archiving" @click="archiveConversation">
            Archiver la conversation
          </PxButton>
        </div>

        <div class="conversation__messages" aria-live="polite">
          <div v-if="loadingMessages" class="conversation__loading">Chargement des messages…</div>
          <ul v-else-if="messages.length" class="conversation__list">
            <li
              v-for="message in messages"
              :key="message.id"
              class="conversation__message"
              :data-role="message.role"
            >
              <div class="conversation__message-header">
                <span class="conversation__message-role">{{ roleLabel(message.role) }}</span>
                <time class="conversation__message-time">{{ formatTimestamp(message.created_at) }}</time>
              </div>
              <p class="conversation__message-body">
                {{ message.content }}
              </p>
            </li>
          </ul>
          <div v-else class="conversation__empty">Aucun message pour le moment.</div>
        </div>

        <div v-if="pagination.next" class="conversation__load-more">
          <PxButton variant="ghost" size="sm" :loading="loadingMessages" @click="loadMessages(true)">
            Charger plus
          </PxButton>
        </div>

        <form class="conversation__composer" @submit.prevent="sendMessage">
          <label class="conversation__composer-label" for="conversation-message">Ton message</label>
          <textarea
            id="conversation-message"
            v-model="draft"
            class="conversation__composer-input"
            rows="4"
            placeholder="Rédige ton message sécurisé…"
            :disabled="sending || conversation?.status === 'archived'"
            required
          />
          <div class="conversation__composer-actions">
            <PxButton
              type="submit"
              :loading="sending"
              :disabled="!draft.trim() || conversation?.status === 'archived'"
            >
              Envoyer
            </PxButton>
            <PxButton
              variant="ghost"
              type="button"
              :disabled="sending"
              @click="refreshMessages"
            >
              Actualiser
            </PxButton>
          </div>
        </form>
      </PxCard>
    </section>

    <PxToast v-model="toast.visible" :variant="toast.variant" :message="toast.message" />
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { navigateTo, useRoute } from '#app'
import type { FetchError } from 'ofetch'

definePageMeta({
  middleware: ['dojo'],
})

type Conversation = {
  id: string
  title: string
  status: 'open' | 'closed' | 'archived'
  agent: string
  agent_title?: string
  agent_description?: string
  created_at: string
  updated_at: string
}

type Message = {
  id: string
  conversation: string
  role: 'user' | 'agent' | 'system'
  content: string
  created_at: string
}

type MessagePage = {
  count: number
  next: string | null
  previous: string | null
  results: Message[]
}

const route = useRoute()
const nuxtApp = useNuxtApp()
const auth = useAuth()
const nonce = useNonce()

const conversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const pagination = reactive<{ next: string | null; previous: string | null }>({
  next: null,
  previous: null,
})

const loadingConversation = ref(false)
const loadingMessages = ref(false)
const sending = ref(false)
const draft = ref('')
const archiving = ref(false)

const toast = reactive({
  visible: false,
  message: '',
  variant: 'info' as 'info' | 'success' | 'warning' | 'danger',
})

const dateFormatter = new Intl.DateTimeFormat('fr-FR', {
  dateStyle: 'short',
  timeStyle: 'short',
})

const conversationId = computed(() => route.params.id as string)

const agentLabel = computed(() => conversation.value?.agent_title || conversation.value?.agent || 'Inconnu')

const statusMap: Record<string, { label: string; variant: 'info' | 'success' | 'warning' | 'danger' }> = {
  open: { label: 'Ouverte', variant: 'info' },
  closed: { label: 'Clôturée', variant: 'warning' },
  archived: { label: 'Archivée', variant: 'danger' },
}

const statusLabel = computed(() => statusMap[conversation.value?.status || 'open']?.label || 'Ouverte')
const statusVariant = computed(() => statusMap[conversation.value?.status || 'open']?.variant || 'info')

const createdAtLabel = computed(() => (conversation.value ? formatTimestamp(conversation.value.created_at) : ''))

const openToast = (message: string, variant: 'info' | 'success' | 'warning' | 'danger' = 'info') => {
  toast.message = message
  toast.variant = variant
  toast.visible = true
}

const formatTimestamp = (iso: string) => dateFormatter.format(new Date(iso))

const roleLabel = (role: Message['role']) => {
  switch (role) {
    case 'agent':
      return 'Agent'
    case 'system':
      return 'Système'
    default:
      return 'Admin'
  }
}

const ensureNonce = async () => {
  if (!nonce.current) {
    await nonce.refresh()
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

const extractPageNumber = (url: string | null): number | null => {
  if (!url) return null
  try {
    const parsed = new URL(url)
    const page = parsed.searchParams.get('page')
    return page ? Number.parseInt(page, 10) : null
  } catch {
    return null
  }
}

const loadConversation = async () => {
  loadingConversation.value = true
  try {
    const data = await nuxtApp.$fetch<Conversation | null>(`/api/conversations/${conversationId.value}/`, {
      method: 'GET',
    })
    if (!data) {
      openToast('Conversation introuvable.', 'warning')
      await navigateTo('/ask-agents')
      return
    }
    conversation.value = data
  } catch (err) {
    openToast('Impossible de charger la conversation.', 'danger')
    console.error(err)
  } finally {
    loadingConversation.value = false
  }
}

const loadMessages = async (append = false) => {
  if (!conversationId.value) return
  if (append && !pagination.next) return

  loadingMessages.value = true
  try {
    const pageParam = append ? extractPageNumber(pagination.next) : null
    const payload = await nuxtApp.$fetch<MessagePage>('/api/messages/', {
      method: 'GET',
      query: {
        conversation: conversationId.value,
        ...(pageParam ? { page: pageParam } : {}),
      },
    })

    pagination.next = payload.next
    pagination.previous = payload.previous
    messages.value = append ? [...messages.value, ...payload.results] : payload.results
  } catch (err) {
    openToast('Lecture des messages impossible.', 'danger')
    console.error(err)
  } finally {
    loadingMessages.value = false
  }
}

const refreshMessages = async () => {
  await loadMessages(false)
}

const sendMessage = async () => {
  const content = draft.value.trim()
  if (!content) {
    openToast('Saisis un message avant envoi.', 'warning')
    return
  }
  if (conversation.value?.status === 'archived') {
    openToast('Conversation archivée, envoi bloqué.', 'danger')
    return
  }

  await ensureNonce()
  sending.value = true

  try {
    const result = await requestWithNonce(() =>
      nuxtApp.$fetch<Message>('/api/messages/', {
        method: 'POST',
        body: {
          conversation: conversationId.value,
          content,
        },
      }),
    )
    draft.value = ''
    messages.value = [...messages.value, result].sort((a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    )
    openToast('Message envoyé.', 'success')
  } catch (err) {
    const error = err as FetchError<{ error?: string }>
    const code = error?.response?._data?.error
    if (code === 'conversation_archived') {
      openToast('Cette conversation est archivée.', 'warning')
      await loadConversation()
    } else if (code) {
      openToast(`Erreur : ${code}`, 'danger')
    } else {
      openToast('Envoi impossible. Réessayez.', 'danger')
    }
  } finally {
    sending.value = false
  }
}

const archiveConversation = async () => {
  if (!conversation.value || conversation.value.status === 'archived') {
    return
  }

  await ensureNonce()
  archiving.value = true

  try {
    await requestWithNonce(() =>
      nuxtApp.$fetch(`/api/conversations/${conversationId.value}/`, {
        method: 'DELETE',
      }),
    )
    openToast('Conversation archivée.', 'success')
    if (conversation.value) {
      conversation.value = { ...conversation.value, status: 'archived' }
    }
  } catch (err) {
    const error = err as FetchError<{ error?: string }>
    const code = error?.response?._data?.error
    if (code) {
      openToast(`Erreur : ${code}`, 'danger')
    } else {
      openToast('Archivage impossible. Réessayez.', 'danger')
    }
  } finally {
    archiving.value = false
  }
}

onMounted(async () => {
  await auth.fetchMe(true).catch(() => {})
  if (!auth.gate.value.ok) {
    await navigateTo('/gate')
    return
  }

  await ensureNonce()
  await loadConversation()
  await loadMessages()
})
</script>

<style scoped>
@reference "@/assets/css/main.css";

.conversation {
  @apply mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8 md:px-8;
}

.conversation__card {
  @apply flex flex-col gap-6;
}

.conversation__heading {
  @apply flex flex-col gap-3 md:flex-row md:items-center md:justify-between;
}

.conversation__titles {
  @apply grid gap-1;
}

.conversation__status {
  @apply inline-flex items-center justify-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide;
  @apply border border-color-border bg-color-elev text-color-muted;
}

.conversation__status[data-variant='info'] {
  @apply border-color-primary text-color-primary;
}

.conversation__status[data-variant='warning'] {
  @apply border-color-accent text-color-accent;
}

.conversation__status[data-variant='danger'] {
  @apply border-color-danger text-color-danger;
}

.conversation__title {
  @apply text-xl font-semibold text-color-text;
}

.conversation__subtitle {
  @apply text-sm text-color-muted;
}

.conversation__agent {
  @apply font-medium text-color-text;
}

.conversation__meta {
  @apply flex flex-wrap gap-4 text-xs text-color-muted;
}

.conversation__messages {
  @apply grid gap-4;
}
.conversation__actions {
  @apply flex justify-end;
}

.conversation__loading,
.conversation__empty {
  @apply rounded-[var(--radius-md)] border border-dashed border-color-border bg-color-elev px-4 py-6 text-center text-sm text-color-muted;
}

.conversation__list {
  @apply grid gap-3;
}

.conversation__message {
  @apply rounded-[var(--radius-md)] border border-color-border bg-color-bg px-4 py-3 shadow-sm;
}

.conversation__message[data-role='user'] {
  @apply border-color-primary bg-color-primary-soft;
}

.conversation__message[data-role='agent'] {
  @apply border-color-accent bg-color-accent-soft;
}

.conversation__message[data-role='system'] {
  @apply border-color-border bg-color-elev;
}

.conversation__message-header {
  @apply flex items-center justify-between gap-4;
}

.conversation__message-role {
  @apply text-xs font-semibold uppercase tracking-wide text-color-muted;
}

.conversation__message-time {
  @apply text-[11px] text-color-muted;
}

.conversation__message-body {
  @apply mt-2 whitespace-pre-wrap text-sm text-color-text;
}

.conversation__load-more {
  @apply flex justify-center;
}

.conversation__composer {
  @apply grid gap-3;
}

.conversation__composer-label {
  @apply text-sm font-medium text-color-text;
}

.conversation__composer-input {
  @apply rounded-[var(--radius-md)] border border-color-border bg-color-bg px-3 py-3 text-sm text-color-text shadow-sm transition focus-visible:u-focus-ring;
}

.conversation__composer-input:disabled {
  @apply cursor-not-allowed opacity-60;
}

.conversation__composer-actions {
  @apply flex flex-wrap gap-3;
}
</style>
