## 03 — Threat Model (Sprint Auth 0)

Approche STRIDE allégée, centrée sur le flux **admin → conversation Dojo**.

### Spoofing (usurpation)
- **Risques**
  - Reuse d’identifiants admin sans MFA (login simpliste, pas de Turnstile).
  - Session fixation (cookie non régénéré après login, `SESSION_COOKIE_SECURE` désactivé en dev).
  - WebAuthn/nonce accessible sans authentification préalable.
- **Parades prévues**
  - Session login CSRF-protect + régénération session key (`auth.login` + `rotate_session`).
  - Cookies `__Host-pp_session` (Secure, HttpOnly, SameSite Lax).
  - Endpoint nonce REST nécessite session superuser + rate-limit 5/min.
  - Backlog S1 : TOTP/WebAuthn obligatoire, Turnstile conditionnel.

### Tampering (altération)
- **Risques**
  - Requêtes POST sans CSRF (`api_auth_creds`, gating).
  - Absence de `X-Request-Nonce` → risque relecture/mitm sur `ask`.
  - Conversation payload injouable (pas de validation stricte).
- **Parades prévues**
  - Double submit token (cookie + `X-CSRFToken`) requis pour toute mutation.
  - Nonces signés HMAC + stockage Redis (`SET NX`, TTL 60 s) + header `X-New-Request-Nonce` pour chaînage.
  - Validation DRF stricte (agent actif, status autorisé, contenu non vide) sur conversations/messages.
  - Logging `message_hash` déjà présent (SHA256) — conserver.

### Repudiation (non répudiation)
- **Risques**
  - AuditLog incomplet (login/logout/gate non corrélés).
  - Absence de tracing pour conversations (pas de Conversation ID).
- **Parades prévues**
  - Enrichir `AuditLog`: événements login/logout/gate/conversation (req.id, user, ip).
  - Conserver `X-Request-ID` sur toutes réponses, refuser s’il manque côté proxy (Caddy).
  - Option S0D : exporter logs JSON (filebeat / Loki).

### Information Disclosure
- **Risques**
  - `api_auth_creds` retourne `is_superuser` sans restriction.
  - Cookies realm exposés sans chiffrement (Strict).
  - Conversations non isolées (risque IDOR si M2M introduit).
  - CSRF token accessible JS (nécessaire) → s’assurer absence XSS.
- **Parades prévues**
  - Réponse `login` = données minimales (username, is_superuser).
  - Conversations scoping par owner (UUID, superuser only) + soft-delete (`status=archived`).
  - CSP enforcement futur (enforced vs report-only), revue composants Vue (# of inline).
  - Désactiver `DEBUG` + `ALLOWED_HOSTS` strict hors dev.

### Denial of Service
- **Risques**
  - Login/gate sans throttle suffisant (fails count local).
  - `RequestNonce.validate` dépend du cache → risque non partagé si multiple instances.
  - `ask_agent` throttle 5/min seulement, global.
- **Parades prévues**
  - Rate-limit DRF (anon/user scope) + tarpit `_tarpit_sleep` conservé.
  - Redis partagé (fallback cache) pour nonces + throttles scoped `conversations_create` 5/min et `messages_create` 30/min.
  - Ajouter `Retry-After` & backoff UI ; monitoring via Prometheus `record_auth_event`.

### Elevation of Privilege
- **Risques**
  - Login simple permet accès session admin si compte non superuser (contrôle tardif).
  - REST_FRAMEWORK JWT only → si access token volé, DRF complet accessible.
  - GatedSessionMiddleware check superuser mais login simpliste ne filtre pas.
- **Parades prévues**
  - `api/auth/login` vérifie `is_superuser`; renvoie `403` sinon (realm dojo).
  - Conversations API `IsAdminUser` ou rôle explicite (`scopes`).
  - Rotate/détruire tokens lors logout, blacklisting refresh (déjà en place).
  - Backlog : RBAC fine-grained (agents, actions).

### Résumé des actions critiques Sprint 0
1. Supprimer `csrf_exempt` sur login/gate/agents ; introduire pipeline CSRF complet.
2. Générer & valider `RequestNonce` via API officielle + headers chans.
3. Restaurer `SessionAuthentication` pour DRF (Dojo) + restreindre aux comptes admin.
4. Créer `Conversation`/`Message` pour tracer & auditer les actions.
5. Tests automatisés (Playwright + httpie) pour couvrir scénarios d’attaque (brute-force, CSRF, nonce replay).
6. Documenter backlog (MFA, RBAC, passkeys) dans roadmap.
