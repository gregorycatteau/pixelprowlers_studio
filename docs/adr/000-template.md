# ADR 000: <Titre concis de la décision>

- Status: Proposed | Accepted | Deprecated | Superseded | Rejected
- Date: YYYY-MM-DD
- DRI/Owner: @<personne>
- Co-auteurs/Consultés: @<personnes>
- Portée: <système/service/module concerné>
- Catégorie: Architecture | API | Données | Sécurité | Infra | Front | Back | Autre

## Résumé (one-liner)
En une phrase, quelle décision prenons-nous et pourquoi maintenant ?

## Contexte
- Quel problème tentons-nous de résoudre ?
- Contraintes, hypothèses, exigences (fonctionnelles, non-fonctionnelles, budgets perf/fiabilité/coût).
- Alternatives déjà envisagées informellement ou historique pertinent.

## Enjeux (Decision drivers)
- 1–3 critères principaux qui guident le choix (ex: time-to-market, coût exploitation, simplicité, compat).

## Options considérées
- Option A — <nom court>
  - Avantages:
  - Inconvénients:
  - Coûts/risques:
- Option B — <nom court>
  - Avantages:
  - Inconvénients:
  - Coûts/risques:
- Option C — <nom court>
  - Avantages:
  - Inconvénients:
  - Coûts/risques:

## Décision
- Choix retenu:
- Justification brève par rapport aux drivers:
- Échéance/validité (timebox, réévaluation prévue le …):
- Compatibilité ascendante: Oui | Non (détails)

## Conséquences
- Positives:
- Négatives / compromis acceptés:
- Impacts:
  - API/Contrats: <OpenAPI/GraphQL/messagerie>
  - Données/Schéma/Migrations:
  - Perf/budgets (latence, mémoire, taille bundle):
  - Sécurité/Confidentialité:
  - Observabilité (logs, métriques, traces, alertes):
  - Coûts (infra, licences):
  - Expérience Dev (DX) / Maintenance:

## Sécurité & Confidentialité
- Surfaces d’attaque affectées:
- Permissions/Scopes/Least privilege:
- Données sensibles et rétention:
- Conformité (si applicable):

## Opérations & Fiabilité
- SLO/SLA et erreurs attendues:
- Déploiement: canary | progressif | full
- Rollback plan:
- Runbook: <lien/notes>

## Stratégie de tests / QA
- Critères d’acceptation (Given/When/Then):
  - Given …
  - When …
  - Then …
- Tests requis: unitaires | intégration | e2e | perfs | sécurité
- Données de test / fixtures:

## RACI (implémentation de cette décision)
- A (Accountable, 1 seul): @
- R (Responsible, 1+): @
- C (Consulted): @
- I (Informed): @
- Note: S’aligner par défaut sur docs/RACI.md; documenter toute déviation.

## Plan d’implémentation (incréments)
- Étapes:
  1) …
  2) …
  3) …
- Feature flags / toggles:
- Migrations et rétrocompatibilité:
- Estimation / timebox:

## Mesure du succès
- KPI/metrics:
- Méthode de suivi (dashboards/alerts):
- Date de revue post-implémentation:

## Alternatives non retenues (et pourquoi)
- Option X: rejetée car …
- Option Y: rejetée car …

## Questions ouvertes
- …
- …

## Références
- Liens vers issues/PR, docs, benchmarks, POC, discussions, normes.

---
Meta
- Supersedes: ADR-XXX (si remplace)
- Superseded by: ADR-YYY (complété le …)
- Changelog:
  - YYYY-MM-DD: Proposed par @
  - YYYY-MM-DD: Accepted par @
  - YYYY-MM-DD: Ajustements mineurs (…)
