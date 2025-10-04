# PixelProwlers Studio — Plan 15 jours (V1 “ready to go”)

Statut: plan validé
Période: J1 → J15
Coordinatrice: Alice (@gregorycatteau)
Source de vérité: ce document + issues/PRs liées

---

## 1) Objectifs V1 et ordre de priorités

Objectifs “ready to go” (V1)
- Auth JWT RS256 (login/logout/refresh), rôles admin/user
- API v1 (OpenAPI): auth/*, users/*, projects/* (CRUD minimal)
- Front Nuxt 4: dashboard, liste + détail “projet”, formulaires avec validation serveur
- Pages: accueil + onboarding minimal
- Docs: README, RACI, CONTRIBUTING, SECURITY, ADR “posture sécu v1”

Priorités (ordre d’attaque)
1) Sécurité (headers, auth, secrets, SAST/secret scan)
2) CI/CD (lint/type/tests, audits deps, jobs stables)
3) Back API (contrat, validation, logs sans PII)
4) Front (accessibilité, perfs, ergonomie)
5) QA (tests ciblés + couverture)
6) Analytics (événements + privacy by design)

---

## 2) Non-fonctionnel (DoR/DoD v1)

Budgets de performance
- API p95 < 200 ms (staging), p99 < 500 ms; endpoints auth p95 < 300 ms
- Front: bundle initial < 180 kB gz, TTI < 2.0 s (desktop câble/staging)

Disponibilité / erreurs
- Staging: 99%; Prod (phase suivante): 99.5%
- Erreurs 5xx < 0.5% sur 7 jours (staging)

Environnements
- dev local + .env; staging; prod
- DB: PostgreSQL 16 (staging/prod); SQLite autorisée seulement en local/test
- Redis: optionnel V1 (sessions/rate limit si besoin)

Politiques sécurité
- JWT RS256 en prod (HS256 dev-only)
- Headers: CSP stricte (report-only d’abord), X-Frame-Options=DENY, Referrer-Policy=strict-origin-when-cross-origin, X-Content-Type-Options=nosniff
- Secrets via GitHub Secrets; jamais en repo
- Logs sans PII + corrélation (Request-ID)

---

## 3) Accès & setups

Domaines
- Staging: staging.pixelprowlers.io (web), api.staging.pixelprowlers.io (api)
- Prod (plus tard): www.pixelprowlers.io, api.pixelprowlers.io

Secrets GitHub (Actions → Secrets & variables)
- DJANGO_SECRET_KEY
- JWT_PRIVATE_KEY (PEM RS256) / JWT_PUBLIC_KEY (PEM)
- DATABASE_URL (ex: postgresql://user:pass@host:5432/app)
- REDIS_URL (si activé)
- NUXT_PUBLIC_API_URL (= URL de l’API)
- SENTRY_DSN (optionnel)

Variables d’env (staging)
- Back: DJANGO_SETTINGS_MODULE=studio_core.settings.prod, DJANGO_DEBUG=false, DJANGO_ALLOWED_HOSTS=api.staging.pixelprowlers.io, DJANGO_CSRF_TRUSTED_ORIGINS=https://*.pixelprowlers.io
- Front: NUXT_PUBLIC_API_URL=https://api.staging.pixelprowlers.io

---

## 4) Cadence & gouvernance

- Revues: tech async quotidienne (≤ 15 min) + check CI; produit bi-hebdo (milieu/fin)
- SLO de réponse PR: 24–48 h; freeze merge veille du jalon Release
- Acceptation: Alice (merge final); CODEOWNERS = veto sur domaine si gates cassés
- Branch protections (après S1 merge): PR obligatoire, checks requis (Web/API), CODEOWNERS review

---

## 5) Phases et jalons

Phase 0 — Cadrage (J1)
- Finaliser DoD/DoR, budgets perf, exigences sécu, envs
- Décisions: JWT RS256 prod ✅; headers sécu côté proxy/CDN ou Nitro routeRules → trancher; SLO audits deps (fenêtre correction High/Critical)
- Sorties: ADR posture sécu v1; tableau de bord gates

S1 — CI & hygiène (J2–J4)
- ruff.toml; pytest.ini; coverage report (backend); Vitest coverage (front)
- Audits deps bloquants: npm audit High/Critical; stratégie pip-audit validée
- Quick-wins lint front pour verdir CI
- Gates: CI verte (sans continue-on-error), coverage visible (seuils informatifs), audits deps bloquants

S2 — Sécurité (J5–J8)
- backend/bandit.yaml v1; gate bloquant ≥ medium
- gitleaks non-bloquant (bloquant si repo clean)
- Headers sécu: ADR + implémentation (CSP report-only → enforce)
- Backend hardening batch 2 (I/O confinées, logs sans PII, nettoyage)
- Gates: Bandit bloquant, headers actifs, CI stable

S3 — Qualité produit (J9–J12)
- Tests front ciblés (composants critiques); back (chemins critiques, e2e léger)
- Couverture back ≥ 60%; front: informative (seuil si réaliste)
- Observabilité min: logs actionnables, métriques candidates (latence, erreurs)

Release readiness (J13–J15)
- Dry-run déploiement (migrations, collectstatic, configs)
- Runbook post-deploy + rollback; freeze; smoke tests; go/no-go
- Protections de branches activées; tag + changelog

---

## 6) Plan quotidien (J1 → J15)

J1 — Cadrage & ADR
- [ ] DoR/DoD finalisés (perf, sécu, envs)
- [ ] ADR “Posture sécurité v1” (JWT RS256, headers, scans, audits)
- [ ] Décider l’emplacement des headers sécu (Nitro vs proxy/CDN)
- [ ] SLO audits deps (High: 72h; Critical: 24h → à confirmer)
- [ ] Secrets GitHub: liste validée; variables d’env staging listées

J2 — CI durcissement (partie 1)
- [ ] Ajouter ruff.toml (E,F,I,B,UP,SIM,PL,RUF; ignorer E501 si Black)
- [ ] Ajouter pytest.ini (markers slow, filterwarnings)
- [ ] Mettre à jour workflows pour ruff check/format & pytest

J3 — Couverture & audits deps
- [ ] Backend: coverage report (text + xml/lcov), artefacts CI
- [ ] Front: Vitest coverage (text + lcov), artefacts CI
- [ ] CI: npm audit bloquant (High/Critical)
- [ ] CI: pip-audit stratégie (bloquant ou allowlist court)

J4 — Stabilisation CI & docs
- [ ] Quick wins ESLint/Stylelint (top 10 erreurs)
- [ ] CI hors “relax mode” pour Web/API
- [ ] CONTRIBUTING: règles CI/gates & secrets
- [ ] S1 Gate Check: “CI verte, coverage visible, audits deps bloquants”

J5 — Bandit (setup)
- [ ] backend/bandit.yaml v1 (starter + éventuels skips justifiés)
- [ ] CI: Bandit non-bloquant initial + triage findings P1
- [ ] Plan fixes/refactors (batch 2 côté back)

J6 — Bandit (gate)
- [ ] CI: Bandit bloquant (>= medium, confidence medium)
- [ ] Corrections findings priorisées (si applicable)
- [ ] Doc exceptions (bandit.yaml, pas #nosec sauvage)

J7 — Headers sécurité
- [ ] ADR headers: choix Nitro routeRules vs proxy/CDN
- [ ] Implémentation CSP (report-only), X-Frame-Options=DENY, Referrer-Policy, nosniff
- [ ] Tests basiques de présence d’en-têtes

J8 — Secrets scanning & hardening back
- [ ] Gitleaks périmètre + exclusions minimales; passage bloquant si repo clean
- [ ] Backend hardening batch 2 (I/O confinées, logs sans PII, cleanup)
- [ ] S2 Gate Check: “Bandit bloquant, headers actifs, CI stable”

J9 — Tests back (chemins critiques)
- [ ] Tests unitaires/intégration sur endpoints auth/users/projects
- [ ] Validation stricte (schemas/serializers), erreurs non verbeuses
- [ ] Logs actionnables (sans PII), Request-ID

J10 — Tests front (composants haute valeur)
- [ ] Vitest sur composants critiques (liste/détail projet, forms)
- [ ] A11y quick checks (règles de base)

J11 — Couverture & observabilité
- [ ] Atteindre ≥ 60% backend; fixer seuil CI (soft) à 60%
- [ ] Observabilité minimale: métriques kandid (latence, erreurs), doc

J12 — E2E léger & run readiness
- [ ] Smoke E2E (scénarios clés auth+CRUD) si faisable
- [ ] “Run readiness” checklist (pré-prod)

J13 — Dry-run déploiement
- [ ] Migrations check; collectstatic; configs prod/staging revues
- [ ] Secrets vérifiés; ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS
- [ ] Préparer runbook post-deploy + rollback

J14 — Freeze & smoke
- [ ] Freeze (pas de features)
- [ ] Smoke tests manuels/automatisés staging; rollback drill
- [ ] Changelog préparé

J15 — Release
- [ ] Go/No-Go
- [ ] Tag release; protections de branche ON (si pas déjà)
- [ ] Rétro rapide; issues “phase suivante” ouvertes

---

## 7) Workstreams & livrables clés

Sécurité
- bandit.yaml v1; gate ≥ medium (S2)
- gitleaks (plan blocage & exclusions)
- headers sécu (CSP report-only → enforce)
- hardening back (I/O confinées; logs sans PII)

CI/CD
- CI non-relax; ruff + coverage; audits deps bloquants
- protections main; CODEOWNERS effectif

Backend
- OpenAPI v1; validation stricte; erreurs non verbeuses
- JWT RS256 prod; tests prioritaires

Frontend
- Lints essentiels OK; Vitest composants haute valeur
- headers sécu: choix Nitro vs proxy, implémentation

QA
- pytest.ini; coverage report; seuils 60 → 80
- plan d’acceptation Given/When/Then

Docs/Knowledge
- ADR posture sécu v1; SECURITY.md (rotate secrets + incident runbook)
- README/CONTRIBUTING à jour

Analytics
- “Events & Privacy” (nomenclature, consentement, minimisation PII)

---

## 8) Gates par phase (exits)

- S1: CI verte (lint/type/tests), coverage publié, audits deps bloquants
- S2: Bandit bloquant, headers actifs, secret scan passé, hardening batch 2
- S3: Back coverage ≥ 60%, tests front critiques présents, runbook prêt
- Release: smoke OK, dry-run déploiement, rollback plan, branch protections ON

---

## 9) Risques & mitigations

- Bruit CI initial
  - Mitigation: traiter top 10 erreurs lints; allowlist datée si indispensable
- pip-audit strict
  - Mitigation: bloquer High/Critical; SLO (High ≤ 7j, Critical ≤ 1–3j); allowlist minimale documentée
- CSP trop restrictive
  - Mitigation: report-only → correction → enforce progressif
- Délais review
  - Mitigation: SLO PR 24–48 h; PR petites; merges fréquents

---

## 10) Rôles et responsabilités (opérationnel)

- Owner unique provisoire: @gregorycatteau (toutes paths CODEOWNERS)
- Mapping agents virtuels → owner réel: .github/owners.yml
- Assignations: issues/PRs labellées “agent:*” route vers @gregorycatteau

---

## 11) Conventions issues/PR

Issues
- Titre: domaine: sujet (ex: CI: audits deps bloquants)
- Corps: contexte, portée, RACI, DoD, plan de test, dépendances

PR
- Titre: conventional commit (ex: chore(ci): enable audits deps blocking)
- Corps: résumé, DoD (Given/When/Then), impacts, tests, risques
- Petites PR, CI verte, reviews CODEOWNERS

---

## 12) Checklists (gabarits)

Tâche (général)
- [ ] Contexte/portée validés
- [ ] RACI & owner/assignees
- [ ] DoD (Given/When/Then)
- [ ] Implé + tests + docs
- [ ] CI verte
- [ ] Risques/rollback notés

Security Gate (PR)
- [ ] Pas de secrets/PII
- [ ] Entrées validées/sanitized
- [ ] Permissions/Scopes OK
- [ ] Bandit/Gitleaks/audits deps OK
- [ ] Logs/métriques prudents

Release readiness
- [ ] Migrations & collectstatic OK
- [ ] Secrets & ALLOWED_HOSTS OK
- [ ] Headers sécu en place
- [ ] Smoke tests OK
- [ ] Rollback plan prêt

---

## 13) Table de suivi quotidien (remplir au fil de l’eau)

| Jour | Principales tâches | Gate cible | Statut | Owner | Notes |
|------|---------------------|------------|--------|-------|-------|
| J1   | Cadrage + ADR sécu  | —          | ☐      | @gregorycatteau | |
| J2   | ruff/pytest.ini     | S1         | ☐      | @gregorycatteau | |
| J3   | Coverage + audits   | S1         | ☐      | @gregorycatteau | |
| J4   | Stabilisation CI    | S1         | ☐      | @gregorycatteau | |
| J5   | Bandit.yaml v1      | S2         | ☐      | @gregorycatteau | |
| J6   | Bandit bloquant     | S2         | ☐      | @gregorycatteau | |
| J7   | Headers sécu ADR+impl | S2       | ☐      | @gregorycatteau | |
| J8   | Gitleaks + hardening | S2        | ☐      | @gregorycatteau | |
| J9   | Tests back critiques | S3        | ☐      | @gregorycatteau | |
| J10  | Tests front critiques | S3       | ☐      | @gregorycatteau | |
| J11  | Couverture 60% back | S3         | ☐      | @gregorycatteau | |
| J12  | E2E léger + readiness | S3      | ☐      | @gregorycatteau | |
| J13  | Dry-run déploiement | Release    | ☐      | @gregorycatteau | |
| J14  | Freeze + smoke      | Release    | ☐      | @gregorycatteau | |
| J15  | Go/No-Go + tag      | Release    | ☐      | @gregorycatteau | |

---

## 14) Annexes

Références fichiers/dirs
- CI: .github/workflows/
- Conventions: CONTRIBUTING.md
- Sécurité: security/SECURITY.md
- RACI & ownership: docs/RACI.md, .github/CODEOWNERS, .github/owners.yml
- ADR template: docs/adr/000-template.md

Notes
- Les “agents” sont des rôles virtuels mappés à un owner réel tant que l’équipe humaine n’est pas en place.
- Toute exception sécurité (skip Bandit/allowlist audit) doit être documentée et datée (échéance de retrait).

Fin du plan
