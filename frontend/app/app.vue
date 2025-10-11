<template>
  <NuxtLayout :name="layoutKey">
    <NuxtPage />
  </NuxtLayout>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useRequestHeaders } from '#app'

// Using useDevice() directly (no device/theme imports)



const device = useDevice()

const layoutKey = computed(() => {
  // UA heuristic: if the user agent clearly looks like a desktop OS, force "laptop"
  // This protects against false mobile detection in some environments.
  const serverUA = process.server ? (useRequestHeaders(['user-agent'])['user-agent'] || '') : ''
  const clientUA = process.client ? (navigator.userAgent || '') : ''
  const ua = serverUA || clientUA

  const looksDesktopUA =
    /X11|Linux x86_64|Windows NT|Macintosh/i.test(ua) &&
    !/Mobile|Android|iPhone|iPad|iPod|IEMobile|BlackBerry/i.test(ua)

  if (looksDesktopUA) return 'laptop'

  if (device.isMobile) return 'mobile'
  if (device.isTablet) return 'tablet'
  if (device.isDesktopOrTablet) return 'laptop'
  return 'laptop'
})



if (import.meta.dev) {
  watch(
    layoutKey,
    (next, prev) => {
      if (next === prev) return
      console.info('[ui] layout ->', next)
    },
    { immediate: true },
  )
}
</script>

<style scoped>
@reference "@/assets/css/main.css";
</style>
