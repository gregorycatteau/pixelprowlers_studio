import { createHash } from 'node:crypto'

/**
 * Minimal shim for ohash.hash used by @vitejs/plugin-vue during SFC transform in Vitest.
 * Deterministic SHA-256 over stringified input.
 */
export function hash(input: unknown): string {
  const s = typeof input === 'string' ? input : JSON.stringify(input)
  return createHash('sha256').update(s || '').digest('hex')
}
