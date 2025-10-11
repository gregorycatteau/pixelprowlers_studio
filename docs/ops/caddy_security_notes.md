# Notes de sécurité Caddy (dev)

- `deploy/caddy/Caddyfile` applique désormais :
  - `Content-Security-Policy-Report-Only` minimal pour `/api/*` (futur durcissement possible).
  - `Referrer-Policy: no-referrer`, `Permissions-Policy` restrictive, `COOP/COEP`.
  - Baseline `nosniff`, `X-Frame-Options: DENY` conservé.
- Les navigateurs reçoivent donc les mêmes en-têtes que le middleware Django quand Caddy n’est pas devant l’app.
- Adapter la politique CSP avant passage en production (passage en mode `enforce` + endpoints de report dédiés).
