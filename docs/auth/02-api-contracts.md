## 02 — API Contracts (cibles Sprint Auth 0)

Notation : toutes les routes répondent JSON, erreur standard `{ ok: false, error: "<code>" }`.
Sécurité par défaut : session Django (`__Host-pp_session`) + cookie `csrftoken` (non HttpOnly).
Chaque requête mutative doit inclure `X-CSRFToken: <csrftoken>` **et** `credentials: include`.

### Auth / Session

#### `GET /api/auth/csrf/`
- **But** : déposer/rafraîchir `csrftoken`.
- **Réponse 200**
```json
{ "ok": true, "csrf": "Z9p0..." }
```
- **Headers** : `Set-Cookie: csrftoken=Z9p0...; Path=/; SameSite=Lax; Secure; HttpOnly=false`

#### `POST /api/auth/login/`
- **Headers** : `Content-Type: application/json`, `X-CSRFToken`, cookies `csrftoken`.
- **Body**
```json
{ "username": "admin", "password": "••••••••" }
```
- **Réponses**
  - `200 OK` (session active)
    ```json
    { "ok": true, "next": "/gate", "user": { "username": "admin", "is_superuser": true } }
    ```
    & `Set-Cookie: __Host-pp_session=...; HttpOnly; Secure; SameSite=Lax`
    & `Set-Cookie: __Host-pp_realm=A; HttpOnly; Secure; SameSite=Strict`.
  - `401` : `{"ok": false, "error": "invalid_credentials"}` (+ tarpit via header `Retry-After`).
  - `429` : `{"ok": false, "error": "rate_limited"}`.

#### `GET /api/auth/me/`
- **Auth** : session valide.
- **Réponse 200**
```json
{
  "ok": true,
  "user": {
    "username": "admin",
    "display_name": "Admin",
    "is_superuser": true,
    "scopes": ["dojo:converse"]
  },
  "gate": { "ok": false, "ts": null }
}
```

#### `POST /api/auth/logout/`
- **Headers** : `X-CSRFToken`.
- **Réponse 200**
```json
{ "ok": true }
```
- **Effets** : supprime `__Host-pp_session`, `__Host-pp_realm`, invalide session serveur.

#### `POST /api/auth/nonce/`
- **Auth** : session + superuser (Dojo).
- **Headers** : `X-CSRFToken`.
- **Réponse 200**
```json
{ "ok": true, "nonce": "ZXlKaGJHY2lPaUpJVXpJMU5pSXNJ...", "expires_in": 60 }
```
- **Headers réponse** : `X-New-Request-Nonce` (nonce de chaînage).
- **Notes** : chaque nonce est signé, TTL 60 s, usage unique (stocké en Redis). À fournir ensuite dans `X-Request-Nonce`.

### Gate Dojo

#### `POST /api/gates/absurdity-check`
- **Headers** : `X-CSRFToken`, `X-Request-Nonce` optionnel.
- **Body** : `{ "text": "2 + 2 = 5" }`
- **Réponses**
  - `200` : `{ "ok": true, "score": 1.0 }`
  - `200` (échec) : `{ "ok": false, "error": "no_absurd_match", "fails": 3 }`
  - `403` si session invalide, `429` si rate-limit.

#### `POST /api/gates/challenge-init`
- **Body** : `{ "agent": "Claire" }`
- **Réponse** : `{ "ok": true, "prompt": "Bonjour admin..." }`

#### `POST /api/gates/challenge-verify`
- **Body** : `{ "agent": "Claire", "response": "Bonjour Claire, moi c'est Admin et on se tutoie." }`
- **Réponse succès** : `{ "ok": true }` + session marquée `pp_gate_ok`.

### Agents & Conversations

#### `GET /api/agents/`
- **Auth** : session + superuser + `pp_gate_ok`.
- **Réponse 200** : tableau (pas d’enveloppe) d’agents actifs.
```json
[
  {
    "slug": "orchestrator",
    "title": "Orchestrator",
    "description": "Agent coordination SecOps.",
    "capabilities": { "tier": "mock" },
    "is_active": true
  }
]
```

#### `GET /api/conversations/`
- **Headers** : `Cookie` session (GET → pas de nonce requis).
- **Query** : `page` (optionnel, 20 éléments/page).
- **Réponse 200**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "c8f1e821-2bce-4ca0-8f36-5b7a71f8a91c",
      "title": "Audit release 12.4",
      "status": "open",
      "agent": "orchestrator",
      "agent_title": "Orchestrator",
      "agent_description": "Agent coordination SecOps.",
      "creator": "security_ops",
      "created_at": "2025-10-10T09:12:34Z",
      "updated_at": "2025-10-10T09:12:34Z"
    }
  ]
}
```

#### `POST /api/conversations/`
- **Headers** : `X-CSRFToken`, `X-Request-Nonce`.
- **Body**
```json
{ "agent": "orchestrator", "title": "Audit release 12.4" }
```
- **Réponse 201**
```json
{
  "id": "c8f1e821-2bce-4ca0-8f36-5b7a71f8a91c",
  "title": "Audit release 12.4",
  "status": "open",
  "agent": "orchestrator",
  "agent_title": "Orchestrator",
  "agent_description": "Agent coordination SecOps.",
  "creator": "security_ops",
  "created_at": "2025-10-10T09:12:34Z",
  "updated_at": "2025-10-10T09:12:34Z"
}
```
- **Headers réponse** : `X-New-Request-Nonce`.

#### `GET /api/conversations/{id}/`
- **Réponse 200** : même payload qu’en création (pas d’enveloppe).
- **404** si conversation inexistante ou non détenue par le superuser courant.

#### `PATCH /api/conversations/{id}/`
- **Headers** : `X-CSRFToken`, `X-Request-Nonce`.
- **Body** : `{ "title": "Nouveau titre" }` ou `{ "status": "closed" }`.
- **Réponse 200** : conversation mise à jour (champ `agent` immuable).
- **Headers réponse** : `X-New-Request-Nonce`.

#### `DELETE /api/conversations/{id}/`
- **Headers** : `X-CSRFToken`, `X-Request-Nonce`.
- **Effet** : soft-delete → `status = "archived"`.
- **Réponse 204** + header `X-New-Request-Nonce`.

#### `GET /api/messages/`
- **Headers** : session (GET).
- **Query obligatoire** : `conversation=<UUID>` ; `page` optionnel (50 messages/page, ordre chronologique).
- **Réponse 200**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "msg-1",
      "conversation": "c8f1e821-2bce-4ca0-8f36-5b7a71f8a91c",
      "conversation_id": "c8f1e821-2bce-4ca0-8f36-5b7a71f8a91c",
      "role": "user",
      "content": "Bonjour Orchestrator",
      "tokens": null,
      "created_at": "2025-10-10T09:13:00Z"
    }
  ]
}
```
- **400** si paramètre `conversation` absent.

#### `POST /api/messages/`
- **Headers** : `X-CSRFToken`, `X-Request-Nonce`.
- **Body**
```json
{ "conversation": "c8f1e821-2bce-4ca0-8f36-5b7a71f8a91c", "content": "Donne-moi le statut prod." }
```
- **Réponse 201**
```json
{
  "id": "msg-42",
  "conversation": "c8f1e821-2bce-4ca0-8f36-5b7a71f8a91c",
  "conversation_id": "c8f1e821-2bce-4ca0-8f36-5b7a71f8a91c",
  "role": "user",
  "content": "Donne-moi le statut prod.",
  "tokens": null,
  "created_at": "2025-10-10T09:13:58Z"
}
```
- **Headers réponse** : `X-New-Request-Nonce`.
- **Notes** : le champ `role` est forcé côté serveur sur `user`. `conversation_archived` renvoyé si la cible est archivée.

### Erreurs standardisées
| Code | Description | HTTP |
| --- | --- | --- |
| `invalid_credentials` | Identifiants incorrects | 401 |
| `csrf_failed` | Token manquant ou divergent | 403 |
| `gate_required` | Gate non franchi | 403 |
| `nonce_missing` / `nonce_expired` / `nonce_replay` | Problème de nonce | 400 |
| `rate_limited` | Seuils dépassés (inclure `Retry-After`) | 429 |
| `forbidden` | Permissions insuffisantes (non superuser) | 403 |
| `conversation_not_found` | UUID inexistant ou non autorisé | 404 |
| `conversation_archived` | Mutation non autorisée (status archivé) | 400 |

### Notes d’implémentation
- **Cookies** : utiliser préfixe `__Host-` pour session & realm (nécessite path `/`, secure, pas de domaine).
- **Headers additionnels** :
  - `X-Request-ID` (lire & répercuter).
  - `X-Retry-After-Ms` optionnel pour backoff UI.
  - `X-New-Request-Nonce` pour chaîner les appels conversation.
- **Versionnement** : prévoir prefix `/api/v1/` lorsque l’API quittera la phase alpha.
- **Tests** : HTTPie exemples alignés (voir `/docs/auth/01` & `/docs/auth/04`).
