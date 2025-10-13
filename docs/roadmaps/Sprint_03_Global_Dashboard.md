# Sprint 03 — Global Dashboard v1

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Périmètre: Écran “en un coup d’œil” présentant 4 KPIs essentiels et un système d’alertes minimal.
Alignements: EVENTS v1, RBAC v1, journaux corrélables (correlation_id), deny-by-default côté widgets.
Références: docs/specs/GOVERNANCE_v1.md

---

## But du sprint
Fournir un tableau de bord global permettant aux rôles autorisés d’observer l’état opérationnel du système à tout instant, avec:
- 4 KPIs v1:
  1) Volume de messages (24h glissantes)
  2) Erreurs par criticité (24h, par niveaux: warn|error|critical)
  3) Latence moyenne de stream (p50/p90, sur fenêtre 15 min et 24h)
  4) Rooms actives (compte courant et pic 24h)
- Seuils d’alertes et codage couleur.
- Données sourcées de manière sûre (validées, traçables) avec rafraîchissement contrôlé.
- Contrats d’accès (RBAC) et logs/événements associés.

---

## Livrables
- docs/roadmaps/Sprint_03_Global_Dashboard.md — ce document (roadmap + checklists).
- docs/specs/DASHBOARD_v1.md — définition des KPIs, sources de données, règles d’agrégation, seuils d’alerte, rafraîchissement.
- Références transverses:
  - Conformité aux champs communs EVENTS v1: `type`, `ts`, `actor`, `room?`, `thread_id`, `correlation_id`, `payload`, `sig?`.
  - Alignement RBAC v1 (docs/specs/RBAC_v1.md) pour lecture des métriques et alertes.
  - QA e2e (docs/checklists/QA_E2E.md) enrichi des scénarios Dashboard.

---

## Plan de tests
- e2e (Playwright)
  - Scénario pivot “KPIs + Alerte simulée”
    - Préconditions:
      - Utilisateur avec rôle `viewer` (ou `ops`/`superuser` selon cas).
      - Données factices injectées ou sources mockées stables.
    - Étapes:
      1) Ouvrir le Global Dashboard v1.
      2) Vérifier l’affichage de 4 KPIs:
         - Volume messages (24h)
         - Erreurs par criticité
         - Latence moyenne stream (p50/p90)
         - Rooms actives (courant + pic 24h)
      3) Simuler une condition de seuil pour déclencher 1 alerte (ex: taux d’erreurs > seuil).
      4) Vérifier que l’alerte s’affiche avec le codage couleur approprié et génère un event `system:alert`.
    - Attendus:
      - Tous les KPI panels chargent sans erreur et respectent les schémas de données définis.
      - Un `system:alert` est produit avec `correlation_id`, `severity`, `code`, `message`, `context`.
      - RBAC: `viewer` a un accès lecture-only au Dashboard; tentatives d’écriture (inexistantes ici) refusées.
      - Pas d’erreurs de console liées à CSP/permissions.
- Intégration/contrats
  - Validation de formats de réponses pour l’API KPIs (jsonschema/zod).
  - Cohérence des horodatages (TZ, ISO 8601) et fenêtres (24h, 15 min).
  - Vérification de la propagation de `correlation_id` du fetch KPIs jusqu’aux logs d’accès.
- Non-régression
  - Snapshots d’exemples canoniques de réponses KPIs.
  - Tests de seuils (sous, proche, au-dessus) avec assertions sur les couleurs et messages.

---

## Sécurité (gates)
- RBAC v1:
  - `viewer`: lecture-only du Dashboard et KPIs; aucun endpoint d’écriture.
  - `ops`: lecture + accès diagnostics agrégés (logs de requêtes KPIs).
  - `superuser`: lecture complète + accès à l’historique d’alertes; pas d’action destructive.
  - `agent`: pas d’accès au Dashboard global (deny-by-default), sauf policy explicite.
- Journalisation & traçabilité:
  - Chaque requête KPIs logguée avec `correlation_id`, `actor`, `role`, `source`, `latency_ms`, `status`.
  - Alerte simulée/produite émet un `system:alert` (EVENTS v1) et un log hashé.
- CSP / Données:
  - Aucune ressource tierce non autorisée; `connect-src` limité aux APIs internes.
  - Données KPI validées (jsonschema/zod) avant rendu; rejet en cas d’incohérence.
- DDoS / Backpressure:
  - Throttling sur endpoints KPIs (ex: 1 req/sec par utilisateur, burst limité).
  - Cache/ETag/If-None-Match pour windows 5–30s selon KPI (configurable).
- Gate de promotion Sprint 03:
  - e2e pivot “4 KPIs + 1 alerte simulée” vert en CI.
  - RBAC lecture-only respecté pour `viewer`.
  - Logs structurés présents et corrélables pour chaque fetch KPI et alerte.
  - Validation des schémas de données KPIs/alertes sans erreurs.

---

## Checklist d’avancement
- [ ] Spécification DASHBOARD_v1 rédigée (KPIs, sources, agrégations, seuils, refresh).
- [ ] Contrats de réponse (jsonschema/zod) pour chaque KPI + alerte.
- [ ] RBAC v1 appliqué aux endpoints de lecture KPIs.
- [ ] e2e pivot écrit: rendu 4 KPIs + 1 alerte simulée.
- [ ] Logs d’accès KPIs corrélables (correlation_id) + hashing activé côté back.
- [ ] Codage couleur/états (ok|warn|error) pour chaque KPI et pour les alertes.
- [ ] DoD atteint (ci-dessous).

---

## Definition of Done (DoD)
- Dashboard défini (contrats + KPIs + requêtes) dans docs/specs/DASHBOARD_v1.md.
- Test e2e passe: affichage des 4 KPIs + 1 alerte simulée avec `system:alert` conforme à EVENTS v1.
- RBAC lecture-only effectif pour `viewer`; `ops`/`superuser` selon matrice.
- Logs corrélables (correlation_id) pour toutes les interactions Dashboard et alertes.
- Schémas de données validés (KPIs et alertes); aucune erreur de validation en CI.

---

## Risques & Mitigations
- Données incohérentes ou incomplètes (latence, erreurs)
  - Mitigation: validations strictes (jsonschema/zod), valeurs par défaut documentées, fallback UI neutre (état “data-stale”).
- Rafraîchissements trop fréquents (charge)
  - Mitigation: cache côté serveur, ETag, fenêtre de poll 5–30s; quotas et throttling par rôle.
- Dérive de définitions KPI (changement non versionné)
  - Mitigation: versionner les contrats KPIs; Append Log + CI schemas; revue SecOps/QA obligatoire.
- Alert fatigue (trop d’alertes)
  - Mitigation: seuils adaptés, hystérésis (suppression d’oscillations), agrégation par période, priorité/criticity.
- Fuite d’information (KPIs exposant des données sensibles)
  - Mitigation: RBAC strict, masquage éventuel, minimisation des payloads, logs d’accès audités.

---

## Notes d’implémentation (guides)
- KPIs v1 (définitions minimales)
  - Volume messages (24h): somme des événements `chat:*` + `widget:update` + `system:*` pertinents; group-by heure (24 points).
  - Erreurs/criticité (24h): compte par `severity` (warn|error|critical) à partir d’`error:occurred`; sparkline + totals.
  - Latence moyenne stream: calcul p50/p90 des durées `chat:user_message` → dernier `chat:agent_stream` chunk; fenêtres 15 min roulante et 24h.
  - Rooms actives: count de rooms en `status=active` (courant) + pic (max) sur 24h.
- Seuils et codage couleur (exemple initial)
  - Latence p90: ok < 2.0s, warn 2.0–3.5s, error > 3.5s.
  - Taux erreurs (24h): ok < 1%, warn 1–3%, error > 3% (par service).
  - Rooms actives: seuils d’alerte dépendants de la capacité (config).
- Sources & agrégations
  - Préférer lectures sur store agrégé (time-series, index sur ts/correlation_id/type).
  - Exposer endpoints lecture-only: `/api/kpis/volume24h`, `/api/kpis/errors24h`, `/api/kpis/latency`, `/api/kpis/rooms`.
  - Emit `metrics:tick` périodique pour cadencer des rafraîchissements contrôlés.
- Observabilité
  - Log sur chaque appel KPI: `actor`, `role`, `kpi`, `params`, `latency_ms`, `status`, `correlation_id`.
  - Sur alerte: produire un `system:alert` avec `severity`, `code`, `threshold`, `observed`, `window`.
- UI/UX minimal
  - 4 cartes KPI responsives + barre d’alerte; filtre temporel (24h fixe v1), tooltips avec valeurs/horaires.
  - États: loading, data-stale, error; pas d’auto-refresh agressif (documenter intervalle).

---

## Données de test (e2e)
- Volume (24h): série synthétique 24 points avec croissance légère.
- Erreurs: 3 niveaux, total > 0 pour valider les couleurs; injecter un pic pour déclencher warn.
- Latence: p50≈0.9s, p90≈2.4s (dépasser légèrement le seuil warn pour test).
- Rooms actives: courant=7, pic=12; seuils configurés pour ne pas déclencher error par défaut.
- Alerte simulée: forcer `errors24h.rate_critical > threshold` pour déclencher `system:alert`.

---

## Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale, définition des 4 KPIs, gates sécurité (RBAC lecture-only, logs corrélés), plan e2e “4 KPIs + 1 alerte simulée”, seuils/couleurs initiaux et notes d’implémentation.
