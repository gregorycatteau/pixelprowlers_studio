# 00 — Vision et portée e-OTP (Sprint 0)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Résumé exécutif
- Objectif: Concevoir et planifier une authentification e-OTP (Email One‑Time Passcode) robuste, traçable et compatible avec l’architecture existante (Django + Nuxt), sans modifier le code métier pendant le Sprint 0.
- Contraintes clés:
  - Pas de Turnstile (ni CAPTCHA tiers) pour l’instant
  - Activation progressive via feature flags
  - Zéro fuite de secret: aucun secret en clair dans les logs ni dans cette documentation
  - Compatibilité CI/CD actuelle (Pytest, Vitest, Playwright) et non‑régression
- Résultat attendu: Paquet de documents Sprint 0, cartographie précise de l’existant, architecture cible e-OTP et plan de sprints actionnable.

Table des matières
1. Contexte et objectifs
2. Contraintes et principes de sécurité
3. Compatibilité avec l’existant (synthèse)
4. Portée fonctionnelle e-OTP cible
5. Portée technique e-OTP cible
6. Out of scope / hypothèses
7. Références internes
8. Points ouverts / TODO

1) Contexte et objectifs
Le studio PixelProwlers dispose déjà d’un socle d’authentification hybride côté backend (Django) et d’un proxy d’API côté Nuxt qui gère les en‑têtes de sécurité applicatifs (CSRF, Nonce). L’objectif du chantier est d’élever le niveau de sécurité et de résilience de la voie “e‑OTP” (code envoyé par email) avec:
- Un modèle de données explicite (“challenge” e-OTP) à l’épreuve des re-jeux, avec traçabilité et statuts
- Des limites (rate limits) et backoff, en l’absence de Turnstile
- Une UX e-OTP claire et accessible côté frontend (écrans, timers, resend)
- Une observabilité précise (events, métriques, corrélation) et une journalisation sans fuite de secrets

Sprint 0 produit uniquement de la documentation et, si nécessaire, de mini scripts de smoke-check isolés (répertoire tools/), sans impact sur l’application.

2) Contraintes et principes de sécurité
- Sans Turnstile: pas de CAPTCHA/Proof-of-Human. Impliquer:
  - Ratelimits côté Django/Redis (IP/compte)
  - Backoff/cooldown progressifs
  - Anti‑rejeu strict des challenges e‑OTP (chaque code utilisable une seule fois)
  - Contexte de vérification: liaison du challenge à la session et métadonnées minimales (UA hash, IP prefix)
- Secrets/sensibles:
  - Aucune valeur de secret en clair dans la doc, ni dans les logs
  - Hashing côté serveur: Argon2id + pepper (pepper issu d’un secret serveur), salt aléatoire par challenge
  - Journaux: appliquer la redaction PII (emails, tokens, UUID) déjà en place
- Activation progressive:
  - Feature flags pour activer le tunnel e‑OTP par realm/population
  - Rolloff et rollback documentés (désactivation rapide)
- Observabilité/traçabilité:
  - Corrélation via X‑Request‑ID
  - Events auth:eotp_* (issued, resent, ok, failed, expired, locked)
  - Métriques clés (taux succès/échec, bounces, resend, anomalies IP/ASN)

3) Compatibilité avec l’existant (synthèse)
Synthèse à partir de l’inspection code (Django + Nuxt):
- Backend (Django)
  - Settings & Middlewares (studio_core/settings/base.py):
    - MIDDLEWARE comprend SecurityMiddleware, CsrfViewMiddleware, …, SecurityHeadersMiddleware, RequestIDAndAuditMiddleware, ApiAuthRedirectTo401Middleware, GatedSessionMiddleware
    - CORS/CSRF configurables (realms dojo/clients/laby avec cookies spécifiques: SESSION_COOKIE_NAME/CSRF_COOKIE_NAME)
    - DRF: SessionAuthentication + JWT, throttling configurable
    - Logging structuré + filtres de redaction (studio_core/logging.py)
  - Anti‑rejeu générique (ai_assistants/security.py): RequestNonce avec backend Redis (ou fallback cache), TTL 60s, tests Pytest couvrant CSRF/nonce/replay/throttle
  - E‑OTP déjà présent (accounts/auth.py):
    - api_auth_login → “pending_2fa” + e‑OTP émis, code 6 chiffres uniformes, TTL (≈180s), hash SHA‑256 + pepper (actuellement SECRET_KEY), stockage cache lié à la session
    - api_auth_eotp_verify (CSRF protect) et api_auth_eotp_resend (CSRF protect, cooldown/quota), endpoint test‑only _peek (APP_ENV=test)
    - journalisation record_auth_event(“eotp”, …) + logs JSON
  - Observabilité/événements & intégrations:
    - record_auth_event, events gateway HTTP → NATS (optionnel), Sentry (optionnel)
- Frontend (Nuxt)
  - Plugins/composables:
    - useCsrf() (double‑submit), useNonce(), useAuth(), fetch‑auth plugin qui ajoute X‑CSRFToken / X‑Request‑Nonce aux requêtes mutatives et gère retry CSRF
    - Proxies Nitro côté serveur vers Django: /server/api/auth/* (login, csrf, eotp verify/resend, me, logout…), qui propagent cookies/CSRF et normalisent les erreurs
  - Tests Playwright existants:
    - eotp‑happy.spec.ts (happy path en APP_ENV=test, via endpoint _peek)
    - dojo‑security.spec.ts (403 sans CSRF, rejet nonce replay)
    - flows d’auth/gate
  - Vitest: smoke tests de base
- Redis / Brokering
  - Redis employé en production (CELERY_BROKER_URL par défaut redis://… / Celery)
  - Nonce store peut utiliser REDIS_URL
- Build & CI (extraits)
  - backend: Pytest (pytest.ini), Makefile, scripts tools
  - frontend: Vitest, Playwright (playwright.config.ts), docker-compose.playwright.yml
Conclusion: La pile est déjà structurée “security‑first” (CSRF, nonce, redaction, SSR proxy). L’e‑OTP existe mais gagnera à être formalisé (modèle/migrations, Argon2id, statuts, observabilité, stratégie resend stricte, rate‑limit sans Turnstile, liaison de contexte).

4) Portée fonctionnelle e-OTP cible
- Flux utilisateur cible (résumé)
  1. Login (identifiant/mot de passe ou identité backend existante) → statut pending_2fa
  2. Émission e‑OTP (secret 128 bits) associé à la session + contexte (UA/IP prefix), TTL court
  3. L’utilisateur saisit le code sur l’écran 2FA (timer, normalisation, accessibilité)
  4. Vérification:
     - Hash Argon2id + pepper
     - Anti‑rejeu (one‑time), ratelimits et backoff
     - Vérification de contexte (session/UA/IP)
  5. Succès → authentification finalisée (session + JWT si applicable), génération corr_id
  6. Échecs → erreurs uniformes, verrouillage si contournement, resend sous quotas/cooldown
- États & transitions (cible)
  - pending → consumed | expired | locked
  - resend_count (quota) et next_resend_at (cooldown)
  - tries_count et locked_until (si trop d’échecs)
- Resend
  - Cooldown croissant et quota serré (p.ex. 1/30s, 3/10min, 6/jour configurables)
  - Messages UI explicites, Retry‑After exploité côté proxy Nuxt

5) Portée technique e-OTP cible
- Backend (Django)
  - Modèle eotp_challenge (table dédiée):
    - id (uuid), user (nullable si flux “email”), session_key (index), code_hash, salt, algo (argon2id), pepper_id, status (pending/consumed/expired/locked), created_at/expires_at, tries_count, resend_count, last_sent_at, context (ua_hash, ip_prefix/24), audit fields (corr_id)
    - Index: (session_key), (status, expires_at), (user, created_at), TTL purge par job planifié (management command + cron/celery beat)
  - Services:
    - issue(user/session): génère secret 128 bits, code utilisateur (6/8 chiffres), stocke hash argon2id+pepper
    - verify(user/session, code, context): constant‑time compare, consomme le challenge, backoff/cooldown, transitions d’état
    - resend: applique quotas/cooldown, ré‑émet email, journalise
  - Endpoints:
    - POST /api/auth/2fa/email/issue (si besoin explicite) — ou piggy‑back sur login pending_2fa
    - POST /api/auth/2fa/email/verify
    - POST /api/auth/2fa/email/resend
    - (test‑only) POST /api/auth/2fa/email/_peek (APP_ENV=test)
  - Sécurité:
    - CSRF protect sur verify/resend
    - Rate‑limits (IP & compte) avec Redis
    - Liaison contexte (session/UA/IP) vérifiée à la consommation
  - Observabilité:
    - events auth:eotp_issued|resent|ok|failed|expired|locked
    - métriques: taux succès/échec, latence, resend, bounces, anomalies IP/ASN
- Frontend (Nuxt)
  - UX:
    - Écran login → écran 2FA e‑OTP avec compte à rebours, ergonomie mobile, a11y
    - Gestion d’erreurs uniformes, resend grisé selon cooldown, messagerie claire
  - Stores/composables:
    - Intégration avec useAuth/useCsrf/useNonce existants (headers, retry)
    - Formatage/normalisation des codes (6 ou 8 chiffres)
  - E2E:
    - Scénarios Playwright “happy path” + “rate limit/cooldown/expired/replay”
- Email/transport:
  - Abstraction de provider (Postmark / Sendgrid) + fallback SMTP
  - Modèles d’email minimalistes, entêtes anti‑phishing (no PII/exposition)
  - Pré‑requis DNS (SPF/DKIM/DMARC + MTA‑STS/TLSRPT) documentés

6) Out of scope / hypothèses
- Pas de modification de logique applicative en Sprint 0
- Pas de Turnstile pour l’instant; planifié Sprint 4 (throttling & résilience sans Turnstile, prêt à intégrer ultérieurement un défi secondaire léger si nécessaire)
- Pas d’implémentation d’un provider d’email spécifique pendant Sprint 0 (documentation et abstraction uniquement)
- Hypothèse: Redis disponible pour ratelimits/nonce; sinon fallback cache avec limites

7) Références internes
- 01 — Cartographie de l’existant: ./01-cartographie-existant.md
- 02 — Architecture cible: ./02-architecture-cible.md
- 03 — Threat model: ./03-threat-model.md
- 04 — Plan de sprints: ./04-plan-de-sprints.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 06 — Plan migrations & rollback: ./06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md
- 08 — Mail, transport & DNS: ./08-mail-transport-et-dns.md
- 09 — UX spec e‑OTP: ./09-ux-spec-eotp.md
- 10 — Risques & contingences: ./10-risques-et-contingences.md
- Changelog Sprint 0: ../CHANGELOG-S0.md

8) Points ouverts / TODO
- Valider dimensionnement exact des rate‑limits/cooldown (par IP/compte/session)
- Décider sur la longueur du code utilisateur (6 vs 8 chiffres) et la stratégie d’affichage/masquage UI
- Choisir provider d’email cible (Postmark/Sendgrid) et préciser la surface de fallback SMTP
- Valider la stratégie de purge (TTL) côté DB (cron/Celery beat) et observabilité associée
- Définir le schéma d’events auth:eotp_* final (champs, labels) et les dashboards initiaux
