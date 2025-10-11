<template>
  <NuxtLayout :name="layoutKey">
    <NuxtPage />
  </NuxtLayout>
</template>

<script setup lang="ts">
import { watch } from 'vue'

import { useDeviceKind } from '~/composables/useDeviceKind'
import { useUserTheme } from '~/composables/useUserTheme'



const { isMobile, isTablet, isLaptop } = useDeviceKind()
const { isDark } = useUserTheme()

const layoutKey = computed(() => {
  if (isMobile.value) return 'mobile'
  if (isTablet.value) return 'tablet'
  if (isLaptop.value) return 'laptop'
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
