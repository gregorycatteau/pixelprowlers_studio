# CHANGELOG-S3 (append-only)
Sprint 3 — Front UX e‑OTP (Nuxt + Pinia + Tailwind)
Statut: en cours — fondations livrées (store + tests unitaires verts)

2025-10-17 — Fondations livrées (partiel S3)
- Activation Pinia
  - nuxt.config.ts: ajout du module « @pinia/nuxt ».
- Store e‑OTP (Pinia)
  - Fichier: frontend/app/stores/useEotpStore.ts
  - State: status (idle/pending/verifying/ok/invalid/expired/locked/rate_limited/error), expiresAt (ms), retryAfterVerify, retryAfterResend, lastError (PII‑safe).
  - Getters: ttlLeftSec (compte à rebours côté UI), cooldownActive.
  - Actions:
    - verify(code): gère réponses 200/401/403/429, respecte Retry‑After (entête), met à jour status/lastError/cooldown.
    - resend(): lit retry_after + expires_in du payload (200) ou entête (429), met à jour expiresAt (sessionStorage) et cooldown.
    - fetchPeek(): accès _peek strictement en dev/test (selon appEnv).
  - Sécurité UI: aucune fuite d’OTP/email; expiresAt en sessionStorage uniquement (pas de persistance durable).
- Tests unitaires (Vitest) — VERT (7/7)
  - Fichier: frontend/app/__tests__/eotp.store.test.ts
  - Couverture: TTL (compute & hydration sessionStorage), resend (200/429), verify (200/429), tick cooldown.
  - Environnement tests:
    - frontend/vitest.config.ts: environment=jsdom, alias « #imports » → frontend/test/shims/nuxt-imports.ts.
    - Shims: frontend/test/shims/nuxt-imports.ts (useCsrf, useRuntimeConfig) — stubs PII‑safe.
- Remédiation toolchain (dev)
  - Incident npm EACCES sur node_modules/playwright (ownership root:root) résolu par reset node_modules (création d’un dossier node_modules.old_*). À purger après validation (rm -rf frontend/node_modules.old_*).

Prochaines étapes (S3)
- Page UI /login/2fa (Vue + Tailwind + a11y)
  - Brancher sur useEotpStore: utiliser ttlLeftSec, retryAfter*, actions verify/resend, messages génériques (pas de distinction invalid vs expired).
  - Accessibilité: aria-live="polite" (timer & messages), focus management, data-testid (#code, btn-continue, btn-resend, ttl, msg).
  - Option dev/test: bouton/_action « _peek » conditionnel via fetchPeek().
- Playwright (E2E UI)
  - Scénarios: happy path (via _peek), invalid, expired (TTL court), resend cooldown (429/Retry‑After), locked (MAX_TRIES).
  - Sélecteurs robustes (role/name ou data-testid), pas de wait arbitraire.
- Observabilité front (léger)
  - Breadcrumbs non sensibles: eotp:verify_click, eotp:resend_click, eotp:error_displayed (si infra existante).
- Documentation
  - Append éventuel 09‑ux‑spec‑eotp.md (captures/filaires, liste data-testid) une fois la page branchée.

Commandes de validation
- Vitest (store):
  - cd frontend && npx vitest run app/__tests__/eotp.store.test.ts
- E2E API (existant, _peek):
  - cd frontend && BACKEND_BASE_URL=http://localhost:8000 npx playwright test test-e2e/eotp-happy.spec.ts

Notes
- Aucune donnée sensible loggée côté tests; respect strict Retry‑After en UI.
- _peek limité à dev/test (flag appEnv); pas exposé en prod.

---

2025-10-18 — Scénarios d’erreur E2E + Preuves ops (append)
- Playwright E2E (API, _peek) — VERT en série (--workers=1)
  - Nouveaux specs:
    - frontend/test-e2e/eotp-invalid.spec.ts (OTP faux → générique 401/403, error=invalid_code si JSON)
    - frontend/test-e2e/eotp-expired.spec.ts (TTL court → verify générique, resend OK avec Retry-After)
    - frontend/test-e2e/eotp-locked.spec.ts (> MAX_TRIES → réponses génériques sur challenge verrouillé; nouveau login OK)
    - frontend/test-e2e/eotp-resend-quota.spec.ts (3 resends OK avec cooldown; 4ᵉ → 429, header Retry-After)
  - Stabilisation:
    - Ajout endpoint test-only /flush (backend/studio_core/test_urls_eotp.py) pour réinitialiser le cache entre tests.
    - Backoff basé sur Retry-After + buffer, attente initiale avant le premier resend pour ne pas consommer le quota sur 429.
  - Exécution (exemple):
    - cd frontend && BACKEND_BASE_URL=http://127.0.0.1:8100 npx playwright test test-e2e/eotp-invalid.spec.ts test-e2e/eotp-expired.spec.ts test-e2e/eotp-locked.spec.ts test-e2e/eotp-resend-quota.spec.ts --workers=1 --trace=on
  - Artefacts:
    - Traces/HTML: frontend/test-results/ (dernier run) et playwright-report/ (répertoire standard).

- Preuves Ops — Purge TTL (manage.py eotp_purge_expired)
  - Dry-run (extrait):
    ```
    [eotp_purge_expired] start dry_run=True grace=10m batch=5000
    Expired candidates: 0
    Consumed/Locked (older than 10m) candidates: 0
    Dry-run enabled: no DELETE and no VACUUM executed.
    [eotp_purge_expired] done batches=0 deleted=0 duration=0.071s
    ```
  - Run (DB test sqlite; APP_ENV=test):
    ```
    [eotp_purge_expired] start dry_run=False grace=10m batch=1000
    Expired candidates: 102
    Consumed/Locked (older than 10m) candidates: 36
    VACUUM ANALYZE skipped for vendor=sqlite (only supported on PostgreSQL).
    [eotp_purge_expired] done batches=2 deleted=105 duration=0.017s
    ```
  - Remarque: VACUUM ANALYZE est exécuté automatiquement sur PostgreSQL; sur SQLite, le message « skipped » est attendu.

- Celery beat — inspection planification (à capturer lorsque le broker tourne)
  - Commande de référence:
    ```
    celery -A studio_core inspect scheduled | grep eotp_purge_expired
    ```
  - Environnement local sans broker: capture non réalisée à cette étape; voir runbook « celery-beat-purge.md ».

- Sécurité/PII
  - Aucune fuite de secrets/OTP/emails dans les logs ou artefacts.
  - Messages d’erreur génériques côté API/UI (pas de distinction explicite invalid/expired).
