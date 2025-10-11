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

## Démarrage DEV (PostgreSQL local 5432)

- `make dev-env`
- `make redis-up` (si Redis 6379 n’est pas déjà lancé)
- `./scripts/dev-check.sh`
- `poetry install --with dev --directory backend`
- `npm install --prefix frontend`
- `make init-dev`
- `make dev` → backend: http://localhost:8000 · frontend: http://localhost:3000
- Identifiants dev : **striker / Ide33480/(12)** (usage local uniquement)
  (`npm run dev:bootstrap` reste réservé aux scénarios E2E isolés : purge conversations/messages)

### Run now (résumé express)

1. `make dev-env`
2. `./scripts/dev-check.sh`
3. `poetry install --with dev --directory backend`
4. `npm install --prefix frontend`
5. `APP_ENV=dev poetry run python manage.py init_dev_env`
6. `make dev`
7. Dans un autre terminal : exécuter les smokes `docs/auth/smoke-dojo.http` (HTTPie)
   ```
   cd docs/auth
   bash smoke-dojo.http
   ```
8. `make smoke` (raccourci pour relancer les smokes)

👉 En développement, la CSP est automatiquement assouplie (`'unsafe-inline'`, `'unsafe-eval'`, `ws://localhost:5173`) pour laisser Vite HMR fonctionner. En production, la politique reste stricte (pas d'unsafe, pas de websocket arbitraire).

### API utiles

- `GET /api/auth/me/` — renvoie les informations essentielles de l'utilisateur courant (session ou JWT obligatoire).

## Scripts utiles

Frontend
- Lint: npm run lint
- Typecheck: npm run typecheck
- Stylelint: npm run stylelint
- Build: npm run build
- Tests E2E: npm run test:e2e

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
