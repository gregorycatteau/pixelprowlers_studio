# Contribuer à PixelProwlers Studio

Merci de vouloir contribuer. Ce guide décrit nos règles de collaboration, notre usage de la matrice RACI et les exigences de qualité/sécurité.

- Public cible: contributeurs internes et externes
- Technologies principales: Frontend (Nuxt), Backend (Django)
- Contrats & collaboration: RACI, ADR, templates d’issues/PR

Liens utiles:
- Matrice RACI: docs/RACI.md
- Template d’issue: .github/ISSUE_TEMPLATE/task.md
- Template de PR: .github/PULL_REQUEST_TEMPLATE/raci_pr.md


## 1) RACI: rôles et responsabilités

Nous utilisons RACI pour clarifier qui décide, qui exécute, qui est consulté, qui est informé.

- A (Accountable) — Responsable final, 1 seul par activité.
- R (Responsible) — Réalise l’activité.
- C (Consulted) — Consulté pour avis.
- I (Informed) — Informé du résultat.

Consultez la matrice de référence: docs/RACI.md. Par défaut, alignez chaque tâche/PR sur cette matrice. Toute déviation locale doit être explicitée dans l’issue/PR (section “RACI de la tâche/PR”).

Handoffs attendus:
- “Prêt à coder”: objectifs/acceptance clairs, contrats stables (OpenAPI/GraphQL), mocks si besoin.
- “Prêt à tester”: plan de test, risques connus, feature flag/rollback plan si pertinent.
- “Prêt à déployer”: changelog, plan de migration, runbook, métriques à surveiller.


## 2) Ouvrir une issue

Utilisez le template “Task (RACI)”:
- Choisissez la catégorie (ex: Architecture / ADR, Back Django, Front Nuxt, Contrats API, QA, etc.).
- Renseignez le RACI de la tâche (A, R, C, I).
- Définissez la portée, les critères d’acceptation (Given/When/Then), les budgets de perf/fiabilité.

Découpez en tâches atomiques. Limitez le WIP (1–2 tasks par personne). Assignez clairement.


## 3) Branches, commits, PR

- Nommage de branche: feature/<slug>, fix/<slug>, chore/<slug>, ci/<slug>, docs/<slug>
- Conventional Commits recommandé:
  - feat: … | fix: … | refactor: … | perf: … | chore: … | ci: … | docs: … | test: …
  - scope optionnel: feat(front): … / fix(back): …
- PR petites et cohérentes, liées à une issue: “Closes #<num>”
- Utilisez le template de PR (RACI + Acceptance)
  - Renseignez A/R/C/I, critères Given/When/Then, risques, plan de test, impacts contrats/API, migrations, feature flags
  - Exigence de revue:
    - 1 relecteur technique minimum
    - Approbation du rôle A requise pour les éléments critiques (architecture, sécurité, prod)
- Rebase court et résolution proactive des conflits


## 4) Qualité: style, lint, formatage

Python:
- Formatage: Black (line-length 100), isort (profil black), Flake8
- Fichiers de config présents à la racine
- Commandes usuelles:
  - black .
  - isort .
  - flake8

JavaScript/TypeScript (frontend Nuxt):
- Suivez les linters/formatters configurés dans le projet (ESLint/Prettier si présents)
- Maintenez un bundle raisonnable et des budgets de perf (voir critères de PR)

Pré-commit:
- Activez les hooks: pre-commit install
- Assurez-vous que tous les hooks passent avant push


## 5) Tests et QA

- Écrivez des tests unitaires en priorité
- Ajoutez des tests d’intégration sur les points d’assemblage (API, DB, événements)
- E2E sous feature flag lorsque nécessaire
- Donnez un plan de test clair dans la PR (comment tester localement, jeux de données, commandes)

Backend (Django):
- Gestion des dépendances (si Poetry): cd backend && poetry install
- Lancer les tests: poetry run python manage.py test (ou équivalent local)

Frontend (Nuxt):
- Installez les deps: npm ci (ou yarn/pnpm selon le projet)
- Lancer les tests: npm test (ou équivalent)


## 6) Sécurité

- SAST/DAST activés en CI lorsque disponibles
- Bandit configuré (.bandit, .bandit.yaml)
- Interdiction stricte des secrets en clair dans le code/PR
  - Utilisez des variables d’environnement et un outil de gestion de secrets
  - .secrets.baseline sert à détecter les secrets accidentels; gardez-le à jour si nécessaire
- Validez/sanitisez toutes les entrées utilisateur
- Vérifiez les permissions/scopes sur les actions sensibles
- Pas de données personnelles en dur dans les fixtures


## 7) Contrats et documentation

- Contrats API (OpenAPI/GraphQL) versionnés; toute évolution doit être discutée/validée (A/R/C/I)
- Rédigez/tenez à jour:
  - ADR (Architecture Decision Records) pour décisions significatives
  - README/How-To au fil de l’eau
  - Schémas (DB, séquence), migrations, mapping d’événements
- Mentionnez dans la PR: changements de contrat, migrations, impacts backward-compat, plan de migration


## 8) Observabilité, analytics, performance

- Logs actionnables, sans secrets
- Métriques/alertes sur les chemins critiques
- Événements analytics versionnés/documentés (nommage stable)
- Budgets de perf: latence côté serveur/clients, taille bundle, TTI; justifiez toute régression


## 9) CI/CD, déploiement progressif

- CI doit valider: lint, build, tests, scans sécurité
- Déploiement sous feature flag lorsque l’impact est non trivial
- Stratégies: canary, progressive, full; toujours prévoir un plan de rollback
- Post-déploiement: surveillez métriques/alertes; notez les retours et corrections rapides si besoin


## 10) Collaboration multi-agents (résumé opérationnel)

- Planner/PM: priorise, définit acceptance, timebox
- Architecte: conçoit, garde les contrats stables, rédige ADR
- Builders (vous, moi, autres): implémentent, testent, documentent
- Reviewer: vérifie la qualité, sécurité, et respect des contrats
- QA: définit et automatise les tests d’acceptation
- DevOps: CI/CD, environnements, observabilité
- UX/Contenu/Analytics: intégrés au flux via RACI

Règles pratiques:
- Ownership explicite par répertoire/fonctionnalité
- Limitez le WIP par personne
- Verrou “soft” via assignation sur fichiers sensibles (schémas, migrations)
- Découpez pour maximiser le parallélisme (interfaces stables + mocks)


## 11) Process d’acceptation (DoD)

Une tâche/PR est “Done” si:
- Critères Given/When/Then satisfaits
- Lint/Tests/Build/Scans OK
- Docs/ADR à jour
- Sécurité/Confidentialité respectées
- Observabilité et métriques en place si concerné
- Approbations RACI obtenues (incl. A si requis)
- Rollout/rollback plan documenté si déploiement


## 12) Code de conduite

- Respect, bienveillance, feedback constructif
- Transparence sur les blocages/risques/erreurs
- Pas de blame; privilégiez les post-mortems légers et orientés apprentissage


## 13) Questions et aide

- Si une règle n’est pas claire, ouvrez une issue “docs” pour l’améliorer
- En cas de conflit RACI, escaladez vers le rôle “A” de la catégorie concernée
- Pour démarrer: créez une issue avec le template RACI, faites valider la portée et le RACI, puis ouvrez une PR ciblée

Merci pour vos contributions. Votre rigueur et votre clarté font la qualité du projet.
