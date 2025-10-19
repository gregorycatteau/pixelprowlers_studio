// app/middleware/auth.ts
import { navigateTo } from '#app'

export default defineNuxtRouteMiddleware(async () => {
  const auth = useAuth()
  const ok = await auth.ensureAuthenticated()
  if (!ok) {
    return navigateTo('/login')
  }
})
