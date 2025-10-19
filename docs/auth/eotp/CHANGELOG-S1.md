# CHANGELOG-S1 (append-only)
Sprint 1 — Backend Core e-OTP
Statut: livré (backend), tests unitaires/intégration OK, couverture e-OTP ≥ 85%, audits générés. E2E Playwright: spec livrée (exécution à planifier avec backend APP_ENV=test en service). Preuve purge TTL dry-run OK.

2025-10-17
- Portée livrée (S1)
  - Modèle + migrations: table eotp_challenge (UUID PK, status, code_hash argon2id+pepper, tries_count, resend_count, created_at, expires_at, last_sent_at, session_key, context_ua, context_ip_prefix (IPv4 /24, IPv6 /56), corr_id, pepper_id). Index/contraintes (incl. CHECK expires_at > created_at).
  - Services:
    - eotp_issue: secret 6/8 chiffres (flag), hash Argon2id + EOTP_PEPPER, invalide les pendings frais de la session, TTL, instrumentation PII-safe.
    - eotp_verify: comparaison constant-time (argon2.verify ou fallback HMAC SHA-256), TTL, MAX_TRIES→LOCKED, anti-rejeu (CONSUMED), strict context optionnel par flag.
    - eotp_resend: invalide ancien code, régénère, cooldown minimal + Retry-After.
  - Endpoints (CSRF on):
    - POST /api/auth/login/ → superusers → pending_2fa + émission e-OTP (eotp_issue).
    - POST /api/auth/2fa/email/verify/ → délègue eotp_verify; mappe expired→403, invalid/locked→401/403; entêtes Retry-After si rate_limited.
    - POST /api/auth/2fa/email/resend/ → délègue eotp_resend; 200 + Retry-After (header + body) ou 429.
    - POST /api/auth/2fa/email/_peek/ (APP_ENV=test uniquement): retourne le code pour E2E.
  - Purge TTL:
    - Commande manage.py eotp_purge_expired (batches, grace 10m); VACUUM ANALYZE (PostgreSQL). Tâche Celery disponible. Beat à planifier en dev/prod (voir runbook).
  - Feature flags:
    - EOTP_ENABLED, EOTP_CODE_LENGTH, EOTP_TTL (default 300), EOTP_MAX_TRIES (3), COOLDOWN_SECONDS (30), EOTP_STRICT_CONTEXT (False), EOTP_PEPPER(+ID).
  - Observabilité minimale:
    - Événements PII-safe via studio_core.metrics.record_auth_event: auth:eotp_issued|ok|failed|expired|locked|resent corrélés au realm; compteurs exposables sur /metrics.

- Paramètres figés (S1)
  - EOTP_TTL=300 ; MAX_TRIES=3 ; COOLDOWN_SECONDS=30
  - EOTP_PEPPER=(secret env) ; HASH_CHAIN_ALGO=SHA256 (fallback)
  - ARGON2_M=64MiB ; ARGON2_T=3 ; ARGON2_P=2

- Sécurité/Garde-fous
  - Aucune fuite de codes/emails/secrets; _peek uniquement APP_ENV=test.
  - Comparaison constant-time; pepper non loggé.
  - PII-safe: IP prefix tronqué (IPv4 /24, IPv6 /56), UA hash=sha224.
  - S1: pas d’unicité multi-device (device hash en S3). Pending précédents invalidés à l’issue/resend.
  - Isolation realms: couverte par l’utilisation de la session du realm; tests d’intégration cross-realm à compléter en S2/S3.

- Tests
  - Unitaires services (backend/eotp/tests/test_services.py): 4/4 PASS.
  - Intégration endpoints (backend/eotp/tests/test_endpoints.py): 3/3 PASS (CSRF on, verify OK/KO, resend header Retry-After, expired=403).
  - Couverture ciblée module eotp/: 87%
    - Commande: poetry run pytest -q --cov=eotp --cov-report=term-missing eotp/tests
    - Résumé manquant (extraits): services.py lignes non couvertes: [32-33, 61-67, 89-90, 99-102, 112-113, 121-123, 135, 141-144, 150-151, 200, 241-242, 256, 281-293, 299-300, 328]; tasks.py non couvert en S1 (tâche Celery).
  - E2E Playwright (API) — spec ajoutée:
    - frontend/test-e2e/eotp-happy.spec.ts (utilise _peek avec APP_ENV=test). Assertions: login→pending_2fa, _peek→code, verify 200, rejeu 401/403, resend → Retry-After.
    - Exécution requiert BACKEND_BASE_URL et backend en service.

- Audits sécurité (rapports archivés)
  - pip-audit (docs/auth/eotp/audits/pip-audit.md): 5 vulnérabilités signalées
    - django 5.2.5: GHSA-6w2r-r2m5-xq5w, GHSA-hpr9-3m2g-3j9p, GHSA-q95w-c7qg-hrff → corriger vers 5.2.7 (ou 5.1.13/4.2.25 selon stratégie).
    - mcp 1.9.4: GHSA-j975-95f5-7wqh → upgrader ≥ 1.10.0.
    - pip 25.2: GHSA-4xh5-x5gv-qwph.
  - Bandit JSON (docs/auth/eotp/audits/bandit.json): généré (voir détails).
  - Safety (docs/auth/eotp/audits/safety.txt): 3 vulnérabilités (mcp, gunicorn 22.0.0: 2 advisories). Recommandation: maj gunicorn ≥ 23.x.
  - npm audit (docs/auth/eotp/audits/npm-audit.json): 5 vulnérabilités modérées transitives via vitest/vite/esbuild — proposition: maj vitest → 3.2.4 (major).

- Ops — Purge TTL (preuves)
  - Dry-run:
    - manage.py eotp_purge_expired --dry-run
    - Log:
      [eotp_purge_expired] start dry_run=True grace=10m batch=5000
      Expired candidates: 0
      Consumed/Locked (older than 10m) candidates: 0
      Dry-run enabled: no DELETE and no VACUUM executed.
      [eotp_purge_expired] done batches=0 deleted=0 duration=0.030s
  - Beat (à valider en environnement Celery opérationnel):
    - celery -A studio_core inspect scheduled | grep eotp_purge_expired
    - En dev, planifier via CELERY_BEAT_SCHEDULE conformément au runbook.

- Décisions & Mesures Argon2id (S1)
  - Choix de M=64MiB, T=3, P=2 (calibrage dev). P50/p95/p99 à instrumenter en S2 lors des benchs ciblés (non collectés en S1).

- Actions de remédiation (proposées, non appliquées en S1 pour stabilité)
  - Backend:
    - Bump django → 5.2.7 (patch) et exécuter la suite de tests complète.
    - Bump gunicorn → 23.x (si utilisé en prod) + validation de conf.
    - Bump mcp → ≥ 1.10.0 (si chemin d’exécution concerné en prod).
  - Frontend:
    - Bump vitest → 3.2.4 (major) pour résoudre advisories transitives (vite, vite-node, esbuild).
  - Documenter ces changements dans CHANGELOG-S2 si réalisés dans le sprint suivant.

- Points restants S1 / validations (DoD)
  - E2E Playwright: exécution et rapport HTML (une fois backend en service, APP_ENV=test).
  - Preuve Celery beat (inspect scheduled) — dépend de la stack Celery/Redis active.
  - tasks.py (purge) à couvrir par tests (≥85% module eotp), sinon toléré en S1 (couverture globale eotp 87%).

Notes:
- Fichiers d’audit: docs/auth/eotp/audits/*
- Spec E2E: frontend/test-e2e/eotp-happy.spec.ts
- Paramétrage test: settings test dédiés (ROOT_URLCONF de test, CSRF_COOKIE_HTTPONLY=False pour header X-CSRFToken).

2025-10-17 — Addenda S1 (stabilisations réalisées)
- Webhook Postmark (tests): route exposée dans ROOT_URLCONF de test backend/studio_core/test_urls_eotp.py → /api/webhooks/postmark/bounce/; tests de signature OK/KO verts.
- Test quota resend (déterminisme): neutralisation du cooldown session et patch de la constante à l’import pour vérifier la limite 3/h (verts).
- Durcissement vérification code: ajout du flag EOTP_DISABLE_HMAC_FALLBACK (désactive le fallback SHA‑256 en prod). backend/.env.example mis à jour.
- Documentation DNS Postmark: création docs/auth/eotp/dns/POSTMARK_DNS.md (SPF, DKIM 2048, Return‑Path, DMARC, MTA‑STS, TLSRPT). Pas de secrets.
- Statut tests ciblés e‑OTP: suites backend eotp/ vertes. Limitation connue: la collecte globale peut échouer sur d’autres apps (ai_assistants) — exécuter eotp/ ciblé.
