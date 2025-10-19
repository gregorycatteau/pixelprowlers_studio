// Minimal Nuxt #app shim for Vitest transform/runtime
// Provides navigateTo used by pages/components in tests.
export async function navigateTo(_path: string) {
  // no-op in unit tests, emulate a successful navigation
  return Promise.resolve()
}

// Optional default export to mimic Nuxt module style
export default { navigateTo }
