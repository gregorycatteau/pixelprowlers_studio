# ROADMAP — Cockpit Template v1 (Master)
Consolidation des Sprints 00 → 03 • Stack front: Nuxt 4 + Tailwind 4 • Hardened v1: uuidv7 (correlation_id/trace_id), idempotency_key (uuidv7), widgets internalOnly, CSP stricte, rétention logs 90j, gap_request, CI gates
Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Références: ../specs/GOVERNANCE_v1.md

Ce document est la vue mère qui consolide la vision, les livrables et les gates de sécurité des quatre sprints permettant d’atterrir:
1) Un Backbone minimal sécurisé (événements v1, RBAC v1, logs corrélés, registre de widgets).
2) Un Cockpit Template v1 standardisé (chat user↔agent + host de widgets).
3) Des Conference Rooms v1 (structure + sockets bridge minimal).
4) Un Global Dashboard v1 (KPIs essentiels “en un coup d’œil”).

— Tous les contrats et checklists référencés sont “appendables” et versionnés.

-----------------------------------------------------------------------

## Table des liens (documents source)

- Roadmaps par sprint
  - Sprint 00 — Backbone minimal: ../roadmaps/Sprint_00_Backbone.md
  - Sprint 01 — Cockpit Template v1: ../roadmaps/Sprint_01_Cockpit_Template.md
  - Sprint 02 — Conference Rooms v1: ../roadmaps/Sprint_02_Conference_Rooms.md
  - Sprint 03 — Global Dashboard v1: ../roadmaps/Sprint_03_Global_Dashboard.md

- Spécifications (contrats)
  - EVENTS v1: ../specs/EVENTS_v1.md
  - RBAC v1: ../specs/RBAC_v1.md
  - WIDGET_REGISTRY: ../specs/WIDGET_REGISTRY.md
  - SECURITY_BASELINES: ../specs/SECURITY_BASELINES.md
  - COCKPIT_TEMPLATE v1: ../specs/COCKPIT_TEMPLATE_v1.md
  - ROOMS v1: ../specs/ROOMS_v1.md
  - SOCKETS_BRIDGE v1: ../specs/SOCKETS_BRIDGE_v1.md
  - DASHBOARD v1: ../specs/DASHBOARD_v1.md

- QA & Tests
  - QA E2E — Checklist v1: ../checklists/QA_E2E.md

-----------------------------------------------------------------------

## 1) Contexte & Objectifs

- Vision
  - Offrir un cockpit agent standardisé et extensible par widgets sandboxés, opéré sur un socle sécurisé, traçable et observable.
- Objectifs stratégiques
  - Standardiser et versionner le protocole d’événements (EVENTS v1).
  - Définir et appliquer un RBAC minimal (RBAC v1) sur endpoints, sockets, et widgets.
  - Assurer une journalisation corrélable et inviolable (hash chain).
  - Encadrer l’extensibilité via un registre de widgets avec capabilities explicites (deny-by-default).
  - Livrer un template cockpit v1 (chat + stream + WidgetHost) puis des conference rooms v1 et un dashboard global v1.

- Garde-fous
  - Standardisation obligatoire (EVENTS v1, RBAC v1, Widget Registry).
  - Tout message/action → event + log avec correlation_id.
  - Deny-by-default pour toute capability write côté widgets.
  - Tests e2e dès Sprint 1 (chat + mount widget factice).
  - Documents vivants (.md) avec “Append Log”.

-----------------------------------------------------------------------

## 2) Périmètre & Non-objectifs

- In-scope v1
  - Contrats documentés, exemples JSON canoniques, schémas de validation (jsonschema/zod).
  - API mock chat/stream, sockets bridge minimal (rooms).
  - Cockpit Template v1 (Nuxt 4 + Tailwind 4): ChatPanel, MessageStream, WidgetHost, MetricsStrip.
  - Dashboard v1: 4 KPIs + 1 alerte simulée.

- Out-of-scope v1
  - Widgets métiers riches (seulement un widget factice read-only).
  - Design system avancé/branding complet.
  - Observabilité distribuée avancée (tracing fin).
  - Hardening infra prod (au-delà des baselines de sécurité posées).

-----------------------------------------------------------------------

## 3) Standards transverses (Backbone)

- EVENTS v1 (contrat)
  - Types obligatoires: chat:user_message, chat:agent_stream, widget:update, system:alert, metrics:tick, error:occurred.
  - Champs communs: type, ts, actor, room?, thread_id, correlation_id, payload, sig?.
  - Validation par schémas + exemples canoniques.

- RBAC v1 (matrice initiale)
  - Rôles: superuser, ops, viewer, agent.
  - Endpoints/sockets/widgets mappés à des capabilities explicites (least privilege).

- Widget Registry
  - Contract `widget_registry.json` validé; capabilities explicites; scope agent; status (alpha|beta|stable).
  - Deny-by-default pour write:* (dérogation via RFC sécurité uniquement).

- Security Baselines
  - CSRF, session binding, anti-replay (nonce/ts/sig), logs hashés (hash_prev/hash_curr), CSP stricte & sandbox widgets.

Références: ../specs/EVENTS_v1.md • ../specs/RBAC_v1.md • ../specs/WIDGET_REGISTRY.md • ../specs/SECURITY_BASELINES.md

-----------------------------------------------------------------------

## 4) Synthèse Sprints (objectifs, livrables, DoD)

- Sprint 00 — Backbone minimal
  - But: socle commun (EVENTS v1, RBAC v1, logs corrélés, registry).
  - Livrables: specs backbone + QA plan.
  - DoD: schémas/events validés; RBAC appliqué (chat mock + lecture logs); registry validé; 1 e2e “POST chat → log corrélé → stream conforme”.
  - Détails: ../roadmaps/Sprint_00_Backbone.md

- Sprint 01 — Cockpit Template v1
  - But: page template standardisée (chat + stream + zone widgets + métriques).
  - Livrables: spec COCKPIT_TEMPLATE v1; contrats composants.
  - DoD: layout + composants + contrats figés; e2e superuser → cockpit Jared → message → stream → widget factice mount().
  - Détails: ../roadmaps/Sprint_01_Cockpit_Template.md

- Sprint 02 — Conference Rooms v1
  - But: structure room, rôles participants, sockets bridge minimal, tour de parole.
  - Livrables: ROOMS v1, SOCKETS_BRIDGE v1; scénarios e2e multi-clients.
  - DoD: création/connexion room documentées; e2e “2 agents + 1 humain → diffusion contextualisée conforme”.
  - Détails: ../roadmaps/Sprint_02_Conference_Rooms.md

- Sprint 03 — Global Dashboard v1
  - But: KPIs (volume 24h, erreurs, latence stream, rooms actives) + alerte.
  - Livrables: DASHBOARD v1 (défs + sources + seuils).
  - DoD: 4 KPIs factices rendus + 1 alerte simulée; schémas validés.
  - Détails: ../roadmaps/Sprint_03_Global_Dashboard.md

-----------------------------------------------------------------------

## 5) Gates sécurité par sprint (promotion)

- Gate commun (tous sprints)
  - Validation schémas (EVENTS/registry/rooms/sockets/KPIs) sans erreurs.
  - Logs corrélés (correlation_id) + chainage de hash vérifié.
  - Aucune capability write:* non autorisée côté widgets.

- Sprint 00
  - RBAC v1 effectif sur chat mock (write) et lecture logs (read).
  - e2e Backbone → PASS.

- Sprint 01
  - RBAC UI (masquage/disable) conforme; CSP/sandbox widgets sans violation.
  - e2e Cockpit → PASS.

- Sprint 02
  - AuthZ sockets: deny-by-default; backpressure/retry testés.
  - e2e Rooms → PASS.

- Sprint 03
  - RBAC lecture-only pour viewer sur KPIs; throttling KPIs actif.
  - e2e Dashboard → PASS.

Références: ../specs/SECURITY_BASELINES.md • ../checklists/QA_E2E.md

-----------------------------------------------------------------------

## 6) Stratégie QA & E2E

- Scénarios pivots (Playwright)
  - E2E-00: POST chat → log corrélé → stream conforme.
  - E2E-01: superuser → cockpit Jared → message → stream → widget mount.
  - E2E-02: 2 agents + 1 humain → join_room → agent_message → diffusion contextualisée.
  - E2E-03: Dashboard → 4 KPIs + 1 alerte simulée.

- Négatifs sécurité (extraits)
  - CSRF manquant; viewer tente write chat; sockets cross-room; anti-replay; origin WS invalide; throttling KPIs.

- Oracles
  - Conformité EVENTS v1; RBAC decisions logguées; logs hash chain OK; CSP sans violation; KPIs cohérents.

Détails: ../checklists/QA_E2E.md

-----------------------------------------------------------------------

## 7) RACI minimal (pilotage)

- Lead Orchestrator (Alice)
  - Scope et cohérence inter-sprints, gates sécurité, arbitrage standardisation.
- Backend
  - Endpoints mock, bus d’événements, sockets bridge, journaux corrélés.
- Frontend
  - Cockpit Template (Nuxt 4 + Tailwind 4), WidgetHost, rendu stream, Dashboard v1.
- SecOps
  - Baselines, RBAC policies, revue capabilities widgets, audit journaux.
- QA
  - QA_E2E.md, scénarios e2e, oracles, tests négatifs sécurité.

-----------------------------------------------------------------------

## 8) Planning & Jalons (indicatif)

- S00 (Backbone): Semaine 1 → Schémas + RBAC + journaux + 1 e2e pivot.
- S01 (Cockpit): Semaines 2–3 → Template + contrats + e2e cockpit + CSP sans violation.
- S02 (Rooms): Semaines 4–5 → Modèles + Bridge + e2e rooms (multi-clients) + backpressure/retry.
- S03 (Dashboard): Semaine 6 → KPIs + alerte + e2e dashboard + RBAC viewer lecture-only.

Chaque jalon exige gates sécurité PASS avant promotion.

-----------------------------------------------------------------------

## 9) Risques & Mitigations

- Dérive des contrats / non-conformité schémas
  - CI validation schémas + exemples canoniques; revues multi-disciplinaires.
- Évasion sandbox / escalade via widgets
  - CSP stricte, origin allowlist, deny-by-default write:*, validation postMessage, audit mount/update.
- Corrélation lacunaire
  - Middleware correlation_id; e2e vérifiant bout-en-bout; refus de promotion si absent.
- Flaky e2e (streams/sockets)
  - Mocks déterministes, backoff contrôlé, assertions robustes, temps limites documentés.
- Charge/abus (KPIs / sockets)
  - Throttling, quotas, backpressure, cache + ETag, alerting `system:alert`.

-----------------------------------------------------------------------

## 10) Versionnage & Rollback documentaire

- Versionnage
  - EVENTS/RBAC/REGISTRY/ROOMS/SOCKETS/DASHBOARD sont v1; breaking → v2 + plan de migration.
- Rollback
  - Revert Git vers v-1 de la spec concernée; restaurer exemples canoniques; relancer e2e pivots; maj “Append Log”.

Références: ../specs/EVENTS_v1.md • ../specs/RBAC_v1.md • ../specs/WIDGET_REGISTRY.md • ../specs/ROOMS_v1.md • ../specs/SOCKETS_BRIDGE_v1.md • ../specs/DASHBOARD_v1.md

-----------------------------------------------------------------------

## 11) Critères d’acceptation globaux (Sprints 00–01 priorité)

- Tous les .md existent et sont remplis avec sections, exemples et checklists.
- Protocole EVENTS v1 documenté + exemples JSON cohérents.
- RBAC v1 défini + matrice d’accès initiale; appliqué sur endpoints chat mock + lecture logs.
- Widget Registry défini + schéma validable; deny-by-default write:*.
- Cockpit Template v1 documenté (UI + lifecycle + API WidgetHost).
- QA e2e: scénario “chat user→agent (mock) + mount widget factice” prêt et jouable.
- “Append Log” présent dans chaque doc.

-----------------------------------------------------------------------

## 12) Comment utiliser ce roadmap (mises à jour)

- À chaque changement de contrat, mettre à jour:
  - La spec concernée (section “Compatibilité & versionnage”) + Append Log.
  - La roadmap du sprint affecté (gates/checklists).
  - La checklist QA (ajout/ajustement des scénarios et oracles).
- Toute extension de capabilities (surtout write:* / manage:*) passe par une RFC sécurité et des tests négatifs dédiés.

-----------------------------------------------------------------------

## Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création du master ROADMAP consolidant S00→S03; ajout des liens vers specs et QA; formalisation des gates sécurité, critères globaux et procédures de rollback.
