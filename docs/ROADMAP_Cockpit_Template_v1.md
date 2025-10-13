# ROADMAP — Cockpit Template v1 (Consolidé Sprints 00→03)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Stack cockpit: Nuxt 4 + Tailwind 4
Référence gouvernance: docs/specs/GOVERNANCE_v1.md

Ce document consolide la vision et le phasage des sprints 00→03 pour livrer:
1) Un backbone minimal sécurisé (événements v1, RBAC v1, logs corrélés, registre de widgets).
2) Un Cockpit Template v1 standardisé (chat user↔agent + host de widgets).
3) Des Conference Rooms v1 (structure + sockets bridge minimal).
4) Un Global Dashboard v1 (KPIs essentiels “en un coup d’œil”).

Chemins cibles des documents:
- docs/roadmaps/Sprint_00_Backbone.md
- docs/roadmaps/Sprint_01_Cockpit_Template.md
- docs/roadmaps/Sprint_02_Conference_Rooms.md
- docs/roadmaps/Sprint_03_Global_Dashboard.md
- docs/specs/EVENTS_v1.md
- docs/specs/RBAC_v1.md
- docs/specs/WIDGET_REGISTRY.md
- docs/specs/SECURITY_BASELINES.md
- docs/specs/COCKPIT_TEMPLATE_v1.md
- docs/specs/ROOMS_v1.md
- docs/specs/SOCKETS_BRIDGE_v1.md
- docs/specs/DASHBOARD_v1.md
- docs/specs/GOVERNANCE_v1.md
- docs/checklists/QA_E2E.md

---

## 1) Contexte & Objectifs

- Vision: un socle minimal standardisé pour opérer des agents de façon sécurisée, traçable et extensible via des widgets sandboxés.
- Objectifs stratégiques:
  - Établir un protocole d’événements v1, un RBAC minimal, une journalisation corrélable et un registre global de widgets.
  - Livrer un cockpit template standard (Nuxt 4 + Tailwind 4) avec chat, stream et host de widgets.
  - Préparer des Conference Rooms multi-participants avec bridge sockets minimal et tour de parole.
  - Exposer un Global Dashboard v1 avec KPIs essentiels et alertes basiques.

Garde-fous obligatoires:
- Standardisation: protocole d’événements v1, registre de widgets, RBAC minimal.
- Logs corrélables: tout message/action → event + log avec correlation_id.
- Deny-by-default côté widgets: aucune action “write” sans capability explicite.
- Tests e2e dès Sprint 1: chat + mount widget factice.
- Docs vivantes en .md, appendables, avec “Append Log”.

---

## 2) Périmètre & Non-Objectifs

- In-scope:
  - Spécs, roadmaps, checklists, exemples JSON, contrats d’intégration.
  - API mock pour chat et stream (backend minimal ou simulé).
  - Cockpit front template (UI skeleton + contrats).
  - Sockets bridge minimal (events, scoping, sécurité).
  - KPIs et requêtes de base pour dashboard.

- Out-of-scope (v1):
  - Widgets métiers avancés (seulement un widget factice pour tests).
  - Optimisations UI/UX poussées ou design system complet.
  - Observabilité complexe (traces distribuées avancées).
  - Infra prod hardened (WAF/CDN avancés) au-delà des baselines sécurité documentées.

---

## 3) Standards transverses (Backbone minimal)

- Protocole d’événements v1 (docs/specs/EVENTS_v1.md):
  - Événements obligatoires: chat:user_message, chat:agent_stream, widget:update, system:alert, metrics:tick, error:occurred.
  - Champs communs: type, ts, actor, room?, thread_id, correlation_id, payload, sig?.
  - Versionnage, compat ascendante, exemples canoniques JSON.

- RBAC v1 (docs/specs/RBAC_v1.md):
  - Rôles: superuser, ops, viewer, agent.
  - Matrix endpoints × rôles (read/write).
  - Principe: least privilege par défaut.

- Registre des widgets (docs/specs/WIDGET_REGISTRY.md):
  - widget_registry.json (schema validable jsonschema/zod).
  - Capabilities explicites (read:*, emit:*, write:*), status alpha|beta|stable.
  - Owner, scope, deps, version semver.

- Baselines sécurité (docs/specs/SECURITY_BASELINES.md):
  - CSRF, session binding, nonce anti-replay.
  - Logs hashés, champs structurés (niveau, source, IP/UA, correlation_id).
  - Deny-by-default pour widgets; sandbox (iframe/CSP), nonces, origin checks.

---

## 4) RACI minimal

- Lead Orchestrator: Alice — décide du scope, des gates sécurité, de la cohérence inter-sprints.
- Backend: responsable endpoints mock, event bus, logs corrélés, sockets bridge minimal.
- Frontend: responsable Cockpit Template (Nuxt 4 + Tailwind 4), host de widgets, stream rendering.
- SecOps: responsable baselines, RBAC, revues sécurité et journaux.
- QA: responsable QA_E2E.md, scénarios e2e Playwright, oracles de validation.

---

## 5) Plan de jalons (Sprints 00→03)

- Sprint 00 — Backbone minimal
  - DoD: EVENTS v1 versionné + exemples; RBAC appliqué (endpoints chat mock + lecture logs); widget_registry.json validé; 1 test e2e: POST chat → log corrélé → event stream conforme.

- Sprint 01 — Cockpit Template v1
  - DoD: Template figé (layout + composants + contrats); test e2e: superuser → cockpit {agent} → envoi message → stream reçu → widget factice monté.

- Sprint 02 — Conference Rooms v1
  - DoD: Contrats et exemples de création/connexion room; test e2e: 2 agents simulés + 1 humain → diffusion message contextualisé conforme.

- Sprint 03 — Global Dashboard v1
  - DoD: KPIs définis + requêtes; test e2e: rendu 4 KPIs factices + 1 alerte simulée.

---

## 6) Synthèse par Sprint (détails opérationnels)

### Sprint 00 — Backbone minimal
- But du sprint
  - Poser la colonne vertébrale: événements v1, RBAC v1, logs corrélés, registre widgets.
- Livrables
  - docs/specs/EVENTS_v1.md
  - docs/specs/RBAC_v1.md
  - docs/specs/WIDGET_REGISTRY.md
  - docs/specs/SECURITY_BASELINES.md
  - docs/checklists/QA_E2E.md
  - docs/roadmaps/Sprint_00_Backbone.md
- Plan de tests
  - e2e Playwright: POST /api/agents/{slug}/chat (mock) → vérifier log corrélé + event chat:agent_stream conforme.
  - Validation schema widget_registry.json.
- Sécurité (gates)
  - RBAC enforced pour endpoints chat mock + lecture logs.
  - Logs hashés et correlation_id requis.
- Checklist d’avancement
  - [ ] Spécs événements v1 validées (exemples canoniques).
  - [ ] RBAC v1 implémenté (deny-by-default).
  - [ ] Registre widgets + schéma de validation.
  - [ ] Baselines sécurité approuvées SecOps.
  - [ ] Test e2e backbone passe.
  - [ ] DoD atteint.
- Risques & Mitigations
  - Ambiguïté champs d’événements → exemples exhaustifs + jsonschema.
  - Fuite capabilities widget → deny-by-default + review SecOps.

### Sprint 01 — Cockpit Template v1 (Nuxt 4 + Tailwind 4)
- But du sprint
  - Livrer une page template standardisée: chat + zone widgets + métriques minimales.
- Livrables
  - docs/roadmaps/Sprint_01_Cockpit_Template.md
  - docs/specs/COCKPIT_TEMPLATE_v1.md
  - Composants (spécifiés): ChatPanel, WidgetHost, MessageStream, MetricsStrip.
- Plan de tests
  - e2e: superuser ouvre cockpit d’un agent; envoie message; stream s’affiche; widget factice mount(); deny-by-default vérifiée (aucun write sans capability).
- Sécurité (gates)
  - WidgetHost sandbox + CSP; isolation de contexte (loadContext).
  - Propagation correlation_id front→backend pour chaque action.
- Checklist d’avancement
  - [ ] Layout figé (Header/Main/Aside).
  - [ ] Contrats intégration composants.
  - [ ] Lifecycle widgets (idle → connecting → ready → error → reconnecting).
  - [ ] e2e chat + mount widget factice.
  - [ ] DoD atteint.
- Risques & Mitigations
  - Incompat Nuxt 4/Tailwind 4 → starter minimal + lint CI.
  - Fuites de contexte widget → API restreinte + typesafe.

### Sprint 02 — Conference Rooms v1
- But du sprint
  - Préparer multi-participants: structure Room, rôles, sockets bridge minimal.
- Livrables
  - docs/roadmaps/Sprint_02_Conference_Rooms.md
  - docs/specs/ROOMS_v1.md
  - docs/specs/SOCKETS_BRIDGE_v1.md
- Plan de tests
  - e2e: 2 agents simulés + 1 humain; join_room; envoi agent_message; réception contextualisée; logs de room ≥ events.
- Sécurité (gates)
  - Scoping sockets par room + token + rôle; backpressure + retry.
  - Journalisation join/leave + anomalies (rate limit, flood).
- Checklist d’avancement
  - [ ] Modèles ConferenceRoom/RoomParticipant.
  - [ ] Événements sockets: join_room, leave_room, agent_message, system_update.
  - [ ] Bridge sockets minimal (auth, scoping).
  - [ ] e2e room passe.
  - [ ] DoD atteint.
- Risques & Mitigations
  - Épuisement sockets → backpressure + quotas.
  - Usurpation room → signatures/sig? + validation rôle.

### Sprint 03 — Global Dashboard v1
- But du sprint
  - KPIs “en un coup d’œil”: volume messages (24h), erreurs/criticity, latence moyenne stream, rooms actives.
- Livrables
  - docs/roadmaps/Sprint_03_Global_Dashboard.md
  - docs/specs/DASHBOARD_v1.md
- Plan de tests
  - e2e: rendu 4 KPIs factices + 1 alerte seuil simulée.
- Sécurité (gates)
  - RBAC lecture-only pour viewer; accès restreint aux sources KPIs.
- Checklist d’avancement
  - [ ] KPIs définis (sources, agrégation, seuils).
  - [ ] Requêtes/contrats d’accès.
  - [ ] e2e KPIs + alerte.
  - [ ] DoD atteint.
- Risques & Mitigations
  - Qualité données KPIs → mocks + contrats + oracles QA.

---

## 7) Stratégie de tests & Qualité

- e2e (Playwright), dès Sprint 00/01:
  - Scénario pivot: user superuser → cockpit agent → POST chat → stream affiché → widget factice mount().
  - Oracles de validation: conformité EVENTS v1, présence correlation_id, RBAC effectif.
- Intégration:
  - Validation JSON schemas (events, widget_registry.json).
  - Contrats sockets (join_room/agent_message).
- Non-régression:
  - Snapshots d’exemples JSON canoniques.
  - Checklists QA (docs/checklists/QA_E2E.md).

---

## 8) Observabilité & Journalisation

- Logs structurés: level, ts, source, actor, IP/UA, room?, thread_id, correlation_id, event_type, hash.
- Corrélation: correlation_id propagate front↔backend↔sockets.
- Sécurité journaux: hashing tamper-evident, stockage append-only là où possible.
- Alertes minimales: system:alert + seuils KPIs.

---

## 9) Widget Registry — Gouvernance

- Process d’ajout:
  - Déclarer id, version semver, owner, scope, deps, status.
  - Capabilities explicites; deny-by-default si absent.
  - Validation via jsonschema/zod + revue SecOps pour capabilities write:*.
- Compatibilité:
  - Contract stable par version de widget; breaking → major bump.
- Observabilité:
  - Événements widget:update; audit mount/unmount.

---

## 10) Versionnage, Compatibilité & Rollback

- EVENTS v1:
  - Ajouts compatibles en mineur; breaking en major (v2).
  - Exemples canoniques versionnés dans docs/specs/EVENTS_v1.md.
- RBAC v1:
  - Nouveau rôle/capability → review SecOps + QA e2e.
- Rollback documentaire:
  - Toute spec modifiée → entrée “Append Log” + tag version dans en-tête de la spec.
  - Procédure de retour à v-1: revert Git + restauration des exemples canoniques + rerun e2e pivot.

---

## 11) Dépendances critiques & Risques transverses

- Dépendances:
  - Nuxt 4, Tailwind 4 pour front.
  - Playwright pour e2e.
  - jsonschema/zod pour validations.
  - Sockets (WS) pour rooms.
- Risques:
  - Dérive des contrats → verrouiller exemples canoniques + CI de schemas.
  - Érosion sécurité → gates sprint + revue SecOps obligatoire.
  - Flaky e2e → stabilisation données/mocks, timeouts maîtrisés.

---

## 12) Critères d’acceptation globaux (00–01)

- Tous les .md existent aux chemins listés, remplis avec sections, exemples et checklists.
- Protocole EVENTS v1 documenté + exemples JSON cohérents.
- RBAC v1 défini + matrice d’accès initiale.
- Widget registry défini + schéma validable.
- Cockpit Template v1 documenté (UI + lifecycle + API WidgetHost).
- QA e2e: scénario “chat user→agent (mock) + mount widget factice” prêt et jouable.
- Chaque doc comporte un “Append Log”.

---

## 13) Pistes d’implémentation (contrats & endpoints)

- Chat mock:
  - POST /api/agents/{slug}/chat → enregistre log corrélé → émet chat:user_message + chat:agent_stream (mock stream).
- Logs lecture:
  - GET /api/logs?correlation_id=... (RBAC: superuser|ops).
- Sockets bridge:
  - Namespace /rooms; events: join_room, leave_room, agent_message, system_update; token + rôle requis.
- Cockpit Template (Nuxt 4):
  - ChatPanel → POST → écoute MessageStream (SSE/WS).
  - WidgetHost API: mount(), unmount(), loadContext(project|agent); sandbox + CSP; deny-by-default write.

---

## 14) Suivi & Gouvernance

- Revue hebdo: état checklists sprints; incidents sécurité; couverture e2e.
- Gates de promotion:
  - Aucune promotion si gate sécurité échoue (CSRF, nonce, RBAC, logs hashés).
  - Aucune promotion si e2e pivot échoue.

---

## Append Log

- 2025-10-13 – Alice (Lead Orchestrator) – Création initiale du roadmap consolidé Sprints 00→03, ajout des garde-fous sécurité et des DoD par sprint, définition du scénario e2e pivot.
