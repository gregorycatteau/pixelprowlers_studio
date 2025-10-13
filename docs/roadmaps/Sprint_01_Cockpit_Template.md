# Sprint 01 — Cockpit Template v1 (Nuxt 4 + Tailwind 4)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Périmètre: page Cockpit standardisée (agent individuel) incluant Chat, Host de widgets, Stream messages, Bandeau métriques.
Contraintes transverses: EVENTS v1, RBAC v1, logs corrélés avec correlation_id, deny-by-default côté widgets, docs vivantes.
Références: docs/specs/GOVERNANCE_v1.md

---

## But du sprint
Livrer un template de cockpit standardisé, réutilisable pour tous les agents, intégrant:
- Un Chat opérateur→agent basé sur le POST /api/agents/{slug}/chat (mock stream).
- Un WidgetHost sandboxé (API: mount, unmount, loadContext) avec deny-by-default pour toute capability write.
- Un MessageStream abonné aux événements chat:agent_stream (bufferisation + fold).
- Un MetricsStrip affichant latence moyenne, erreurs récentes, rôle courant, état de connexion.
- Des contrats d’intégration figés (UI, lifecycle, événements, RBAC surface côté front).

---

## Livrables
- docs/roadmaps/Sprint_01_Cockpit_Template.md — ce document.
- docs/specs/COCKPIT_TEMPLATE_v1.md — définition du layout, slots/sections, lifecycle et API de WidgetHost.
- Spécification des composants (SQUELETTE UI, standardisés, extensibles):
  - ChatPanel: champ input, history minimal, envoie le POST /api/agents/{slug}/chat, affiche l’accusé (correlation_id).
  - MessageStream: écoute et rend les events chat:agent_stream (chunks), buffer fold avec grouping par correlation_id/thread_id.
  - WidgetHost: API mount(), unmount(), loadContext(project|agent); sandbox (iframe/CSP), deny-by-default write.
  - MetricsStrip: latence (p50/p90 stream), taux d’erreur (5m), rôle courant, statut sockets/transport.
- Contrats d’intégration et exemples:
  - Conformité aux champs communs EVENTS v1: type, ts, actor, room?, thread_id, correlation_id, payload, sig?.
  - Mapping UI ↔ endpoints/socket (POST chat, flux stream SSE/WS).
- Checklists et critères:
  - DoD figé (ci-dessous).
  - Scénarios e2e (Playwright) prêts et jouables.

---

## Plan de tests
- e2e (Playwright)
  - Scénario pivot “superuser → cockpit Jared → message → stream → widget factice monté”
    - Authentification: user avec rôle superuser.
    - Action: ouvrir le cockpit d’un agent (ex: slug = jared).
    - Action: envoyer un message via ChatPanel; POST /api/agents/jared/chat.
    - Attendus:
      - Réponse 2xx contenant un correlation_id.
      - MessageStream affiche au moins 2 chunks de chat:agent_stream corrélés.
      - MetricsStrip met à jour latence moyenne et compteur d’erreurs (0 si succès).
      - Un widget factice ayant capability read:* uniquement est mount() avec loadContext(agent="jared"); aucune action write possible.
      - Journaux côté front incluent correlation_id sur chaque interaction clé (émission chat, réception stream, mount widget).
- Tests d’intégration
  - Conformité EVENTS v1: parsing strict des champs communs; rejet si un champ critique manque (au minimum type, ts, correlation_id, payload).
  - RBAC front: contrôle d’affichage/activation d’actions selon rôle (superuser peut chatter; viewer lecture-only; ops lecture + diagnostics; agent accès restreint).
  - WidgetHost sandbox: vérification CSP (no inline), intégrité (SRI le cas échéant), isolation d’origine, filtrage postMessage par origin autorisée.
  - Propagation correlation_id: du POST à chaque chunk de stream et aux logs front.
- Non-régression
  - Snapshots UI minimaux pour ChatPanel/MessageStream (états: idle, connecting, streaming, error, reconnecting).
  - Vérification du lifecycle widget (mount → ready → unmount) sur navigation/rafraîchissement.

---

## Sécurité (gates)
- RBAC v1 (least privilege)
  - Règles d’usage côté front:
    - superuser: chat write, lecture stream, accès logs/metrics cockpit.
    - ops: lecture stream, metrics, diagnostics lecture-only (pas de chat write).
    - viewer: lecture stream (si autorisé), pas d’actions; masquage ChatPanel.
    - agent: accès restreint selon policy (par défaut pas de write, ni privilèges sensibles).
- CSRF & Session binding pour POST chat
  - Utiliser cookies same-site strict (ou token CSRF signé) et lier la session à des attributs stables (ex: device key/UA partiel).
- Anti-replay (frontend-side)
  - Nonce unique par requête POST; stockage court-terme; rejet si duplication détectée dans un intervalle court.
- Journaux front corrélables
  - Tous les événements UI critiques loggués avec: ts, actor (user id/role), route, component, action, correlation_id, thread_id?, result, err?.
- Sandbox & CSP
  - Widgets internes only (internalOnly: true); aucune origin externe autorisée; CSP host minimale: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; iframe sandbox="allow-scripts allow-same-origin".
  - PostMessage strict: schéma obligatoire { type, nonce, origin, capability, payload, correlation_id }; origin ∈ allowlist interne; contrôle capability à chaque message; types inconnus/origins non autorisées → reject + log sécurité.
- Capabilities widgets
  - Aucune capability write:* autorisée par défaut; lecture explicitement déclarée; vérification à mount(); refus si mismatch capability/scope.
- Transport stream
  - Préférence SSE pour simplicité; fallback WS documenté; backoff exponentiel et jitter; limites de reconnection.

Gate de promotion Sprint 01:
- e2e pivot “superuser → cockpit Jared → message → stream → widget mount” vert en CI.
- CSP/sandbox vérifiés (aucune violation console en mode strict).
- Widgets internalOnly: registre avec internalOnly=true; aucune origin/URL externe autorisée.
- PostMessage strict: schéma + contrôle capability à chaque message; tests négatifs pass.
- Robustesse stream: gap_request (rattrapage chunks manquants) et réordonnancement par chunk_index validés.
- RBAC front effectif (UI et actions) selon matrix.
- Journaux front montrent un correlation_id stable et traçable bout-en-bout.

---

## Checklist d’avancement
- [ ] Layout cockpit figé: Header (status/agent select) / Main (ChatPanel + WidgetHost) / Aside (logs/metrics).
- [ ] Contrats intégration composants (props/events/interfaces) documentés.
- [ ] ChatPanel: envoi POST chat avec injection/propagation correlation_id.
- [ ] MessageStream: rendu des events chat:agent_stream avec buffer/fold et regroupement par thread_id.
- [ ] WidgetHost: API mount(), unmount(), loadContext(project|agent) + sandbox/CSP + deny-by-default write.
- [ ] MetricsStrip: latence moyenne stream, compteur d’erreurs, rôle courant, statut transport (SSE/WS).
- [ ] RBAC front: masquage/disable des actions selon rôle (superuser/ops/viewer/agent).
- [ ] Scénarios e2e définis et exécutables (Playwright); données de test prêtes.
- [ ] Logs front corrélables (correlation_id présent sur actions clés).
- [ ] DoD du sprint atteint (ci-dessous).

---

## Definition of Done (DoD)
- Cockpit template v1 figé (layout + composants + contrats d’intégration).
- Test e2e: user superuser → ouvre cockpit Jared → envoie message → reçoit stream → widget factice se monte.
- RBAC front conforme à la matrice; widgets deny-by-default pour write.
- Conformité EVENTS v1: champs communs et structures d’événements respectés pour chat:user_message et chat:agent_stream.
- CSP/sandbox actifs pour WidgetHost; AUCUNE capability write:* non autorisée.
- Journaux front corrélables (correlation_id, actor, action, résultat/erreur).

---

## Risques & Mitigations
- Incompatibilités Nuxt 4 / Tailwind 4 / tooling SSR
  - Mitigation: starter minimal, désactivation progressive des features non-critiques, CI lint + build sur PR.
- Évasion sandbox widget (CSP insuffisante, postMessage non filtré)
  - Mitigation: CSP stricte, allowlist origins, schéma strict des messages, deny-by-default, audits manuels.
- Flaky stream (pertes de chunks, reconnections)
  - Mitigation: bufferisation côté client, retry/backoff, idempotence par correlation_id, tests de robustesse.
- Escalade de privilèges par l’UI
  - Mitigation: double gate (front RBAC + back RBAC), masquage + blocage actions; tests négatifs.
- Fuite de correlation_id ou mauvaise corrélation
  - Mitigation: middleware d’injection, validations dans e2e, logs structurés avec vérifications.

---

## Notes d’implémentation (guides)
- Structure UI (exemple)
  - Header: sélecteur d’agent (avec permission), état transport (SSE/WS), rôle courant.
  - Main: grille responsive 2 colonnes (ChatPanel + WidgetHost).
  - Aside: panneau compact logs récents + métriques.
- Flux chat minimal
  - Envoi: payload minimal { message, thread_id? } → POST; récup correlation_id en réponse; l’injecter dans le contexte de stream.
  - Réception: afficher chat:user_message local, puis les chunks chat:agent_stream groupés par correlation_id.
- Lifecycle composants
  - idle → connecting (init stream) → ready (reçoit) → error (affiche retry) → reconnecting (backoff).
- Observabilité
  - Console interdite en PROD; utiliser une fonction de log structurée unique; inclure correlation_id/actor/component/action.
- Accessibilité/UX
  - Focus management (chat input), shortcuts (Ctrl+Enter), état disabled selon RBAC.

---

## Données de test (e2e)
- Utilisateur: superuser (id: su_test, rôle: superuser).
- Agent: slug “jared”.
- Message test: “ping cockpit”.
- Attendus stream: au moins 2 événements chat:agent_stream, temps total de réponse < 2s (latence mesurée dans MetricsStrip).
- Widget factice: capabilities = [ "read:metrics" ], status = beta; aucun write.

---

## Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale du roadmap Sprint 01 (Cockpit Template v1), définition des composants, des gates sécurité, du scénario e2e pivot et du DoD.
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — widgets internalOnly, PostMessage strict (schéma + capability par message), tests gap_request et ordre des chunks, gates renforcés (CSP stricte, idempotency_key, uuidv7), Safe Mode documenté.
