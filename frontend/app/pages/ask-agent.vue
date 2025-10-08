<!-- frontend/app/pages/ask-agent.vue -->
<script setup lang="ts">
/**
 * Console IA — UI léchée, dark accessible, micro-anim propre (prefers-reduced-motion OK)
 * - Liste d’agents via /api/agents (proxy Nuxt server)
 * - Envoi prompt -> /api/agents/<slug>/ask
 * - Historique local (UI only)
 */
type AgentSummary = {
  slug: string
  name: string
  alias: string
  remaining_eur_today: string
  schema_version: string
  profile_version: string
}
type AskResponse = {
  ok: boolean
  agent: string
  provider?: string
  model_uri?: string
  output?: string | Record<string, unknown>
  tokens_in?: number
  tokens_out?: number
  cost_eur?: number
  latency_ms?: number
  error?: string
  blocked_reason?: string
}

const agents = ref<AgentSummary[]>([])
const selectedSlug = ref<string>('')
const selectedAgent = computed(
  () => agents.value.find((a) => a.slug === selectedSlug.value) || null,
)

const isLoading = ref(false)
const output = ref('')
const history = ref<{ ts: string; agent: string; msg: string }[]>([])

const { data, error } = await useFetch<{ agents: AgentSummary[] }>('/api/agents', { method: 'GET' })
if (!error.value && data.value?.agents?.length) {
  agents.value = data.value.agents
  selectedSlug.value = data.value.agents?.[0]?.slug ?? ''
}

async function sendToAgent(message: string) {
  if (!selectedAgent.value) return
  isLoading.value = true
  output.value = ''
  try {
    const res = await $fetch<AskResponse>(`/api/agents/${selectedAgent.value.slug}/ask`, {
      method: 'POST',
      body: { message, temperature: 0.2, max_tokens: 800 },
    })
    output.value = !res.ok
      ? res.error || res.blocked_reason || '⚠️ Requête refusée.'
      : typeof res.output === 'string'
        ? res.output
        : JSON.stringify(res.output, null, 2)
    history.value.unshift({
      ts: new Date().toISOString().slice(0, 19).replace('T', ' '),
      agent: selectedAgent.value.slug,
      msg: message,
    })
  } catch (e: any) {
    output.value = `❌ Erreur: ${e?.message || e}`
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <section class="ask-wrap">
    <!-- Hero -->
    <header class="hero">
      <div class="hero-title">
        <span class="hero-emoji">🧠</span>
        <h1 class="hero-text">Console d’interrogation IA</h1>
      </div>
      <p class="hero-sub">Sélectionne un agent, envoie un prompt, analyse la réponse.</p>
    </header>

    <div class="grid">
      <!-- Col gauche -->
      <div class="left">
        <div class="panel neon">
          <div class="panel-head">
            <span class="panel-title">Choisir un agent</span>
            <span class="chip" v-if="selectedAgent">v{{ selectedAgent.profile_version }}</span>
          </div>
          <!-- Auto-registered components -->
          <AgentSelector v-model="selectedSlug" :agents="agents" />
          <div class="divider"></div>
          <AgentProfileCard v-if="selectedAgent" :agent="selectedAgent" />
        </div>
      </div>

      <!-- Col droite -->
      <div class="right">
        <div class="panel glass">
          <div class="panel-head">
            <span class="panel-title">Session</span>
            <span class="chip alt" v-if="selectedAgent"
              >€ {{ selectedAgent.remaining_eur_today }} restants</span
            >
          </div>

          <div class="output" :class="{ loading: isLoading }">
            <pre v-if="output" class="pre">{{ output }}</pre>
            <div v-else class="placeholder">
              L’agent <strong>{{ selectedAgent?.name || '—' }}</strong> est prêt. Tape ton message
              ci-dessous.
            </div>
          </div>

          <AgentChatBox :disabled="!selectedAgent || isLoading" @send="sendToAgent" />
        </div>

        <div class="panel subtle">
          <div class="panel-head">
            <span class="panel-title">🕘 Derniers échanges (UI locale)</span>
          </div>
          <ul class="history">
            <li v-for="(h, i) in history" :key="i" class="history-item">
              <span class="h-ts">{{ h.ts }}</span>
              <span class="h-agent">→ {{ h.agent }}</span>
              <span class="h-msg">{{ h.msg }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
@reference "@/assets/css/main.css";

/* === Layout global === */
.ask-wrap {
  @apply min-h-screen mx-auto  sm:px-6 bg-black rounded-lg;
  background-image:
    radial-gradient(1200px 600px at 10% -10%, rgba(124, 58, 237, 0.18), transparent),
    radial-gradient(1000px 500px at 110% 10%, rgba(34, 211, 238, 0.12), transparent);
}

/* === Hero === */
.hero {
  @apply mx-auto mb-8 pt-4 max-w-6xl;
}
.hero-title {
  @apply flex items-center gap-3;
}
.hero-emoji {
  @apply text-3xl md:text-4xl;
}
.hero-text {
  @apply text-3xl font-bold text-emerald-400 md:text-4xl;
}
.hero-sub {
  @apply mt-1 text-slate-300;
}

/* === Grid === */
.grid {
  @apply mx-auto grid max-w-6xl gap-6 md:grid-cols-[360px,1fr];
}
.left {
  @apply space-y-6;
}
.right {
  @apply space-y-6;
}

/* === Panel styles === */
.panel {
  @apply rounded-2xl border p-4 shadow-xl md:p-6;
}
.panel-head {
  @apply mb-4 flex items-center justify-between;
}
.panel-title {
  @apply font-semibold text-slate-100;
}

.neon {
  @apply border-emerald-600/40 bg-black/50 backdrop-blur;
  box-shadow: 0 0 24px rgba(16, 185, 129, 0.15);
}
.glass {
  @apply border-slate-700/50 bg-slate-900/60 backdrop-blur;
}
.subtle {
  @apply border-slate-700/40 bg-black/30 backdrop-blur;
}

.chip {
  @apply inline-flex items-center rounded-md px-2.5 py-1 text-xs font-semibold;
  @apply border border-emerald-700/40 bg-emerald-900/40 text-emerald-200;
}
.chip.alt {
  @apply border-sky-700/40 bg-sky-900/40 text-sky-200;
}

.divider {
  @apply my-4 h-px bg-gradient-to-r from-emerald-600/30 via-slate-600/30 to-transparent;
}

/* === Output === */
.output {
  @apply mb-4 min-h-[180px] overflow-x-auto rounded-xl border border-slate-700/60 bg-slate-950/70 p-4 md:p-5;
}
.output.loading {
  background-image: linear-gradient(
    90deg,
    rgba(16, 185, 129, 0.1) 25%,
    transparent 25%,
    transparent 50%,
    rgba(16, 185, 129, 0.1) 50%,
    rgba(16, 185, 129, 0.1) 75%,
    transparent 75%,
    transparent
  );
  background-size: 32px 32px;
  animation: stripes 1s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .output.loading {
    animation: none;
  }
}
@keyframes stripes {
  from {
    background-position: 0 0;
  }
  to {
    background-position: 32px 0;
  }
}

.pre {
  @apply whitespace-pre-wrap text-sky-300;
}
.placeholder {
  @apply text-slate-400;
}

/* === History === */
.history {
  @apply max-h-64 space-y-2 overflow-y-auto pr-1;
}
.history-item {
  @apply flex flex-wrap gap-2 text-sm text-slate-300;
}
.h-ts {
  @apply text-slate-400;
}
.h-agent {
  @apply text-emerald-400;
}
.h-msg {
  @apply text-sky-300;
}
</style>
