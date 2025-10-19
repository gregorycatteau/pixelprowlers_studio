import { createHash, webcrypto } from 'node:crypto'

/**
 * Shim for 'uncrypto' used by some dependencies (e.g., @vitejs/plugin-vue via ohash/uncrypto).
 * Provides a minimal crypto.hash(algo, data) and exposes webcrypto.subtle when available.
 * Test-only polyfill for Vitest environment.
 */
function toBuffer(data: ArrayBuffer | string | Buffer | Uint8Array): Buffer {
  if (typeof data === 'string') return Buffer.from(data)
  if (Buffer.isBuffer(data)) return data
  if (data instanceof Uint8Array) return Buffer.from(data)
  // ArrayBuffer
  return Buffer.from(new Uint8Array(data as ArrayBuffer))
}

export const crypto = {
  // Align with uncrypto signature (algo: string, data: ArrayBuffer|string)
  async hash(algorithm: string, data: ArrayBuffer | string) {
    const algo = (algorithm || 'SHA-256').toLowerCase().replace('-', '')
    const hasher = createHash(algo)
    hasher.update(toBuffer(data))
    // Return a Buffer (ArrayBuffer-like) as many consumers accept it
    return hasher.digest()
  },
  subtle: (webcrypto as any)?.subtle,
} as const

export default { crypto }
