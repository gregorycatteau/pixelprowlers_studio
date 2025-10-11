## 04 — UX Flows (Sprint Auth 0)

### Flow A — Connexion admin (desktop + mobile)
1. **Landing `/login`**
   - Affiche formulaire (identifiant, mot de passe).
   - Appel `useAuth().bootstrap()` → `GET /api/auth/csrf/` (spinner court).
   - Si utilisateur déjà authentifié via `me`, redirect `next` (/gate ou /console).
2. **Soumission**
   - Bouton désactivé pendant la requête.
   - `useAuth().login()` → `POST /api/auth/login/` (credentials include, `X-CSRFToken`).
   - Succès : store renseigne `user`, `PxToast` “Session ouverte”, navigation `/gate`.
   - Échec : message générique “Identifiants invalides” + backoff (afficher `Retry-After`, timer).
   - `429` : affichage toast warning + disable bouton pendant `retryAfter`.
3. **Accessibilité**
   - Focus automatique sur champ identifiant.
   - Aria-live pour message d’erreur.
   - Mode sombre contrasté (déjà en place).

### Flow B — Gate (absurdité + rituel)
1. **Pré-check**
   - `onMounted` appelle `useAuth().ensureAuthenticated()` + `GET /api/auth/me/`.
   - Si `gate.ok === true`, skip direct `/ask-agents`.
   - Récupération nonce `POST /api/auth/nonce/` → stocker via composable `useNonce()`.
2. **Étape absurdité**
   - Champ textarea → validation local (non vide).
   - `POST /api/gates/absurdity-check` avec headers `X-CSRFToken`, `X-Request-Nonce`.
   - Réponse `ok:false` → message neutre (“Commande non reconnue”), afficher compteur `fails`.
   - `rate_limited` → bouton disabled 60 s, afficher timer.
3. **Étape rituel**
   - Après succès, auto-fetch `challenge-init` (affiche prompt).
   - Input text, CTA retour (←).
   - `POST /api/gates/challenge-verify` (headers idem).
   - Succès → toast “Gate validé” + set state `gate.ok=true` + navigate `/ask-agents`.
   - Échec → message neutre, `fails` => CTA “Recommencer” si >3.
4. **Défaillances**
   - `403` (session expirée) → redirection `/login` + toast “Session expirée”.
   - `nonce_*` → regénérer nonce, informer utilisateur (“Veuillez réessayer”).
   - `X-New-Request-Nonce` header → rafraîchir store.

### Flow C — Console / Conversation
1. **Entrée `/ask-agents`**
   - `AppShell` + `PxHeader` (logout).
   - `useAuth().fetchMe(true)` ; si `gate.ok` absent → redirect `/gate`.
   - `useNonce().refresh()` déclenché au mount.
2. **Liste agents**
   - `GET /api/agents/` (proxy SSR) → liste (slug, title, description, capabilities).
   - Sélection met à jour carte détail ; CTA “Ouvrir une conversation” activé si agent choisi.
3. **Création conversation**
   - CTA → `await ensureNonce()` + `POST /api/conversations/` (`X-CSRFToken`, `X-Request-Nonce`).
   - Succès 201 → toast “Conversation créée” + `navigateTo('/conversations/{id}')`.
   - Plugin `$fetch` absorbe `X-New-Request-Nonce` pour chaînage automatique.
4. **Page `/conversations/[id]`**
   - `useAuth().fetchMe` + `ensureNonce()` puis fetch conversation (`GET /api/conversations/{id}/`).
   - Chargement messages via `GET /api/messages/?conversation=<id>` (pagination 50 items).
   - Bouton “Charger plus” si `next` présent (appends).
5. **Envoi message**
   - Formulaire textarea + CTA `PxButton`.
   - `requestWithNonce()` → `POST /api/messages/`.
   - Réponse 201 → tri ascendant + toast succès.
   - Gestion erreurs : `conversation_archived` → toast warning + refresh conversation ; `nonce_*` → auto-refresh puis retry unique.
6. **Logout**
   - Depuis header (`useAuth().logout()`). Succès → reset stores + `/login`.

### Flow D — États d’erreur & dégradations
- **Session expirée** : 401 → intercepté par `onResponseError`, purge store, toast “Session expirée, reconnectez-vous”.
- **CSRF mismatch** : 403 `csrf_failed` → auto-refresh token (`GET /api/auth/csrf/`), retenter une fois, sinon message support.
- **Rate-limit** : afficher badge `⏳ Réessayer dans Xs`, désactiver inputs.
- **Backend KO** : message neutre “Service indisponible” + lien support, log console `console.warn`.

### Composants & Patterns
- `useAuth()` : expose `user`, `isAuthenticated`, `login`, `logout`, `fetchMe`, `ensureAuthenticated`.
- `useCsrf()` : lazily fetch, met à jour cookie, fournit helper `withCsrf(fetchFn)`.
- `useNonce()` : `current`, `refresh()`, `cycle(responseHeaders)`.
- `PxToast` : success/info/warning/danger pour feedback instantané.
- `PxModal` : confirmations (ex. purge historique).
- `PxButton` : états `loading`, `disabled`, `danger`.
- `PxTable` : futurs logs conversations.
- Accessibilité : aria-live pour toasts, `sr-only` labels, focus visible.

### Playwright (extraits cibles)
- `auth-login.spec.ts`
  - Fill identifiant/mdp → `expect(page).toHaveURL('/gate')`.
  - Simuler mauvais mdp (3x) → message neutre + pas d’indication sur credential.
- `dojo-conversation.spec.ts`
  - Démarrer de zéro → login → gate → `GET /api/agents` intercept (200).
  - Créer conversation + envoyer 1 message → vérifier affichage output.
  - Logout → retour `/login`, visite `/ask-agents` renvoie `/login`.
