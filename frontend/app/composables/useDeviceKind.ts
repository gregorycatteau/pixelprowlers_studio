// app/composables/useDeviceKind.ts
/**
 * Détection d'appareil via @nuxtjs/device.
 * Retourne les flags globaux exposés par le plugin et quelques alias utiles.
 */
export function useDeviceKind() {
  const nuxtApp = useNuxtApp()
  const device = nuxtApp.$device ?? useDevice()

  const isMobile = computed(() => Boolean(device.isMobile))
  const isTablet = computed(() => Boolean(device.isTablet))
  const isDesktop = computed(() => Boolean(device.isDesktop))
  const isLaptop = computed(() => {
    const desktop = Boolean(device.isDesktop)
    const tablet = Boolean(device.isTablet)
    const mobile = Boolean(device.isMobile)
    return desktop && !tablet && !mobile
  })

  return {
    device,
    isMobile,
    isTablet,
    isDesktop,
    isLaptop,
    isApple: computed(() => Boolean(device.isApple)),
    isAndroid: computed(() => Boolean(device.isAndroid)),
  }
}
