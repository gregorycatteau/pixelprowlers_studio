# Sprint 00 — Backbone minimal

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Scope stack global: (front ciblé pour tests), backend mock pour chat/stream, validations schemas, journaux.
Références: docs/specs/GOVERNANCE_v1.md

---

## But du sprint
Poser la colonne vertébrale commune et sécurisée pour l’écosystème cockpits/rooms/dashboard:
- Protocole d’événements v1 versionné, avec exemples canoniques et schémas de validation.
- RBAC v1 minimal appliqué aux endpoints “chat mock” et lecture des logs.
- Journalisation corrélable et inviolable (hash), avec propagation stricte de `correlation_id`.
- Registre global des widgets et contrat de validation (deny-by-default).

---

## Livrables
- docs/specs/EVENTS_v1.md — contrat JSON des événements v1 (chat, stream, widget, system, metrics, error) + schémas + exemples.
- docs/specs/RBAC_v1.md — rôles (`superuser`, `ops`, `viewer`, `agent`), matrix endpoints × rôles, principes least privilege.
- docs/specs/WIDGET_REGISTRY.md — contrat `widget_registry.json` (schema, capacités explicites, owner, scope, status).
- docs/specs/SECURITY_BASELINES.md — baselines sécurité (CSRF, session binding, nonce anti-replay, logs hashés, CSP).
- docs/checklists/QA_E2E.md — plan de tests e2e (Playwright), scénarios, données, oracles, critères d’acceptation.
- docs/roadmaps/Sprint_00_Backbone.md — ce document (roadmap + checklists).

Livrables implicites (dans les specs)
- Schémas de validation (jsonschema et/ou zod) pour: EVENTS v1, widget_registry.json.
- Exemples JSON canoniques prêts à être utilisés par les tests.
- Procédure de rollback documentaire (versionnage, revert, revalidation e2e).

---

## Plan de tests
- e2e (Playwright)
  - Scénario pivot “chat stream corrélé”
    - Préconditions: user authentifié rôle `superuser`.
    - Action: POST `/api/agents/{slug}/chat` (mock) avec payload minimal.
    - Attendus:
      - 2xx avec `correlation_id` renvoyé.
      - Log structuré écrit avec hash, `correlation_id`, IP/UA, actor.
      - Émission d’événements conformes:
        - `chat:user_message` (payload user)
        - `chat:agent_stream` (mock stream, au moins 2 chunks)
      - Champs communs présents: `type`, `events_version`, `ts`, `server_ts`, `actor`, `room?`, `thread_id`, `correlation_id` (uuidv7), `trace_id` (uuidv7), `span_id` (uuidv4), `payload`, `sig?`.
      - Schémas validés sans erreur (events + payloads).
- Intégration/contrats
  - Validation schema `widget_registry.json` (deny-by-default si capability absente) et internalOnly=true obligatoire; refuser toute origin/URL externe.
  - RBAC matrix: tests sur endpoints “chat mock” (write) et lecture logs (read).
  - Idempotence: POST /chat requiert `idempotency_key` (uuidv7) côté client; le back doit dédupliquer (409 Conflict ou 200 { idempotent: true }).
  - Vérification de la propagation du `correlation_id` (uuidv7) et du `trace_id` (uuidv7) bout-en-bout (requête → logs → events); `span_id` (uuidv4) présent.
  - Vérification `server_ts` et fenêtre anti-replay (60s, drift client ±500ms).
  - Vérification hash d’intégrité des logs (tamper-evident).
- Non-régression
  - Snapshots d’exemples canoniques EVENTS v1.
  - Lint/CI schema (events, widget_registry).

---

## Sécurité (gates)
- RBAC v1 appliqué et testé sur:
  - POST `/api/agents/{slug}/chat` (permissions: `superuser|agent` write; `ops|viewer` deny).
  - GET `/api/logs?correlation_id=...` (permissions: `superuser|ops` read; `agent|viewer` deny).
- Idempotence (obligatoire):
  - POST `/api/agents/{slug}/chat` inclut `idempotency_key` (uuidv7) générée côté client; le backend déduplique (409 Conflict ou 200 { idempotent: true }).
- Anti-replay & clocks:
  - Fenêtre anti-replay = 60s (source vérité = `server_ts`), drift horloge client toléré ±500ms; messages hors fenêtre rejetés (loggés WARN+).
- Identifiants & traçabilité:
  - `correlation_id` (uuidv7) et `trace_id` (uuidv7) obligatoires; `span_id` (uuidv4) présent; propagation bout-en-bout exigée.
- Journaux:
  - Logs hashés avec `hash_prev`/`hash_curr`; PII masquées (IP tronquée /24 IPv4, /48 IPv6 ou hash salé; UA réduit à la famille).
  - Rétention journaux corrélés: 90 jours (purge/archivage documentés).
- Widgets:
  - Deny-by-default: aucune action `write:*` sans capability explicite et revue SecOps.
  - Politique interne-only (v1): `internalOnly: true` requis dans le registre; aucune origin/URL externe autorisée.
- CSP/Isolation (préfiguration Sprint 01):
  - Exemple host: `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'`; iframe sandbox="allow-scripts allow-same-origin".
- CSRF & Session binding:
  - CSRF actif sur endpoints state-changing; session binding à attributs stables (UA partiels, device key).
- Secrets/API keys:
  - Jamais commit; variables d’environnement + scanning pré-commit.

Gate de promotion Sprint 00
- Tous les schémas valident les exemples.
- e2e pivot “chat stream corrélé” passe en CI.
- RBAC effectif sur endpoints ciblés (tests verts).
- Idempotence en place sur POST chat (`idempotency_key` uuidv7; duplicate non exécuté).
- Conformité identifiants: `correlation_id`/`trace_id` en uuidv7, `span_id` en uuidv4; `server_ts` présent.
- Journaux montrent `correlation_id`, `trace_id`, `span_id` et hashing; vérifications intégrité OK; PII masquées; rétention 90 jours.
- Registre widgets: `internalOnly: true` et aucune origin/URL externe; CSP de base documentée.

---

## Checklist d’avancement
- [ ] Spécification EVENTS v1 rédigée (contrats, champs communs, versionnage, exemples).
- [ ] Schémas de validation EVENTS v1 prêts (jsonschema/zod) + tests unitaires.
- [ ] Idempotence documentée: `idempotency_key` (uuidv7) client → back (POST chat).
- [ ] Conformité identifiants: `correlation_id`/`trace_id` en uuidv7, `span_id` en uuidv4; `server_ts` présent.
- [ ] Fenêtre anti-replay (60s) et drift (±500ms) documentés.
- [ ] RBAC v1 défini (rôles, matrix endpoints × rôles) et documenté.
- [ ] RBAC v1 appliqué sur endpoints “chat mock” et lecture logs.
- [ ] Spécification WIDGET_REGISTRY (+ schema de validation) finalisée avec `internalOnly: true`, origin="self"/URL internes uniquement.
- [ ] Baselines sécurité rédigées (CSRF, session binding, logs hashés, PII masking, rétention 90 jours, CSP préfiguré).
- [ ] QA_E2E.md: scénarios, données de test, oracles, critères d’acceptation complétés (incl. scénarios négatifs).
- [ ] e2e pivot “POST chat → log corrélé → stream conforme” passe local + CI.
- [ ] DoD du sprint atteint.

---

## Definition of Done (DoD)
- Protocole d’événements versionné v1 + exemples validés par schema, incluant `events_version`, `server_ts`, uuidv7/uuidv4 requis.
- RBAC appliqué sur endpoints chat mock + lecture logs; tests verts.
- Idempotence opérationnelle: `idempotency_key` (uuidv7) sur POST chat; duplicate non exécuté (409 ou 200 idempotent).
- `widget_registry.json` validé par schéma (jsonschema/zod) avec `internalOnly: true`, origin/URL internes uniquement.
- Un test e2e passe: POST chat → log corrélé → event “chat:agent_stream” conforme (champs communs+schema OK), y compris indices de chunk et champ final.

---

## Risques & Mitigations
- Ambiguïtés de champs EVENTS v1
  - Mitigation: exemples canoniques exhaustifs; jsonschema strict; revues croisées.
- Capabilities trop larges côté widgets
  - Mitigation: deny-by-default; revue SecOps obligatoire pour `write:*`; logs/audit mount/update.
- Absence de corrélation uniforme dans les logs
  - Mitigation: middleware d’injection de `correlation_id`; tests d’intégration systématiques.
- Fuites CSRF/session
  - Mitigation: same-site cookies, tokens anti-CSRF, session binding; tests négatifs.
- Flaky e2e (timing stream)
  - Mitigation: mocks déterministes; timeouts maîtrisés; retrys contrôlés pour stream.
- Régression de sécurité par changements non documentés
  - Mitigation: gate sécurité + Append Log versionné + CI schemas + revue obligatoire.

---

## Notes d’implémentation (guides)
- Endpoints mock (références pour tests)
  - POST `/api/agents/{slug}/chat`: accepte `{ message, thread_id?, idempotency_key }`, renvoie `{ accepted: true, correlation_id }` (uuidv7) ou 409/200 idempotent en cas de doublon.
  - Stream “mock”:
    - Émet `chat:user_message` puis 2+ `chat:agent_stream` corrélés avec `payload.chunk_index` (0..n) et `payload.final` (true sur le dernier).
    - Supporte resynchronisation: endpoint/commande “gap_request” permettant de renvoyer les chunks manquants sur indices demandés.
- Journaux:
  - Champs: level, ts, server_ts, source, actor, IP(mask)/UA(family), room?, thread_id, correlation_id(uuidv7), trace_id(uuidv7), span_id(uuidv4), event_type, hash_prev, hash_curr.
- Schémas:
  - EVENTS v1: jsonschema public avec définitions réutilisables (common fields, payloads spécifiques), incluant `events_version`, `server_ts`, uuidv7/uuidv4, `chunk_index`/`final`.
  - Widget registry: validation semver, capabilities, owner interne, scope, status, `internalOnly: true`, origin="self", `entry_url` interne (pas de schéma externe).
- Rollback documentaire:
  - Toute modification de spec → Append Log + bump version locale + re-run e2e; rollback = revert Git + relance CI.

---

## Dépendances & Outils (minimaux)
- Validations: jsonschema/zod.
- e2e: Playwright.
- Lint schemas/examples: job CI dédié.
- Hashing journaux: algo stable (ex: SHA-256) + chaînage logique.
- CI gates: échec si `internalOnly` absent/false, si `server_ts`/uuidv7/uuidv4 manquants, ou si schémas/exemples invalides.

---

## Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale, objectifs, gates sécurité, DoD, plan e2e pivot défini.
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — idempotency_key côté client (uuidv7), champs `server_ts` et identifiants (`correlation_id`/`trace_id` en uuidv7, `span_id` en uuidv4), anti-replay 60s (drift ±500ms), registre widgets interne-only, CSP minimal, PII masking & rétention 90 jours, et gates CI renforcés.
