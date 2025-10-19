<template>
  <AppShell>
    <template #header>
      <PxHeader />
    </template>

    <template #toolbar>
      <div class="dashboard-toolbar">
        <div class="dashboard-toolbar__group">
          <h1 class="dashboard-toolbar__title">Synthèse studio</h1>
          <p class="dashboard-toolbar__subtitle">
            Vue instantanée des activités produit, sécurité et opérations.
          </p>
        </div>
        <div class="dashboard-toolbar__actions">
          <PxButton variant="ghost" class="dashboard-toolbar__action" @click="openInsights">
            Voir les budgets
          </PxButton>
          <PxButton class="dashboard-toolbar__action" @click="showToast = true">
            Rafraîchir les KPI
          </PxButton>
        </div>
      </div>
    </template>

    <section class="dashboard">
      <section class="dashboard-kpis" aria-label="Indicateurs principaux">
        <PxCard
          v-for="metric in metrics"
          :key="metric.id"
          class="dashboard-kpis__card"
        >
          <template #header>
            <span class="dashboard-kpis__label">{{ metric.label }}</span>
          </template>
          <p class="dashboard-kpis__value">{{ metric.value }}</p>
          <p class="dashboard-kpis__delta">{{ metric.delta }}</p>
        </PxCard>
      </section>

      <section class="dashboard-shortcuts" aria-label="Raccourcis">
        <PxCard class="dashboard-shortcuts__card">
          <template #header>
            <div class="dashboard-shortcuts__header">
              <h2 class="dashboard-shortcuts__title">Actions rapides</h2>
              <span class="dashboard-shortcuts__caption">24h</span>
            </div>
          </template>
          <ul class="dashboard-shortcuts__list">
            <li
              v-for="shortcut in shortcuts"
              :key="shortcut.id"
              class="dashboard-shortcuts__item"
            >
              <div class="dashboard-shortcuts__item-body">
                <span class="dashboard-shortcuts__item-title">{{ shortcut.title }}</span>
                <p class="dashboard-shortcuts__item-description">{{ shortcut.description }}</p>
              </div>
              <PxButton
                variant="ghost"
                class="dashboard-shortcuts__item-button"
                @click="() => handleShortcut(shortcut.id)"
              >
                Ouvrir
              </PxButton>
            </li>
          </ul>
        </PxCard>

        <PxCard class="dashboard-shortcuts__card">
          <template #header>
            <div class="dashboard-shortcuts__header">
              <h2 class="dashboard-shortcuts__title">Prochaines revues</h2>
              <span class="dashboard-shortcuts__caption">Semaine</span>
            </div>
          </template>
          <PxTable caption="Sessions de revue à venir" aria-label="Prochaines revues">
            <template #head>
              <tr class="dashboard-table__head-row">
                <th scope="col" class="dashboard-table__head-cell">Date</th>
                <th scope="col" class="dashboard-table__head-cell">Sujet</th>
                <th scope="col" class="dashboard-table__head-cell">Owner</th>
              </tr>
            </template>

            <tr
              v-for="review in reviews"
              :key="review.id"
              class="dashboard-table__row"
            >
              <td class="dashboard-table__cell">{{ review.date }}</td>
              <td class="dashboard-table__cell">{{ review.topic }}</td>
              <td class="dashboard-table__cell">{{ review.owner }}</td>
            </tr>
          </PxTable>
        </PxCard>
      </section>
    </section>

    <template #footer>
      <div class="dashboard-footer">
        <p>Budgets LCP / INP / CLS suivis en continu · Objectif 95+</p>
      </div>
    </template>
  </AppShell>

  <PxModal v-model="insightsOpen" title="Budgets en cours" class="dashboard-modal">
    <p class="dashboard-modal__text">
      Les budgets actuels couvrent les chantiers infra, sécurité appli et audit IA. Mise à
      jour tous les vendredis avant 12h CET.
    </p>
    <PxTable caption="Vue synthétique" aria-label="Budgets par domaine">
      <template #head>
        <tr class="dashboard-table__head-row">
          <th scope="col" class="dashboard-table__head-cell">Domaine</th>
          <th scope="col" class="dashboard-table__head-cell">Allocation</th>
          <th scope="col" class="dashboard-table__head-cell">Reste</th>
        </tr>
      </template>
      <tr v-for="budget in budgets" :key="budget.id" class="dashboard-table__row">
        <td class="dashboard-table__cell">{{ budget.domain }}</td>
        <td class="dashboard-table__cell">{{ budget.allocated }}</td>
        <td class="dashboard-table__cell">{{ budget.remaining }}</td>
      </tr>
    </PxTable>
    <template #footer>
      <PxButton variant="ghost" @click="insightsOpen = false">Fermer</PxButton>
      <PxButton>Exporter le rapport</PxButton>
    </template>
  </PxModal>

  <PxToast v-model="showToast" variant="success" message="KPI synchronisés (cache local)" />
</template>

<script setup lang="ts">
definePageMeta({
  middleware: ['dojo'],
})

const metrics = [
  { id: 'projects', label: 'Projets actifs', value: '12', delta: '+8% vs semaine-1' },
  { id: 'sla', label: 'SLA critiques', value: '99.4%', delta: 'Stable' },
  { id: 'security', label: 'Tickets sécu', value: '3 ouverts', delta: '0 blocage' },
  { id: 'ai', label: 'Sessions IA', value: '42', delta: '+5 en 24h' },
]

const shortcuts = [
  {
    id: 'create-project',
    title: 'Créer un projet client',
    description: 'Brief et backlog en une interface, onboarding mTLS possible.',
  },
  {
    id: 'launch-preflight',
    title: 'Préparer Preflight',
    description: 'Checklist audit avant livraison, incluant armes sécu.',
  },
  {
    id: 'sync-agents',
    title: 'Synchroniser les agents',
    description: 'Rafraîchir les contexts Nova / Claire / Marty.',
  },
]

const reviews = [
  { id: 'rev-1', date: 'Mardi 14:00', topic: 'Revue RGPD phase 2', owner: 'Ops' },
  { id: 'rev-2', date: 'Mercredi 10:30', topic: 'Alignement roadmap IA', owner: 'Studio' },
  { id: 'rev-3', date: 'Jeudi 16:00', topic: 'Patch management', owner: 'SecOps' },
]

const budgets = [
  { id: 'bud-1', domain: 'Infrastructure', allocated: '€120k', remaining: '€45k' },
  { id: 'bud-2', domain: 'Sécu applicative', allocated: '€80k', remaining: '€32k' },
  { id: 'bud-3', domain: 'IA & R&D', allocated: '€150k', remaining: '€78k' },
]

const insightsOpen = ref(false)
const showToast = ref(false)

const openInsights = () => {
  insightsOpen.value = true
}

const handleShortcut = (id: string) => {
  console.info('[ui] action', id)
  showToast.value = true
}
</script>

<style scoped>
@reference "@/assets/css/main.css";
.dashboard {
  @apply mx-auto grid max-w-6xl gap-6 px-4 py-8 md:px-8;
}
.dashboard-toolbar {
  @apply flex flex-col gap-4 px-4 py-4 md:flex-row md:items-center md:justify-between md:px-6;
}
.dashboard-toolbar__group {
  @apply grid gap-1;
}
.dashboard-toolbar__title {
  @apply text-xl font-semibold text-color-text;
}
.dashboard-toolbar__subtitle {
  @apply text-sm text-color-muted;
}
.dashboard-toolbar__actions {
  @apply flex flex-wrap gap-3;
}
.dashboard-toolbar__action {
  @apply min-w-[160px];
}
.dashboard-kpis {
  @apply grid gap-4 md:grid-cols-2 xl:grid-cols-4;
}
.dashboard-kpis__card {
  @apply flex flex-col gap-2;
}
.dashboard-kpis__label {
  @apply text-sm text-color-muted;
}
.dashboard-kpis__value {
  @apply text-2xl font-semibold text-color-text;
}
.dashboard-kpis__delta {
  @apply text-xs text-color-primary;
}
.dashboard-shortcuts {
  @apply grid gap-6 md:grid-cols-[1fr,1fr];
}
.dashboard-shortcuts__card {
  @apply flex flex-col gap-4;
}
.dashboard-shortcuts__header {
  @apply flex items-center justify-between;
}
.dashboard-shortcuts__title {
  @apply text-base font-semibold text-color-text;
}
.dashboard-shortcuts__caption {
  @apply text-xs text-color-muted;
}
.dashboard-shortcuts__list {
  @apply grid gap-3;
}
.dashboard-shortcuts__item {
  @apply flex items-center justify-between gap-4 rounded-[var(--radius-md)] border border-color-border bg-color-bg px-3 py-3;
}
.dashboard-shortcuts__item-body {
  @apply flex-1;
}
.dashboard-shortcuts__item-title {
  @apply font-medium text-color-text;
}
.dashboard-shortcuts__item-description {
  @apply text-sm text-color-muted;
}
.dashboard-shortcuts__item-button {
  @apply whitespace-nowrap;
}
.dashboard-table__head-row {
  @apply bg-color-elev;
}
.dashboard-table__head-cell {
  @apply px-4 py-3 text-xs font-semibold uppercase tracking-wide text-color-muted;
}
.dashboard-table__row {
  @apply transition hover:bg-color-elev;
}
.dashboard-table__cell {
  @apply px-4 py-3 text-sm text-color-text;
}
.dashboard-footer {
  @apply flex items-center justify-center px-4 py-3 text-xs text-color-muted;
}
.dashboard-modal__text {
  @apply text-sm text-color-text;
}
.dashboard-modal :deep(.px-table__wrapper) {
  @apply mt-4;
}
.dashboard-modal__text + :deep(.px-table__wrapper) {
  @apply mt-4;
}
</style>
