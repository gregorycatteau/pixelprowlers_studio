# SECURITY BASELINES v1 — Baselines de Sécurité (Backbone minimal)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Couvre: CSRF, session binding, anti-replay, journaux hashés, RBAC d’exécution, widgets deny-by-default, transport et gouvernance.

Cette spécification définit les baselines minimales et obligatoires applicables aux 4 sprints (Backbone, Cockpit Template, Conference Rooms, Global Dashboard). Elle sert de référence pour les revues SecOps, les gates CI/CD et les tests e2e.

-----------------------------------------------------------------------

1) Objet & portée
- Normaliser et imposer un socle de contrôles de sécurité transverses à l’ensemble de la plateforme (frontend, backend, sockets, widgets).
- Protéger contre les attaques usuelles (CSRF, session fixation/vol, replay, altération de logs) et renforcer la traçabilité (correlation_id).
- S’intégrer avec EVENTS v1, RBAC v1, Widget Registry, Sockets Bridge et Dashboard.

Hors de portée (v1):
- Hardening OS/containers avancé, secrets manager externe, WAF de niveau L7 — référencés mais non détaillés ici.

-----------------------------------------------------------------------

2) Modèle de menace & objectifs
- Menaces:
  - CSRF sur endpoints state-changing.
  - Session hijacking/fixation, tokens réutilisés hors contexte.
  - Replay de requêtes ou d’événements valides en dehors d’une fenêtre autorisée.
  - Tampering/altération et suppression de journaux (indétectables).
  - Escalade de privilèges via widgets ou sockets (write/emit non autorisés).
  - Exfiltration de données via canaux front (CSP laxiste, postMessage non filtré).
- Objectifs:
  - Nier les actions non explicitement autorisées (deny-by-default).
  - Lier fermement l’identité et le contexte (session binding).
  - Rendre les journaux anti-altération (hash chain) et corrélables (correlation_id).
  - Contrôler et tracer tous les événements conformément à EVENTS v1.

-----------------------------------------------------------------------

3) Invariants de sécurité transverses
- correlation_id obligatoire:
  - Généré à l’initiation d’une action (ex: POST chat), propagé dans tous les événements, réponses et logs liés.
- Champs communs EVENTS v1:
  - type, ts (UTC RFC3339), actor, room?, thread_id, correlation_id, payload, sig?.
- Deny-by-default:
  - Toutes les actions write:* et emit:* sont interdites par défaut (notamment côté widgets).
- Journalisation structurée:
  - Logs avec champs: level, ts, server_ts, source, actor, ip(mask), ua(family), room?, thread_id, correlation_id, trace_id, span_id, event_type?, hash_prev, hash_curr.

-----------------------------------------------------------------------

4) Protection CSRF (endpoints HTTP state-changing)
- Cookies:
  - SameSite=strict (ou lax si besoin SSE), Secure, HttpOnly pour la session.
- Anti-CSRF:
  - Synchronizer token pattern: token CSRF signé stocké côté client (non HttpOnly) + header X-CSRF-Token exigé sur POST/PUT/PATCH/DELETE.
  - Double Submit Cookie optionnel si besoin de compatibilité; la valeur doit être liée à la session et tourner régulièrement.
- Origin/Referer checks:
  - Vérifier Origin ou Referer sur endpoints state-changing; refuser si mismatch (liste d’origines autorisées).
- CORS:
  - Désactiver les origins non attendues; preflight strict; pas de wildcard sur Authorization.

Gate CSRF:
- Aucun endpoint write ne passe sans token CSRF valide + origin autorisée + cookie SameSite correct.

-----------------------------------------------------------------------

5) Session binding (anti-hijacking/fixation)
- Liaison de session à des attributs stables:
  - Exemple: hachage des (user_id, user_agent partiel, device key, ip range tronquée).
  - Stocker la “session_fingerprint” côté serveur; refuser si écart significatif.
- Rotation:
  - Rotation de l’ID de session après login, élévation de privilèges, et régulièrement (ex: 24h).
- TTL:
  - Expiration absolue (ex: 7 jours) et glissante (ex: 30 min d’inactivité).
- Token-based (si JWT):
  - Short-lived (ex: 15 min) + refresh token côté serveur avec rotation et invalidation en cas de vol suspecté.

Gate session:
- Toute requête authentifiée doit correspondre à la session_fingerprint; mismatch → invalidation + system:alert.

-----------------------------------------------------------------------

6) Anti-replay & horodatage
- Fenêtre temporelle:
  - Window anti-replay = 60s; drift horloge client toléré ±500ms.
  - server_ts (UTC) = source de vérité pour logs/événements; messages hors fenêtre → rejet (log WARN+).
- Horloge monotone:
  - Toutes les mesures internes (latence, backoff, timeouts) se basent sur une horloge monotone indépendante de l’horloge système.
- Nonces:
  - Requêtes sensibles et signatures d’événements incluent un nonce unique (par acteur/correlation_id).
  - Store anti-replay: garder le couple (actor_id, nonce|sig, ts) pour la fenêtre; rejeter si déjà vu.
- Signature (sig? dans EVENTS v1):
  - Signature base64 d’un JSON canonique (ex: JCS). Les clés (rotation, stockage) sont gérées côté plateforme; vérifier l’intégrité si présent.
- Idempotence:
  - Opérations identifiées par (correlation_id, thread_id, index?) ne doivent pas produire d’effets multiples.

Gate anti-replay:
- Rejet de tout message hors fenêtre ou utilisant un nonce/sig déjà consommé sur la période.

-----------------------------------------------------------------------

7) Journalisation inviolable (logs hashés)
- Chaînage de hash:
  - Chaque log contient hash_prev (dernier hash confirmé) et hash_curr (hash(log_entry_contenu + hash_prev)).
  - hash_curr devient hash_prev du log suivant (par stream logique: service, partition ou catégorie).
- Algorithme:
  - SHA-256 (au minimum) sur un canonical form (JSON stable sans champs volatils).
- Champs minimaux:
  - ts, level, source, actor.id?, role?, ip, ua, route/resource, action, decision, correlation_id, event_type?, payload_summary, hash_prev, hash_curr.
- Stockage:
  - Append-only (ou immutabilité logique) avec snapshots périodiques des ancrages (ex: publier les hash d’ancre dans un registre séparé).
  - Rétention: 90 jours pour les journaux corrélés (purge/archivage documentés).
- Validation:
  - Outils d’audit permettant de rejouer la chaîne et détecter toute altération.
- Redaction & PII:
  - Masquage IP (IPv4 /24, IPv6 /48) ou hash salé; UA réduit (famille navigateur/OS, sans détails de build). Jamais de secrets en clair (API keys, tokens); détails d’erreurs redacted si sensibles.

Gate journaux:
- Aucune promotion si l’audit de chaîne (hash_prev/hash_curr) échoue ou si le correlation_id est absent pour des actions critiques.

-----------------------------------------------------------------------

8) Identité, RBAC d’exécution et décisions d’accès
- RBAC v1 obligatoire:
  - Évaluation: AuthN → Rôle → Capabilities → Ressource → Scope → Décision.
  - Toute décision consignée en AccessDecision (log structuré corrélé).
- Matrice initiale (rappel):
  - superuser: read/write/emit/manage:* (sous gates).
  - ops: read:logs, read:kpis, read:room_updates, join:room (lecture), quelques system_update restreints.
  - viewer: read:kpis, lecture limitée room (policy explicite).
  - agent: emit:chat_stream, emit:room_message (si autorisé), join:room (policy).
- Tests négatifs:
  - Les tentatives d’accès non autorisées produisent error:occurred ou system:alert selon criticité, toujours loggées.

Gate RBAC:
- Toute action write/emit/manage sans capability explicite → deny + log + (optionnel) system:alert.

-----------------------------------------------------------------------

9) Sécurité des Widgets & du WidgetHost (deny-by-default)
- Sandbox iframe:
  - Utiliser sandbox="allow-scripts allow-same-origin" (pas d’allow-forms/navigation).
- CSP du Host (minima):
  - default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'
- Registry contrôlé:
  - widget_registry.json valide (jsonschema/zod); capabilities explicites; scope des agents autorisés.
  - Aucun write:* ni manage:* en v1 sans RFC sécurité approuvée.
- postMessage:
  - Filtrage strict par origin autorisée (registry.origin) et schéma des messages (zod/jsonschema). Refuser type inconnu, origin non autorisée, capability absente; journaliser une alerte sécurité.
- SRI / Supply chain:
  - Subresource Integrity exigée en prod si bundle externe (entry_url+integrity).
- Observabilité:
  - widget:update (mount/unmount/state_changed) émis et loggé avec correlation_id; audit mount par acteur/agent/slug.

Gate widgets:
- Échec si une capability non déclarée est requise ou si origin ne matche pas; la console ne doit signaler aucune violation CSP en mode strict.

-----------------------------------------------------------------------

10) Sockets & temps réel (Rooms, Bridge)
- Auth:
  - Jeton court (ex: JWT ≤ 15 min) avec claims: sub, role, scopes, room_id?; revocation/rotation active.
- Scoping:
  - Namespaces/rooms distincts; contrôle room_id à chaque message; interdiction cross-room.
- Backpressure & rate limiting:
  - Quotas par acteur/room; mesures de débit; rejet gracieux avec system:alert en cas de flood.
- Anti-replay sockets:
  - Nonce/ts par message sensible; fenêtre courte; idempotence par (correlation_id, index).
- Transport:
  - TLS obligatoire; origin check pour WS; pas de wildcard sur CORS WS.

Gate sockets:
- Tests e2e doivent couvrir join/leave/message autorisés et refus des writes non autorisés; retries bornés + journalisation.

-----------------------------------------------------------------------

11) Données, secrets, transport
- Transport:
  - TLS 1.2+; HSTS (front public); pas de mixed content.
- Secrets:
  - Jamais en dépôt; variables d’environnement chiffrées au repos; rotation programmée; scanning pré-commit/CI.
- Données sensibles:
  - Minimisation; PII pseudonymisées; masquage dans logs; rétention bornée et documentée.

-----------------------------------------------------------------------

12) Validation des entrées, sérialisation & formats
- Entrées:
  - Validation stricte (zod/jsonschema) pour payloads API et EVENTS v1; schémas en CI.
- Sérialisation:
  - JSON UTF-8; canonicalisation pour signatures/log hashing; horodatages ISO 8601 (UTC).
- Erreurs:
  - error:occurred toujours sans secrets; details redacted; code/message standardisés.

-----------------------------------------------------------------------

13) Observabilité & alerting
- system:alert:
  - Produit aux seuils (latence p90, taux d’erreurs, anomalies sockets, violations sécurité); severity ∈ info|warn|error|critical.
- KPIs:
  - metrics:tick périodique (fenêtres définies) — sources fiables et validées.
- Dashboards:
  - Accès lecture-only (RBAC); logs d’accès KPIs corrélés.

-----------------------------------------------------------------------

14) Tests de sécurité & QA (gates CI/CD)
- e2e (Playwright) minimaux:
  - Sprint 00–01: POST chat (CSRF ok) → log corrélé hashé → chat:agent_stream conforme.
  - Sprint 01: Cockpit Template — widget factice mount (deny write), CSP strict OK.
  - Sprint 02: Rooms — join/leave/message autorisés; refus write non autorisé; backpressure/retry.
  - Sprint 03: Dashboard — 4 KPIs + alerte simulée; viewer lecture-only.
- Tests négatifs:
  - CSRF manquant, Origin invalide, session_fingerprint mismatch, nonce rejoué, ts hors fenêtre, capability absente.
- CI:
  - Validation schémas (events, registry); scanning secrets; audit de chaîne de logs sur un jeu de test.
- Oracles:
  - Absence d’erreurs de console liées à CSP/permissions en mode strict.
  - Présence de correlation_id sur chaque interaction critique.

-----------------------------------------------------------------------

15) Gouvernance, versionnage & rollback
- Changements:
  - Toute modification des baselines documentée ici avec justification et impacts.
- Compatibilité:
  - Évolutions additionnelles (renforcer des contrôles) = compatibles; assouplissements = exigent RFC + approbation SecOps + nouvelle version.
- Rollback:
  - Revert Git vers v-1 de la spec; restaurer configs; relancer e2e pivots avant promotion.
- Append-only pour l’historique:
  - Conserver toutes les entrées d’Append Log; ne pas réécrire l’historique.

-----------------------------------------------------------------------

Références croisées
- docs/specs/EVENTS_v1.md — champs communs, signature (sig?), exemples, validations.
- docs/specs/RBAC_v1.md — rôles, capabilities, matrice d’accès, AccessDecision.
- docs/specs/WIDGET_REGISTRY.md — registre + capabilities, SRI, origins, deny-by-default.
- docs/specs/COCKPIT_TEMPLATE_v1.md — WidgetHost API, lifecycle, CSP côté front.
- docs/specs/SOCKETS_BRIDGE_v1.md — events sockets, scoping, backpressure, retry.
- docs/specs/DASHBOARD_v1.md — KPIs, seuils, system:alert, RBAC lecture-only.
- docs/checklists/QA_E2E.md — scénarios e2e, données, oracles, critères d’acceptation.
- docs/specs/GOVERNANCE_v1.md — processus d’évolution, versionnage semver, Governance Ledger.

-----------------------------------------------------------------------

Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale des baselines (CSRF, session binding, anti-replay, journaux hashés, gates CI/CD, références croisées).
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — rétention 90 jours, PII (IP tronquées/UA réduits), server_ts source de vérité, window 60s & drift ±500ms, CSP exemple + sandbox iframe, logs incluant correlation_id/trace_id/span_id.
- 2025-10-13 — Alice (Lead Orchestrator): Patch v1b — Clarification horloge monotone (pour mesures internes) vs server_ts (source de vérité logs/événements); rappel drift ±500 ms et fenêtre anti-replay 60 s; ajout lien vers GOVERNANCE_v1.md.
