<script setup lang="ts">
/**
 * Nuxt /health page
 * - Shows the X-Request-ID from the incoming request (if present)
 * - Calls the backend /api/hello and shows the X-Request-ID returned by Django
 * - Intended for Sprint 0 validation behind Caddy
 */

const reqHeaders = useRequestHeaders(['x-request-id', 'x-forwarded-for', 'user-agent'])
const incomingXrid = (reqHeaders['x-request-id'] as string | undefined) || null

const runtimeConfig = useRuntimeConfig()
/**
 * Prefer explicitly configured backend base URL; default is set in nuxt.config.ts
 * Example (docker-compose): NUXT_DJANGO_BASE_URL=http://api.dev.localhost
 */
const DJANGO_BASE_URL = (runtimeConfig.public?.DJANGO_BASE_URL || '').replace(/\/+$/, '')
const apiHelloUrl = `${DJANGO_BASE_URL || 'http://localhost:8000'}/api/hello/`

let backendStatus = 0
let backendXrid: string | null = null
let backendBody: any = null
let backendError: string | null = null

try {
  // Use raw fetch to access response headers
  const res = await $fetch.raw(apiHelloUrl, {
    headers: {
      // If a correlation ID already exists on the incoming request, propagate it downstream
      ...(incomingXrid ? { 'X-Request-ID': incomingXrid } : {}),
    },
  })
  backendStatus = res.status
  // Header names are case-insensitive; standardize on lowercase when reading
  backendXrid = res.headers.get('x-request-id')
  // ofetch.raw exposes the parsed body as _data
  // eslint-disable-next-line no-underscore-dangle
  backendBody = (res as any)._data ?? null

  // Some backends also echo the request ID in the JSON body
  if (!backendXrid && backendBody && typeof backendBody === 'object') {
    backendXrid = backendBody.request_id ?? null
  }
} catch (e: any) {
  backendError = e?.message || 'Request to backend failed'
}
</script>

<template>
  <div class="min-h-[60vh] w-full px-6 py-10 flex flex-col items-center bg-gray-50">
    <div class="w-full max-w-3xl space-y-6">
      <header class="space-y-2">
        <h1 class="text-2xl font-semibold tracking-tight text-gray-900">
          Health Check — Frontend
        </h1>
        <p class="text-gray-600">
          This page confirms the Nuxt app is reachable and displays correlation IDs.
        </p>
      </header>

      <section class="rounded-lg border bg-white shadow-sm">
        <div class="px-5 py-4 border-b">
          <h2 class="text-sm font-medium text-gray-700">Request Correlation</h2>
        </div>
        <div class="px-5 py-4 space-y-3">
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-xs uppercase text-gray-500">Incoming X-Request-ID (to Nuxt)</div>
              <div class="font-mono text-sm break-all">
                {{ incomingXrid || '— (absent)' }}
              </div>
            </div>
            <span
              class="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-800"
              title="Read from the HTTP request headers to Nuxt"
            >
              inbound
            </span>
          </div>

          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-xs uppercase text-gray-500">
                Backend X-Request-ID (from Django response)
              </div>
              <div class="font-mono text-sm break-all">
                {{ backendXrid || '— (absent)' }}
              </div>
            </div>
            <span
              class="inline-flex items-center rounded-md bg-blue-100 px-2 py-1 text-xs font-medium text-blue-800"
              title="Captured from /api/hello response headers"
            >
              backend
            </span>
          </div>
        </div>
      </section>

      <section class="rounded-lg border bg-white shadow-sm">
        <div class="px-5 py-4 border-b flex items-center justify-between">
          <h2 class="text-sm font-medium text-gray-700">Backend Probe — /api/hello</h2>
          <div v-if="backendError" class="inline-flex items-center gap-2">
            <span class="h-2 w-2 rounded-full bg-red-500"></span>
            <span class="text-xs font-medium text-red-700">Error</span>
          </div>
          <div v-else class="inline-flex items-center gap-2">
            <span
              class="h-2 w-2 rounded-full"
              :class="backendStatus === 200 ? 'bg-emerald-500' : 'bg-amber-500'"
            ></span>
            <span class="text-xs font-medium text-gray-700">HTTP {{ backendStatus || '—' }}</span>
          </div>
        </div>
        <div class="px-5 py-4">
          <div v-if="backendError" class="text-sm text-red-700">
            {{ backendError }}
          </div>
          <div v-else class="text-xs text-gray-600">
            <div class="mb-2 font-semibold text-gray-700">Response Body</div>
            <pre
              class="text-xs overflow-auto rounded bg-gray-900 text-gray-100 p-3"
              :title="JSON.stringify(backendBody, null, 2)"
            >{{ JSON.stringify(backendBody, null, 2) }}</pre>
          </div>
        </div>
      </section>

      <section class="rounded-lg border bg-white shadow-sm">
        <div class="px-5 py-4 border-b">
          <h2 class="text-sm font-medium text-gray-700">How to test</h2>
        </div>
        <div class="px-5 py-4 space-y-2 text-sm text-gray-700">
          <p>
            Tip: you can set a custom correlation header to verify propagation end-to-end:
          </p>
          <pre class="text-xs overflow-auto rounded bg-gray-900 text-gray-100 p-3">
curl -H 'X-Request-ID: demo-123' http://dev.localhost/health
</pre>
          <p class="text-xs text-gray-600">
            Expected: the same ID should appear above and be propagated to the backend call.
          </p>
        </div>
      </section>
    </div>
  </div>
</template>
