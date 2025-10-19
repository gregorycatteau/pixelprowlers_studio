# 02 — Architecture cible e‑OTP
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Vue d’ensemble
2. Modèle de données minimal (eotp_challenge)
3. Endpoints backend (contrats d’API)
4. Services internes (issue/verify/resend)
5. Flux séquentiel (du login à la console)
6. Throttling, backoff, cooldowns (sans Turnstile)
7. Contexte & anti‑rejeu (session/UA/IP)
8. Intégration Frontend (Nuxt)
9. Observabilité (events, métriques, corrélation)
10. Feature flags & stratégie d’activation
11. Dépendances & configuration
12. Références internes
13. Points ouverts / TODO

1) Vue d’ensemble
Objectif: formaliser une architecture e‑OTP robuste et observable, s’insérant dans l’écosystème existant (Django + Nuxt + Redis + NATS optionnel), sans casser les flux actuels ni la CI.

Principes:
- Code secret haute entropie (128 bits interne) → code utilisateur court (6–8 chiffres) généré uniformément.
- Stockage côté serveur d’un hash (Argon2id + pepper) du code utilisateur; jamais le code en clair.
- Contexte lié: session_key obligatoire + empreintes minimales (ua_hash, ip_prefix/24).
- One‑time & TTL: un challenge est utilisable une seule fois, avec expiration stricte; purge automatisée.
- Ratelimits & backoff progressifs (IP/compte/session) — sans Turnstile.
- Observabilité: events auth:eotp_* + métriques; corrélation via X‑Request‑ID; logs redaction PII.

2) Modèle de données minimal (eotp_challenge)
Table eotp_challenge (nouvelle, dédiée):
- id: uuid (PK)
- user_id: FK → auth_user (nullable pour flux “email‑first” si jamais requis)
- session_key: varchar(64) not null (index) — lie le challenge à la session Django
- status: enum('pending','consumed','expired','locked') not null default 'pending'
- code_hash: varbinary / text (Argon2id)
- algo: varchar(16) default 'argon2id'
- salt: varbinary (si mode Argon2 indépendant) — optionnel, Argon2 inclut son propre salt
- pepper_id: varchar(32) — identifie la pepper active (rotation possible)
- tries_count: int default 0
- resend_count: int default 0
- created_at: timestamptz not null default now()
- expires_at: timestamptz not null (p.ex. now()+3min)
- last_sent_at: timestamptz null
- context_ua: char(56) — sha224(User‑Agent canonique) ou vide si indisponible
- context_ip_prefix: inet / varchar(64) — e.g. “203.0.113.42/24” (v4) ou “2001:db8::/64” (v6)
- corr_id: varchar(64) — corrélation request‑ID (optionnel)
Index suggérés:
- (session_key)
- (status, expires_at)
- (user_id, created_at desc)
- (created_at) pour purge
Purge:
- Job périodique (management command + cron/Celery beat): delete where expires_at < now OR status ∈ {consumed, locked} and older than N minutes.

3) Endpoints backend (contrats d’API)
- POST /api/auth/login/
  - Retour “pending_2fa” + user_hint; e‑OTP “issue” implicite si superuser (aligné à l’existant).
- POST /api/auth/2fa/email/verify/
  - Headers: X‑CSRFToken (double‑submit), X‑Requested‑With
  - Body: { code: "123456" }
  - Réponses:
    - 200 { ok: true } + cookies de session/JWT éventuels; events: auth:eotp_ok
    - 401/400 uniformisés { ok:false, error:"invalid_code" } (anti‑énumération)
    - 429 Retry‑After pour backoff
- POST /api/auth/2fa/email/resend/
  - Headers: X‑CSRFToken
  - Body: {} (optionnel)
  - Réponses:
    - 200 { ok: true, cooldown_sec: 30 }
    - 429 Retry‑After (cooldown/quota)
- (test‑only) POST /api/auth/2fa/email/_peek/
  - APP_ENV=test; renvoie { ok:true, code:"123456" } — jamais en prod.

Notes:
- /issue/ explicite optionnel (si besoin d’un endpoint séparé); sinon émis au moment “pending_2fa”.

4) Services internes (issue/verify/resend)
- issue(user, session, ctx):
  - secret_bytes = os.urandom(16) (128 bits), code_user = uniform(000000–999999)
  - hash = Argon2id(code_user + pepper), status=pending, expires_at=now()+TTL
  - email send async; resend_count=1; last_sent_at=now()
  - event auth:eotp_issued {user_id, session_key, expires_in, realm}
- verify(user, session, code, ctx):
  - lookup challenge by session_key & status=pending & not expired
  - constant‑time compare Argon2id(code + pepper), increment tries_count
  - contexte: ua/ip prefix: tolérance stricte (mismatch configurable → fail)
  - on success: status=consumed; event auth:eotp_ok
  - on fail: rate‑limit; éventuellement lock après N essais; event auth:eotp_failed/locked
- resend(user, session):
  - quotas/cooldown (ex: 1/30s, 3/10min, 6/24h); si dépassé → 429 Retry‑After
  - ré‑émission (nouveau code + invalidation de l’ancien ou réutilisation? cible: invalider ancien et regénérer)
  - update resend_count, last_sent_at; event auth:eotp_resent

5) Flux séquentiel (du login à la console)
- Login POST /api/auth/login/ (CSRF ok) → pending_2fa, e‑OTP “issued”
- UI redirige /login/2fa (timer sur TTL restant; bouton “Renvoyer” grisé avec countdown)
- L’utilisateur saisit le code → POST /api/auth/2fa/email/verify/
- Succès → session/JWT prêts → redirection /gate puis /console
- Échecs:
  - mauvais code: compteur, backoff (tarpit), messages génériques
  - expired: UI propose “Renvoyer” après cooldown
  - lock: délai imposé (cooldown long), event auth:eotp_locked
- Observabilité:
  - Chaque mutation journalise corr_id + realm + decision + ratelimit/backoff; metrics incrémentées.

6) Throttling, backoff, cooldowns (sans Turnstile)
- Dimensions:
  - IP: p.ex. 10/min, 100/h
  - Compte/session: p.ex. 6 essais/10 min; resend: 3/10 min
  - Cooldown resend: 30s, puis backoff exponentiel (30→60→120… plafond 10 min)
- Redis:
  - Clés: ratelimit:eotp:verify:{user_id|sess}:{window}, ratelimit:eotp:resend:{user_id|sess}
  - Expirations naturelles (window size)
- Tarpit:
  - Sur échec récurrent, sleep côté serveur (court, borné) + Retry‑After côté client si pertinent
- Faute d’UA/IP:
  - Ne pas bloquer en cas d’absence (reverse proxy) mais dégrader (réduire tolérance resend, marquer “low confidence”).

7) Contexte & anti‑rejeu (session/UA/IP)
- session_key obligatoire pour lier challenge ↔ client
- UA canonique (lower, tokens stables), hash SHA‑224 stocké
- ip_prefix: /24 pour IPv4, /64 pour IPv6 (préfixes raisonnables)
- verify:
  - Par défaut exiger correspondance UA hash ET ip_prefix
  - Paramètre de tolérance (feature flag) pour réseaux mobiles/NAT (p.ex. autoriser mismatch IP si UA constant, ou l’inverse)
- One‑time:
  - Au succès, status→consumed et suppression de tout réemploi; au fail, pas de signal fort (anti‑énumération)
  - Toute tentative avec un code déjà consommé doit retourner invalid_code (éviter fuite d’état)

8) Intégration Frontend (Nuxt)
- Proxies Nitro existants continuent d’être utilisés:
  - /server/api/auth/2fa/email/verify.post.ts et resend.post.ts propagent X‑CSRFToken, cookies, Retry‑After
- Composables:
  - useCsrf(): refresh proactif avant login/verify/resend
  - useAuth(): login() retourne pending_2fa; fetchMe() pour hydrater header; logout() nettoie et refresh CSRF
- UX:
  - /login/2fa:
    - Input code (#code), normalisation (digits only, trim)
    - Timer TTL (MM:SS), bouton Renvoyer (disabled tant que cooldown)
    - Messages:
      - invalid_code générique
      - locked → “Trop de tentatives. Réessayer dans X min.”
      - expired → proposer resend
  - Accessibilité: labels, focus, ARIA live region pour erreurs/cooldowns
- Ergon. erreurs:
  - 429: lire Retry‑After (seconds); afficher compte à rebours
  - 401/403: rediriger /login si non authentifié/CSRF KO (plugin fetch‑auth gère déjà)

9) Observabilité (events, métriques, corrélation)
- Events (studio_core.metrics.record_auth_event):
  - auth:eotp_issued|resent|ok|failed|expired|locked
  - Labels: realm, endpoint, decision; fields: user_id (hashé/pseudonymisé), corr_id
- Métriques:
  - Compteurs par decision; histogrammes latence (issue→ok)
  - Taux bounces (côté provider email; à intégrer Sprint 2)
  - Taux resend / utilisateur / IP
  - Anomalies par ASN/IP (si données dispo via forward_auth)
- Logs:
  - Redaction PII en place; ne jamais logguer le code ou email complet
  - Corrélation X‑Request‑ID propagée Nuxt⇄Django

10) Feature flags & stratégie d’activation
- Flags:
  - eotp_enabled (par realm)
  - eotp_strict_context (UA/IP stricts)
  - eotp_code_length (6/8)
  - eotp_cooldown_profile (palier de cooldown)
- Activation progressive:
  - Dojo (admins) en premier, puis Clients
  - Monitoring rapproché (échecs/429/locked); rollback = désactiver flag

11) Dépendances & configuration
- Pepper:
  - EOTP_PEPPER séparé de SECRET_KEY (env & rotation), stocker pepper_id dans la ligne
- Argon2:
  - django‑argon2 ou libsodium/argon2‑cffi; paramètres (m, t, p) calibrés selon infra
- Redis:
  - URL/cred; pool size; alerting clés expirées/latences
- Email:
  - Provider API + fallback SMTP (fail_silently=false en prod, avec circuit‑breaker)
- Jobs:
  - Purge TTL (Celery beat/cron); métriques de volumes purgés

12) Références internes
- 00 — Vision & portée: ./00-vision-et-portee.md
- 01 — Cartographie: ./01-cartographie-existant.md
- 03 — Threat model: ./03-threat-model.md
- 04 — Plan de sprints: ./04-plan-de-sprints.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 06 — Migrations & rollback: ./06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md
- 08 — Mail & DNS: ./08-mail-transport-et-dns.md
- 09 — UX spec: ./09-ux-spec-eotp.md
- 10 — Risques & contingences: ./10-risques-et-contingences.md

13) Points ouverts / TODO
- Arbitrer 6 vs 8 chiffres (sécurité vs UX), et si code alphanum court est acceptable (non recommandé)
- Définir paramètres Argon2id (m/t/p) cibles et processus de re‑hash eventual
- Étudier la tolérance UA/IP en mobilité (règle heuristique vs stricte)
- Finaliser le schéma d’events (clés/labels) et les dashboards initiaux
- Valider stratégie de rotation de pepper (pepper_id) et procédure opérationnelle
