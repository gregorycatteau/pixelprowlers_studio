# SOCKETS_BRIDGE v1 — Spécification (Bridge temps réel Rooms)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Références croisées:
- docs/specs/EVENTS_v1.md (champs communs, corrélation, signature)
- docs/specs/RBAC_v1.md (rôles, capabilities, deny-by-default)
- docs/specs/ROOMS_v1.md (modèles, tour de parole, règles)
- docs/specs/SECURITY_BASELINES.md (CSRF, session binding, anti-replay, logs hashés)
- docs/checklists/QA_E2E.md (scénarios multi-participants, négatifs)
- docs/specs/GOVERNANCE_v1.md (processus d’évolution, semver, ledger)

Statut: v1 (contrats figés pour Sprint 02)

-----------------------------------------------------------------------

1) Objet & portée

- Définir le bridge sockets v1 pour la fonctionnalité “Conference Rooms”.
- Standardiser:
  - Topologie (namespaces/rooms), scoping et isolation par room.
  - AuthN/AuthZ (RBAC v1), capabilities, et principes deny-by-default.
  - Contrat d’événements sockets et contrôles (anti-replay, signature optionnelle).
  - Stratégies de backpressure, retry/reconnexion, idempotence.
  - Journalisation corrélée (correlation_id) et exigences d’observabilité.
- Hors de portée:
  - Widgets métiers en room (non couverts par v1).
  - Médias temps réel (audio/vidéo); seuls messages textuels/metadata.

-----------------------------------------------------------------------

2) Topologie & Transport

- Transport: WebSocket (WS) sur TLS (wss://), origin-check strict (voir Sécurité).
- Namespace recommandé: /ws/rooms (exemple)
- Scoping par room:
  - Chaque client s’abonne explicitement à 1..N rooms.
  - Toute émission DOIT inclure un room_id scoping; cross-room interdit.
- Contrat de frame:
  - Les événements applicatifs (join_room, leave_room, agent_message, system_update) sont envoyés en JSON, enveloppe conforme aux champs communs EVENTS (type, ts, actor, room, thread_id, correlation_id, payload, sig?).
  - Pour validation, un schéma “socket_event.v1.json” est utilisé (cf. section 6), compatible avec les champs communs d’EVENTS v1.
  - Les messages de contrôle (auth/sub/ack/ping) utilisent une enveloppe minimale spécifique “bridge_ctrl.v1.json”.

-----------------------------------------------------------------------

3) AuthN/AuthZ & RBAC (deny-by-default)

- AuthN:
  - WS Upgrade: Authorization: Bearer <token_court> (préféré).
  - Fallback (si requis): message de contrôle “bridge:auth” en tout début de session.
  - Token court (5–10 min), kid obligatoire; JWKS interne (Key Rotation):
    - Publication d’une clé active (active_kid) et d’une clé suivante (next_kid) avec grace period.
    - Validation côté client sur kid; en cas de kid inconnu, rejet + refresh proactif du token, puis reconnexion propre.
    - En cas de bascule de clé, le serveur peut émettre `system_update(kind="force_disconnect", reason="key_rotation")` pour forcer une fermeture propre et la purge de l’état sensible.
  - Claims minimaux: sub (acteur), role (superuser|ops|viewer|agent), scopes (join:room|emit:room_message|read:room_updates…), iat/exp, kid.
- AuthZ (RBAC v1):
  - join_room (emit): nécessite capability join:room (selon policy room).
  - agent_message (emit): nécessite capability emit:room_message et respect du tour de parole/policy speak.
  - system_update (emit): réservé system/superuser/owner (selon policy).
  - read:room_updates (read): pour lecture d’événements room.
  - Deny-by-default: toute action non autorisée est refusée et logguée.
- Scope:
  - L’émetteur ne peut agir que dans les rooms auxquelles il est abonné et autorisé.
  - Les claims peuvent inclure un room_id autorisé; sinon fournir la preuve au join (invitation/owner_approved).

-----------------------------------------------------------------------

4) Opérations du Bridge (contrats)

4.1 Messages de contrôle (enveloppe “bridge_ctrl.v1.json”)
- Envelope:
  {
    "kind": "bridge:auth|bridge:subscribe|bridge:subscribed|bridge:error|bridge:ping|bridge:pong",
    "ts": "ISO-8601-UTC",
    "payload": { /* spécifique au kind */ },
    "correlation_id?": "uuid-v4"
  }

- bridge:auth (fallback)
  - payload: { "token": "jwt" }
  - réponse attendue: bridge:subscribed (si auth réussie et room join automatique) ou ack distinct après subscribe.
- bridge:subscribe
  - payload: { "room_id": "string" }
  - réponse: bridge:subscribed { room_id } OU bridge:error (code, message).
- bridge:subscribed
  - payload: { "room_id": "string" }
- bridge:error
  - payload: { "code": "string", "message": "string", "context?": {} }
- bridge:ping / bridge:pong
  - payload: { "seq": number }

4.2 Événements applicatifs (enveloppe EVENTS-like)
- Types v1: join_room, leave_room, agent_message, system_update
- Champs communs obligatoires:
  - type, ts (UTC), actor { id, kind, role? }, room (== payload.room_id), thread_id?, correlation_id (uuid-v4), payload, sig?
- Payloads:
  - join_room.payload
    { "room_id": "string", "participant": { /* RoomParticipant subset */ }, "reason?": "string" }
  - leave_room.payload
    { "room_id": "string", "participant": { "id": "string" }, "reason?": "string" }
  - agent_message.payload
    {
      "room_id": "string",
      "from": { "id": "string", "kind": "user|agent|system" },
      "thread_id?": "string",
      "content": "string",
      "content_type": "text/plain|text/markdown",
      "attachments?": [ { "id":"string","name":"string","mime":"type/subtype","size":0 } ],
      "idempotency_key": "string",
      "index?": 0
    }
  - system_update.payload
    {
      "room_id": "string",
      "kind": "participant_joined|participant_left|speaking_turn_changed|room_closed|policy_changed|force_disconnect",
      "details": { "reason?": "role_downgrade|key_rotation|policy_violation", "...": "..." }
    }

-----------------------------------------------------------------------

5) Sécurité (menaces, contrôles, gates)

- Menaces:
  - Usurpation d’identité (token volé/expiré), cross-room injection, flood, replay, exfiltration via origin non autorisée.
- Contrôles clés:
  - TLS (wss://), HSTS; CORS/WS origin allowlist stricte; pas de wildcard.
  - AuthN sur Upgrade (Bearer) et reauth périodique si sessions longues (token rotation).
  - RBAC v1 strict: join:room, emit:room_message, read:room_updates. Toute action non permise → deny + log + optionnel system:alert.
  - Anti-replay: fenêtre temporelle ±5 min; nonce implicite via ts/sig; store anti-replay sur (sub, sig|hash, ts).
  - Signature optionnelle (sig) sur JSON canonique; clés gérées plateforme (rotation).
  - Scoping: room dans frame et payload; validation server-side; mismatch → deny.
  - Backpressure/quotas: limites par acteur/room; rejet gracieux; alerting en overflow.
- Journaux inviolables (logs hashés):
  - Toutes décisions d’accès et événements sont loggés: ts, actor, room, action, decision, correlation_id, hash_prev/hash_curr.
- Gates de promotion:
  - Tests négatifs: token invalide/expiré, origin non autorisée, cross-room, replay → refus + logs.
  - Aucune promotion si des violations CSP/origin sont détectées en environnement de test.
  - e2e pivot “2 agents + 1 humain” vert (cf. QA_E2E.md).

-----------------------------------------------------------------------

6) Schémas JSON (type-safe)

6.1 Socket Event Envelope (socket_event.v1.json)
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pixelprowlers.local/schemas/socket_event.v1.json",
  "title": "Socket Event v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["type","ts","actor","room","correlation_id","payload"],
  "properties": {
    "type": { "type": "string", "enum": ["join_room","leave_room","agent_message","system_update"] },
    "ts": { "type": "string", "format": "date-time" },
    "actor": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id","kind"],
      "properties": {
        "id": { "type": "string" },
        "kind": { "type": "string", "enum": ["user","agent","system"] },
        "role": { "type": "string", "enum": ["superuser","ops","viewer","agent"] },
        "display_name": { "type": "string" }
      }
    },
    "room": { "type": "string", "pattern": "^[a-zA-Z0-9:_\\-]{3,64}$" },
    "thread_id": { "type": "string" },
    "correlation_id": {
      "type": "string",
      "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    },
    "payload": { "type": "object" },
    "sig": { "type": "string", "contentEncoding": "base64" }
  },
  "allOf": [
    { "if": { "properties": { "type": { "const": "join_room" } } }, "then": { "$ref": "#/$defs/payload_join_room" } },
    { "if": { "properties": { "type": { "const": "leave_room" } } }, "then": { "$ref": "#/$defs/payload_leave_room" } },
    { "if": { "properties": { "type": { "const": "agent_message" } } }, "then": { "$ref": "#/$defs/payload_agent_message" } },
    { "if": { "properties": { "type": { "const": "system_update" } } }, "then": { "$ref": "#/$defs/payload_system_update" } }
  ],
  "$defs": {
    "attachment": {
      "type": "object",
      "required": ["id","name","mime","size"],
      "properties": {
        "id": { "type": "string" },
        "name": { "type": "string" },
        "mime": { "type": "string", "pattern": "^[^/]+/[^/]+$" },
        "size": { "type": "integer", "minimum": 0 }
      },
      "additionalProperties": false
    },
    "payload_join_room": {
      "properties": {
        "payload": {
          "type": "object",
          "required": ["room_id","participant"],
          "additionalProperties": false,
          "properties": {
            "room_id": { "type": "string" },
            "participant": {
              "type": "object",
              "required": ["id","actor","joined_at","status","role_in_room","capabilities"],
              "properties": {
                "id": { "type": "string" },
                "actor": {
                  "type": "object",
                  "required": ["id","kind"],
                  "properties": {
                    "id": { "type": "string" },
                    "kind": { "type": "string", "enum": ["user","agent","system"] },
                    "role": { "type": "string", "enum": ["superuser","ops","viewer","agent"] }
                  },
                  "additionalProperties": false
                },
                "joined_at": { "type": "string", "format": "date-time" },
                "status": { "type": "string", "enum": ["active","left","kicked"] },
                "role_in_room": { "type": "string", "enum": ["owner","speaker","listener"] },
                "capabilities": { "type": "array", "items": { "type": "string" }, "maxItems": 50 }
              },
              "additionalProperties": false
            },
            "reason": { "type": "string" }
          }
        }
      }
    },
    "payload_leave_room": {
      "properties": {
        "payload": {
          "type": "object",
          "required": ["room_id","participant"],
          "additionalProperties": false,
          "properties": {
            "room_id": { "type": "string" },
            "participant": { "type": "object", "required": ["id"], "properties": { "id": { "type": "string" } }, "additionalProperties": false },
            "reason": { "type": "string" }
          }
        }
      }
    },
    "payload_agent_message": {
      "properties": {
        "payload": {
          "type": "object",
          "required": ["room_id","from","content","content_type"],
          "additionalProperties": false,
          "properties": {
            "room_id": { "type": "string" },
            "from": {
              "type": "object",
              "required": ["id","kind"],
              "properties": {
                "id": { "type": "string" },
                "kind": { "type": "string", "enum": ["user","agent","system"] }
              },
              "additionalProperties": false
            },
            "thread_id": { "type": "string" },
            "content": { "type": "string" },
            "content_type": { "type": "string", "enum": ["text/plain","text/markdown"] },
            "attachments": { "type": "array", "items": { "$ref": "#/$defs/attachment" }, "maxItems": 10 },
            "idempotency_key": { "type": "string", "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-7[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$" },
            "index": { "type": "integer", "minimum": 0 }
          }
        }
      }
    },
    "payload_system_update": {
      "properties": {
        "payload": {
          "type": "object",
          "required": ["room_id","kind","details"],
          "additionalProperties": false,
          "properties": {
            "room_id": { "type": "string" },
            "kind": {
              "type": "string",
              "enum": ["participant_joined","participant_left","speaking_turn_changed","room_closed","policy_changed","force_disconnect"]
            },
            "details": { "type": "object" }
          }
        }
      }
    }
  }
}

6.2 Bridge Control Envelope (bridge_ctrl.v1.json)
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pixelprowlers.local/schemas/bridge_ctrl.v1.json",
  "title": "Bridge Control v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["kind","ts","payload"],
  "properties": {
    "kind": { "type": "string", "enum": ["bridge:auth","bridge:subscribe","bridge:subscribed","bridge:error","bridge:ping","bridge:pong"] },
    "ts": { "type": "string", "format": "date-time" },
    "payload": { "type": "object" },
    "correlation_id": { "type": "string", "pattern": "^[0-9a-fA-F-]{36}$" }
  }
}

-----------------------------------------------------------------------

7) Exemples canoniques

7.1 Contrôle — Subscribe
Client→Server:
{
  "kind": "bridge:subscribe",
  "ts": "2025-10-13T06:45:00.000Z",
  "payload": { "room_id": "room-abc123" },
  "correlation_id": "b1a5a4aa-58b0-4f7f-9a8c-4a2a9b2f0f0e"
}
Server→Client:
{
  "kind": "bridge:subscribed",
  "ts": "2025-10-13T06:45:00.050Z",
  "payload": { "room_id": "room-abc123" },
  "correlation_id": "b1a5a4aa-58b0-4f7f-9a8c-4a2a9b2f0f0e"
}

7.2 join_room
{
  "type": "join_room",
  "ts": "2025-10-13T06:45:01.000Z",
  "actor": { "id": "user_su_001", "kind": "user", "role": "superuser" },
  "room": "room-abc123",
  "thread_id": "th_room_abc123",
  "correlation_id": "a9a8f4e8-3d37-4b1e-a38e-6d2f8ae0d1b7",
  "payload": {
    "room_id": "room-abc123",
    "participant": {
      "id": "user_su_001",
      "actor": { "id": "user_su_001", "kind": "user", "role": "superuser" },
      "joined_at": "2025-10-13T06:45:01.000Z",
      "status": "active",
      "role_in_room": "owner",
      "capabilities": ["join:room","read:room_updates","emit:room_message"]
    }
  }
}

7.3 agent_message
{
  "type": "agent_message",
  "ts": "2025-10-13T06:45:15.300Z",
  "actor": { "id": "user_su_001", "kind": "user", "role": "superuser" },
  "room": "room-abc123",
  "thread_id": "th_room_abc123",
  "correlation_id": "eadc64f0-6f7d-4e1a-8c82-8b3e2a7f9d93",
  "payload": {
    "room_id": "room-abc123",
    "from": { "id": "user_su_001", "kind": "user" },
    "content": "Bonjour, agents. Résumez l'incident #245.",
    "content_type": "text/plain",
    "attachments": []
  }
}

7.4 system_update (speaking_turn_changed)
{
  "type": "system_update",
  "ts": "2025-10-13T06:45:15.450Z",
  "actor": { "id": "room_control", "kind": "system" },
  "room": "room-abc123",
  "thread_id": "th_room_abc123",
  "correlation_id": "eadc64f0-6f7d-4e1a-8c82-8b3e2a7f9d93",
  "payload": {
    "room_id": "room-abc123",
    "kind": "speaking_turn_changed",
    "details": { "from": "agent_talia", "to": "agent_bruce", "reason": "round_robin_next" }
  }
}

7.5 leave_room
{
  "type": "leave_room",
  "ts": "2025-10-13T07:05:00.000Z",
  "actor": { "id": "agent_talia", "kind": "agent", "role": "agent" },
  "room": "room-abc123",
  "thread_id": "th_room_abc123",
  "correlation_id": "b0b86a26-6d7c-42c1-9b9e-3f2f3e73f2a1",
  "payload": {
    "room_id": "room-abc123",
    "participant": { "id": "agent_talia" },
    "reason": "voluntary"
  }
}

7.6 system_update (force_disconnect — key_rotation)
{
  "type": "system_update",
  "ts": "2025-10-13T07:06:00.000Z",
  "actor": { "id": "room_control", "kind": "system" },
  "room": "room-abc123",
  "thread_id": "th_room_abc123",
  "correlation_id": "c7b2c4d8-9a6e-4f31-b2d1-7e9f0a1b2c3d",
  "payload": {
    "room_id": "room-abc123",
    "kind": "force_disconnect",
    "details": { "reason": "key_rotation" }
  }
}

-----------------------------------------------------------------------

8) Backpressure, Idempotence & Retry

- Backpressure (serveur):
  - Quotas par acteur: messages_per_sec (par défaut 5), burst limité.
  - Quotas par room: messages_per_room_per_sec (par défaut 50).
  - Buffers bornés par acteur (ex: 100). En overflow: drop le plus ancien non-ack + bridge:error + system:alert warn.
  - Mesures: latence de diffusion, drops, retry_count, messages/min par room et par acteur.
- Idempotence:
  - Utiliser idempotency_key sur agent_message pour dédoublonnage sur une fenêtre de 60s; pour messages segmentés, combiner (idempotency_key, index).
- Retry (client):
  - Reconnexion: backoff exponentiel: base 500 ms, factor 1.6, jitter 30%, plafond 8 s; max 8 essais, puis pause manuelle.
  - Re-subscribe automatique aux rooms après reconnexion réussie; invalider si token expiré → exige reauth.
  - Resume: si support d’offset local, demander retransmission basique (optionnel v1) en fournissant last_correlation_id connu.
- Heartbeat:
  - bridge:ping/bridge:pong (trame keepalive) toutes 20–30s; timeout → reconnect.

-----------------------------------------------------------------------

9) Contrôles & validations

- Validation schéma:
  - bridge_ctrl.v1.json pour messages de contrôle.
  - socket_event.v1.json pour événements applicatifs; champs communs et payloads spécifiques conformes.
- Règles métier:
  - room == payload.room_id.
  - agent_message: requiert capability emit:room_message + respect de policy speak (owner_led ou round_robin).
  - join_room: requiert capability join:room et policy.join (open|invite|owner_approved).
  - system_update: seuls acteurs autorisés (system/superuser/owner).
- Sécurité:
  - Anti-replay: ts dans la fenêtre; rejeter signatures/nonce déjà vus.
  - Origin: vérifier l’origin WS; refuser origins non listées.
  - RBAC: decisions journalisées (AccessDecision) avec correlation_id; deny-by-default.
- Observabilité:
  - Logs hashés avec hash_prev/hash_curr; champs: ts, actor, room, action, decision, correlation_id, latency_ms, status.

-----------------------------------------------------------------------

10) Compatibilité & versionnage

- v1 (couverte par ce document):
  - Ajouts compatibles: nouveaux kinds de system_update; champs optionnels supplémentaires non destructeurs.
  - Ruptures: changement sémantique des champs obligatoires, retrait de types/kinds → exiger v2 et plan de migration/rollback.
- Rollback:
  - Revert Git vers version précédente de la spec; restaurer exemples canoniques; relancer e2e pivot “2 agents + 1 humain”.

-----------------------------------------------------------------------

11) Tests & QA (exigences minimales)

- e2e (pivot Sprint 02):
  - 2 agents simulés + 1 humain → join_room → agent_message → diffusion contextualisée; tour de parole mis à jour; logs corrélés et hashés.
- Tests négatifs:
  - token expiré/invalide, origin non autorisée, join sans capability/policy, cross-room, replay, flood (quotas).
- Intégration:
  - Validation schémas (bridge_ctrl & socket_event).
  - Mesure de latence message→diffusion; vérification retry/backoff contrôlé.
- Oracles:
  - Aucune perte au-delà du configurable; presence correlation_id sur tout le flux; RBAC effectif; system:alert sur anomalies.

-----------------------------------------------------------------------

12) Matrice de capacités (résumé v1)

- join_room → requires: join:room
- leave_room → requires: session active; leave self
- agent_message → requires: emit:room_message (+ scope room + policy speak)
- system_update → requires: emit:system_update (réservé system/superuser/owner)
- read flux → requires: read:room_updates (lecture)

Référence complète: docs/specs/RBAC_v1.md

-----------------------------------------------------------------------

Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale SOCKETS_BRIDGE v1 (événements, scoping & sécurité, schémas JSON, backpressure/retry, contrôles & QA, références croisées).
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — JWT TTL 5–10 min (kid obligatoire, JWKS interne/rotation), system_update force_disconnect (éjection/downgrade), idempotency_key sur agent_message (fenêtre 60s), backoff par défaut (base 500 ms, facteur 1.6, jitter 30%, max 8 s).
- 2025-10-13 — Alice (Lead Orchestrator): Patch v1b — Key Rotation (JWKS interne) avec clé active + suivante (grace period), validation client sur kid et refresh proactif; `system_update(kind="force_disconnect")` avec raisons `role_downgrade|key_rotation|policy_violation`; `idempotency_key` au format UUIDv7 exigée; exemple ajouté.
