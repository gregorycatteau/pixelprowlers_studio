<script setup lang="ts">
const props = defineProps<{
  agent: {
    slug: string
    name: string
    alias: string
    remaining_eur_today: string
    schema_version: string
    profile_version: string
  }
}>()
</script>

<template>
  <article class="card">
    <h3 class="card-title">{{ agent.name }}</h3>
    <p class="card-sub">
      Alias : <span class="alias">{{ agent.alias || '—' }}</span>
    </p>
    <div class="kpis">
      <div class="kpi">
        <span class="kpi-label">Restant aujourd’hui</span>
        <span class="kpi-value">€ {{ agent.remaining_eur_today }}</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Schema</span>
        <span class="badge">{{ agent.schema_version }}</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Profil</span>
        <span class="badge">{{ agent.profile_version }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
@reference "@/assets/css/main.css";

.card {
  @apply rounded-2xl border border-emerald-700/40 bg-slate-900/60 p-5 shadow-xl backdrop-blur;
}
.card-title {
  @apply text-xl font-bold text-emerald-300;
}
.card-sub {
  @apply mt-1 text-slate-300;
}
.alias {
  @apply text-sky-300;
}

.kpis {
  @apply mt-4 grid grid-cols-3 gap-3;
}
.kpi {
  @apply rounded-xl border border-slate-700/40 bg-black/40 p-3;
}
.kpi-label {
  @apply block text-xs text-slate-400;
}
.kpi-value {
  @apply block text-lg font-semibold text-emerald-300;
}
.badge {
  @apply inline-flex items-center rounded-md border border-emerald-700/40 bg-emerald-900/40 px-2 py-1 text-xs font-semibold text-emerald-200;
}
</style>
