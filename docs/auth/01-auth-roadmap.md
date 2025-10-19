## 01 — Auth Roadmap (Sprint Auth 0)

### Vision
Livrer un flux **admin Dojo** sécurisé : connexion → CSRF/nonce → gate → conversation → message.
Découpage en sous-sprints pour livrer incrémentalement, chaque jalon ayant un DoD clair.

---

### S0A — Backend Hardening & Foundations
**Objectifs**
1. Remplacer `ai_assistants.views.api_auth_creds` par un contrôleur sécurisé :
   - `POST /api/auth/login/` (`@csrf_protect`, rate-limit, audit).
   - `GET /api/auth/csrf/` (pré-dépose `csrftoken`).
   - `POST /api/auth/logout/` (`@csrf_protect`, supprime session + cookies realm).
   - Retour JSON `{ ok, next }`, sessionid HttpOnly (`__Host-pp_session`), cookie `pp_realm`.
2. Réactiver `SessionAuthentication` dans `REST_FRAMEWORK` et restreindre JWT à Dojo-only endpoints.
3. Créer un endpoint `POST /api/auth/nonce/` (session requise, `RequestNonce.generate()`, TTL 60 s).
4. Organiser GatedSessionMiddleware : TTL configurable, message clair (`gate_required`).
5. Durcir cookies : `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_AGE` 8 h, `SESSION_EXPIRE_AT_BROWSER_CLOSE=True`.
6. CSRF : s’assurer que `CSRF_COOKIE_HTTPONLY=False` (accessible JS), `CSRF_COOKIE_SECURE=True` en prod, `CSRF_TRUSTED_ORIGINS` aligné.
7. Logging & metrics : journaliser login/logout/gate/conversation dans `AuditLog` + `record_auth_event`.

**DoD**
- Nouveaux endpoints en place, anciens (`/api/auth/creds`) supprimés ou redirigés.
- Tests Django : login (succès/échec), logout, nonce, gate (CSRF ok), rate-limit.
- Documentation mise à jour (`README_AUTH` + `/docs/auth/02-api-contracts.md`).
- Lint/pytest backend verts.

---

### S0B — Front Integration (Nuxt)
**Objectifs**
1. Créer un composable `useAuth()` ou store Pinia : `login()`, `logout()`, `fetchMe()`, `isAuthenticated`, `user`.
2. Gestion CSRF : `GET /api/auth/csrf/` au boot SSR, stockage token (cookie + state), helpers `withCsrf` pour `$fetch`.
3. Route guard : intercepter 401/403 via `onResponseError`, rediriger vers `/login`, nettoyer store.
4. Mettre à jour pages :
   - `login.vue` → utilise `useAuth().login`, affiche erreurs rate-limit/backoff.
   - `gate.vue` & `ask-agents.vue` → injectent `X-CSRFToken` + `X-Request-Nonce` (via endpoint S0A).
   - `PxHeader` → bouton logout, état utilisateur.
5. UI d’état : skeleton/progress, affichage message pour gate expiré, session expirée.
6. Tests Playwright (login success/fail, refresh, logout).

**DoD**
- Playwright `auth-login.spec.ts` et `dojo-gate.spec.ts` passent en local (desktop & mobile).
- Composables `useAuth`, `useCsrf`, `useNonce` + plugin `$fetch` documentés (`docs/auth/04-ux-flows.md`).
- Toutes les requêtes mutatives incluent `X-CSRFToken` (et `X-Request-Nonce` pour gates/agents).
- Plus aucun appel au legacy `/api/auth/creds`; nouveaux Nitro proxies `/api/auth/*`.
- UI : toasts login/gate, backoff 429, redirections protégées.

**Front Integration — statut**
✅ Livré. Le front Nuxt consomme désormais `/api/auth/login/`, `/api/auth/me/`, `/api/auth/logout/`, `/api/auth/nonce/` via le store `useAuth` et le plugin `fetch-auth`. Les pages `login.vue`, `gate.vue`, `ask-agents.vue` gèrent CSRF + nonce, route guards `dojo` protègent les écrans et les tests E2E couvrent login (succès/échec) et gate (succès/échec).

---

### S0C — Dojo Conversation API & Permissions
**Objectifs**
1. Modèles Django (app dédiée `dojo_chat` ou `ai_assistants`) :
   - `Conversation` (id UUID, owner, agent_slug, status, created_at).
   - `Message` (conversation FK, role {admin,agent}, content, tokens, latency, created_at).
   - Signals pour audit (create conversation/message).
2. DRF ViewSet ou APIView (`/api/conversations/`, `/api/messages/`) :
   - Require `IsAuthenticated`, superuser ou scope `dojo_converse`.
   - CSRF/session friendly (SessionAuthentication + JWT option).
   - Throttles (5 conv/min, 30 messages/min).
3. Adapter `ai_assistants.api_ask_agent` → crée `Message` (role admin + agent).
4. Génération `RequestNonce` : inclure dans header réponse `X-Request-Nonce` + endpoint explicit.
5. Tests Django (permissions, rate-limit, nonce replay, owner scoping).

**DoD**
- Migration appliquée, tests unitaires & API (pytest + httpie script) couvrent CRUD minimal.
- Documentation `/docs/auth/02-api-contracts.md` mise à jour (schémas JSON).
- AuditLog enregistre clé conversation/message.
- Manual QA : création conversation via HTTPie + check DB.

**Statut**
✅ Livré. Les modèles Dojo (agents/conversations/messages/audit) sont en production avec migrations, DRF ViewSets protégé CSRF + nonce Redis (anti-rejeu), throttles 5/30 rpm et audit structuré. Le frontend Nuxt (ask-agents + /conversations/[id]) consomme les nouvelles API via `$fetch` (nonce chaining) et les tests Django couvrent nonce/CSRF/soft-delete. Le script `docs/auth/smoke-dojo.http` valide le flux complet.

---

### S0D — End-to-End Flow & QA
**Objectifs**
1. Chaîne complète : login → `whoami` → gate (absurdity + ritual) → conversation creation → premier message → logout.
2. Playwright E2E (desktop & mobile) couvrant enchaînement, rechargement (refresh cookie/session).
3. Scripts HTTPie (doc `/docs/auth/01` / `/02`) validant login/logout/me/conversation/message.
4. Observabilité : logs corrélés (request-id), métriques `record_auth_event` pour chaque étape.
5. Durcir Caddy (option) : CSP enforce (sauf inline), ajouter `Strict-Transport-Security` pour env HTTPS.
6. Hand-off doc : FAQ, troubleshooting, matrice erreurs (rate-limit, CSRF fail, nonce missing).

**DoD**
- Playwright + HTTPie scripts automatisés dans CI (ou job dédié).
- Rapport final (README_AUTH appendice) confirmant budgets LCP/INP/CLS, perf login & ask-agents.
- AuditLog montre la timeline complètes.
- Session invalidée après logout (accès protégé → 401).
- Rétro documentée (gaps résiduels, backlog S1 : TOTP, WebAuthn, RBAC fin, MFA).

**Statut**
- ✅ Tests E2E Playwright réels (login → gate → conversation → message → archive + scénarios erreurs nonce/CSRF/throttle).
- ✅ Pipeline CI `ci_dojo.yml` (pytest + Playwright, artefacts).
- ✅ CSP enforce (Nuxt + Caddy), logs JSON corrélés via `request_id`, Sentry (front/back) avec scrub PII.
- ✅ Runbooks `docs/ops/runbook_csp.md`, `docs/ops/runbook_incidents.md` + smoke script enrichi (`docs/auth/smoke-dojo.http`).

---

### Au-delà du Sprint 0
- **S1** : activer TOTP & WebAuthn Dojo (réactiver endpoints accounts, UI, stockage `pending_2fa`).
- **S2** : RBAC fin (permissions par agent), journaux exportables, intégration mTLS / Passkeys.
- **S3** : Observabilité approfondie (SIEM, alertes brute-force), secrets manager, rotation clés JWT.
