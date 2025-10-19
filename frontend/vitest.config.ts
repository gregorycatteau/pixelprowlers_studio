import { defineConfig } from 'vitest/config'
import path from 'node:path'
import vue from '@vitejs/plugin-vue'
import type { Plugin } from 'vite'

const ensureCryptoHash = () => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { createHash, webcrypto } = require('node:crypto')
    const g: any = globalThis as any
    if (!g.crypto) {
      g.crypto = webcrypto
    }
    if (typeof g.crypto.hash !== 'function') {
      g.crypto.hash = (algorithm: string, data: ArrayBuffer | string) => {
        const algo = (algorithm || 'SHA-256').toLowerCase().replace('-', '')
        const hasher = createHash(algo)
        const input =
          typeof data === 'string'
            ? Buffer.from(data)
            : Buffer.isBuffer(data)
              ? (data as Buffer)
              : Buffer.from(new Uint8Array(data as ArrayBuffer))
        hasher.update(input)
        return hasher.digest()
      }
    }
  } catch {
    // no-op
  }
}

// Ensure immediately at config load time (before any plugin transform)
ensureCryptoHash()

const cryptoHashPolyfill = (): Plugin => ({
  name: 'polyfill-crypto-hash',
  enforce: 'pre',
  configResolved() {
    ensureCryptoHash()
  },
  transform(code) {
    // Vitest plugin transforms run inside worker context — ensure here as well.
    ensureCryptoHash()
    return null
  },
})

const uncryptoAliasPlugin = (): Plugin => ({
  name: 'alias-uncrypto',
  enforce: 'pre',
  resolveId(id) {
    if (id === 'uncrypto') {
      return path.resolve(__dirname, 'test/shims/uncrypto.ts')
    }
    return null
  },
})

export default defineConfig({
  plugins: [uncryptoAliasPlugin(), cryptoHashPolyfill(), vue()],
  test: {
    environment: 'jsdom',
    include: ['app/__tests__/**/*.test.ts', 'app/__tests__/**/*.spec.ts', 'app/__tests__/**/*.ts'],
    setupFiles: ['test/setup/vitest.polyfills.ts'],
  },
  resolve: {
    alias: [
      // Mappe les imports virtuels Nuxt (#imports/#app) vers des shims Vitest
      { find: '#imports', replacement: path.resolve(__dirname, 'test/shims/nuxt-imports.ts') },
      { find: '#app', replacement: path.resolve(__dirname, 'test/shims/nuxt-app.ts') },
      // Forcer toute variante d'import 'ohash' à pointer vers notre shim
      { find: /^ohash(\/.*)?$/, replacement: path.resolve(__dirname, 'test/shims/ohash.ts') },
      // Forcer toute variante d'import 'uncrypto' à pointer vers notre shim (crypto.hash)
      { find: /^uncrypto(\/.*)?$/, replacement: path.resolve(__dirname, 'test/shims/uncrypto.ts') },
    ],
  },
})
