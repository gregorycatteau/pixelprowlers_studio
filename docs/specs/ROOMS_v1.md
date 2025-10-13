# ROOMS v1 — Spécification (Conference Rooms)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Références croisées:
- docs/specs/EVENTS_v1.md (champs communs: type, ts, actor, room?, thread_id, correlation_id, payload, sig?)
- docs/specs/RBAC_v1.md (rôles, capabilities, deny-by-default)
- docs/specs/SECURITY_BASELINES.md (CSRF, session binding, anti-replay, logs hashés)
- docs/specs/SOCKETS_BRIDGE_v1.md (transport sockets, scoping, backpressure, retry)
- docs/specs/COCKPIT_TEMPLATE_v1.md (intégration front, UI Cockpit/Rooms)
- docs/checklists/QA_E2E.md (scénarios multi-participants)
- docs/specs/GOVERNANCE_v1.md (processus d’évolution, semver, ledger)

Statut: v1 (contrats figés pour Sprints 02–03)


-----------------------------------------------------------------------
1) Objet & portée

- Définir les modèles et règles de fonctionnement des Conference Rooms v1, permettant des échanges multi-participants (humains et agents) sécurisés, traçables et orchestrés.
- Standardiser les événements sockets associés (join_room, leave_room, agent_message, system_update) via l’enveloppe EVENTS v1.
- Décrire un tour de parole minimal (round-robin orchestré).
- Encadrer la sécurité (RBAC, scoping par room, anti-replay), la résilience (backpressure, retry) et la journalisation corrélée.

Hors de portée (v1):
- Widgets métiers dans les rooms (coordination seulement).
- Modération avancée (bannissements, enregistrements audio/vidéo).
- Partage de fichiers volumineux (seuls des liens/ids d’attachements sont envisagés).


-----------------------------------------------------------------------
2) Modèles (données minimales)

2.1 ConferenceRoom (ressource logique)
- id: string — identifiant unique de la room (ex: "room-abc123").
- title?: string — titre lisible.
- created_by: string — id de l’acteur créateur (user/agent/system).
- created_at: string — ISO 8601 (UTC).
- status: enum — active | closed.
- policy: object — politique d’adhésion/émission:
  - join: enum open | invite | owner_approved (default: invite).
  - speak: enum owner_led | round_robin (default: round_robin).
- metadata?: object — clés/valeurs non sensibles (tags, description).
- version: string (semver) — version de modèle si besoin d’évolution.

2.2 RoomParticipant (projection dans une room)
- id: string — identifiant du participant (stable).
- actor: object — { id: string, kind: enum user|agent|system, role?: RBAC role }.
- joined_at: string — ISO 8601 (UTC).
- status: enum — active | left | kicked.
- role_in_room: enum — owner | speaker | listener (default: listener).
- capabilities: array<string> — ex: ["emit:room_message","read:room_updates"].
- last_seen_at?: string — ISO 8601 (UTC).
- metadata?: object — informations non sensibles (display_name, avatar?).

2.3 TurnState (état minimal du tour de parole)
- room_id: string — référence room.
- mode: enum — round_robin | owner_led.
- speakers: array<string> — ordered list des participant.id éligibles.
- pointer: integer — index courant dans speakers (round-robin).
- quantum_ms: integer — temps nominal par tour (ex: 30000).
- updated_at: string — ISO 8601 (UTC).


-----------------------------------------------------------------------
3) Schéma JSON (type-safe)

3.1 ConferenceRoom (jsonschema, draft 2020-12)
    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "title": "ConferenceRoom v1",
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "created_by", "created_at", "status", "policy", "version"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-zA-Z0-9:_\\-]{3,64}$" },
        "title": { "type": "string", "maxLength": 200 },
        "created_by": { "type": "string", "minLength": 1 },
        "created_at": { "type": "string", "format": "date-time" },
        "status": { "type": "string", "enum": ["active","closed"] },
        "policy": {
          "type": "object",
          "additionalProperties": false,
          "required": ["join","speak"],
          "properties": {
            "join": { "type": "string", "enum": ["open","invite","owner_approved"] },
            "speak": { "type": "string", "enum": ["owner_led","round_robin"] }
          }
        },
        "metadata": { "type": "object" },
        "version": {
          "type": "string",
          "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$"
        }
      }
    }

3.2 RoomParticipant (jsonschema)
    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "title": "RoomParticipant v1",
      "type": "object",
      "additionalProperties": false,
      "required": ["id","actor","joined_at","status","role_in_room","capabilities"],
      "properties": {
        "id": { "type": "string", "minLength": 1 },
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
        "joined_at": { "type": "string", "format": "date-time" },
        "status": { "type": "string", "enum": ["active","left","kicked"] },
        "role_in_room": { "type": "string", "enum": ["owner","speaker","listener"] },
        "capabilities": {
          "type": "array",
          "items": { "type": "string" },
          "maxItems": 50
        },
        "last_seen_at": { "type": "string", "format": "date-time" },
        "metadata": { "type": "object" }
      }
    }

3.3 Événements sockets (payloads, enveloppés par EVENTS v1)
- join_room.payload
    {
      "room_id": "string",
      "participant": { /* RoomParticipant v1 (subset) */ },
      "reason?": "string"
    }
- leave_room.payload
    {
      "room_id": "string",
      "participant": { "id": "string" },
      "reason?": "string"
    }
- agent_message.payload
    {
      "room_id": "string",
      "from": { "id": "string", "kind": "user|agent|system" },
      "thread_id?": "string",
      "content": "string",
      "content_type": "text/plain|text/markdown",
      "attachments?": [ { "id": "string", "name": "string", "mime": "type/subtype", "size": 0 } ],
      "idempotency_key": "uuidv7",
      "index?": 0
    }
- system_update.payload
    {
      "room_id": "string",
      "kind": "participant_joined|participant_left|speaking_turn_changed|room_closed|policy_changed",
      "details": { /* object, dépend du kind (voir exemples) */ }
    }

Nota: Chaque message sockets est enveloppé dans EVENTS v1 avec les champs communs et room = room_id.


-----------------------------------------------------------------------
4) Règles d’adhésion, départ et abonnement

- Adhésion (join)
  - join_room autorisé si:
    - AuthN valide; RBAC v1 autorise join:room; room.status=active.
    - Policy.join= open → autorisé; invite/owner_approved → nécessite preuve/claim (invitation/approval).
  - À l’adhésion:
    - Émettre un event EVENTS v1 type=join_room avec room=room_id et correlation_id.
    - Ajouter le participant à la liste active; initialiser last_seen_at.

- Départ (leave)
  - leave_room autorisé si participant.status=active et possession d’une session valide pour cette room.
  - Émettre un event leave_room avec reason? (volontaire/timeout/kicked).

- Abonnement (sockets)
  - Scoping strict par room: impossible de publier/écouter en dehors de room_id.
  - Origin checks (WS): refuser origins non autorisées (CORS/WS).
  - Namespaces/rooms: utiliser un namespace par feature, un canal par room_id.

- Fermeture room
  - Seul owner (ou superuser) peut clore: status → closed; émettre system_update.kind=room_closed.


-----------------------------------------------------------------------
5) Tour de parole minimal (round-robin)

- Modes
  - owner_led: l’owner désigne le speaker explicite via system_update.kind=speaking_turn_changed.
  - round_robin: ordre établi dans TurnState.speakers; pointer itère circulairement.

- Règles round_robin
  - Initialisation: speakers = [participants.role_in_room=="speaker"] par ordre de join.
  - Quantum: quantum_ms borne le temps de parole recommandé (non bloquant).
  - Transition:
    - Sur agent_message du speaker courant OU sur timeout quantum_ms, pointer = (pointer+1) % speakers.length.
    - Émettre system_update.kind=speaking_turn_changed avec details { from, to, reason }.
  - Reprise après silence (acteur muet / timeout):
    - Si aucun agent_message n’est reçu du speaker courant dans le délai quantum_ms, marquer le speaker comme "silent_once" et passer au suivant.
    - Après 2 occurrences "silent_once" sur une fenêtre de 5 minutes pour un même speaker, le rétrograder temporairement en listener et émettre system_update.kind=policy_changed avec details { action: "speaker_to_listener", participant }.
    - À la première reprise (agent_message valide), rétablir le statut speaker (si policy le permet) et réinsérer le participant en fin de speakers.
  - Évolutions:
    - Join d’un participant avec role_in_room=speaker → append en fin de speakers.
    - Leave/kick d’un speaker → retirer de speakers; ajuster pointer pour rester valide.
  - Sécurité:
    - Un agent/user sans capability emit:room_message ne peut pas émettre; deny + log + éventuel system:alert.


-----------------------------------------------------------------------
6) Événements sockets v1 (enveloppe EVENTS v1)

Champs communs (obligatoires):
- type ∈ { "join_room", "leave_room", "agent_message", "system_update" }
- ts (UTC, ISO 8601), actor (id, kind, role?), room = room_id, thread_id?, correlation_id (UUID v4), payload, sig?

Contraintes:
- room doit matcher room_id dans payload.
- correlation_id propagé dans toute la séquence liée (join → messages → updates).
- agent_message.payload.index croissant par émetteur si segmenté.

Transport:
- WS (recommandé pour rooms), TLS obligatoire, backoff exponentiel + jitter côté client.


-----------------------------------------------------------------------
7) Exemples (canoniques)

7.1 join_room
    {
      "type": "join_room",
      "ts": "2025-10-13T06:45:00.000Z",
      "actor": { "id": "user_su_001", "kind": "user", "role": "superuser" },
      "room": "room-abc123",
      "thread_id": "th_room_abc123",
      "correlation_id": "a9a8f4e8-3d37-4b1e-a38e-6d2f8ae0d1b7",
      "payload": {
        "room_id": "room-abc123",
        "participant": {
          "id": "user_su_001",
          "actor": { "id": "user_su_001", "kind": "user", "role": "superuser" },
          "joined_at": "2025-10-13T06:45:00.000Z",
          "status": "active",
          "role_in_room": "owner",
          "capabilities": ["join:room","read:room_updates","emit:room_message"]
        }
      }
    }

7.2 agent_message (humain → agents)
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

7.3 system_update (tour de parole)
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
        "details": {
          "from": "agent_talia",
          "to": "agent_bruce",
          "reason": "round_robin_next"
        }
      }
    }

7.4 leave_room
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


-----------------------------------------------------------------------
8) Contrôles & validations

Validation schéma:
- Enveloppe EVENTS v1 obligatoire; `type` doit ∈ { join_room, leave_room, agent_message, system_update }.
- room == payload.room_id.
- ts au format RFC 3339, UTC; correlation_id = UUID v4.
- actor.kind ∈ user|agent|system; role conforme à RBAC v1 si présent.

Règles métier:
- join_room → un participant déjà active devient no-op ou state refresh (éviter duplication).
- leave_room → transition status=left/kicked; double leave toléré comme no-op.
- agent_message → refus si capability émettrice absente (emit:room_message) ou policy.speak non respectée.
- system_update → speaking_turn_changed doit référencer des participants actifs.

- Sécurité:
 - RBAC v1: evaluation join:room, emit:room_message, read:room_updates selon rôle/capabilities.
 - Anti-replay: fenêtre 60s (server_ts source de vérité, drift client ±500ms). Chaque message inclut un nonce unique; agent_message doit fournir idempotency_key (UUIDv7) pour dédoublonnage (fenêtre 60s); doublon = ack idempotent (pas de re-diffusion).
 - Scoping strict: toute tentative cross-room est refusée et journalisée.

- Journalisation:
 - Chaque événement génère un log structuré avec correlation_id, trace_id et span_id, ainsi que le chaînage hash (hash_prev/hash_curr).
 - Violations (RBAC, replay, origin) → error:occurred et/ou system:alert.


-----------------------------------------------------------------------
9) RBAC (résumé v1)

- superuser: join_room emit/read, agent_message emit, system_update emit/read, leave_room.
- ops: join_room read, system_update read, agent_message emit=deny (par défaut), leave_room (self).
- viewer: read:room_updates (si policy explicite), join=deny par défaut.
- agent: join_room (policy), agent_message emit (si capability), system_update read, leave_room (self).

Deny-by-default: toute action non listée est refusée. Toute capability write/manage exige RFC.


-----------------------------------------------------------------------
10) Backpressure & retry (rooms)

- Quotas:
  - messages_per_actor_per_sec (ex: 5), messages_per_room_per_sec (ex: 50).
  - buffer_max (ex: 100 messages/acteur), drop = oldest non-ack + system:alert warn.
- Acks (optionnels v1):
  - Agent peut renvoyer un ack implicite (heartbeat) pour marquer last_seen_at.
- Retry:
  - Reconnect client: backoff exponentiel (250ms → 10s) + jitter, max 8 essais avant pause manuelle.
- Idempotence:
  - Dédoublonnage via (correlation_id, index?) côté consommateurs.
- Observabilité:
  - Mesurer latence msg→diffusion, taux retry, drops; émettre metrics:tick périodiques.


-----------------------------------------------------------------------
11) Compatibilité & versionnage

- v1 stable pour Sprints 02–03.
- Ajouts compatibles:
  - Nouveaux kinds de system_update.
  - Détails optionnels additionnels dans payloads.
- Ruptures → ROOMS v2:
  - Changement sémantique des champs obligatoires.
  - Modification des règles de tour de parole ou des policies par défaut.
- Rollback:
  - Revert Git + revalidation d’exemples canoniques + rerun e2e “2 agents + 1 humain”.


-----------------------------------------------------------------------
12) Risques sécurité (parano v1) & mitigations

- Usurpation d’accès room:
  - Jetons courts (claims: sub, role, scopes, room_id?), origin allowlist, scoping strict server-side.
- Flood/DDoS:
  - Backpressure/quotas, throttling, alerting system:alert, coupure contrôlée par owner/superuser.
- Escalade via system_update:
  - Émission limitée aux rôles autorisés; logs/audit; validations strictes.
- Data leakage:
  - Minimisation payloads; pas de secrets; redaction des erreurs.
- Replay:
  - Fenêtre temporelle stricte; store anti-replay; signature (sig) si disponible (EVENTS v1).


-----------------------------------------------------------------------
13) Observabilité & journaux

- Logs structurés:
  - ts, source, actor, room, action(type), correlation_id, decision, hash_prev, hash_curr.
- KPIs (Dashboard v1):
  - rooms_actives (courant, pic 24h), latence diffusion, taux retry, erreurs sockets, messages/min.
- Alertes:
  - system:alert sur anomalies: invalid_token, flood_detected, room_closed_write, turn_inconsistency.


-----------------------------------------------------------------------
14) Tests & QA

- e2e (pivot Sprint 02):
  - 2 agents simulés + 1 humain → join_room → agent_message → diffusion contextualisée conforme.
  - Vérifier: correlation_id propagé; RBAC effectif; system_update pour tour de parole; logs hashés OK.
- Négatifs:
 - join sans droit/policy, message sans capability, cross-room, token invalide/expiré, E2E-SEC-ROOMS-01 (idempotence: même idempotency_key → 1 seul message visible), E2E-SEC-ROOMS-02 (message hors fenêtre 60s → rejet + log).
- Schémas:
  - Valider ConferenceRoom, RoomParticipant, payloads sockets; exemples canoniques → OK.
- Résilience:
  - Simuler latence et micro-coupures; vérifier retry/backoff; pas de pertes au-delà du configurable.


-----------------------------------------------------------------------
Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale ROOMS v1 (modèles, règles d’adhésion, tour de parole round-robin, événements sockets, contrôles de sécurité, backpressure/retry, exemples canoniques, QA).
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — round-robin: reprise sur timeout (acteur muet), idempotency_key & nonce (fenêtre anti-replay 60s), journalisation join/leave incluant trace_id et span_id.
- 2025-10-13 — Alice (Lead Orchestrator): Patch v1b — idempotency_key (UUIDv7) exigée pour agent_message; doublon sur 60s = ack idempotent (pas de re-diffusion); références QA E2E ajoutées (E2E-SEC-ROOMS-01/02); lien Governance ajouté dans Références.
