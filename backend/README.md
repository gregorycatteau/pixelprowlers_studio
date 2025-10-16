# PixelProwlers Studio

Monorepo Nuxt 4 + Tailwind 4 (frontend) et Django (Poetry) + PostgreSQL/SQLite (backend).

## Accès rapide
- RACI : docs/RACI.md
- Contribuer : CONTRIBUTING.md
- ADR (décisions d’architecture) : docs/adr/
- CI : .github/workflows/
- Sécurité : security/

## Prérequis
- Node.js >= 22
- Python 3.13
- Poetry (gestion des dépendances Python)
- npm (gestion des dépendances frontend)

## Démarrer (dev)

Frontend (Nuxt 4)
    cd frontend
    npm ci
    npm run dev

Backend (Django)
    cd backend
    poetry install
    poetry run python manage.py migrate
    poetry run python manage.py runserver 0.0.0.0:8000

## Scripts utiles

Frontend
- Lint: npm run lint
- Typecheck: npm run typecheck
- Stylelint: npm run stylelint
- Build: npm run build

Backend
- Migrations: poetry run python manage.py makemigrations
- Migrer: poetry run python manage.py migrate
- Tests (pytest): poetry run pytest -q
- Vérifs déploiement: poetry run python manage.py check --deploy

## Structure
backend/       (Django, settings dans studio_core/settings/*)
frontend/      (Nuxt 4 + Tailwind 4)
docs/
  adr/         (Architecture Decision Records)
  RACI.md
security/      (Guides, check-lists)
docker/
.github/
  workflows/   (CI)

## Qualité & CI
- PR petites, incrémentales; utiliser des Conventional Commits (feat:, fix:, chore:, ci:, docs:, test:, refactor:, perf:)
- CI: lint, typecheck, tests; scans de sécurité dépendances (Python/Node)
- Respecter les templates d’issue/PR et le RACI pour clarifier A/R/C/I par tâche/PR

## Sécurité
- Jamais de secrets en clair (utiliser GitHub Secrets / .env local)
- Django prod: SECURE_* (HSTS, cookies sécurisés), ALLOWED_HOSTS, redirection HTTPS
- Nuxt prod: en-têtes de sécurité (CSP, X-Frame-Options, Referrer-Policy), erreurs non verbeuses
- Logs sans PII; appliquer le moindre privilège (permissions, tokens, accès)

## RACI et collaboration
- La matrice RACI (docs/RACI.md) définit A (Accountable), R (Responsible), C (Consulted), I (Informed) par domaine
- Chaque issue/PR doit expliciter son RACI (et toute déviation vs la matrice)
- Décisions structurantes: ouvrir un ADR (docs/adr/) et lier l’issue/PR

## Branches & releases
- Branches: feature/<slug>, fix/<slug>, chore/<slug>, ci/<slug>, docs/<slug>
- Protections recommandées sur main: PR obligatoire, checks CI requis, review CODEOWNERS, résolution des conversations

## Environnements & base de données
- DATABASE_URL pris en charge (PostgreSQL via dj-database-url) avec fallback SQLite en local
- Variables d’environnement: .env (commun) + .env.<APP_ENV> (dev/test/prod/upgrade)

Bon build et bonne chasse aux pixels 🐾

## Mode non‑interactif (Cline/CI)

Objectif: exécuter des commandes Django/Poetry sans interaction, avec sorties flushées et fin détectable par un marqueur.

- Script: `scripts/run-ni.sh` (ajoute timeout, force le mode non‑interactif, imprime une sentinelle de fin)
- Sentinelle de fin imprimée: `[[CLINE:DONE]]`
- Environnement forcé: `PYTHONUNBUFFERED=1`, `POETRY_FORCE_INTERACTIVE=no`
- Timeout par défaut: 120s (overridable avec `-t` ou `TIMEOUT=...`)
- Connexion DB: `DB_CONNECT_TIMEOUT` (défaut 5s) pour éviter les hangs si PostgreSQL est indisponible
- Superuser: variables `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` (non loguées)

Exemples:

- Initialiser l’environnement dev (non‑interactif)
  bash
  bash scripts/run-ni.sh -C backend -t 120 -- poetry run python -u manage.py init_dev_env --noinput

- Variante si une commande pose des questions (piping “yes”)
  bash
  bash scripts/run-ni.sh -C backend -t 120 --yes -- poetry run python -u manage.py <commande>

- Lancer un serveur de manière détachée (logs redirigés)
  bash
  bash scripts/run-ni.sh -C backend --detach /tmp/django.out -- poetry run python -u manage.py runserver 127.0.0.1:8000

Notes:
- La commande `init_dev_env` supporte `--noinput` et lit les variables `DJANGO_SUPERUSER_*`.
- Le script imprime systématiquement `[[CLINE:DONE]] exit=<code>` (ou `pid=<pid>` en mode détaché) pour que Cline détecte la fin proprement.
