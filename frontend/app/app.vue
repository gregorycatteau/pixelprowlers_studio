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
  if (isMobile.value) return isDark.value ? 'mobile-dark' : 'mobile-light'
  if (isTablet.value) return isDark.value ? 'tablet-dark' : 'tablet-light'
  if (isLaptop.value) return isDark.value ? 'laptop-dark' : 'laptop-light'
  return isDark.value ? 'laptop-dark' : 'laptop-light'
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
