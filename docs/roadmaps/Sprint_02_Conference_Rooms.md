# Sprint 02 — Conference Rooms v1

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Périmètre: structure multi-participants (humains et agents), bridge sockets minimal, tour de parole minimal, traçabilité événementielle v1.
Références: docs/specs/GOVERNANCE_v1.md

---

## But du sprint
Mettre en place la première version des Conference Rooms pour permettre des échanges multi-participants orchestrés, sécurisés et traçables:
- Modèle de room minimal: `ConferenceRoom`, `RoomParticipant`, règles d’adhésion/départ et journalisation.
- Bridge sockets minimal avec événements standardisés: `join_room`, `leave_room`, `agent_message`, `system_update`.
- Tour de parole minimal (round-robin ou owner-led) et scoping par room.
- Intégration avec le protocole d’événements v1 et les baselines sécurité (RBAC, correlation_id, logs hashés).
- Tests e2e validant la diffusion contextualisée d’un message entre 2 agents simulés et 1 humain.

---

## Livrables
- docs/roadmaps/Sprint_02_Conference_Rooms.md — ce document (roadmap + checklists).
- docs/specs/ROOMS_v1.md — modèle `ConferenceRoom`, `RoomParticipant`, règles d’abonnement, tour de parole minimal.
- docs/specs/SOCKETS_BRIDGE_v1.md — événements sockets (`join_room`, `leave_room`, `agent_message`, `system_update`), namespaces/rooms, scoping, sécurité (token + rôle), backpressure, retry.
- Mise à jour transversale (références):
  - Alignement avec docs/specs/EVENTS_v1.md pour les champs communs (`type`, `ts`, `actor`, `room?`, `thread_id`, `correlation_id`, `payload`, `sig?`).
  - Alignement RBAC v1 (docs/specs/RBAC_v1.md) pour accès endpoints/sockets.
  - QA E2E étendu (docs/checklists/QA_E2E.md) avec scénarios rooms.

---

## Plan de tests
- e2e (Playwright)
  - Scénario pivot “2 agents simulés + 1 humain dans une room”
    - Préconditions:
      - Utilisateur humain authentifié (rôle selon matrice, ex: `superuser`).
      - Deux agents simulés (slugs `talia`, `bruce`) inscrits dans la room.
      - Jetons d’accès valides (scopes/claims conformes).
    - Étapes:
      1) L’humain crée ou rejoint la room `room-abc` (join_room).
      2) Les deux agents rejoignent la même room (join_room côté sockets).
      3) L’humain envoie un message contextualisé via l’UI room (bridge → `agent_message`).
      4) Les deux agents reçoivent la diffusion scoping par room.
      5) Le tour de parole se met à jour (round-robin minimal) et est reflété côté UI.
      6) Un `system_update` est émis (ex: “participant joined/left”, “speaking turn changed”).
    - Attendus:
      - Tous les messages/events contiennent un `correlation_id` cohérent sur le flux d’action.
      - Les events sockets respectent les schémas de docs/specs/SOCKETS_BRIDGE_v1.md.
      - Les logs côté backend et/ou proxy sockets sont hashés et chaînés.
      - RBAC empêche un participant non autorisé d’émettre un `agent_message` (tests négatifs).
      - Backpressure et retry fonctionnent (test: simuler latence et micro-coupures; pas de pertes au-delà du configurable).
- Tests d’intégration
  - Validation des schémas d’événements (jsonschema/zod) pour `join_room`, `leave_room`, `agent_message`, `system_update`.
  - Validation du modèle `ConferenceRoom`/`RoomParticipant` (création, join, leave, liste participants).
  - Vérification de la propagation du `correlation_id` bout-en-bout (UI → sockets → logs → events).
  - Sécurité: refus si token invalide/expiré, rôle insuffisant, origin non autorisée, room inexistante/fermée.
- Non-régression
  - Snapshots d’exemples canoniques d’events sockets.
  - Scénarios négatifs (spam, double join, leave fantôme, messages hors-scope room, E2E-SEC-SOCKETS-01, E2E-SEC-SOCKETS-02).

---

## Sécurité (gates)
- AuthN/AuthZ sockets
  - JWT court TTL (5–10 min), kid obligatoire; JWKS interne avec publication d’une clé active + clé suivante (grace period); validation côté client sur kid et refresh proactif en cas de bascule.
  - Jeton signé avec claims: `sub` (acteur), `role`, `scopes`, `room_id` (optionnel, ou join-time).
  - En cas de rotation/déclassement/violation de policy, le serveur peut émettre `system_update(kind="force_disconnect", reason="role_downgrade"|"key_rotation"|"policy_violation")`; le client ferme la socket, purge l’état sensible et bloque l’émission.
  - RBAC v1:
    - `superuser`: join/leave rooms + émettre `agent_message` + lire tout.
    - `ops`: join/leave + lecture + `system_update` lecture; pas d’émission `agent_message`.
    - `viewer`: join lecture-only (si policy) + aucun write.
    - `agent`: join/leave selon policy; `agent_message` seulement si capability explicite.
- Scoping & isolation
  - Namespaces/rooms WS séparés; validation stricte `room_id` à chaque message.
  - Filtrage par origin (CORS/WS origin) + CSP côté front pour tout contenu lié.
- Deny-by-default
  - Aucun write (ex: `agent_message`) sans capability explicite (`emit:room_message` ou équivalent) validée à la jonction.
- Anti-replay & nonce
  - Messages sensibles incluent un `nonce`/`ts` signé; rejet des replays hors fenêtre.
- Journaux & traçabilité
  - Tous les événements génèrent logs structurés avec `correlation_id` + chainage hash (hash_prev/hash_curr).
  - Émissions de `system:alert` en cas d’anomalies (flood, invalid token, room not found).
- Robustesse transport
  - Backpressure: quotas par acteur, débit max par room; file tampon; drop policé avec alerting.
  - Retry & backoff: stratégie exponentielle + jitter; limites max; état `reconnecting` documenté côté UI.
- Gate de promotion Sprint 02
  - e2e pivot “2 agents + 1 humain” vert en CI (diffusion contextualisée conforme).
  - RBAC v1 effectif pour sockets (tests: refus des writes non autorisés).
  - Backpressure/retry testés; journaux hashés + corrélation vérifiés.
  - Conformité aux schémas d’événements `S0CKETS_BRIDGE_v1` (validation sans erreurs).

---

## Checklist d’avancement
- [ ] Spécification `ROOMS_v1` validée (modèles, adhésion, départ, journaux room).
- [ ] Spécification `SOCKETS_BRIDGE_v1` validée (events, scoping, sécurité, backpressure, retry).
- [ ] Contrats testés (jsonschema/zod) et exemples canoniques publiés.
- [ ] RBAC v1 mappé pour actions rooms/sockets (join/leave/message/system).
- [ ] e2e pivot “2 agents + 1 humain” écrit et vert (local/CI).
- [ ] DoD atteint.

---

## Definition of Done (DoD)
- Création/connexion à une room documentée (contrats + exemples) et validée par schémas.
- Events sockets `join_room`, `leave_room`, `agent_message`, `system_update` livrés avec scoping et sécurité effectifs.
- Test e2e: 2 agents simulés + 1 humain → diffusion d’un message contextualisé conforme (corrélation, RBAC, logs hashés).
- Backpressure et stratégie de retry implémentées et testées.
- Append Log mis à jour et références croisées avec EVENTS v1/RBAC v1.

---

## Risques & Mitigations
- Épuisement ressources (flood de messages/sockets)
  - Mitigation: quotas par acteur/room, backpressure, throttling, alertes `system:alert`.
- Usurpation/accès non autorisé à une room
  - Mitigation: jetons courts, validation rôle/capability à chaque message, scoping strict par `room_id`, allowlist origins.
- Incohérence tour de parole
  - Mitigation: algorithme déterministe (round-robin avec horodatage/priority), events `system_update` pour synchroniser l’UI.
- Pertes de messages sous reconnection
  - Mitigation: idempotence via `correlation_id` + index de chunk, re-ask sur gap, buffers limités + resend des manquants.
- Flaky e2e (timing WS)
  - Mitigation: test harness avec délais contrôlés, retries bornés, assertions robustes (attendre états, non seulement timeouts).
- Régression sécurité (policies non alignées RBAC)
  - Mitigation: matriçage exhaustif, tests négatifs, revue SecOps, CI schémas.

---

## Notes d’implémentation (guides)
- Modèles
  - `ConferenceRoom`: id, title?, created_by, created_at, status (active|closed), policy (join policy), metadata?.
  - `RoomParticipant`: id, actor (user|agent), role_in_room (owner|speaker|listener), capabilities, joined_at, status (active|left|kicked).
- Événements sockets (payload minimal)
  - `join_room`: { room_id, participant, correlation_id }
  - `leave_room`: { room_id, participant, reason?, correlation_id }
  - `agent_message`: { room_id, from, thread_id?, content, tags?, correlation_id }
  - `system_update`: { room_id, kind, details, correlation_id }
- Intégration EVENTS v1
  - Les messages sockets sont enveloppés/bridgés vers des events conformes (champs communs v1) pour la journalisation.
- Tour de parole
  - Round-robin: liste ordonnée de `speakers`; transition sur `agent_message` complété ou timeout; `system_update` notifie le prochain.
- Observabilité
  - Mesures: latence moyenne message→diffusion, débit par room, taux de retry, nombre de participants actifs, erreurs par type.
- Rollback documentaire
  - Toute modification de `ROOMS_v1`/`SOCKETS_BRIDGE_v1` est logguée; revert = retour à v-1 + re-run e2e pivot.

---

## Dépendances & Outils
- Validation: jsonschema/zod pour sockets payloads + modèles Room.
- e2e: Playwright (multi-clients simulés).
- Transport: WS (optionnel SSE pour certaines mises à jour système).
- Sécurité: signature de jetons (ex: JWT), CSP/Origin policies, rate limiting.

---

## Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale du roadmap Sprint 02 (Conference Rooms v1), définition des événements sockets, du tour de parole minimal, des gates sécurité et du scénario e2e pivot.
- 2025-10-13 — Alice (Lead Orchestrator): Patch v1b — Ajout Key Rotation (JWKS/kid) et `force_disconnect` (role_downgrade|key_rotation|policy_violation); ajout des références de tests négatifs E2E-SEC-SOCKETS-01/02.
