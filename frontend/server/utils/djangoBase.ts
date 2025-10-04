// server/utils/djangoBase.ts
import type { H3Event } from 'h3'

export function djangoBase(event: H3Event) {
  const cfg = useRuntimeConfig(event)
  // Priorité à la valeur privée serveur pour éviter la tampering client
  return cfg.DJANGO_BASE_URL || cfg.public?.DJANGO_BASE_URL || 'http://localhost:8000'
}
