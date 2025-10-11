/**
 * CSP report collection endpoint for Nitro (Nuxt server).
 * - Accepts CSP violation reports (report-only and enforce).
 * - Never throws or blocks navigation; always returns { ok: true }.
 * - Logs a structured, sanitized report to server logs (no PII).
 *
 * Spec notes:
 * - Older UAs: Content-Type: application/csp-report with body { "csp-report": { ... } }
 * - Newer reporting: application/reports+json or application/json with arrays/objects
 *
 * Route: POST /api/csp-report
 */

import { defineEventHandler, getRequestHeaders, readBody } from 'h3'
import type { H3Event } from 'h3'

type AnyRecord = Record<string, unknown>

function nowIso(): string {
  return new Date().toISOString()
}

function coerceObject(input: unknown): AnyRecord {
  if (Array.isArray(input)) {
    // Some agents send an array of reports; keep first element if object-like
    const first = input.find((x) => x && typeof x === 'object') as AnyRecord | undefined
    return first ?? {}
  }
  if (input && typeof input === 'object') return input as AnyRecord
  return {}
}

/**
 * Extract the CSP report object from various shapes:
 * - { "csp-report": {...} }
 * - { "csp_report": {...} }
 * - { "violations": [ {...} ] }
 * - { ... } generic object
 */
function extractCspReport(body: unknown): AnyRecord {
  const obj = coerceObject(body)
  if ('csp-report' in obj && obj['csp-report'] && typeof obj['csp-report'] === 'object') {
    return obj['csp-report'] as AnyRecord
  }
  if ('csp_report' in obj && obj['csp_report'] && typeof obj['csp_report'] === 'object') {
    return obj['csp_report'] as AnyRecord
  }
  if ('violations' in obj && Array.isArray((obj as AnyRecord)['violations'])) {
    const first = (obj as AnyRecord)['violations']?.[0]
    return coerceObject(first)
  }
  return obj
}

/**
 * Sanitize an object to avoid overly large/verbose strings in logs.
 * Truncates string values and depth-flattens mildly for safe logging.
 */
function sanitizeForLog(input: unknown, maxLen = 512, maxDepth = 4): unknown {
  const seen = new WeakSet<object>()
  const helper = (val: unknown, depth: number): unknown => {
    if (depth > maxDepth) return '[TruncatedDepth]'
    if (val == null) return val
    if (typeof val === 'string') {
      return val.length > maxLen ? `${val.slice(0, maxLen)}…[+${val.length - maxLen}]` : val
    }
    if (typeof val !== 'object') return val
    if (seen.has(val as object)) return '[Circular]'
    seen.add(val as object)
    if (Array.isArray(val)) return val.slice(0, 20).map((v) => helper(v, depth + 1))
    const out: AnyRecord = {}
    for (const [k, v] of Object.entries(val as AnyRecord)) {
      out[k] = helper(v, depth + 1)
    }
    return out
  }
  return helper(input, 0)
}

export default defineEventHandler(async (event: H3Event) => {
  try {
    const headers = getRequestHeaders(event)
    const ct = (headers['content-type'] || '').toString().toLowerCase()

    // Attempt to parse JSON body regardless of exact content-type.
    const rawBody = await readBody(event).catch(() => null)

    // Build a structured, sanitized log record (no IPs/PII).
    const report = extractCspReport(rawBody)
    const sanitized = sanitizeForLog(report)

    const logRecord = {
      type: 'CSP-REPORT',
      ts: nowIso(),
      contentType: ct || undefined,
      userAgent: headers['user-agent'] || undefined, // UA only; avoid logging IPs/PII
      // Note: Referer/Origin can be sensitive; omit by default unless needed for debugging.
      report: sanitized,
    }

    // Use console.warn to make CSP signals stand out in logs without breaking flow.
    // eslint-disable-next-line no-console
    console.warn(JSON.stringify(logRecord))
  } catch {
    // Never block navigation; swallow errors
  }

  // Always acknowledge quickly
  return { ok: true }
})
