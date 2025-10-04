# PR — PixelProwlers Studio (RACI + Acceptance)

<!--
Cette PR template s’aligne sur la matrice RACI du repo (voir docs/RACI.md).
RACI: A = Accountable (responsable final, 1 seul), R = Responsible (réalise), C = Consulted, I = Informed.
Merci de garder la PR petite, ciblée, et de cocher ce qui est pertinent.
-->

## Résumé
- Problème/objectif:
- Contexte (lien specs/ADR/discussion):
- Portée (ce que cette PR fait / ne fait pas):

## Liens
- Issues liées: Closes #..., Relates to #...
- ADR / Docs:
- Previews / Environnements (si applicable):

## RACI de la PR
<!-- Se caler par défaut sur docs/RACI.md. Documenter toute déviation locale. -->
- A (Accountable, 1 seul): @
- R (Responsible, 1+): @
- C (Consulted): @
- I (Informed): @
- Déviations vs matrice (si applicable) + justification:

## Type de changement
- [ ] feat (nouvelle fonctionnalité)
- [ ] fix (correction)
- [ ] refactor (sans changement de comportement)
- [ ] perf (performance)
- [ ] chore/build (tooling, deps)
- [ ] ci (pipelines, jobs)
- [ ] docs (documentation)
- [ ] test (ajout/ajustement de tests)
- [ ] other: __________

## Critères d’acceptation (DoD)
- [ ] Given/When/Then:
  - Given …
  - When …
  - Then …
- [ ] Non-régressions vérifiées
- [ ] Budgets/perf (latence, bundle, mémoire) respectés
- [ ] Accessibilité / i18n (si UI)
- [ ] Sécurité / confidentialité (pas de secrets, contrôle d’accès)
- [ ] Observabilité (logs, métriques, traces, alertes)
- [ ] Documentation à jour (README, How-To, ADR si décision)

## Changements principaux
- Résumé orienté utilisateur:
- Points techniques notables (design, patterns, compromis):
- Endpoints/API/Contrats impactés (OpenAPI/GraphQL):
- Migrations/Schémas DB:
- Feature flag: [ ] Oui  [ ] Non  Nom du flag:

## Tests
- [ ] Unitaires ajoutés/mis à jour
- [ ] Intégration
- [ ] E2E / Manuel
- [ ] Données de test / fixtures
- [ ] Couverture des chemins critiques
- Comment tester (pas-à-pas local + commandes):

## Sécurité
- [ ] SAST passe
- [ ] DAST (si exposé)
- [ ] Entrées validées/sanitized
- [ ] Permissions/Scopes vérifiés
- [ ] Données sensibles protégées

## CI/CD
- [ ] Lint/Typecheck OK
- [ ] Tests OK
- [ ] Build OK
- [ ] Scans sécurité OK
- [ ] déploiement: [ ] canary  [ ] progressif  [ ] full
- Plan de rollback (si nécessaire):

## Observabilité & Analytics
- [ ] Logs utiles et actionnables
- [ ] Métriques/alertes ajoutées/ajustées
- [ ] Événements analytics/tracking ajoutés/mis à jour
- KPI de succès attendus:

## Captures / Démos (si UI)
- Screenshots / vidéo / storybook:

## Breaking changes
- [ ] Non
- [ ] Oui (impacts, plan de migration, communication):

## Checklist de revue
- [ ] PR petite et cohérente
- [ ] Nommage clair / code lisible
- [ ] Éviter la dette technique non nécessaire
- [ ] Aucune fuite de secret / info sensible
- [ ] Erreurs et messages actionnables
- [ ] Compatibilité (versions, navigateurs, API)
- [ ] Docs/ADR synchronisés

## Approbations et Handoff
- Relecteurs suggérés (tech + fonctionnel): @
- Approbation requise par A: [ ] Obtenue / [ ] En attente
- Note de handoff (si passation QA/ops):
