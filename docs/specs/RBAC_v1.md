# RBAC v1 — Rôles, Capabilities et Matrice d’accès (Backbone minimal)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Statut: v1 (stable pour Sprints 00–03)
Références: EVENTS v1, SECURITY_BASELINES, WIDGET_REGISTRY, COCKPIT_TEMPLATE v1, SOCKETS_BRIDGE v1, GOVERNANCE v1

---

## 1) Objet & portée

Cette spécification définit le modèle RBAC minimal de la plateforme et son mode d’application:
- Rôles standards: superuser, ops, viewer, agent.
- Capabilities canoniques (read:*, write:*, emit:*, manage:*).
- Matrice d’accès d’exemples pour endpoints HTTP, événements Sockets, et Host de widgets.
- Règles d’évaluation, traçabilité (correlation_id), et exigences de sécurité (deny-by-default).

Hors de portée (v1):
- Rôles métiers additionnels et politiques d’organisation (tenants complexes).
- Délégation inter-organisations (fédérations).
Ces points doivent être ajoutés via une RFC, versionnés et testés e2e.

---

## 2) Principes directeurs

- Least privilege: chaque rôle ne possède que les permissions strictement nécessaires.
- Deny-by-default: toute action non explicitement permise est refusée.
- Capability-based: les décisions s’appuient sur des capabilities explicites (ex: emit:chat_stream).
- Defense in depth: contrôle côté client (UI), côté backend (API), et côté transport (sockets).
- Traçabilité forte: toute décision génère un log corrélable (correlation_id) et un event si pertinent.
- Séparation des pouvoirs: les capacités d’écriture (write:*) et d’émission (emit:*) sont limitées et auditables.
- Compatibilité: les changements breaking des politiques nécessitent une nouvelle version (RBAC v2).

---

## 3) Glossaire

- Rôle: profil de haut niveau attaché à un acteur (superuser|ops|viewer|agent).
- Capability: permission nominale atomique (ex: read:logs, emit:chat, manage:widget_registry).
- Ressource: objet cible d’une action (endpoint, room, widget, registry…).
- Action: opération sur la ressource (read, write, emit, join, manage…).
- Contexte: contraintes supplémentaires (ex: agent slug, room_id, tenant, origin).
- Décision: allow|deny (+ raisons), consignée dans les journaux avec `correlation_id`.

---

## 4) Rôles (définition et portée)

- superuser
  - Portée: globale (limitable par tenant si multi-tenant).
  - Accès: lecture/écriture/émission sur l’ensemble des ressources documentées.
  - Usage: break-glass, opérations d’administration, audits, diagnostique complet.

- ops
  - Portée: opérations/fiabilité.
  - Accès: lecture des logs, dashboards/KPIs, diagnostics; pas d’écriture de chat; pas de mutation de registre.
  - Peut rejoindre des rooms en lecture; pas d’émission de messages agent.

- viewer
  - Portée: observation minimale.
  - Accès: lecture Dashboard/KPIs autorisés; aucun accès aux logs bruts; pas de chat write; pas de sockets write.
  - Par défaut, pas de join room; peut être autorisé par policy explicite lecture-only.

- agent
  - Portée: identité de service pour les agents.
  - Accès: émission de `chat:agent_stream` et messages autorisés dans sa propre portée (son slug/room) avec capabilities explicites.
  - Pas d’accès aux logs; pas de gestion de registry; join room selon policy et scope.

Nota: Toute élévation de privilèges doit être auditable et soumise à revue.

---

## 5) Capabilities canoniques (exemples v1)

- Chat
  - emit:chat — autorise l’émission d’un message utilisateur côté système (ex: relai control-plane).
  - write:chat — autorise POST /api/agents/{slug}/chat.
  - emit:chat_stream — autorise l’émission d’événements `chat:agent_stream`.

- Logs & Observabilité
  - read:logs — autorise la lecture des journaux corrélés.
  - read:kpis — autorise la lecture des endpoints KPIs/Dashboard.

- Rooms (Sockets Bridge)
  - join:room — autorise la jonction à une room donnée.
  - emit:room_message — autorise `agent_message` dans une room.
  - read:room_updates — autorise la réception d’événements de room (join/leave/system_update).

- Widgets & Registry
  - read:widget_registry — lecture du registre global.
  - manage:widget_registry — création/mise à jour de définitions dans le registre.
  - widget:read:* — portée lecture sandbox (via WidgetHost).
  - widget:write:* — portée écriture sandbox (rare, nécessite revue SecOps).
  - widget:emit:* — permet l’émission d’événements `widget:update` (limité et auditable).

- Système
  - emit:system_alert — émission d’alertes `system:alert`.
  - emit:metrics — émission `metrics:tick`.

Les capabilities des widgets sont déclarées dans `widget_registry.json` (voir WIDGET_REGISTRY) et validées au mount (deny-by-default si absent).

---

## 6) Matrice d’accès initiale (exemples)

Nota: “Allow (✓) / Deny (✗)” exprime la valeur par défaut v1. Des checks de scope s’ajoutent ensuite (slug, room_id, tenant).

1) Endpoints HTTP

| Endpoint                               | Action | superuser | ops | viewer | agent | Notes |
|----------------------------------------|--------|-----------|-----|--------|-------|-------|
| POST /api/agents/{slug}/chat           | write  | ✓         | ✗   | ✗      | ✓     | agent: seulement pour son propre slug ou délégation explicite; CSRF/nonce requis |
| GET /api/logs?correlation_id=…         | read   | ✓         | ✓   | ✗      | ✗     | filtres obligatoires; redaction champs sensibles |
| GET /api/kpis/*                        | read   | ✓         | ✓   | ✓      | ✗     | throttling/caching; viewer lecture-only |
| GET /api/widgets/registry              | read   | ✓         | ✓   | ✓      | ✓     | lecture globale; secrets exclus |
| POST/PUT /api/widgets/registry         | manage | ✓         | ✗   | ✗      | ✗     | change control + revue SecOps |
| POST /api/rooms                        | write  | ✓         | ✗   | ✗      | ✗     | création room via backoffice; hors v1 UI standard |

2) Sockets (Rooms) — Events

| Event              | Direction | superuser | ops | viewer | agent | Notes |
|--------------------|-----------|-----------|-----|--------|-------|-------|
| join_room          | emit      | ✓         | ✓   | ✗(1)   | ✓(2)  | (1) viewer join lecture-only via policy explicite; (2) agent limité à rooms autorisées |
| leave_room         | emit      | ✓         | ✓   | ✓      | ✓     | doit correspondre à une session active |
| agent_message      | emit      | ✓         | ✗   | ✗      | ✓(3)  | (3) capability emit:room_message requise; scoping par room_id |
| system_update      | emit      | ✓         | ✓   | ✗      | ✗     | émis par système/ops; lecture autorisée selon read:room_updates |
| join_room          | read      | ✓         | ✓   | ✓(policy) | ✓ | réception d’événements d’adhésion |
| agent_message      | read      | ✓         | ✓   | ✓(policy) | ✓ | diffusion scoping par room |
| system_update      | read      | ✓         | ✓   | ✓(policy) | ✓ | notifications système (ex: tour de parole) |

3) Widgets (via WidgetHost)

| Opération WidgetHost           | Action    | superuser | ops | viewer | agent | Notes |
|--------------------------------|-----------|-----------|-----|--------|-------|-------|
| mount(widget)                  | manage    | ✓         | ✓   | ✓      | ✓     | deny-by-default si capabilities incompatibles |
| postMessage → widget:read:*    | read      | ✓         | ✓   | ✓      | ✓     | filtrage par origin + schéma |
| postMessage → widget:emit:*    | emit      | ✓         | ✓   | ✓      | ✓     | seulement si déclaré dans registry |
| postMessage → widget:write:*   | write     | ✓(4)      | ✗   | ✗      | ✗     | (4) rare; exige capability explicite + revue SecOps + log renforcé |

---

## 7) Évaluation des décisions (algorithme minimal)

Ordre d’évaluation:
1) AuthN: identité valide (token/session) + intégrité (SECURITY_BASELINES: session binding, CSRF, nonce).
2) Rôle: rôle principal (superuser|ops|viewer|agent) dérivé de l’identité.
3) Capabilities: union des capabilities (rôle + spécifiques, ex: widget_registry, per-agent).
4) Ressource: correspondance endpoint/event + action (read/write/emit/manage).
5) Scope: contraintes de ressource (agent slug, room_id, tenant, origin widget, time window).
6) Décision: allow si et seulement si toutes les conditions sont remplies; sinon deny.
7) Journalisation: log structuré + event (ex: error:occurred pour violations critiques) avec correlation_id.

Pseudo-exemple de décision (log “AccessDecision”):
```json
{
  "ts": "2025-10-13T06:31:00Z",
  "actor": { "id": "user_su_001", "role": "superuser" },
  "action": "write:chat",
  "resource": "/api/agents/jared/chat",
  "scope": { "agent_slug": "jared" },
  "capabilities_checked": ["write:chat"],
  "decision": "allow",
  "correlation_id": "a6dd8c0b-4b79-4f85-8b69-2e5a5d7c5a3f",
  "policy_version": "rbac_v1",
  "reasons": ["role superuser", "capability write:chat", "scope ok"],
  "hash_prev": "…",
  "hash_curr": "…"
}
```

Exemple de deny (ops tentant de chatter):
```json
{
  "ts": "2025-10-13T06:31:20Z",
  "actor": { "id": "user_ops_009", "role": "ops" },
  "action": "write:chat",
  "resource": "/api/agents/jared/chat",
  "scope": { "agent_slug": "jared" },
  "capabilities_checked": ["write:chat"],
  "decision": "deny",
  "correlation_id": "9b9f9a44-5f31-4d7c-9f61-1f2b7b0b6a91",
  "policy_version": "rbac_v1",
  "reasons": ["role ops lacks write:chat"],
  "hash_prev": "…",
  "hash_curr": "…"
}
```

---

## 8) Exigences de sécurité (gates)

- CSRF & Session binding: obligatoires pour endpoints d’écriture; lier session à attributs stables (SECURITY_BASELINES).
- Anti-replay: nonce/ts pour opérations sensibles; fenêtre d’acceptation stricte.
- Journaux hashés: tous les AccessDecision et événements critiques sont chaînés (hash_prev/hash_curr).
- Origin & CSP: filtrage des postMessage et iframes Widgets; deny-by-default pour write:*.
- Rate limiting / Backpressure: quotas par acteur/ressource; stratégie de retry taxée côté sockets.
- Double gate: l’UI masque les actions non permises; le backend tranche et journalise la décision.
- Redaction: logs dépourvus de secrets; `error:occurred` redacted si nécessaire.

Gate de promotion (par sprint):
- Sprint 00: RBAC appliqué sur chat mock + lecture logs; tests verts.
- Sprint 01: RBAC front (masquage/disable) conforme à la matrice; deny-by-default côté widgets.
- Sprint 02: RBAC sockets effectif (join/message/system); tests négatifs (write non autorisé) vérifiés.
- Sprint 03: RBAC Dashboard lecture-only pour viewer; audit d’accès KPIs.

---

## 9) Mappage rôles → capabilities (profil initial)

- superuser
  - read:* / write:* / emit:* / manage:* (tout), sous réserve des gates sécurité.
- ops
  - read:logs, read:kpis, read:room_updates, join:room (lecture), emit:system_update (restreint).
- viewer
  - read:kpis, read:room_updates (si policy join lecture-only); rien d’autre.
- agent
  - emit:chat_stream, emit:room_message (si autorisé), join:room (selon policy), read:room_updates; aucun accès logs/KPIs par défaut.

Toute capability write:* / manage:* hors superuser requiert RFC + revue SecOps.

---

## 10) Tests & conformité

- e2e (Playwright): scénarios positifs/négatifs sur chat, rooms, dashboard (voir QA_E2E.md).
- Validation de la matrice: tests d’intégration (mocks) par endpoint/event et par rôle.
- Journaux: présence de AccessDecision pour toute tentative d’accès; corrélation vérifiée.
- Schémas: EVENTS v1 utilisés pour `system:alert` et `error:occurred` sur violations graves.

---

## 11) Compatibilité & versionnage

- RBAC v1 couvre le scope Sprints 00–03.
- Changements compatibles (mineurs):
  - Ajout de capabilities read:* ou emit:* non-destructeurs.
  - Autorisations plus restrictives (jamais plus permissives sans RFC).
- Ruptures (breaking) → RBAC v2:
  - Élargissement d’accès, ajout de write:* ou manage:* à un rôle existant.
  - Modification sémantique d’une capability existante.
- Rollback documentaire:
  - Toute modification est inscrite dans “Append Log”.
  - Retour v-1 = revert Git + relance des e2e pivots.

---

## 12) Références croisées

- docs/specs/EVENTS_v1.md — événements, champs communs, anti-replay, journaux.
- docs/specs/SECURITY_BASELINES.md — CSRF, session binding, nonce, logs hashés, CSP.
- docs/specs/WIDGET_REGISTRY.md — registre global des widgets, capabilities, statut.
- docs/specs/COCKPIT_TEMPLATE_v1.md — UI, lifecycle, WidgetHost.
- docs/specs/SOCKETS_BRIDGE_v1.md — events sockets rooms, scoping, sécurité.
- docs/specs/DASHBOARD_v1.md — KPIs, sources, accès lecture-only.

---

## Append Log

- 2025-10-13 — Alice (Lead Orchestrator): Création initiale RBAC v1 (rôles, capabilities, matrice d’accès HTTP/Sockets/Widgets, gates sécurité, tests et versionnage).
