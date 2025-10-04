---
name: "Task (RACI)"
about: "Définir et exécuter une tâche alignée sur la matrice RACI"
title: "[Task] <titre concis>"
labels: ["task"]
assignees: []
---

<!--
Guide: ce gabarit aligne la tâche avec la matrice RACI de PixelProwlers Studio.
Référence: ../../docs/RACI.md
RACI: A = Accountable (responsable final, 1 seul), R = Responsible (réalise), C = Consulted, I = Informed.
-->

## Contexte
- Description courte:
- Problème/opportunité:
- Liens (ticket parent, specs, ADR, discussion):

## Portée
- Objectif (résultat utilisateur mesurable):
- Hors-scope (non-objectifs):
- Hypothèses/contraintes:

## Catégorie (choisir)
- [ ] Vision & Priorisation
- [ ] Architecture / ADR
- [ ] Contrats API (OpenAPI/GraphQL)
- [ ] Implémentation Front (Nuxt)
- [ ] Implémentation Back (Django)
- [ ] Revue sécurité (SAST/DAST)
- [ ] CI/CD & Infra
- [ ] Stratégie de tests / QA
- [ ] Connaissance / RAG
- [ ] UX / Contenu
- [ ] Analytics / Growth
- [ ] Autre: ________

## RACI de la tâche
Se caler par défaut sur la matrice RACI (../../docs/RACI.md). Documenter toute déviation.
- A (Accountable, 1 seul): @
- R (Responsible, 1+): @
- C (Consulted): @
- I (Informed): @
- Déviations vs matrice (si applicable) + justification:

## Définition de fait (DoD) / Critères d’acceptation
- [ ] Énoncés Given/When/Then:
  - Given …
  - When …
  - Then …
- [ ] Performance/budgets (latence, coût, taille bundle, etc.):
- [ ] Compatibilité / migrations:
- [ ] Accessibilité / i18n (si UI):
- [ ] Sécurité / confidentialité (données, secrets, permissions):
- [ ] Observabilité (logs, métriques, traces, alertes):

## Livrables
- Code/PRs attendus:
- Docs (README, guide How-To, ADR si décision):
- Artefacts (schémas, mockups, OpenAPI, migrations, etc.):

## Plan de tests
- Unitaires:
- Intégration:
- E2E / manuel:
- Données de test / fixtures:
- Gate CI requis (lint, test, SAST/DAST):

## Dépendances / Impacts
- Dépend de:
- Impacte:
- Feature flag: [ ] Oui  [ ] Non  Nom du flag:
- Rollout: [ ] Canary  [ ] Progressive  [ ] Full
- Plan de rollback:

## Mesures & Analytics
- Événements/tracking à ajouter/modifier:
- Métriques de succès (KPI):
- Tableaux de bord / alertes:

## Planning
- Estimation (temps/points):
- Deadline/Timebox:
- Disponibilités / fuseaux:

## Checklist d’exécution
- [ ] Ticket découpé et estimé
- [ ] RACI validé et communiqué
- [ ] Spécifications/contrats figés (API, schémas, invariants)
- [ ] Implémentation terminée
- [ ] Tests passent en CI
- [ ] Revue(s) effectuée(s) (technique + fonctionnelle)
- [ ] Sécurité revue (si nécessaire)
- [ ] Documentation à jour
- [ ] Déploiement effectué / planifié
- [ ] Monitoring actif et stable
- [ ] Rétro/notes post-livraison (optionnel)

## Notes
- Points ouverts / risques:
- Décisions prises (ou lien ADR):
