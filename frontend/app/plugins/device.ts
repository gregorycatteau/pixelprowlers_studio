// app/plugins/device.ts
import type { DeviceInjection } from '~/types/device'

const APPLE_FLAGS = ['isApple', 'isIOS', 'isIPhone', 'isIPad'] as const

export default defineNuxtPlugin(() => {
  const device = useDevice() as Record<string, unknown> & DeviceInjection

  if (typeof device.isDesktop !== 'boolean') {
    device.isDesktop = Boolean(device.isDesktop)
  }
  if (typeof device.isMobile !== 'boolean') {
    device.isMobile = Boolean(device.isMobile)
  }
  if (typeof device.isTablet !== 'boolean') {
    device.isTablet = Boolean(device.isTablet)
  }
  if (typeof device.isMacOS !== 'boolean') {
    device.isMacOS = Boolean(device.isMacOS)
  }
  if (typeof device.isAndroid !== 'boolean') {
    device.isAndroid = Boolean(device.isAndroid)
  }

  if (typeof device.isApple !== 'boolean') {
    device.isApple = Boolean(
      device.isMacOS ||
        APPLE_FLAGS.some((flag) => typeof device[flag] === 'boolean' && device[flag]),
    )
  }
})
