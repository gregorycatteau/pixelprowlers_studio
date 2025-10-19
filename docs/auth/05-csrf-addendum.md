# 05 — CSRF Addendum (Dojo Secure Access)

But
- Rendre explicite la stratégie CSRF côté Django + Nuxt.
- Expliquer comment récupérer/rafraîchir le token, l’envoyer correctement (double-submit), et déboguer les 403.

Modèle choisi
- CSRF “double-submit cookie” classique Django:
  - Cookie non sensible `csrftoken` (lisible par JS), SameSite=Lax.
  - En-tête `X-CSRFToken` envoyé par le front et égal à la valeur du cookie.
  - En prod, le cookie est `Secure`; en dev, `Secure=False` pour HTTP local.

Statut (Sprint S2)
- Endpoint CSRF opérationnel: `GET /api/auth/csrf/` → 200 `{ ok: true, csrf: "<token>" }` + `Set-Cookie: csrftoken=...`.
- Dev:
  - `CSRF_COOKIE_HTTPONLY=False` (lisible par JS)
  - `CSRF_COOKIE_SAMESITE="Lax"`
  - `CSRF_COOKIE_SECURE=False`
- Prod (via settings de sécurité):
  - `CSRF_COOKIE_HTTPONLY=False` (toujours lisible par JS)
  - `CSRF_COOKIE_SAMESITE="Lax"` (au minimum)
  - `CSRF_COOKIE_SECURE=True` (HTTPS obligatoire)

Note: Ne jamais rendre le cookie CSRF HttpOnly, sinon le front ne peut pas l’émettre en en-tête (double-submit impossible).

---

## 1) API

### GET /api/auth/csrf/
- But: déposer/rafraîchir le cookie `csrftoken` et renvoyer la valeur.
- Réponse (200):
```json
{ "ok": true, "csrf": "Z9p0..." }
```
- Headers: `Set-Cookie: csrftoken=Z9p0...; Path=/; SameSite=Lax; Secure?; HttpOnly=false`

Commandes (dev):
```bash
# curl (affiche les headers et le corps)
curl -i https://api.dev.localhost/api/auth/csrf/

# HTTPie
http -v GET https://api.dev.localhost/api/auth/csrf/
```

---

## 2) Usage côté front

Principe
- Toutes les requêtes mutatives (POST/PUT/PATCH/DELETE) doivent inclure:
  - `credentials: 'include'` (pour que les cookies voyagent)
  - L’en-tête `X-CSRFToken` égal à la valeur du cookie `csrftoken`

Exemple (client-only)
```js
// Lecture du cookie csrftoken (client only)
function getCsrfFromCookie() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

async function postWithCsrf(url, body) {
  const csrf = getCsrfFromCookie()
  return fetch(url, {
    method: 'POST',
    credentials: 'include',     // cookies inclus (session/csrf)
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrf,
    },
    body: JSON.stringify(body),
  })
}
```

Nuxt (recommandé)
- Ajoutez un plugin `$fetch` qui:
  - Lit `csrftoken` côté client, et ajoute `X-CSRFToken` aux requêtes mutatives.
  - Passe `credentials: 'include'`.
  - Respecte `Retry-After` en cas de 429 (backoff).

Snippet (idée)
```ts
export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.$fetch = $fetch.create({
    credentials: 'include',
    onRequest({ options }) {
      const method = (options.method || 'GET').toUpperCase()
      const mutative = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)
      if (process.client && mutative) {
        const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
        const csrf = m ? decodeURIComponent(m[1]) : ''
        options.headers = { ...(options.headers || {}), 'X-CSRFToken': csrf }
      }
    },
    onResponse({ response }) {
      if (response.status === 429) {
        // lire Retry-After et appliquer backoff si besoin (UX)
      }
    }
  })
})
```

Note SSR
- Le cookie CSRF est lisible côté serveur (SSR) via les headers de la requête entrante, mais:
  - L’en-tête `X-CSRFToken` n’est requis que pour les requêtes sortantes mutatives côté client (navigateur). Conserver l’envoi côté client-only simplifie et évite d’exposer le token au SSR si inutile.

---

## 3) CORS / Origines / Cookies

- Cookies requis: assurez-vous que le front appelle l’API **sur le même site** (localhost/ *.dev.localhost) et avec `credentials: 'include'`.
- `CSRF_TRUSTED_ORIGINS`: liste explicite des origines autorisées:
  - Dev: `http://dev.localhost`, `https://dev.localhost`, `http://api.dev.localhost`, `https://api.dev.localhost`
- SameSite:
  - Lax permet de suivre la navigation intra-site; éviter `None` sauf cas cross-site spécifiques (avec `Secure`).
- Prod: HTTPS obligatoire (cookies `Secure`).

---

## 4) Débogage (403 & co)

Matriciel rapide:
- 403 CSRF cookie not set:
  - Appeler `GET /api/auth/csrf/` en premier.
  - Vérifier dans DevTools -> Application -> Cookies que `csrftoken` existe (domaine/Path=/, SameSite=Lax).
- 403 CSRF failed (token manquant/mismatch):
  - Vérifier que l’en-tête `X-CSRFToken` est envoyé et égal à la valeur du cookie.
  - Vérifier `credentials: 'include'`.
  - Vérifier l’origine (doit figurer dans `CSRF_TRUSTED_ORIGINS`).
- 401 Unauthorized:
  - Session absente/expirée; re-login.
- Rien ne marche en HTTPS local:
  - Certificat de dev non approuvé? Installer mkcert et redémarrer Caddy (SELON SPRINT TLS).
  - Vérifier que les hôtes https://*.dev.localhost sont utilisés côté front (runtimeConfig/public.apiBase).

Exemples (HTTPie/cURL):
```bash
# 1) Récupérer le cookie et le token
http --session=dojo GET https://api.dev.localhost/api/auth/csrf/

# 2) Requête POST mutative avec le header CSRF et cookies
http --session=dojo POST https://api.dev.localhost/api/auth/login/ \
  X-CSRFToken:"$(jq -r .csrf <(http --session=dojo --pretty=none GET https://api.dev.localhost/api/auth/csrf/ | tail -n1))" \
  Content-Type:application/json username=admin password=******

# cURL équivalent (cookie jar)
curl -c /tmp/jar -b /tmp/jar -sS https://api.dev.localhost/api/auth/csrf/ | jq -r .csrf >/tmp/csrf.txt
curl -c /tmp/jar -b /tmp/jar -sS -X POST https://api.dev.localhost/api/auth/login/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $(cat /tmp/csrf.txt)" \
  --data '{"username":"admin","password":"******"}' | jq .
```

---

## 5) Pièges connus

- CSRF cookie en HttpOnly: interdit (double-submit nécessite lecture côté JS).
- “Credentials: 'omit'” (ou défaut) sur fetch: empêche l’envoi/lecture des cookies → 403.
- Origines non listées: `CSRF_TRUSTED_ORIGINS` doit contenir les schémas `http://` et `https://` des hôtes dev/prod utilisés par le front.
- Proxies/ports différents: rester sur `.dev.localhost` pour front & API via Caddy.
- DevTools “device toolbar”: change l’UA; n’influe pas directement sur CSRF mais peut perturber d’autres heuristiques. Tester avec UA desktop réel si doute.

---

## 6) Bonnes pratiques

- Toujours appeler `GET /api/auth/csrf/` au boot (ou au moment du premier POST) pour garantir que le cookie existe.
- Centraliser l’ajout de `X-CSRFToken` dans un plugin `$fetch` (évite les oublis).
- Respecter `Retry-After` (429) avec un backoff exponentiel en UI.
- Journaliser `X-Request-ID` côté serveur et corréler les erreurs (utile en 403/429).
- En test E2E (Playwright): utiliser un helper qui appelle `/api/auth/csrf/` avant les POST, ou configurer le contexte à réutiliser la session/cookies.

---

## 7) Check-list (DoD S2)

- [ ] `GET /api/auth/csrf/` dépose le cookie et renvoie `{ ok:true, csrf }`.
- [ ] Front envoie `X-CSRFToken` + `credentials:'include'` pour POST/PUT/PATCH/DELETE.
- [ ] `CSRF_TRUSTED_ORIGINS` couvre les origines dev (`http(s)://dev.localhost`, `http(s)://api.dev.localhost`).
- [ ] Prod: `CSRF_COOKIE_SECURE=True` (HTTPS), `CSRF_COOKIE_SAMESITE="Lax"`.
- [ ] Doc (ce fichier) présent et à jour.

---

## 8) Troubleshooting rapide

1) 403 sur POST:
   - Vérifie `/api/auth/csrf/` → cookie présent.
   - Vérifie header `X-CSRFToken` (valeur exacte du cookie).
   - Vérifie `credentials:'include'`.
   - Vérifie `CSRF_TRUSTED_ORIGINS`.

2) Postman/HTTPie:
   - Utilise une “session” (jar cookies) ou passe `-b/-c` (curl) pour conserver `csrftoken`.

3) Edge cases:
   - Si front ≠ API (cross-site), évaluer `SameSite=None; Secure` et CORS strict (complexifie). Préférer proxy local unique en dev.

---

Références
- Django CSRF: https://docs.djangoproject.com/en/stable/ref/csrf/
- Nuxt 4 / Fetch: https://nitro.unjs.io/guide/introduction (pour les proxys serveur) / ofetch
- @nuxtjs/device (non lié à CSRF mais à SSR/CSR, traité en S1)
