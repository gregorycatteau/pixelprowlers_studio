/**
 * Nuxt global middleware — realm routing by HttpOnly cookie (SSR-only).
 *
 * Behavior:
 * - Reads the HttpOnly cookie "pp_realm" (set by the backend) on the server.
 * - Values:
 *   - "A" → Dojo/Admins → target "/console"
 *   - "C" → Clients     → target "/dashboard"
 *   - "H" → Laby        → target "/console" (honeypot façade)
 * - Redirects only on the server (never tries to read HttpOnly cookie on client).
 * - Avoids redirect loops by checking the current path.
 *
 * Notes:
 * - This does not expose the cookie value to client code.
 * - Keep routes like "/api/*" or server endpoints out of page-level middleware scope.
 */

export default defineNuxtRouteMiddleware((to) => {
  // Only act on the server to read HttpOnly cookies safely.
  if (process.client) return

  // Read the realm cookie (SSR can read HttpOnly).
  const realmCookie = useCookie<string | null>('pp_realm', { sameSite: 'lax' })
  const rawRealm = (realmCookie.value || '').toUpperCase()
  if (!rawRealm || !['A', 'C', 'H'].includes(rawRealm)) {
    // No routing decision without a recognized realm; let the request continue.
    return
  }

  // Compute desired landing by realm.
  const desiredPath = rawRealm === 'C' ? '/dashboard' : '/console'
  const current = to.path

  // Avoid loops: if already on the desired section, do nothing.
  if (current === desiredPath || current.startsWith(desiredPath + '/')) return

  // If on the "other realm" main section, route to the correct one.
  if (rawRealm === 'C' && (current === '/console' || current.startsWith('/console/'))) {
    return navigateTo('/dashboard', { redirectCode: 302 })
  }
  if ((rawRealm === 'A' || rawRealm === 'H') && (current === '/dashboard' || current.startsWith('/dashboard/'))) {
    return navigateTo('/console', { redirectCode: 302 })
  }

  // Redirect common entry points (/, /login) to the realm home.
  if (current === '/' || current === '/login') {
    return navigateTo(desiredPath, { redirectCode: 302 })
  }

  // Otherwise, do not enforce; allow deep links unless explicitly conflicting.
})
