/**
 * Server middleware — X-Request-ID echo and propagation
 *
 * Goals (Sprint 0):
 * - Read incoming X-Request-ID (if provided by client/reverse proxy)
 * - Generate a new, safe request ID when missing
 * - Expose the ID on the response headers (X-Request-ID)
 * - Attach the ID to event.context so server routes can propagate it to upstream calls
 *
 * Usage in server handlers:
 *   const rid = event.context.requestId
 *   await $fetch(url, { headers: { ...(event.context.propagateHeaders || {}), ...otherHeaders } })
 */

import { defineEventHandler, getRequestHeader, setResponseHeader } from 'h3'

/**
 * Generate a RFC4122-like UUID (prefer crypto.randomUUID when available).
 * Falls back to a compact ULID-ish string if crypto is not available.
 */
function generateRequestId(): string {
  // Use the runtime crypto when available (Node 18+/modern runtimes)
  try {
    // eslint-disable-next-line no-restricted-globals
    const g = (globalThis as any)
    if (g?.crypto?.randomUUID) {
      return g.crypto.randomUUID()
    }
  } catch {
    // ignore and fallback
  }
  // Fallback: time-based random string (not a real UUID, but unique enough for correlation)
  const ts = Date.now().toString(36)
  const rnd = Math.random().toString(36).slice(2, 10)
  return `req_${ts}_${rnd}`
}

/**
 * Sanitize an incoming request ID to avoid header injection or absurdly long values.
 * - Trim whitespace
 * - Restrict to a safe character set
 * - Enforce a max length (128)
 */
function sanitizeIncomingId(v: string): string | null {
  if (!v) return null
  const trimmed = v.trim()
  if (!trimmed) return null
  // Allow a conservative subset: alnum + dash + underscore + dot + colon
  const safe = trimmed.replace(/[^A-Za-z0-9._:-]/g, '')
  if (!safe) return null
  return safe.length > 128 ? safe.slice(0, 128) : safe
}

export default defineEventHandler((event) => {
  // 1) Read incoming correlation header
  const incoming = getRequestHeader(event, 'x-request-id') || ''
  const sanitized = sanitizeIncomingId(String(incoming))

  // 2) Use incoming or generate a new ID
  const requestId = sanitized || generateRequestId()

  // 3) Expose on response headers (echo)
  setResponseHeader(event, 'X-Request-ID', requestId)

  // 4) Attach to context for server routes and utilities
  //    - requestId: string
  //    - propagateHeaders: suggested default headers for upstream calls
  event.context.requestId = requestId
  event.context.propagateHeaders = Object.freeze({ 'X-Request-ID': requestId })
})

/* -----------------------------------------------------------------------------------------------
 * Type augmentation — allows TypeScript to recognize our custom context fields
 * --------------------------------------------------------------------------------------------- */
declare module 'h3' {
  interface H3EventContext {
    requestId?: string
    propagateHeaders?: Record<string, string>
  }
}
