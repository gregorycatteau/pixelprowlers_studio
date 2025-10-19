# 01 — Cartographie de l’existant (Django/Nuxt/Redis/CI)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Vue d’ensemble
2. Backend Django
   2.1 Settings & middlewares
   2.2 Authentification, CSRF, sessions, cookies
   2.3 API/Views/Routes (incl. e‑OTP et Nonce)
   2.4 Modèles & schéma DB (axé auth/observabilité)
   2.5 Logs & Observabilité (events, Sentry, NATS)
   2.6 Intégrations Redis et NATS
3. Frontend Nuxt
   3.1 Middleware de navigation & garde d’accès
   3.2 Composables (auth, csrf, nonce) et plugin fetch
   3.3 Endpoints consommés (proxy Nitro → Django)
   3.4 UX actuelle (login → pending_2fa → e‑OTP)
   3.5 Tests (Vitest & Playwright)
4. Redis (disponibilité/config/espaces de noms)
5. Build & CI (scripts, Docker/Compose)
6. Risques identifiés (premier balayage)
7. Sources inspectées
8. Points ouverts / TODO

1) Vue d’ensemble
- Pile actuelle orientée sécurité:
  - Django: Middlewares sécurité (Security, CSRF), redaction PII, audit request‑ID, throttling DRF, JWT+Sessions, realms (cookies distincts par sous‑domaine), endpoints auth (login, totp, webauthn, e‑OTP).
  - Nuxt: Proxies Nitro côté serveur vers Django, injection autom. des en‑têtes X‑CSRFToken et X‑Request‑Nonce, middlewares de navigation (auth, dojo), gestion SSR des cookies HttpOnly de realm, tests E2E couvrant CSRF et anti‑rejeu.
  - Redis: utilisé pour Celery broker et optionnellement pour les stores Nonce/rate‑limits.
  - NATS: Events gateway HTTP → NATS JetStream (optionnel) + consumer Django.

2) Backend Django

2.1 Settings & middlewares
- Fichier principal: backend/studio_core/settings/base.py
  - INSTALLED_APPS inclut django.contrib.*, DRF, simplejwt, apps internes (accounts, api, ai_assistants, studio_core).
  - CORS (activé si corsheaders présent) et listes d’origines autorisées construites à partir d’env (CORS_ALLOWED_ORIGINS); CORS_ALLOW_CREDENTIALS=true possible.
  - CSRF_TRUSTED_ORIGINS défini à partir de defaults + env.
  - MIDDLEWARE (ordre pertinent):
    - SecurityMiddleware
    - WhiteNoise
    - (eventuel) CorsMiddleware
    - SessionMiddleware
    - CommonMiddleware
    - CsrfViewMiddleware
    - AuthenticationMiddleware
    - MessageMiddleware
    - XFrameOptions
    - studio_core.middleware.SecurityHeadersMiddleware
    - accounts.middleware.RequestIDAndAuditMiddleware
    - studio_core.api_auth_middleware.ApiAuthRedirectTo401Middleware
    - studio_core.gates_middleware.GatedSessionMiddleware
  - DRF:
    - DEFAULT_AUTHENTICATION_CLASSES: SessionAuthentication, JWTAuthentication
    - DEFAULT_THROTTLE_CLASSES/DEFAULT_THROTTLE_RATES configurables
  - SIMPLE_JWT:
    - AUTH_HEADER_TYPES: ("Bearer",), rotation refresh, blacklist après rotation.
  - Email:
    - Dev: console EmailBackend; Prod: SMTP (via env), DEFAULT_FROM_EMAIL adapté.
  - Prod (prod.py):
    - ALLOWED_HOSTS strict, CSRF_TRUSTED_ORIGINS, CORS définis via env
    - SECURE_* (HSTS, redirect), LOGGING simple console
    - Celery broker/result par défaut Redis (env CELERY_BROKER_URL)
  - Realms (dojo/clients/laby):
    - Cookies nommés par realm (SESSION_COOKIE_NAME/CSRF_COOKIE_NAME), CORS/CSRF adaptés, AUTH_HEADER_TYPES ("Bearer"), SECURE_SSL_REDIRECT=True, SAMESITE (Strict/Lax selon realm).

2.2 Authentification, CSRF, sessions, cookies
- Sessions et CSRF:
  - Cookies HttpOnly par défaut, SAMESITE "Lax" dans base.py (prod: Secure True).
  - Realms:
    - dojo: SESSION_COOKIE_NAME="__Host-pp_session", CSRF_COOKIE_NAME="pp_dojo_csrftoken".
    - clients: "pp_clients_sessionid", "pp_clients_csrftoken".
    - laby (honeypot): "pp_laby_sessionid", "pp_laby_csrftoken".
- Redirection 401 API:
  - studio_core/api_auth_middleware.py convertit 3xx→401 JSON sur /api/* pointant vers login_url.
- Request ID & Audit:
  - accounts/middleware.py injecte X‑Request‑ID et écrit AuditLog (sans casser la requête).
- Gating:
  - studio_core/gates_middleware.py exige un “gate ok” pour /api/agents/* avec TTL et nettoyage session si expiré.

2.3 API/Views/Routes (incl. e‑OTP et Nonce)
- URLs clés (extraits):
  - studio_core/urls.py: "api/auth/csrf/" (ensure_csrf_cookie), "api/hello", forward_auth endpoints, GraphQL sécurisé.
  - accounts/urls.py: /api/auth/login/, /api/auth/2fa/email/verify|resend|_peek, /api/auth/nonce|nonce/verify, /api/auth/webauthn/options|verify, /api/auth/totp/*, refresh/logout cookie.
- e‑OTP existant (backend/accounts/auth.py):
  - api_auth_login (POST) → "pending_2fa"; si superuser, e‑OTP émis.
  - e‑OTP: code 6 chiffres, TTL ≈ 3 min (paramétrable), stockage côté cache, hash SHA‑256 + pepper (_EOTP_PEPPER=SECRET_KEY par défaut), liaison à session_key, endpoints protégés CSRF:
    - POST /api/auth/2fa/email/verify/ (@csrf_protect)
    - POST /api/auth/2fa/email/resend/ (@csrf_protect, quotas et Retry‑After transmis jusqu’au front)
    - TEST‑ONLY: POST /api/auth/2fa/email/_peek/ (APP_ENV=test)
  - Autres flows:
    - WebAuthn options/verify (plusieurs endpoints @csrf_exempt en dev/compat; en prod préfèrer @csrf_protect)
    - TOTP bootstrap/activate/verify/recovery (gestion des recovery codes hashés en session, pas en clair)
  - Nonce de console (différent de RequestNonce des assistants): GET/POST /api/auth/nonce* avec session["recent_webauthn_at"] comme garde, TTL 60s, consommation one‑time.

- Nonce anti‑rejeu générique (ai_assistants/security.py):
  - RequestNonce signé + tracking Redis/cache avec TTL=60s; exceptions NonceError; tests Pytest couvrant:
    - Requêtes sans nonce rejetées (400), sans CSRF (403), replay bloqué (400).
  - Intégration DRF/Nuxt (headers "X‑Request‑Nonce" et cycle "X‑New‑Request‑Nonce" côté réponses).

2.4 Modèles & schéma DB (axé auth/observabilité)
- Users/Agents/Conversations (ai_assistants/models.py):
  - Conversation, Message, ConversationAuditLog (actor FK → AUTH_USER_MODEL).
  - Indices & FK appropriés; journaux d’actions.
- API (api/models.py):
  - Project (owner FK → user), Lead (email indexé, event_id unique).
- Accounts (accounts/migrations/*):
  - AgentProfile (OneToOne user), AuditLog, diverses liaisons.
- DB config (studio_core/dbconf.py):
  - DATABASE_URL via env (prod.py impose la présence de DATABASE_URL).
  - Fallback sqlite en dev/test (tests confirment fallback).
- Remarque e‑OTP:
  - État actuel: e‑OTP persiste en cache (clé "eotp:{session_key}") plutôt que table dédiée.

2.5 Logs & Observabilité (events, Sentry, NATS)
- Logging structuré (studio_core/logging.py):
  - AgentPIIRedactionFilter: redaction d’emails, tokens sk‑*, UUIDs; tests confirment.
  - RequestContextFilter: contexte par requête injecté dans les logs.
  - JsonLogFormatter: JSON compact avec ts/level/name…
- LOGGING config (base.py):
  - handlers.console JSON + filtres redact_pii & request_context.
- Sentry (base.py):
  - sentry_sdk intégré si SENTRY_DSN, avec LoggingIntegration.
- Metrics (studio_core/metrics.py):
  - record_auth_event(endpoint, decision, realm, …) + counters/latences par realm/endpoint.
- Events Gateway (api/views.py):
  - HTTP → NATS JetStream (serveur configuré via NATS_URL/user/pass); enrichit avec request_id; normalise les erreurs.

2.6 Intégrations Redis et NATS
- Redis:
  - Celery broker/result par défaut (prod).
  - ai_assistants/security.py: Redis (via REDIS_URL ou REQUEST_NONCE_REDIS_URL) pour RequestNonce store (NX+TTL) sinon fallback cache.
  - studio_core/honeypot.py: cache.incr et touch TTL pour honeypot hits (LocMem/Redis).
- NATS:
  - Events gateway + management command events_consumer (JetStream pull durable, auto‑create stream en dev si flag).

3) Frontend Nuxt

3.1 Middleware de navigation & garde d’accès
- app/middleware/auth.ts:
  - ensureAuthenticated() sinon redirect /login.
- app/middleware/dojo.ts:
  - ensureAuthenticated() + guard isSuperuser sinon /login?forbidden=1.
- app/middleware/realm.global.ts (SSR‑only):
  - Route vers “/dashboard” (realm C) vs “/console” (realm A/H) en lisant cookie HttpOnly pp_realm côté serveur; redirige “/” et “/login” vers la home du realm.

3.2 Composables (auth, csrf, nonce) et plugin fetch
- useCsrf():
  - Lit cookie "csrftoken" côté client, permet refresh via /api/auth/csrf (proxy Nitro → Django), stocke dans state.
- useNonce():
  - POST /api/auth/nonce/ (proxy), conserve nonce courant, cycle sur entête "X‑New‑Request‑Nonce".
- useAuth():
  - fetchMe() → /api/auth/me (proxy); login() → /api/auth/login (proxy) avec X‑CSRFToken; logout() → /api/auth/logout (proxy) avec X‑CSRFToken; intègre useCsrf et useNonce.
- app/plugins/fetch-auth.ts:
  - $fetch.create(credentials: 'include'); ajoute X‑CSRFToken pour méthodes mutatives; ajoute X‑Request‑Nonce pour /api/(gates|agents|conversations|messages); gère 401 (reset + redirect login); retry 403 csrf_failed après refresh CSRF; cycle nonce sur headers réponse.

3.3 Endpoints consommés (proxy Nitro → Django) — extraits
- server/api/auth/login.post.ts → {DJANGO}/api/auth/login/
- server/api/auth/logout.post.ts → {DJANGO}/api/auth/logout/
- server/api/auth/csrf.get.ts → {DJANGO}/api/auth/csrf/
- server/api/auth/2fa/email/verify.post.ts → {DJANGO}/api/auth/2fa/email/verify/
- server/api/auth/2fa/email/resend.post.ts → {DJANGO}/api/auth/2fa/email/resend/
- server/api/auth/2fa/email/peek.post.ts (test‑only) → {DJANGO}/api/auth/2fa/email/_peek/
- server/api/auth/nonce.post.ts → {DJANGO}/api/auth/nonce/
- server/api/projects/* → {DJANGO}/api/v1/projects/* (headers cookie + x‑csrftoken forward)
- server/api/agents/[slug]/ask.post.ts → {DJANGO}/api/agents/:slug/ask (x‑request‑nonce forward)

3.4 UX actuelle (login → pending_2fa → e‑OTP)
- E2E décrit un flux:
  - /login → pending_2fa → page /login/2fa
  - Récup e‑OTP via endpoint test‑only /api/auth/2fa/email/_peek (APP_ENV=test)
  - POST verify → redirect /gate puis flows dojo; affichages UI (heading "Vérification à deux facteurs", champ #code).
- Gestion d’erreurs (proxy):
  - Propagation Retry‑After pour 429 resend, erreurs JSON normalisées (“proxy_*_failed”).

3.5 Tests (Vitest & Playwright)
- Vitest: app/__tests__/smoke.test.ts (sanity).
- Playwright:
  - test-e2e/eotp-happy.spec.ts (happy path e‑OTP: login→2FA→peek→verify→/gate).
  - test-e2e/dojo-security.spec.ts: 403 sans CSRF, anti‑rejeu nonce (400), rate‑limit gate (429).
  - test-e2e/dojo-auth-flow.spec.ts: login, gate, header user, logout.
  - test-e2e/availability.spec.ts: render page /login.
- playwright.config.ts: reporters list+junit+html; projets browsers (chromium/firefox/webkit) configurés.

4) Redis (disponibilité/config/espaces de noms)
- Disponibilité/config:
  - Prod: Redis utilisé par Celery (CELERY_BROKER_URL) et potentiellement comme cache (non explicitement vu, fallback LocMem probable en dev).
  - RequestNonce: clés "reqnonce:{user}:{payload}" (pattern construit dans ai_assistants/security).
- e‑OTP existant:
  - Clés cache “eotp:{session_key}” (accounts/auth.py) — backend agnostique du moteur (LocMem/Redis). En prod, recommander Redis pour robustesse TTL.

5) Build & CI (scripts, Docker/Compose)
- Backend:
  - pytest.ini, pyproject/poetry, Makefile, scripts/ (dev-check, bootstrap_e2e, etc.)
- Frontend:
  - Vitest config (via package.json), Playwright config, docker-compose.playwright.yml pour exécuter Playwright dans Docker (headless).
- Compose (deploy/): stacks (db, nats, etc.) pour environnements déployés.
- Recommendation Sprint 0: ne pas casser pipelines actuels; docs uniquement.

6) Risques identifiés (premier balayage)
- CSRF & endpoints @csrf_exempt:
  - Plusieurs endpoints webauthn/totp marqués csrf_exempt pour compat/dev — à aligner en prod ou protéger via proxy et vérifications d’origine; audit à planifier.
- Session/CSRF double‑submit:
  - Synchronisation cookie/header requise; Nuxt plugin gère le retry, mais risque d’échec si cookie absent/non rafraîchi. Tests déjà présents; conserver stratégie de refresh proactive.
- Anti‑rejeu:
  - Pour API assistants: RequestNonce robuste (Redis + NX) avec tests; pour e‑OTP: anti‑rejeu via consommation en cache, mais sans table dédiée la visibilité/audit est moindre (cible: table eotp_challenge).
- Entropie/random:
  - e‑OTP: secrets.randbelow(1_000_000) (uniforme 6 chiffres). OK pour code utilisateur; secret serveur (pepper) actuellement dérivé de SECRET_KEY; cible: pepper dédié (rotation, provenance secret management).
- Hydratation/SSR:
  - Middleware realm.global.ts SSR‑only lit cookies HttpOnly; faible risque de mismatch, règles déjà en place (no‑op côté client).
- CORS/Origine:
  - Bien cadrés via realms et settings; attention aux headers Origin/Referer côté proxy login (explicitement non relayés pour éviter faux positifs CSRF).
- Email:
  - Fallback SMTP silencieux (fail_silently=True) — risque d’illusion de succès en dev si email non délivré; E2E “peek” compense en test; en prod prévoir monitoring bounces/livraison.

7) Sources inspectées (extraits pertinents)
- Settings & middleware:
  - studio_core/settings/base.py (ALLOWED_HOSTS/CSRF/CORS/MIDDLEWARE/LOGGING/SIMPLE_JWT/Email)
  - studio_core/settings/{prod.py, dev.py, test.py}, realms/{dojo.py, clients.py, laby.py}
- Middlewares:
  - studio_core/middleware.py, studio_core/gates_middleware.py, studio_core/api_auth_middleware.py, accounts/middleware.py
- Auth & e‑OTP:
  - accounts/auth.py (login, e‑OTP verify/resend/_peek, webauthn, totp, cookies/CSRF helpers)
- Nonce & sécurité:
  - ai_assistants/security.py (RequestNonce Redis/cache)
  - tests/ai_assistants/test_csrf_or_nonce.py, test_logging_redaction.py, test_throttle.py
- Observabilité:
  - studio_core/logging.py, studio_core/metrics.py, studio_core/views.py (forward_auth)
  - api/views.py (events gateway → NATS), api/management/commands/events_consumer.py
- Frontend:
  - app/composables (useAuth, useCsrf, useNonce), app/plugins/fetch-auth.ts
  - server/api/* proxies vers Django (login, csrf, e‑OTP, projects, agents)
  - middlewares (auth, dojo, realm.global)
  - Playwright tests (eotp-happy, dojo-security, dojo-auth-flow, availability)
  - playwright.config.ts

8) Points ouverts / TODO
- Décider si certains endpoints aujourd’hui @csrf_exempt doivent être protégés en prod (alignement par realm / proxy).
- Confirmer le backend de cache/Redis utilisé en prod pour e‑OTP & RequestNonce; documenter les TTL, tailles pool, monitoring Redis.
- Formaliser les espaces de noms de clés Redis (eotp:*, reqnonce:*, ratelimit:*).
- Compléter la matrice des realms (cookies, CORS, JWT claims) — tests de paramétrage existent (tests/test_realms_settings.py).
- Cartographier les dashboards/métriques prêts à l’emploi (à finaliser dans 07‑observabilite-alerting.md).
