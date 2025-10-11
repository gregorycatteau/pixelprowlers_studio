/* eslint-disable no-console */

// pixelprowlers_studio/frontend/app/plugins/device-debug.client.ts
// Client-side device debug plugin: logs navigator UA and @nuxtjs/device flags.
// Runs only on client (.client.ts). Logs only in development.

export default defineNuxtPlugin(() => {
  // Avoid noisy logs in production
  if (import.meta.env.PROD) return

  try {
    const d = useDevice() as Record<string, unknown>

    const flags = {
      // Primary flags
      isDesktop: Boolean(d.isDesktop),
      isMobile: Boolean(d.isMobile),
      isTablet: Boolean(d.isTablet),
      isMobileOrTablet: Boolean((d as any).isMobileOrTablet),
      isDesktopOrTablet: Boolean((d as any).isDesktopOrTablet),

      // OS / vendor
      isIos: Boolean((d as any).isIos),
      isWindows: Boolean((d as any).isWindows),
      isMacOS: Boolean((d as any).isMacOS),
      isApple: Boolean((d as any).isApple),
      isAndroid: Boolean((d as any).isAndroid),

      // Browsers
      isFirefox: Boolean((d as any).isFirefox),
      isEdge: Boolean((d as any).isEdge),
      isChrome: Boolean((d as any).isChrome),
      isSafari: Boolean((d as any).isSafari),
      isSamsung: Boolean((d as any).isSamsung),

      // Bots
      isCrawler: Boolean((d as any).isCrawler),
    }

    const ua =
      (d as any).userAgent && typeof (d as any).userAgent === 'string'
        ? (d as any).userAgent
        : navigator.userAgent

    console.info('[device][client] UA:', ua)
    console.info('[device][client] flags:', flags)
    console.info('[device][client] viewport:', {
      width: window.innerWidth,
      height: window.innerHeight,
      dpr: window.devicePixelRatio || 1,
    })
  } catch (err) {
    console.warn('[device][client] debug plugin error:', err)
  }
})
