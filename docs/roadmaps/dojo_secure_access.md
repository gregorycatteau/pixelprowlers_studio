# Dojo Secure Access — Feuille de route (Nuxt 4 + Django 5)

Contexte
- Objectif métier: accès Dojo sécurisé pour super-utilisateur (session + CSRF + nonce anti‑rejeu + rate‑limit), conversation avec un agent, logs corrélés (X‑Request‑ID).
- Portée sprint: corrections layouts, endpoints auth (CSRF, login, nonce), composables front, rate‑limit, smoke/tests de base.
- Branche de travail: `feat/dojo-secure-access-sprint`
- Convention de commits (exemples):
  - `auth: align csrf endpoint (contracts + view)`
  - `auth: secure login flow (csrf_protect, rotate, cookies)`
  - `auth: add nonce endpoint + redis anti-replay (+ header)`
  - `front: add useCsrf/useAuth/useNonce + fetch plugin`
  - `security: 429 helper + Retry-After`
  - `tests: update smoke-dojo + playwright skeleton`

Ordre d’exécution (peut être ajusté si nécessaire)
1) S1 — Device/Layout
2) S2 — CSRF endpoint
3) S3 — Login sécurisé
4) S4 — Nonce signé + anti‑rejeu
5) S5 — Composables front + fetch plugin
6) S6 — Rate‑limit/Retry‑After + Tests (smoke/Playwright)

Si l’ordre change, noter la raison dans “Décisions & risques”.

---

## Status board (vue globale)

- [ ] S1 — Device/Layout Stabilization
- [ ] S2 — CSRF endpoint conforme
- [ ] S3 — Login sécurisé (CSRF + rotation + cookies)
- [ ] S4 — Nonce signé + anti‑rejeu (Redis)
- [ ] S5 — Composables front + fetch plugin
- [ ] S6 — Rate‑limit/Retry‑After + smoke + e2e

---

## S1 — Device/Layout Stabilization

Objectifs
- Remplacer la détection maison par `@nuxtjs/device`, garantir SSR‑safety, supprimer le WARN `<NuxtLayout />`.
- Layout stable mobile/tablet/laptop et dark/light cohérent SSR + hydratation.

Tâches
- [ ] Installer/configurer `@nuxtjs/device` (Nuxt 4) et définir un UA par défaut côté SSR.
- [ ] Wrapper `useDeviceKind()` minimal (basé sur `useDevice()`).
- [ ] `app.vue`: `<NuxtLayout :name="layoutKey"> <NuxtPage/> </NuxtLayout>`.
- [ ] Définir `layoutKey` stable (SSR + client): mobile/tablet/laptop × dark/light.
- [ ] Fallback layout par défaut `layouts/default.vue`.
- [ ] Mini note de doc `docs/ui/01-device-layout.md` (guidelines, SSR considerations).

Validation (DoD)
- [ ] Plus aucun WARN “Your project has layouts but the <NuxtLayout /> component has not been used.”
- [ ] Layout cohérent SSR/CSR (pas de “layout swap” visible).
- [ ] Note doc rédigée.

Commandes (rapides)
- `npm run dev` (front) — vérifier logs Nuxt
- `curl -I http://dev.localhost` (Caddy → headers sécu visibles)

Attaques simulées (UX robustness)
- [ ] Hydratation: pas de flash dark/light ni changement de layout au 1er tick.

---

## S2 — CSRF endpoint conforme

Objectifs
- GET `/api/auth/csrf/` → 200 `{ ok:true, csrf }`, Set‑Cookie `csrftoken`.
- CORS/CSRF stricts en dev (origines explicites), double‑submit prêt côté front.

Tâches
- [ ] Adapter view backend (`@ensure_csrf_cookie`) pour enveloppe `{ ok, csrf }`.
- [ ] Vérifier `CSRF_TRUSTED_ORIGINS` dev/prod (http+https .dev.localhost).
- [ ] CSRF cookie: HttpOnly=false (contrat), Secure=prod, SameSite=Lax.
- [ ] Addendum doc `docs/auth/05-csrf-addendum.md`.

Validation (DoD)
- [ ] GET `/api/auth/csrf/` → 200 + Set‑Cookie + body `{ ok, csrf }`.

Commandes
- `curl -i https://api.dev.localhost/api/auth/csrf/`
- `http GET ://api.dev.localhost/api/auth/csrf/`

Attaques simulées
- [ ] Appel mutatif sans X‑CSRFToken → 403
- [ ] Origin non listée → 403

---

## S3 — Login sécurisé

Objectifs
- POST `/api/auth/login/` protégé CSRF (403 sans X‑CSRFToken), rotation session (`cycle_key`), cookies realm.
- Deprecation de la route legacy (redirect 307 transitoire) côté front proxy.

Tâches
- [ ] `accounts.auth.api_auth_login`: retirer `@csrf_exempt`, ajouter `@csrf_protect`.
- [ ] Auth (username/email), `login(request, user)`, `request.session.cycle_key()`.
- [ ] Cookies: `__Host-pp_session` (session) et `__Host-pp_realm=A` (HttpOnly; Secure=prod; SameSite-strict/lax selon besoin).
- [ ] Rate‑limit + tarpit + `Retry-After` (429).
- [ ] Front Nitro `server/api/auth/creds.post.ts`: 307 → `/api/auth/login/` + notice deprecation.

Validation (DoD)
- [ ] 403 sans X‑CSRFToken, 200 avec.
- [ ] Ancienne session invalide (fixation évitée).
- [ ] body `{ ok:true, next:'/gate', user:{…} }`.

Commandes
- `http POST ://api.dev.localhost/api/auth/login/ X-CSRFToken:<token> username=admin password=***`
- `curl -i -XPOST https://api.dev.localhost/api/auth/login/ -H "X-CSRFToken: $CSRF" --data '{"username":"admin","password":"***"}'`

Attaques simulées
- [ ] Bruteforce → 429 + Retry‑After (progressif)
- [ ] Session fixation → ancienne sessionid inutilisable

---

## S4 — Nonce signé + anti‑rejeu (Redis)

Objectifs
- POST `/api/auth/nonce/` (session + superuser): nonce signé TTL 60s, jti en Redis, header `X-New-Request-Nonce`.
- Rejeu rejeté (403/401) + trace audit.

Tâches
- [ ] Helper nonce (HMAC/`TimestampSigner`), payload {sub, iat, exp, jti}.
- [ ] `POST /api/auth/nonce/` (CSRF required) + throttle + `Retry-After`.
- [ ] Anti‑replay: `redis.setex(nonce:<jti>, 60, 1)` et consommation à l’usage.
- [ ] Logging: request_id, subject, rejets.

Validation (DoD)
- [ ] 200 + `{ ok:true, nonce, expires_in:60 }` + header `X-New-Request-Nonce`.
- [ ] Rejeu du même nonce → 403/401 + log.

Commandes
- `http POST ://api.dev.localhost/api/auth/nonce/ X-CSRFToken:$CSRF cookie:"__Host-pp_session=..."`
- `curl -i -XPOST https://api.dev.localhost/api/auth/nonce/ -H "X-CSRFToken: $CSRF"`

Attaques simulées
- [ ] Rejeu nonce (2e utilisation) → rejet
- [ ] Horloge/TTL: nonce expiré → rejet

---

## S5 — Front composables & fetch plugin

Objectifs
- `useCsrf`, `useAuth`, `useNonce`, plugin fetch:
  - Injection X‑CSRFToken auto pour méthodes mutatives si cookie présent.
  - Backoff 429 en lisant `Retry-After`.
  - Remplacer appels legacy (login/gate/agents).

Tâches
- [ ] `useCsrf()` (ensure + header getter), `useAuth()` (login/me/logout), `useNonce()` (get + chain).
- [ ] Plugin fetch: header X‑CSRFToken + gestion 401/403 (redirect login) + `Retry-After`.
- [ ] Pages `login.vue`, `gate.vue`, `ask-agents.vue`: appels conformes (X‑Request‑Nonce quand requis).

Validation (DoD)
- [ ] Toutes les opérations mutatives portent X‑CSRFToken.
- [ ] 429 géré (UX: attente/backoff), 401/403 → redirect.

Commandes
- `npm run dev` (front) et tester login/gate depuis UI
- `http POST ://dev.localhost/api/auth/login` (via proxy Nitro)

Attaques simulées
- [ ] Réessaie côté front en cas de 429 (respect Retry‑After)
- [ ] 401/403 → redirections cohérentes et nettoyage d’état

---

## S6 — Rate‑limit/Retry‑After & Tests

Objectifs
- Helper 429 central + `Retry-After`.
- Smoke HTTPie/curl à jour, Playwright skeleton (login → gate → (conv/msg) si dispo).

Tâches
- [ ] Helper utilitaire pour homogénéiser 429 + `Retry-After`.
- [ ] Mettre à jour `docs/auth/smoke-dojo.http` et `docs/auth/smoke-output.txt`.
- [ ] Playwright minimal (desktop): login → gate → (conv/msg si API prête) → logout.

Validation (DoD)
- [ ] Smoke passe en local.
- [ ] e2e basique tourne et démontre le parcours.

Commandes
- `http --session=dojo ://api.dev.localhost/api/auth/csrf/`
- `npx playwright test -c frontend/playwright.config.ts --grep @auth`

Attaques simulées
- [ ] Burst login/nonce → 429 + Retry‑After cohérents

---

## Décisions & risques (à mettre à jour)

- Ordre S1→S6 conservé. Raison: stabiliser le rendu SSR (layouts/device) évite du bruit UX pendant le durcissement auth.
- Risque device SSR (connus): fallback UA fixe côté SSR pour éviter discrepancies hydratation.
- CSRF/CORS: jamais d’origines `*`; hosts explicites; Secure/HttpOnly/SameSite adaptés selon env (prod strict).
- Sessions: rotation après login; invalider ancienne session; audit corrélé (X‑Request‑ID).
- Nonce: TTL 60s; Redis side‑effects contrôlés; horloge système suffisante.
- Rate‑limit: valeurs à durcir si besoin après premiers tests (login 5/m IP; nonce 30/m IP).

---

## Done (journal)

Append ici un bloc par sous‑sprint validé: fichiers clés modifiés, 2 commandes de test et “Attacks simulated”.

Exemple d’entrée:

### [YYYY‑MM‑DD] S2 — CSRF endpoint — Done
- Fichiers:
  - backend/studio_core/urls.py (view csrf + enveloppe {ok, csrf})
  - docs/auth/05-csrf-addendum.md (nouveau)
- Tests:
  - `curl -i https://api.dev.localhost/api/auth/csrf/`
  - `http GET ://api.dev.localhost/api/auth/csrf/`
- Attacks simulated:
  - POST mutatif sans X‑CSRFToken → 403 (ok)
  - Origin non listée → 403 (ok)
