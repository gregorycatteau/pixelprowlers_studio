<!-- frontend/app/pages/index.vue -->
<script setup lang="ts">
/** Home : redirige vers /ask-agent après un court délai (annulable SR) */
const router = useRouter()
onMounted(() => {
  const t = setTimeout(() => router.replace('/ask-agent'), 50)
  onBeforeUnmount(() => clearTimeout(t))
})
</script>

<template>
  <section class="home-wrap">
    <div class="card">
      <h1 class="title">PixelProwlers Studio</h1>
      <p class="lead">Chargement de la console…</p>
      <NuxtLink to="/ask-agent" class="cta"> Aller à la console maintenant </NuxtLink>
    </div>
  </section>
</template>

<style scoped>
@reference "@/assets/css/main.css";

.home-wrap {
  @apply grid min-h-screen place-items-center px-6;
}
.card {
  @apply space-y-4 rounded-2xl border border-emerald-700/30 bg-slate-900/50 p-8 text-center backdrop-blur;
}
.title {
  @apply text-2xl font-bold text-emerald-400 md:text-3xl;
}
.lead {
  @apply text-slate-300;
}
.cta {
  @apply inline-block rounded-xl bg-emerald-600 px-4 py-2 text-white hover:bg-emerald-500;
}
</style>
