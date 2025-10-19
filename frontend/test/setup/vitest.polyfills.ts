import { createHash, webcrypto } from 'node:crypto'

/**
 * Vitest polyfills for Vue SFC transform pipeline in Node test env.
 * - Provide globalThis.crypto if missing (use Node webcrypto)
 * - Provide crypto.hash expected by some deps (fallback to Node createHash)
 *
 * Note: This is test-only and does not run in production.
 */

const g: any = globalThis as any

// Ensure global crypto exists
if (!g.crypto) {
  g.crypto = webcrypto as any
}

// Provide a crypto.hash function if absent (some libs expect it)
if (typeof g.crypto.hash !== 'function') {
  g.crypto.hash = async (algorithm: string, data: ArrayBuffer | string) => {
    const algo = (algorithm || 'SHA-256').toLowerCase().replace('-', '')
    const hasher = createHash(algo)
    const input =
      typeof data === 'string'
        ? Buffer.from(data)
        : Buffer.isBuffer(data)
          ? (data as Buffer)
          : Buffer.from(new Uint8Array(data as ArrayBuffer))
    hasher.update(input)
    // Return ArrayBuffer-like value to mimic WebCrypto subtle.digest
    return hasher.digest()
  }
}
