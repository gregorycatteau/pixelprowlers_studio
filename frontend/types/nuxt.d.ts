import type { DeviceInjection } from '~/types/device'

declare module '#app' {
  interface NuxtApp {
    $device: DeviceInjection
  }
}

declare module 'vue' {
  interface ComponentCustomProperties {
    $device: DeviceInjection
  }
}

export {}
