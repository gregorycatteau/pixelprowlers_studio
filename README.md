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

## Checkpoints Sprint 0 — Jour J (raccourcis)

- CP#1 — Caddy headers + X-Request-ID
  - Nuxt headers:
    curl -I http://dev.localhost
  - Django health:
    curl -I http://api.dev.localhost/health

- CP#2 — Postgres + NATS
  - NATS subscribe (dojo):
    docker run --rm -it --network host synadia/nats-box:0.14 \
      nats sub -s nats://dojo_user:dojo_pass@127.0.0.1:4222 'intake.>'
  - NATS publish (dojo):
    docker run --rm -it --network host synadia/nats-box:0.14 \
      nats pub -s nats://dojo_user:dojo_pass@127.0.0.1:4222 'intake.lead.created' \
      '{"id":"demo-001","email":"alice@example.com","project_name":"Dojo"}'

- CP#3 — n8n WF-01 (Intake→Roadmap)
  - Trigger (POST):
    curl -sS -X POST http://n8n.dev.localhost/webhook/intake \
      -H 'Content-Type: application/json' \
      -H 'X-Request-ID: demo-n8n-123' \
      -d '{"email":"alice@example.com","project_name":"Dojo"}' | jq .

## Curls utiles (DX rapide)

- Corrélation bout-en-bout (Nuxt /health → Django /api/hello):
    curl -sS -H 'X-Request-ID: demo-123' http://dev.localhost/health | jq .

- OpenAPI (DRF Spectacular):
    curl -sS http://api.dev.localhost/api/schema/ | head -n 40

- API hello:
    curl -sS http://api.dev.localhost/api/hello/ | jq .

- Gate Sécurité v1 (Trivy + Semgrep):
    ./ops/security/gate_v1.sh
