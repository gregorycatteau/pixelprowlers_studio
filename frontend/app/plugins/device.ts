// app/plugins/device.ts
// Do not mutate @nuxtjs/device flags — use them as-is.
// Keep this plugin as a no-op (or add dev-only logs if needed).
export default defineNuxtPlugin(() => {
  // Dev-only diagnostics (uncomment if you want to inspect flags)
  // if (import.meta.dev) {
  //   const d = useDevice() as any
  //   // eslint-disable-next-line no-console
  //   console.info('[device] flags=', {
  //     isMobile: d.isMobile,
  //     isTablet: d.isTablet,
  //     isDesktop: d.isDesktop,
  //     ua: d.userAgent,
  //   })
  // }
})
