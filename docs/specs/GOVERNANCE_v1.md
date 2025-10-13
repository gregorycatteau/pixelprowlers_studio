# GOVERNANCE v1 — Processus d’évolution, Versionnage (semver) et Governance Ledger

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Exigence d’inclusion: Chaque spécification (.md) et roadmap (.md) DOIT référencer ce document dans ses “Références croisées”.

Références principales:
- EVENTS v1 — docs/specs/EVENTS_v1.md
- RBAC v1 — docs/specs/RBAC_v1.md
- WIDGET_REGISTRY v1 — docs/specs/WIDGET_REGISTRY.md
- SECURITY_BASELINES v1 — docs/specs/SECURITY_BASELINES.md
- COCKPIT_TEMPLATE v1 — docs/specs/COCKPIT_TEMPLATE_v1.md
- ROOMS v1 — docs/specs/ROOMS_v1.md
- SOCKETS_BRIDGE v1 — docs/specs/SOCKETS_BRIDGE_v1.md
- DASHBOARD v1 — docs/specs/DASHBOARD_v1.md
- Roadmaps Sprint 00–03 — docs/roadmaps/*
- QA E2E — docs/checklists/QA_E2E.md


-----------------------------------------------------------------------

1) Objet & portée

- Définir un processus d’évolution traçable, sécurisé et auditable pour les contrats et composants critiques (EVENTS, WIDGET_REGISTRY, ROOMS, SOCKETS_BRIDGE, RBAC, COCKPIT_TEMPLATE, DASHBOARD, SECURITY_BASELINES).
- Encadrer:
  - Le cycle de vie d’une proposition (RFC) et les rôles décisionnels.
  - La matrice d’impact et ses seuils (gates sécurité, compatibilité).
  - Le versionnage (semver) et les obligations de test/CI.
  - Le Governance Ledger (journal synthétique des décisions).
- Hors de portée v1:
  - Gouvernance multi-tenant inter-organisations (à spécifier ultérieurement).
  - Processus budgétaires/financiers.

RACI (minimal):
- Proposant: auteur de la RFC (agent/équipe).
- Jared (Gardien de la cohérence): scoring, arbitrage, tenue du Governance Ledger.
- PO (Product Owner): décision finale avec Jared (approve/reject).
- SecOps: revue sécurité (gates).
- QA: validation e2e et gates CI.
- Alice (Lead Orchestrator): cohérence inter-sprints, cadence et intégration.

-----------------------------------------------------------------------

2) Processus d’évolution (RFC → Décision → Merge → Rollback)

Étapes canoniques:
1) Proposition (RFC)
   - Format minimal (fichier MD joint à la PR):
     - Contexte & objectifs (problème à résoudre)
     - Portée & non-objectifs
     - Impacts potentiels (sécurité, compatibilité, perfs, UX, opérabilité)
     - Contrats touchés (EVENTS/WIDGET_REGISTRY/…)
     - Semver pressenti (major/minor/patch) + plan de migration
     - Tests & QA (e2e, négatifs, oracles)
     - Rollback plan (comment revenir à v-1)
   - Référencer: GOVERNANCE_v1.md dans la section “Références”.

2) Scoring (Jared)
   - Dimensions (0 à 3; pondération entre parenthèses):
     - Sécurité (x3): impact/gain de sécurité, respect des baselines, réduction de surface d’attaque
     - Cohérence/Compatibilité (x2): alignement avec les contrats existants, stabilité inter-composants
     - Performance/Coûts (x1): latence, ressources, coûts d’exploitation
     - Traçabilité/Tests (x2): facilité d’audit, couverture QA, CI gates
     - UX/Opérabilité (x1): clarté d’usage sans dégrader la sécurité
   - Sortie: Score global + recommandations (changement de portée, garde-fous).

3) Décision (PO + Jared)
   - Statuts possibles: Approved / Changes Requested / Rejected.
   - Critères bloquants (sécurité/compatibilité) => Rework obligatoire.
   - Si Approved:
     - Exiger: bump semver selon règles (voir §4), mise à jour “Append Log” dans chaque fichier touché, ajout d’une entrée au Governance Ledger, liens vers PR/commits.

4) Merge & Promotion
   - CI gates:
     - Validation de schémas (jsonschema/zod) pour tous les contrats impactés.
     - QA E2E: scénarios pivots + négatifs doivent être verts (incl. nouveaux cas si ajoutés).
     - Lint docs: présence Append Log + lien vers GOVERNANCE_v1.md dans Références.
     - Contrôles sécurité: deny-by-default, anti-replay, uuidv7/uuidv4/time windows, internalOnly si applicable.
   - Promotion interdite si gate sécurité/QA échoue.

5) Rollback (si nécessaire)
   - Conditions typiques: régression sécurité, rupture non anticipée, KPI dégradés au-delà des seuils rouges.
   - Procédure:
     - Revert commit(s) incriminé(s).
     - Bump de version si nécessaire (patch rollback).
     - Mise à jour Append Log + Governance Ledger (status = Rolled-back, motif).
     - Rerun QA e2e pivot + négatifs.
   - Communication: note synthétique dans le Ledger (impact, leçons, follow-up).

-----------------------------------------------------------------------

3) Matrice d’impact (seuils & couleurs)

- Vert (Go):
  - Ajouts compatibles (optionnels) sans élargir la surface d’attaque.
  - Gains de sécurité/observabilité, schémas stables, e2e verts.

- Ambre (Caution, gated):
  - Changements non-breaking mais avec risques opérationnels (ex: backpressure plus strict, CSP renforcée).
  - Exiger: QA renforcée, runbook de rollback, monitoring ciblé.

- Rouge (Stop, RFC renforcée obligatoire):
  - Régression sécurité (CSRF/session/replay/CSP) ou exposition PII non masquée.
  - Rupture de contrat (breaking) sans plan de migration/feature gates.
  - Dégradation KPI critiques (latence p90, taux d’erreur) au-delà des seuils définis (ex: p90 > 3.5s 15m, erreurs > 3% 24h).
  - Absence d’évidence de tests négatifs appropriés.

Nota: Toute entrée rouge ne peut pas être mergée sans mitigation et validation SecOps/QA explicites.

-----------------------------------------------------------------------

4) Versionnage (semver) — Politique contrats et artefacts

Champ d’application:
- Contrats: EVENTS, WIDGET_REGISTRY, ROOMS, SOCKETS_BRIDGE, RBAC, COCKPIT_TEMPLATE, DASHBOARD, SECURITY_BASELINES.
- Artefacts associés: schémas jsonschema/zod, exemples canoniques, références QA.

Règles:
- major (X.y.z): breaking change (suppression/renommage de champ requis, sémantique modifiée, rupture protocole).
- minor (x.Y.z): ajout compatible (nouveaux champs optionnels, nouvelles valeurs non destructives) ou durcissement non-breaking.
- patch (x.y.Z): corrections, clarifications, exemples/corrections de schémas sans changement sémantique.

Obligations:
- Toute modification → Append Log (date, auteur, justification, impacts).
- Bump semver dans la spec impactée (ex: events_version) et dans toute référence nécessaire.
- QA E2E: re-run obligatoire; si major → scénarios de migration/compat ajoutés.
- Dépréciation:
  - Annoncer en minor; suppression effective en major suivante.
  - Documenter période de grâce et feature flags si disponibles.

-----------------------------------------------------------------------

5) Governance Ledger — Journal synthétique

But: tracer toutes les décisions de gouvernance (propositions, décisions, migrations, rollbacks) de manière compacte, diffable et auditée.

Emplacement recommandé:
- docs/specs/GOVERNANCE_LEDGER.md (append-only)
- Format: tableau Markdown + extrait JSON par entrée.

Champs Ledger (minimaux):
- id: GOV-YYYY-XXX (ex: GOV-2025-001)
- date: YYYY-MM-DD
- author: identifiant ou équipe
- title: résumé bref
- components: [EVENTS|WIDGET_REGISTRY|SOCKETS|ROOMS|RBAC|COCKPIT|DASHBOARD|SECURITY]
- impact_level: green|amber|red
- semver: { component: "EVENTS", from: "1.0.0", to: "1.1.0" } (liste si multiple)
- decision: approved|changes_requested|rejected|rolled_back
- rationale: texte court (sécurité/cohérence/perf)
- links: { pr: "...", commit: "...", doc: "...", qa_run: "..." }
- rollback_of?: id (si applicable)
- follow_up?: actions/contenu (ex: “renforcer test E2E-SEC-0X”)

Template (Markdown):

| id           | date       | author | title                                 | components                 | impact | decision    | semver                                   | links.pr | qa_run |
|--------------|------------|--------|----------------------------------------|----------------------------|--------|-------------|-------------------------------------------|---------|--------|
| GOV-2025-001 | 2025-10-13 | alice  | Durcissement EVENTS: uuidv7 + server_ts | EVENTS, SECURITY           | green  | approved    | EVENTS 1.0.0 → 1.1.0                      | #1234   | qa#567 |

Template (JSON):

{
  "id": "GOV-2025-001",
  "date": "2025-10-13",
  "author": "alice",
  "title": "Durcissement EVENTS: uuidv7 + server_ts",
  "components": ["EVENTS","SECURITY"],
  "impact_level": "green",
  "decision": "approved",
  "semver": [
    { "component": "EVENTS", "from": "1.0.0", "to": "1.1.0" }
  ],
  "rationale": "Réduction du risque de replay + tri temps; aucune rupture.",
  "links": {
    "pr": "https://…/pull/1234",
    "commit": "abcd1234",
    "doc": "docs/specs/EVENTS_v1.md",
    "qa_run": "CI-PLAYWRIGHT-567"
  }
}

Exigences Ledger:
- Append-only (pas de réécriture), horodatage UTC.
- Hachage optionnel des entrées (intégrité) si disponible.
- Chaque PR changeant un contrat DOIT ajouter/mettre à jour une entrée.

-----------------------------------------------------------------------

6) Exigences CI & Gates (rappel)

- CI bloquante si:
  - Append Log manquant sur un fichier modifié.
  - Manque de lien vers GOVERNANCE_v1.md dans Références de la spec/roadmap touchée.
  - Schémas non valides / exemples canoniques KO.
  - QA E2E (pivots + négatifs) non verts, ou scénarios requis absents.
  - Violations sécurité: absence de uuidv7/uuidv4 requis, internalOnly manquant/refusé, anti-replay/window non respectés, CSP manquante.
- PR naming recommandé: docs/patch-<topic>-<semver> (ex: docs/patch-backbone-v1b)
- Pre-merge checklist:
  - Semver bump correct, Ledger entry, Append Log(s), refs croisées à jour.
  - Plan de rollback (et critères déclencheurs) présent.

-----------------------------------------------------------------------

7) Rôle de Jared (Gardien de la cohérence)

- Évalue les propositions via le scoring multidimensionnel, priorise la sécurité/cohérence.
- Tranche avec le PO en cas de conflit; demande des garde-fous supplémentaires si nécessaire.
- Tient à jour le Governance Ledger (ou s’assure de sa tenue).
- Veille au respect des baselines (SECURITY_BASELINES), des contrats (EVENTS, SOCKETS, ROOMS, REGISTRY) et de la traçabilité (correlation_id/trace_id/span_id).

-----------------------------------------------------------------------

8) Modèles — RFC & Rollback (extraits)

Modèle RFC (entête minimal):

- Titre
- Auteur(s), Date
- Contexte/Problème
- Objectifs & Portée
- Impacts (sécurité/cohérence/perf/UX/opérations)
- Contrats impactés (+ semver pressenti)
- Design & Alternatives
- Tests (e2e, négatifs, oracles), Données de test
- Plan de déploiement & Rollback
- Références (inclure ce doc)

Modèle Rollback Note:

- Motif du rollback (sécurité/compatibilité/KPIs)
- Portée et composants impactés
- Étapes exécutées (revert, bump patch, purge caches…)
- Résultat QA e2e post-rollback
- Entrée Governance Ledger (decision = rolled_back, rollback_of=GOV-YYYY-XXX)

-----------------------------------------------------------------------

9) Conformité & Audit

- Ce document est normatif pour toute évolution des contrats v1.
- Tout écart doit être justifié par une RFC dédiée et annoté en rouge dans la matrice d’impact.
- Les audits vérifieront:
  - La présence d’entrées Ledger pour toute évolution.
  - La correspondance semver ↔ changements effectifs.
  - La traçabilité Append Log ↔ PR/commits ↔ QA e2e.
  - Le respect des baselines sécurité et des fenêtres anti-replay.

-----------------------------------------------------------------------

Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale du GOVERNANCE v1 (processus d’évolution, matrice d’impact, semver, Governance Ledger, exigences CI/gates, rôle de Jared, modèles RFC/rollback, obligation de lien depuis toutes specs/roadmaps).
