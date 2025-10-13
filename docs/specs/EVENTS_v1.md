# EVENTS v1 — Protocole d’événements (Backbone minimal)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Références croisées: docs/specs/GOVERNANCE_v1.md

Normatif (v1)
- Encodage: UTF-8
- Temps: UTC ISO-8601 (YYYY-MM-DDTHH:MM:SS.sssZ)
- Identifiants:
  - correlation_id: UUIDv7 (time-sortable)
  - trace_id: UUIDv7 (time-sortable)
  - span_id: UUIDv4
- Version de contrat: events_version (semver, ex: "1.0.0")

Cette spécification décrit le contrat d’événements v1: formats, champs communs, schémas de validation, exemples, contrôles de sécurité, compatibilité/versionnage et exigences de traçabilité.

Événements obligatoires v1:
- chat:user_message
- chat:agent_stream
- widget:update
- system:alert
- metrics:tick
- error:occurred

Champs communs requis:
- type (string)
- events_version (semver, ex: "1.0.0")
- ts (client) (string, ISO 8601 / RFC 3339, UTC)
- server_ts (serveur, source de vérité) (string, ISO 8601 / RFC 3339, UTC)
- actor (object)
- room? (string)
- thread_id (string)
- correlation_id (string, UUIDv7)
- trace_id (string, UUIDv7)
- span_id (string, UUIDv4)
- payload (object, dépend du type)
- sig? (string, signature Base64 du message canonique)

---

## 1) Objet & portée

- Normaliser tous les événements circulant entre front, backend, bridges sockets et journaux.
- Offrir des schémas validables (jsonschema/zod) pour prévenir les régressions.
- Garantir la corrélation bout-en-bout via `correlation_id` (user action → logs → events → UI).
- Définir les invariants de sécurité: intégrité, anti-replay, contrôle d’accès (RBAC) et minimisation des données.

Hors de portée (v1):
- Événements métiers spécifiques aux widgets (autres que `widget:update`).
- Traces distribuées complexes; la corrélation repose sur `correlation_id`.

---

## 2) Champs communs

- type: nom de l’événement. Format recommandé: namespace:kind (ex: chat:agent_stream).
- ts: horodatage ISO 8601 strict en UTC, ex: 2025-10-13T06:29:40.327Z.
- actor:
  - id: string (ID stable de l’acteur)
  - kind: enum [user, agent, system, widget]
  - role?: enum [superuser, ops, viewer, agent] (si applicable)
  - display_name?: string (non sensible, optionnel)
- room?: string (ex: room-abc123). Obligatoire lorsque l’événement est scoping “room”.
- thread_id: string. Identifiant de fil/échange (ex: chat thread).
- correlation_id: string (UUID v4). Identique pour une action et tous ses événements dérivés.
- payload: object. Contrat spécifique par type d’événement (voir ci-dessous).
- sig?: string (Base64). Signature du JSON canonique de l’événement pour anti-tamper/anti-replay.

Contraintes supplémentaires:
- Fenêtre anti-replay: 60s (rejet des messages en dehors de la fenêtre).
- Tolérance de drift horloge client: ±500 ms (au-delà → rejet).
- server_ts est la source de vérité pour les métriques et ordonnancements.
- correlation_id doit persister de la requête d’origine jusqu’aux dernières émissions dérivées.
- sig (si présent): doit couvrir l’enveloppe complète (champs communs + payload) selon une canonicalisation JSON stable (ex: JCS). Le mécanisme de clé est documenté côté sécurité.

---

## 3) Schéma JSON (type-safe)

Schéma JSON Schema (draft 2020-12) pour l’enveloppe et les payloads v1. À implémenter avec un validateur standard. Les payloads sont discriminés par `type`.

```/dev/null/schemas/event_v1.schema.json#L1-999
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pixelprowlers.local/schemas/event.v1.json",
  "title": "EVENTS v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["type", "events_version", "ts", "server_ts", "actor", "thread_id", "correlation_id", "trace_id", "span_id", "payload"],
  "properties": {
    "type": {
      "type": "string",
      "enum": [
        "chat:user_message",
        "chat:agent_stream",
        "widget:update",
        "system:alert",
        "metrics:tick",
        "error:occurred"
      ]
    },
    "events_version": { "$ref": "#/$defs/semver" },
    "ts": {
      "type": "string",
      "format": "date-time",
      "description": "Horodatage client"
    },
    "server_ts": {
      "type": "string",
      "format": "date-time",
      "description": "Horodatage serveur (source de vérité)"
    },
    "actor": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "kind"],
      "properties": {
        "id": { "type": "string", "minLength": 1 },
        "kind": { "type": "string", "enum": ["user", "agent", "system", "widget"] },
        "role": { "type": "string", "enum": ["superuser", "ops", "viewer", "agent"] },
        "display_name": { "type": "string" }
      }
    },
    "room": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9:_\\-]+$"
    },
    "thread_id": {
      "type": "string",
      "minLength": 1
    },
    "correlation_id": {
      "type": "string",
      "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-7[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    },
    "trace_id": {
      "type": "string",
      "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-7[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    },
    "span_id": {
      "type": "string",
      "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    },
    "payload": { "type": "object" },
    "sig": {
      "type": "string",
      "contentEncoding": "base64"
    }
  },
  "allOf": [
    {
      "if": { "properties": { "type": { "const": "chat:user_message" } } },
      "then": { "$ref": "#/$defs/payload_chat_user_message" }
    },
    {
      "if": { "properties": { "type": { "const": "chat:agent_stream" } } },
      "then": { "$ref": "#/$defs/payload_chat_agent_stream" }
    },
    {
      "if": { "properties": { "type": { "const": "widget:update" } } },
      "then": { "$ref": "#/$defs/payload_widget_update" }
    },
    {
      "if": { "properties": { "type": { "const": "system:alert" } } },
      "then": { "$ref": "#/$defs/payload_system_alert" }
    },
    {
      "if": { "properties": { "type": { "const": "metrics:tick" } } },
      "then": { "$ref": "#/$defs/payload_metrics_tick" }
    },
    {
      "if": { "properties": { "type": { "const": "error:occurred" } } },
      "then": { "$ref": "#/$defs/payload_error_occurred" }
    }
  ],
  "$defs": {
    "attachment": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "name", "mime", "size"],
      "properties": {
        "id": { "type": "string" },
        "name": { "type": "string" },
        "mime": { "type": "string", "pattern": "^[a-zA-Z0-9!#$&^_.+-]+/[a-zA-Z0-9!#$&^_.+-]+$" },
        "size": { "type": "integer", "minimum": 0 }
      }
    },
    "severity": {
      "type": "string",
      "enum": ["info", "warn", "error", "critical"]
    },
    "semver": {
      "type": "string",
      "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$"
    },
    "payload_chat_user_message": {
      "properties": {
        "payload": {
          "type": "object",
          "additionalProperties": false,
          "required": ["message", "content_type"],
          "properties": {
            "message": { "type": "string", "minLength": 1 },
            "content_type": { "type": "string", "enum": ["text/plain", "text/markdown"] },
            "tokens": { "type": "integer", "minimum": 0 },
            "attachments": {
              "type": "array",
              "items": { "$ref": "#/$defs/attachment" },
              "maxItems": 10
            },
            "metadata": { "type": "object" }
          }
        }
      }
    },
    "payload_chat_agent_stream": {
      "properties": {
        "payload": {
          "type": "object",
          "additionalProperties": false,
          "required": ["chunk", "chunk_index"],
          "properties": {
            "chunk": { "type": "string" },
            "chunk_index": { "type": "integer", "minimum": 0 },
            "final": { "type": "boolean", "default": false },
            "latency_ms": { "type": "integer", "minimum": 0 },
            "model": { "type": "string" }
          }
        }
      }
    },
    "payload_widget_update": {
      "properties": {
        "payload": {
          "type": "object",
          "additionalProperties": false,
          "required": ["widget_id", "version", "action"],
          "properties": {
            "widget_id": { "type": "string" },
            "version": { "$ref": "#/$defs/semver" },
            "action": { "type": "string", "enum": ["mount", "unmount", "state_changed"] },
            "state": { "type": "object" },
            "changes": {
              "type": "array",
              "items": {
                "type": "object",
                "additionalProperties": true
              },
              "maxItems": 100
            },
            "capabilities": {
              "type": "array",
              "items": { "type": "string" },
              "maxItems": 50
            }
          }
        }
      }
    },
    "payload_system_alert": {
      "properties": {
        "payload": {
          "type": "object",
          "additionalProperties": false,
          "required": ["severity", "code", "message"],
          "properties": {
            "severity": { "$ref": "#/$defs/severity" },
            "code": { "type": "string" },
            "message": { "type": "string" },
            "context": { "type": "object" }
          }
        }
      }
    },
    "payload_metrics_tick": {
      "properties": {
        "payload": {
          "type": "object",
          "additionalProperties": false,
          "required": ["name", "values", "window"],
          "properties": {
            "name": { "type": "string" },
            "values": {
              "type": "object",
              "additionalProperties": { "type": "number" }
            },
            "window": {
              "type": "object",
              "additionalProperties": false,
              "required": ["since", "until"],
              "properties": {
                "since": { "type": "string", "format": "date-time" },
                "until": { "type": "string", "format": "date-time" }
              }
            },
            "sample": { "type": "integer", "minimum": 0 }
          }
        }
      }
    },
    "payload_error_occurred": {
      "properties": {
        "payload": {
          "type": "object",
          "additionalProperties": false,
          "required": ["severity", "code", "message", "where"],
          "properties": {
            "severity": { "$ref": "#/$defs/severity" },
            "code": { "type": "string" },
            "message": { "type": "string" },
            "where": { "type": "string", "enum": ["backend", "frontend", "socket", "widget", "database", "external_api"] },
            "details": { "type": "object" },
            "cause_id": { "type": "string" }
          }
        }
      }
    }
  }
}
```

---

## 4) Exemples canoniques

Exemple — chat:user_message

```/dev/null/examples/chat_user_message.json#L1-200
{
  "type": "chat:user_message",
  "events_version": "1.0.0",
  "ts": "2025-10-13T06:29:40.327Z",
  "server_ts": "2025-10-13T06:29:40.400Z",
  "actor": { "id": "user_su_001", "kind": "user", "role": "superuser", "display_name": "Alice" },
  "room": null,
  "thread_id": "th_76m3X7n2",
  "correlation_id": "018f2c8e-af3a-7c10-b9a2-8f1c2d3e4f50",
  "trace_id": "018f2c8e-af3a-7c10-b9a2-8f1c2d3e4f50",
  "span_id": "12f3a456-789b-4cde-8fab-0123456789ab",
  "payload": {
    "message": "Bonjour Jared, peux-tu résumer l'incident #245 ?",
    "content_type": "text/plain",
    "tokens": 8,
    "attachments": []
  },
  "sig": "BASE64_SIGNATURE_OPTIONNELLE"
}
```

Exemple — chat:agent_stream (chunk 0)

```/dev/null/examples/chat_agent_stream_chunk0.json#L1-200
{
  "type": "chat:agent_stream",
  "events_version": "1.0.0",
  "ts": "2025-10-13T06:29:40.612Z",
  "server_ts": "2025-10-13T06:29:40.620Z",
  "actor": { "id": "agent_jared", "kind": "agent", "role": "agent" },
  "thread_id": "th_76m3X7n2",
  "correlation_id": "018f2c8e-af3a-7c10-b9a2-8f1c2d3e4f50",
  "trace_id": "018f2c8e-af3a-7c10-b9a2-8f1c2d3e4f50",
  "span_id": "98a7bcde-4321-4fed-9abc-1234567890ab",
  "payload": {
    "chunk": "Résumé de l'incident #245: ",
    "chunk_index": 0,
    "final": false,
    "latency_ms": 285,
    "model": "gpt-4o-mini"
  }
}
```

Exemple — chat:agent_stream (chunk final)

```/dev/null/examples/chat_agent_stream_final.json#L1-200
{
  "type": "chat:agent_stream",
  "events_version": "1.0.0",
  "ts": "2025-10-13T06:29:41.120Z",
  "server_ts": "2025-10-13T06:29:41.130Z",
  "actor": { "id": "agent_jared", "kind": "agent", "role": "agent" },
  "thread_id": "th_76m3X7n2",
  "correlation_id": "018f2c8e-af3a-7c10-b9a2-8f1c2d3e4f50",
  "trace_id": "018f2c8e-af3a-7c10-b9a2-8f1c2d3e4f50",
  "span_id": "6b5c4d3e-2f1a-4b0c-9def-abcdef012345",
  "payload": {
    "chunk": "impact modéré, résolution en 18min, cause: surcharge I/O.",
    "chunk_index": 2,
    "final": true,
    "latency_ms": 793,
    "model": "gpt-4o-mini"
  }
}
```

Exemple — Resynchronisation (gap_request, contrôle HTTP)
```/dev/null/examples/chat_gap_request.http#L1-60
POST /api/agents/jared/stream/gap HTTP/1.1
Content-Type: application/json

{
  "correlation_id": "018f2c8e-af3a-7c10-b9a2-8f1c2d3e4f50",
  "thread_id": "th_76m3X7n2",
  "missing": [1,2]
}
```

Le serveur renvoie les chunks manquants sous forme d’événements `chat:agent_stream` avec `payload.chunk_index` correspondant aux indices demandés.

Exemple — widget:update (state_changed)

```/dev/null/examples/widget_update_state_changed.json#L1-200
{
  "type": "widget:update",
  "ts": "2025-10-13T06:29:45.005Z",
  "actor": { "id": "widget_metrics_strip", "kind": "widget" },
  "thread_id": "th_76m3X7n2",
  "correlation_id": "42a1c9c3-6f3d-4d6d-b2e9-31e071b3c4f0",
  "payload": {
    "widget_id": "metrics_strip",
    "version": "1.2.0",
    "action": "state_changed",
    "state": { "latency_p50_ms": 910, "errors_5m": 0 },
    "changes": [
      { "op": "replace", "path": "/latency_p50_ms", "value": 910 }
    ],
    "capabilities": ["read:metrics"]
  }
}
```

Exemple — system:alert (warn)

```/dev/null/examples/system_alert_warn.json#L1-200
{
  "type": "system:alert",
  "ts": "2025-10-13T06:30:10.000Z",
  "actor": { "id": "system_monitor", "kind": "system" },
  "thread_id": "th_system_monitoring",
  "correlation_id": "9e27f766-0c2d-4784-9b21-5c0b48cc3c77",
  "payload": {
    "severity": "warn",
    "code": "LATENCY_P90_HIGH",
    "message": "Latence p90 > seuil 3.5s sur 15 min",
    "context": { "observed_ms": 3600, "threshold_ms": 3500, "window": "15m" }
  }
}
```

Exemple — metrics:tick

```/dev/null/examples/metrics_tick.json#L1-200
{
  "type": "metrics:tick",
  "ts": "2025-10-13T06:30:15.000Z",
  "actor": { "id": "metrics_cron", "kind": "system" },
  "thread_id": "th_metrics_tick",
  "correlation_id": "0c40a1d6-38c2-4c95-a0b6-318f5a1fb3e0",
  "payload": {
    "name": "cockpit.core",
    "values": { "messages_24h": 1287, "errors_24h_rate": 0.012, "rooms_active": 7 },
    "window": { "since": "2025-10-12T06:30:15.000Z", "until": "2025-10-13T06:30:15.000Z" },
    "sample": 1024
  }
}
```

Exemple — error:occurred (critical)

```/dev/null/examples/error_occurred_critical.json#L1-200
{
  "type": "error:occurred",
  "ts": "2025-10-13T06:30:20.500Z",
  "actor": { "id": "api_gateway", "kind": "system" },
  "thread_id": "th_req_9a6",
  "correlation_id": "e8b0e1e9-cc28-4481-9f88-63d81df73551",
  "payload": {
    "severity": "critical",
    "code": "SOCKET_BRIDGE_DOWN",
    "message": "Bridge sockets indisponible (timeout > 5s)",
    "where": "backend",
    "details": { "component": "sockets_bridge", "timeout_ms": 5200 }
  }
}
```

---

## 5) Contrôles & validations

Validation schéma (obligatoire):
- Enveloppe: présence des champs communs et types conformes.
- Discrimination par `type`: `payload` doit respecter le sous-schéma associé.
- `ts` format RFC 3339 avec ‘Z’; `correlation_id` UUID v4; `actor.kind` ∈ {user, agent, system, widget}.
- `room` requis si l’événement concerne une room ou une diffusion room-scoped.
- `sig` (si présent) valide la signature sur le JSON canonique (clé/algorithme gérés par la plateforme).

Règles métier (exigences minimales):
- chat:user_message → doit précéder au moins 1 chat:agent_stream partageant le même `thread_id` et `correlation_id`. L’ordre strict n’est pas garanti entre canaux, mais l’indice `index` du stream doit être croissant par émetteur.
- chat:agent_stream final → `done=true` exactement une fois par `correlation_id` et `thread_id` de la même réponse.
- widget:update avec action=mount → doit préciser `version`; avec action=state_changed → `changes` est recommandé.
- system:alert → `severity` ∈ {info,warn,error,critical}; déclenche une entrée de log d’alerte.
- metrics:tick → `window.since < window.until`; horodatages en UTC.
- error:occurred → ne doit pas contenir de secrets; `details` redacted si nécessaire.

Contrôles sécurité:
- RBAC: avant l’émission, vérifier que l’acteur a la capability requise (ex: un widget sans capability write ne peut pas produire un event d’écriture).
- Anti-replay: refuser un `sig` déjà vu avec le même nonce/correlation_id/ts; tolérance de dérive temporelle limitée.
- Journalisation: tout événement émis doit générer un log structuré corrélé (incluant correlation_id) et un chaînage de hash dans les journaux d’audit append-only lorsque possible.

Tests (à automatiser):
- Jeux d’exemples canoniques (ci-dessus) validés par le schéma.
- Tests e2e pivot: POST chat → log corrélé → chat:agent_stream conforme (≥2 chunks + done).
- Tests négatifs: mauvais UUID, ts hors tolérance, type inconnu, payload invalide, actor.kind interdit, capability manquante.

---

## 6) Transport & livraison

- Transport recommandé: SSE pour `chat:agent_stream` et notifications; WS pour rooms (bridge sockets).
- Content-Type: application/json; encodage UTF-8.
- Ordonnancement: non garanti entre canaux; utiliser `thread_id`, `correlation_id` et, pour les flux, `payload.index`.
- Backpressure: l’émetteur doit appliquer une stratégie de débit (buffers bornés, retry/backoff).
- Idempotence: POST /api/agents/{slug}/chat doit inclure `idempotency_key` (UUIDv7) générée côté client et validée côté serveur.
  - En cas de double envoi: répondre HTTP 409 (Conflict) ou 200 avec `{ idempotent: true, correlation_id }` sans ré-exécuter le traitement.

---

## 7) Compatibilité & versionnage

- Version protocole: v1 (ce document).
- Ajouts compatibles:
  - Champs optionnels dans `payload` (doivent être ignorés par les consommateurs v1).
  - Nouvelles valeurs non destructrices dans des enums extensibles (documenter).
  - Nouveaux types d’événements v1.x doivent être documentés et ajoutés à la matrice RBAC.
- Ruptures (breaking):
  - Changement de sens/sémantique d’un champ existant.
  - Retrait d’un champ requis.
  - Renommage d’un type d’événement.
  - Exigent v2 et un plan de migration/rollback.
- Rollback documentaire:
  - Tout changement est journalisé dans “Append Log”.
  - Retour à v-1 = revert Git + revalidation des exemples canoniques + relance des e2e pivots.

---

## 8) Risques sécurité

Menaces:
- Spoofing d’acteur (usurpation d’identité).
- Tampering (altération de payload).
- Replay (réémission d’un event valide).
- Information Disclosure (fuite de données sensibles via `payload`).
- Elevation of Privilege (widget sans capability effectuant un write).

Atténuations:
- Signature `sig` sur JSON canonique + clés gérées côté plateforme (rotation).
- Nonces/exp implicites via `ts` et anti-replay store (fenêtre courte; une signature ne doit être acceptée qu’une fois).
- RBAC strict côté émetteur et récepteur; deny-by-default.
- Minimisation des données: payloads ne contiennent pas de secrets; redaction pour `error:occurred`.
- CSP/postMessage filtré pour les widgets; origin checks; isolation sandbox.
- Journaux hashés (hash_prev/hash_curr) pour la détection d’altérations; stockage append-only si possible.

---

## 9) Annexes — Matrice de capacités (résumé)

- chat:user_message → requires: actor.role ∈ {superuser, agent} et capability emit:chat (selon endpoint).
- chat:agent_stream → émis par un agent/bridge autorisé; capability emit:chat_stream.
- widget:update → émis par un widget enregistré avec capability read:* et/ou emit:widget_update; aucun write:* implicite.
- system:alert → émis par system/ops; capability emit:system_alert.
- metrics:tick → émis par system/metrics; capability emit:metrics.
- error:occurred → émis par tout composant; consommer en lecture contrôlée (ops/superuser).

Nota: La matrice exhaustive est définie dans RBAC v1.

---

## 10) Références croisées

- RBAC v1 — rôles, endpoints, capabilities (deny-by-default).
- SECURITY_BASELINES — CSRF, session binding, nonce anti-replay, logs hashés, CSP.
- WIDGET_REGISTRY — registre + capabilities par widget (semver, owner, scope).
- COCKPIT_TEMPLATE v1 — intégration UI, lifecycle, stream rendering.
- SOCKETS_BRIDGE v1 — events sockets rooms, scoping, backpressure.

---

## Append Log

- 2025-10-13 — Alice (Lead Orchestrator): Création initiale de la spécification EVENTS v1 (enveloppe, schéma JSON, exemples, validations, compatibilité, sécurité, append log).
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — en-tête normatif (UTF-8/UTC), events_version (semver), server_ts, UUIDv7 pour correlation_id/trace_id, span_id v4, streaming chunk_index/final + protocole gap_request, fenêtre anti-replay 60s (drift ±500ms), idempotency_key côté client documentée.
