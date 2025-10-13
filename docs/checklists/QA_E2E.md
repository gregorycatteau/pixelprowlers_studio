# QA E2E — Checklist v1

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Périmètre: Sprints 00→03 (Backbone, Cockpit Template, Conference Rooms, Global Dashboard)
Outillage de test recommandé: Playwright (e2e), jsonschema/zod (validations), parsers de logs

Ce dossier décrit les user stories couvertes, les scénarios e2e, les jeux de données, les oracles de validation, les scénarios négatifs sécurité, ainsi que les bugs connus et contournements. Tous les résultats doivent être corrélables via correlation_id et journalisés avec chaînage de hash.

---

## 1) User stories testées

- Sprint 00 — Backbone
  - En tant que superuser, je peux envoyer un message chat (mock), et je vois les événements stream conformes, corrélés à mon action.
  - En tant qu’ops, je peux consulter les logs corrélés en lecture-only.

- Sprint 01 — Cockpit Template v1
  - En tant que superuser, je peux ouvrir un cockpit d’agent, envoyer un message, voir le stream, et un widget factice se monte en sandbox (deny-by-default pour write).
  - En tant que viewer, je peux consulter le stream (si policy) mais je ne peux pas envoyer de message.

- Sprint 02 — Conference Rooms v1
  - En tant que superuser, je peux rejoindre une room avec 2 agents simulés, envoyer un message contextualisé, et observer la diffusion conforme (tour de parole minimal).
  - En tant qu’agent autorisé, je peux émettre un message dans la room si ma capability le permet.

- Sprint 03 — Global Dashboard v1
  - En tant que viewer, je peux voir 4 KPIs essentiels et je vois une alerte simulée lorsqu’un seuil est dépassé (lecture-only).

---

## 2) Scénarios e2e (détaillés)

ID: E2E-00-CHAT — POST chat → log corrélé → stream conforme
- Préconditions
  - Utilisateur authentifié rôle superuser
  - Endpoint mock POST /api/agents/{slug}/chat accessible
  - Validateurs de schémas (EVENTS v1) prêts
- Étapes
  1) POST /api/agents/jared/chat avec { message: "ping", thread_id: "th_e2e_00" }
  2) Capturer correlation_id de la réponse 2xx
  3) Souscrire au flux (SSE recommandé) et collecter chat:agent_stream (≥ 2 chunks)
  4) Récupérer le log corrélé via GET /api/logs?correlation_id={id}
- Oracles (attendus)
  - Ack: { accepted: true, correlation_id: uuid-v4 }
  - Événements: chat:user_message (écho) puis chat:agent_stream index 0..N, chunk final done=true
  - Schémas EVENTS v1 validés (ts RFC3339, actor.kind ∈ {user,agent}, correlation_id UUID v4)
  - Journaux: présence correlation_id, hash_prev/hash_curr (chaînage intact)
- Gates sécurité
  - RBAC: superuser autorisé (write:chat), ops/viewer refusés
  - CSRF/Origin valides, session binding OK

ID: E2E-01-COCKPIT — superuser → cockpit Jared → message → stream → widget mount
- Préconditions
  - Utilisateur superuser
  - Cockpit Nuxt 4/Tailwind 4 accessible /cockpits/jared
  - Widget factice présent dans widget_registry.json (capabilities: ["read:metrics"], scope incl. "jared")
- Étapes
  1) Ouvrir /cockpits/jared
  2) Envoyer "ping cockpit" via ChatPanel
  3) Observer MessageStream (≥ 2 chunks) groupés par correlation_id
  4) Vérifier MetricsStrip (latence moyenne > 0, erreurs_5m ≥ 0)
  5) Vérifier WidgetHost: mount() du widget factice + loadContext({ agent: "jared" })
- Oracles
  - Ack avec correlation_id
  - Événements chat:agent_stream valides (index monotone, chunk final done=true)
  - Aucune violation CSP dans la console (strict mode)
  - Widget:update (action=mount/state_changed) émis et validé (EVENTS v1)
  - AUCUN write:* depuis le widget (deny-by-default)
- Gates sécurité
  - RBAC UI: viewer ne voit pas/peut pas utiliser le ChatPanel
  - postMessage filtré par origin autorisée; schéma envelope OK

ID: E2E-02-ROOMS — 2 agents + 1 humain → diffusion contextualisée conforme
- Préconditions
  - Utilisateur superuser
  - Agents simulés: talia, bruce
  - Sockets bridge wss://… opérationnel; policies room actives
- Étapes
  1) superuser join_room room-abc
  2) talia join_room room-abc; bruce join_room room-abc
  3) superuser envoie agent_message "brief #245" (room-abc)
  4) Observer system_update.speaking_turn_changed (round-robin)
  5) Agents reçoivent le message; logs et events corrélés
- Oracles
  - join_room/agent_message/system_update conformes aux schémas sockets v1
  - room == payload.room_id (scoping strict)
  - correlation_id propagé sur toute la séquence
  - Journaux hashés OK; AccessDecision présent (RBAC)
- Gates sécurité
  - Deny si emit:room_message sans capability
  - Backpressure: pas de flood, pas de pertes au-delà du configurable
  - Anti-replay: messages en dehors de la fenêtre refusés

ID: E2E-03-DASHBOARD — 4 KPIs affichés + 1 alerte simulée
- Préconditions
  - Utilisateur viewer (lecture-only)
  - Endpoints KPIs mockés/stabilisés (volume24h, errors24h, latency, rooms)
- Étapes
  1) Ouvrir Dashboard
  2) Vérifier 4 cartes KPI rendues sans erreurs
  3) Simuler dépassement de seuil (errors24h.rate > threshold)
  4) Observer system:alert et statut visuel (codage couleur)
- Oracles
  - Réponses valident les schémas KPIEnvelope v1
  - Status.state aligné aux seuils (ok|warn|error)
  - system:alert conforme (severity, code, context)
  - Logs d’accès: correlation_id, latency_ms, status, hash chain
- Gates sécurité
  - RBAC viewer lecture-only
  - Throttling appliqué; pas d’accès agent

---

## 3) Données de test

- Utilisateurs
  - superuser: id=su_test, role=superuser
  - ops: id=ops_test, role=ops
  - viewer: id=viewer_test, role=viewer
- Agents
  - jared (cockpit/cible e2e), talia, bruce
- Rooms
  - room-abc (status=active, policy: { join: "invite", speak: "round_robin" })
- Messages
  - "ping", "ping cockpit", "brief #245"
- Widget factice (extrait)
  - id: "metrics_strip", version: "1.2.0", capabilities: ["read:metrics"], scope: ["jared","talia","bruce"], status: "beta"
- Paramètres sécurité (tests)
  - CSRF token valide, Origin autorisée, session_fingerprint valide
  - Fenêtre anti-replay ±5 min
- Corrélation
  - thread_id: "th_e2e_00", "th_cockpit", "th_room_abc", "th_dashboard"
  - correlation_id: généré au POST, propagé partout

---

## 4) Oracles de validation (généraux)

- EVENTS v1
  - Champs communs: type, ts(UTC RFC3339), actor, room?, thread_id, correlation_id(UUID v4), payload, sig?
  - Schémas jsonschema/zod OK; enums conformes
- Journaux
  - Présence correlation_id; hash_prev/hash_curr forment une chaîne valide sur l’intervalle du test
  - Aucune donnée sensible en clair (redaction si nécessaire)
- RBAC
  - Décisions AccessDecision logguées (allow/deny + raisons)
  - Matrix: superuser(write:chat) ✓, ops(view chat) ✗, viewer(view only) ✓, agent(write) selon capability
- Transport
  - SSE: flux recevable, index de chunk monotone, done=true unique
  - WS: origin autorisée, scoping room strict, retry/backoff contrôlé
- Sécurité
  - CSRF/Origin/Session binding valides pour toute action write
  - Anti-replay: rejets cohérents (nonce/ts)
  - CSP: aucune violation console en mode strict
- Dashboard
  - Cohérence: volume24h.total = somme(series.count), latency p90 ≥ p50, errors24h.totals cohérents

---

## 5) Scénarios négatifs (sécurité)

E2E-SEC-01 — Réseau: perte de chunk (gap_request)
- Étapes:
  1) Forcer la perte du payload.chat:agent_stream pour chunk_index=1 (ne pas l’émettre côté mock).
  2) Le client détecte le trou (chunks reçus: 0 puis 2) et envoie un gap_request { correlation_id, thread_id, missing: [1] }.
  3) Le serveur renvoie les événements manquants avec payload.chunk_index=1.
- Oracles:
  - Le flux reconstitué est {0,1,2} avec final=true uniquement sur le dernier chunk.
  - Aucune duplication; idempotence respectée sur correlation_id + chunk_index.
  - Logs: présence correlation_id/trace_id/span_id; pas d’erreur irréversible; system:alert absent.

E2E-SEC-02 — Ordre: inversion de deux chunks
- Étapes:
  1) Émettre les chunks 1 puis 0 (ordre inversé) pour un même correlation_id/thread_id.
  2) Le client reconstruit l’ordre via payload.chunk_index.
- Oracles:
  - Le rendu final est ordonné par chunk_index (0,1,…,final).
  - Aucune erreur de parsage/affichage; pas de double rendu du même index.
  - Logs front indiquent une réordonnancement non bloquant (niveau info/warn).

E2E-SEC-03 — Replay: message hors fenêtre 60s
- Étapes:
  1) Émettre un event avec ts client en dehors de la fenêtre anti-replay (±60s, drift client > ±500ms).
  2) Côté backend, rejeter le message (server_ts source de vérité).
- Oracles:
  - Réponse rejet (code/motif), journalisation WARN+ “replay_detected”.
  - Aucun effet métier; pas d’émission secondaire.
  - Log corrélé avec hash chain intacte.

E2E-SEC-04 — Idempotence: double POST avec même idempotency_key (uuidv7)
- Étapes:
  1) POST /api/agents/{slug}/chat avec idempotency_key=K (uuidv7).
  2) Répéter le POST identique (K).
- Oracles:
  - Le second POST est traité idempotent: HTTP 409 (Conflict) ou 200 { idempotent: true, correlation_id } sans retraitement.
  - Un seul flux chat:agent_stream est émis; pas de doublon côté logs/events.
  - AccessDecision logged (allow puis idempotent_hit).

E2E-SEC-05 — Widgets: PostMessage hostile
- Étapes:
  1) Envoyer depuis l’iframe un message avec origin non autorisée ou type inconnu ou capability absente.
  2) Le Host applique le schéma strict { type, nonce, origin, capability, payload, correlation_id }.
- Oracles:
  - Message rejeté; aucun effet; log sécurité produit (niveau warn/error).
  - event error:occurred optionnel, aucune mutation; CSP viol = unmount + Safe Mode (bannière).
  - Aucun write:* possible (deny-by-default).

E2E-SEC-06 — Sockets: downgrade rôle en live (force_disconnect)
- Étapes:
  1) Un participant perd un privilège (ex: rôle passe de superuser à viewer).
  2) Le serveur émet system_update(kind="force_disconnect", reason="role_downgrade").
  3) Le client se déconnecte, purge l’état sensible et bloque l’envoi.
- Oracles:
  - Réception de force_disconnect; fermeture propre de la socket; aucune émission post-déconnexion.
  - Logs AccessDecision deny pour toute tentative subséquente.
  - Alerte éventuelle côté UI; pas de fuite de messages cross-room.

E2E-SEC-07 — PII: masquage IP/UA dans les logs
- Étapes:
  1) Déclencher une interaction (chat, sockets, KPIs) et récupérer les logs corrélés.
- Oracles:
  - IP masquées (/24 IPv4, /48 IPv6) ou hash salé; UA réduits (familles uniquement).
  - Présence server_ts, correlation_id (uuidv7), trace_id (uuidv7), span_id (uuidv4).
  - Hash chain valide (hash_prev/hash_curr), aucune donnée sensible en clair.

E2E-SEC-SOCKETS-01 — Downgrade de rôle (force_disconnect)
- Étapes:
  1) Déclasser un participant (ex: superuser → viewer) en cours de session.
  2) Le serveur émet system_update(kind="force_disconnect", reason="role_downgrade").
  3) Le client ferme la socket, purge l’état sensible et bloque toute émission.
- Oracles:
  - Réception du force_disconnect; fermeture propre; aucune émission post-déconnexion.
  - Logs AccessDecision “deny” pour toute tentative subséquente.
  - Aucune fuite inter-room; alerte UI optionnelle.

E2E-SEC-SOCKETS-02 — Rotation de clé (kid inconnu → refresh)
- Étapes:
  1) Basculer la clé active côté JWKS (nouveau kid); forcer l’usage d’un token portant l’ancien kid.
  2) Constater le rejet (kid inconnu/caduque), rafraîchir le token côté client.
  3) Reconnexion propre puis re-subscribe aux rooms.
- Oracles:
  - Premier essai: rejet explicite (mismatch kid), absence d’effets de bord.
  - Après refresh: handshake OK, re-subscribe OK, continuité fonctionnelle.
  - Logs sécurité mentionnant mismatch kid / key_rotation; force_disconnect possible avec reason="key_rotation".

E2E-SEC-ROOMS-01 — Idempotence agent_message (UUIDv7)
- Étapes:
  1) Émettre deux agent_message dans 60s avec le même idempotency_key (uuidv7).
- Oracles:
  - Un seul message visible (pas de re-diffusion); second = ack idempotent.
  - Journaux indiquent idempotent_hit; aucune duplication côté consommateurs.

E2E-SEC-ROOMS-02 — agent_message hors fenêtre 60s
- Étapes:
  1) Émettre un agent_message avec ts client hors fenêtre anti-replay (±60s, drift > ±500ms).
- Oracles:
  - Rejet + log du motif; aucune diffusion; server_ts reste source de vérité.

---

## 6) Pré-requis & Setup (exécution)

- Pré-requis
  - Schémas (EVENTS v1, sockets, registry, KPIs) chargés dans les validateurs
  - widget_registry.json présent et valide (deny write:* par défaut)
  - Mocks/fixtures stables pour chat/streams, rooms, KPIs
- Setup tests
  - Créer/valider comptes: su_test, ops_test, viewer_test
  - S’assurer que les policies RBAC sont chargées (v1)
  - Initialiser room-abc (active) et inscrire talia/bruce (simulés)
- Nettoyage
  - Invalider sessions/tokens créés
  - Archiver logs de test (avec anchors de hash) pour audit

---

## 7) Critères de sortie (gates de promotion)

- E2E-00, E2E-01, E2E-02, E2E-03: PASS (local + CI)
- Zéro violation CSP/Origin en console
- 0 test négatif critique en échec (E2E-SEC-01..07, E2E-SEC-SOCKETS-01/02, E2E-SEC-ROOMS-01/02)
- Schémas: 100% OK sur exemples canoniques et payloads observés
- Journaux: corrélation et chaînage de hash vérifiés pour chaque scénario
- RBAC: décisions conformes à la matrice; aucune élévation non prévue

---

## 8) Checklist d’exécution (rapide)

- [ ] Schémas chargés/validés
- [ ] widget_registry.json valide (deny write:*)
- [ ] Comptes tests prêts (su/ops/viewer)
- [ ] Room-abc prête (talia/bruce simulés)
- [ ] E2E-00: PASS
- [ ] E2E-01: PASS
- [ ] E2E-02: PASS
- [ ] E2E-03: PASS
- [ ] N1..N7: PASS (négatifs)
- [ ] Logs corrélés + hash chain OK
- [ ] Rapport final archivé (captures, logs, schémas, artefacts)

---

## 9) Bugs connus & contournements

- [Flaky] Ordonnancement SSE vs journalisation (micro-dérives ts)
  - Contournement: assertions tolérantes sur l’ordre inter-canaux; se baser sur index et correlation_id
- [Timing] Reconnexion WS agressive sur réseaux instables
  - Contournement: backoff exponentiel + jitter; borne max des retries
- [Horloge] Dérive ts côté client > 5 min provoque anti-replay
  - Contournement: NTP sync dans l’environnement de test
- [UI] Métriques p90 fluctuent pendant warm-up
  - Contournement: attendre 1–2 cycles de refresh avant asserter les couleurs/seuils
- [Cache] KPIs avec ETag peuvent retourner 304 inattendus
  - Contournement: invalider cache entre tests ou ajouter correlation_id distinct

---

## 10) Reporting (format recommandé)

- En-tête
  - Build/commit, date/heure (UTC), test runner, env
- Résultats e2e
  - E2E-00..03: PASS/FAIL + captures + correlation_id clés
- Négatifs
  - N1..N7: PASS/FAIL + logs d’accès/erreurs
- Schémas
  - Comptes de validations (OK/KO) + détails sur échecs
- Sécurité
  - Violations CSP/Origin: 0 attendu
- Journaux
  - Vérifs de chaîne (hash_prev/hash_curr) + ancres
- Conclusion
  - Gate: Promote/Block + actions correctives

---

## 11) Intégrations CI

- Validations schéma (CI obligatoire)
  - EVENTS_v1: champs obligatoires (events_version, ts, server_ts, actor, thread_id, correlation_id uuidv7, trace_id uuidv7, span_id uuidv4, payload).
  - chat:agent_stream: payload.chunk_index et final (booléen) requis; exemples canoniques validés.
  - widget_registry.json: internalOnly=true obligatoire, owner interne, entry_url sans schéma (pas de "://"), origin="self".
- Lint documentaire
  - Vérifier titres/liens des .md et présence du bloc “Append Log” dans chaque document.
- Gates CI (échec bloquant)
  - Échec si internalOnly manquant ou false dans une entrée du registre.
  - Échec si correlation_id/trace_id non conformes (uuidv7) ou manque de server_ts.
  - Échec si scénarios E2E-SEC-01..07, E2E-SEC-SOCKETS-01/02 et E2E-SEC-ROOMS-01/02 ne sont pas référencés dans la suite e2e.
- Exécution e2e en CI
  - E2E-00..03: PASS requis; E2E-SEC-01..07, E2E-SEC-SOCKETS-01/02 et E2E-SEC-ROOMS-01/02: PASS requis.
  - Rapports: inclure correlation_id clés, captures, validations de schémas et vérif de hash chain.

## Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale de la checklist QA E2E (user stories, scénarios détaillés, données de test, oracles, négatifs sécurité, bugs connus, gates).
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — ajout des scénarios négatifs E2E-SEC-01..07 (étapes + oracles), validations CI (schemas EVENTS/registry, lint .md, gates internalOnly/uuidv7/server_ts), et mise à jour des gates de promotion.
- 2025-10-13 — Alice (Lead Orchestrator): Patch v1b — ajout des cas E2E-SEC-SOCKETS-01/02 (downgrade, key rotation) et E2E-SEC-ROOMS-01/02 (idempotence, fenêtre 60s); mise à jour des références CI/gates pour ces scénarios.
