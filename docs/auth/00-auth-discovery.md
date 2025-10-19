## 00 — Auth Discovery (Sprint Auth 0)

### 1. Frontend Inventory (Nuxt 4)
- **Entry points**
  - `app/pages/login.vue` : formulaire simple, POST `fetch('/api/auth/creds')`, `credentials: 'include'`, pas de gestion CSRF ni d’état global.
  - `app/pages/preflight.vue` → `gate.vue` → `ask-agents.vue` : parcours “préflight → gate → console IA”.
  - `app/pages/console.vue` : expérimentation WebAuthn via `/api/auth/theme` (actions `nonce`, `nonceVerify`, `webauthn*`).
- **Middleware & composables**
  - `middleware/realm.global.ts` lit le cookie HttpOnly `pp_realm` côté SSR pour router `/dashboard` (clients) vs `/console` (dojo).
  - Aucun store Pinia ni `useAuth()` ; état session non stocké sur le client.
  - Composants `PxHeader`, `AppShell` attendent qu’une page fournisse header/toolbar/footer.
- **Server routes (Nitro)**
  - `server/api/auth/creds.post.ts` : proxy multi-actions vers Django (`/api/auth/login`, TOTP, WebAuthn, nonce). Forward cookie Turnstile éventuel.
  - `server/api/agents/index.get.ts` & `[slug]/ask.post.ts` : proxy des endpoints Dojo, forward cookies, optionnellement `x-csrftoken`, mais **ne génèrent pas de nonce**.
  - Aucun helper pour récupérer/rafraîchir les cookies CSRF ; le front ne fait pas de `X-CSRFToken`.
- **UI actuelle**
  - `ask-agents.vue` consomme `/api/agents` & `/api/agents/{slug}/ask`, mais n’envoie ni `X-CSRFToken` ni `X-Request-Nonce` → appels voués à échouer (403/nonce_missing).
  - `gate.vue` dépend de `/api/gates/*` (CSRF obligatoire) sans fournir de token → flux cassé hors navigateur pré-authentifié.
- **Runtime config**
  - `nuxt.config.ts` expose `css`, module `@nuxtjs/device`, runtimeConfig `DJANGO_BASE_URL`.
  - Pas de config `components: true` → ajouté manuellement (prefix `~/components/ui`).
  - CSP report-only injectée via Caddy (pass-through).

### 2. Backend Inventory (Django 5)
- **Settings principaux**
  - `studio_core/settings/base.py` :
    - `MIDDLEWARE` inclut `SecurityMiddleware`, `CsrfViewMiddleware`, `accounts.middleware.RequestIDAndAuditMiddleware`, `studio_core.gates_middleware.GatedSessionMiddleware`.
    - `REST_FRAMEWORK` redéclaré deux fois → **configuration effective = JWT seulement** (`SessionAuthentication` supprimée).
    - Session & CSRF cookies `SameSite=Lax`. `SESSION_COOKIE_SECURE` activé seulement en prod via env.
    - Système `SIMPLE_JWT` (RS256 si clés fournies, sinon HS256).
  - `settings/prod.py` + `settings/security.py` : forcent cookies `Secure`, `HttpOnly`, HSTS, CSP via `django-csp`.
  - Realm `dojo` (`settings/realms/dojo.py`) ajoute allauth MFA, définit `SESSION_COOKIE_NAME=pp_dojo_sessionid`, `CSRF_COOKIE_NAME=pp_dojo_csrftoken`, CORS strict.
- **Auth endpoints**
  - `accounts/auth.py` :
    - JWT cookie flow (LoginCookieView/Refresh/Logout/WhoAmI) avec refresh HttpOnly (`pp_refresh`), **CSRF requis en prod** (header + cookie). `WhoAmIView` attend un access JWT (pas session).
    - Clients Dojo : `api_auth_login` (TOTP), `api_auth_totp_verify` (issues JWT + `login(request,user)` + cookies `__Host-pp_refresh`/`__Host-pp_realm`). Beaucoup d’endpoints `@csrf_exempt`.
  - `ai_assistants/views.py` :
    - **Session login simpliste** `api_auth_creds` (`@csrf_exempt`, pas de TOTP, retourne `{ok}`) utilisé par Nuxt.
    - Gating `/api/gates/*` : `@login_required`, `@csrf_protect`, `user_passes_test(is_superuser)`, impose session + superuser.
    - Agents `/api/agents/` (GET) & `/api/agents/<slug>/ask` (POST) nécessitent session + superuser + `X-Request-Nonce` + CSRF.
- **Middleware**
  - `studio_core.api_auth_middleware.ApiAuthRedirectTo401Middleware` convertit les redirections login→401 JSON.
  - `studio_core.gates_middleware.GatedSessionMiddleware` bloque `/api/agents*` si `pp_gate_ok` absent ou expiré (>90 min).
  - `accounts.middleware.RequestIDAndAuditMiddleware` injecte `X-Request-ID`, journalise dans `AuditLog`.
- **Models & logs**
  - Nombreux modèles agents (manifestes, budgets), mais **absence de Conversation/Message** métier.
  - `RequestNonce` fourni (signature + anti-rejeu) mais **aucun endpoint** ne le distribue.

### 3. Infrastructure & Proxy
- **Caddyfile** (`deploy/caddy/Caddyfile`) :
  - CSP report-only (scripts/style self, style autorise `unsafe-inline`).
  - Pas de HSTS en dev.
  - Forward `X-Request-ID`.
  - Séparation `dev.localhost` (Nuxt) / `api.dev.localhost` (Django).
  - TLS locaux gérés.
- **Docker compose** (non analysé en détail) expose Nuxt & Django séparés.
- **Env** : `.env.dev` etc (non audités ici) probablement fournissent DB/sqlite.
- **Audit** : `accounts.middleware` alimente `AuditLog`, mais sortie non exploitée dans UI.

### 4. API & Flux existants
- **Auth côté Nuxt**
  - POST `/api/auth/creds` → proxy POST `/api/auth/login/` (Django) mais front ignore réponse “pending_2fa”; retente TOTP? Non.
  - Pas de route front pour `/api/auth/whoami` (session) ni `/api/accounts/auth/whoami` (JWT).
  - Pas de flux refresh/blacklist côté Nuxt.
  - Logout absent dans UI (endpoint `/api/auth/logout` existe côté Django).
- **Gate & Agents**
  - `/api/gates/absurdity-check` & `/api/gates/challenge-*` exigent CSRF + session + superuser.
  - `/api/agents` renvoie liste `AgentProfile`.
  - `/api/agents/{slug}/ask` vérifie nonce + CSRF + throttle + superuser.
  - Aucun endpoint conversationnel persistant (echo mock).
- **Console WebAuthn**
  - `/api/auth/theme` action `nonce`/`nonceVerify` → proxies `/api/auth/nonce/*` (Dojo).
  - `api/auth/nonce` nécessite session (superuser) & rate-limit ; front n’expose pas fallback si nonce absent.

### 5. Constat & Gaps majeurs
| Zone | Constats | Risques |
| --- | --- | --- |
| Login `/api/auth/creds` | `@csrf_exempt`, accepte username/password, bypass TOTP, ne set pas `pp_realm`, ne fournit pas CSRF | Session fixation, brute-force, pas de realm routing, CSRF absent |
| CSRF | Front n’obtient pas `csrftoken`, n’envoie pas `X-CSRFToken` | Toutes requêtes POST protégées échoueront ou devront être `csrf_exempt` |
| Request nonce | Aucune API pour `RequestNonce.generate()` | `/api/agents` inutilisable hors script interne ; risque de désactivation côté serveur |
| REST config | `DEFAULT_AUTHENTICATION_CLASSES` = JWT only | DRF endpoints ne reconnaissent pas la session Django, couplage forcé au JWT |
| Cookies | `pp_realm` (HttpOnly) seulement posé par TOTPVérify ; login session ne le crée pas | Middleware Nuxt `realm` inefficace -> redirections incohérentes |
| Gating | `login_required` + superuser, mais front login via `api_auth_creds` n’impose pas superuser | Fuite potentielle : utilisateur non admin peut se connecter et se heurter à 403 tardifs |
| Logout | Endpoint existe (`api/auth/logout`), pas de CSRF, pas exposé UI | Sessions persisteront, pas de rotation refresh |
| Conversations | Aucun modèle/endpoint persistant | Flux Dojo final impossible (pas de conversation, pas de message log) |
| Rate-limit & audit | Présent côté Django mais front ne relaie pas erreurs/headers, pas de backoff UI | Expérience brute-force non amortie |
| CSP | Report-only, inline JS/ CSS autorisés | Aucune enforcement XSS, à planifier |

### 6. Points clé pour la suite
- Standardiser l’auth admin sur **cookies HttpOnly + Django session** (renforcée) avec CSRF double submit, tout en gardant JWT access optionnel pour DRF si besoin.
- Remplacer `api_auth_creds` par un flux sécurisé (`POST /api/auth/login` CSRF-protected) et exposer `/api/auth/csrf`.
- Publier un endpoint `POST /api/auth/nonce/` (nonce signé) + headers `X-Request-Nonce` côté front.
- Réintroduire `SessionAuthentication` dans DRF ou fournir endpoints conversation basés sur vues Django.
- Implémenter un composable `useAuth()` + store (Pinia) pour gérer `me`, `logout`, `csrf`.
- Concevoir modèle `Conversation`/`Message` & permission (admin only, owner scoping).
- Scripts/tests : HTTPie (login/me/logout, conversation) + Playwright (login → gate → ask agent).
- Préparer backlog TOTP/WebAuthn & RBAC fin (hors scope Sprint 0).
