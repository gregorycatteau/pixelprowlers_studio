# Activation des agents IA — Runbook opérateur

## 1. Base de données utilisée
- **Option B (Docker)** : service `postgres` du compose local, exposé sur `5544`.
- Port override appliqué via `deploy/override.agent-activation.yml`.
- Connexion Django : `DATABASE_URL=postgresql://pxp_app_user:pxp_app_pass@127.0.0.1:5544/pxp_app`.

```bash
docker compose -f deploy/docker-compose.yml \
  -f deploy/docker-compose.override.yml \
  -f deploy/override.agent-activation.yml \
  up -d postgres
```

### 1.1 Pilotage via variables d'environnement

Deux options équivalentes :

1. **DATABASE_URL** complet :
   ```bash
   export DATABASE_URL='postgresql://pxp_app_user:******@127.0.0.1:5544/pxp_app'
   ```
2. **Quintette DB_*** (prioritaire si `DATABASE_URL` absent) :
   ```bash
   export DB_HOST=127.0.0.1
   export DB_PORT=5432
   export DB_NAME=pxp_dev
   export DB_USER=striker_dev
   export DB_PASSWORD='******'
   ```

Commande de diagnostic :

```bash
APP_ENV=dev DB_HOST=127.0.0.1 DB_PORT=5432 DB_NAME=pxp_dev DB_USER=striker_dev DB_PASSWORD='******' \
poetry run python manage.py print_db_config
```

Sortie : description de la cible (`postgresql://127.0.0.1:5432/pxp_dev`) + résultat de `SELECT version()`.

## 2. Migrations Django
- Exécutées dans un conteneur `backend` éphémère (poetry installé en mode system-site-packages).

```bash
docker compose -f ... run --rm backend sh -lc '
  python -m pip install --upgrade pip &&
  pip install poetry &&
  export POETRY_VIRTUALENVS_CREATE=false &&
  poetry install &&
  APP_ENV=agents_activation \
  DJANGO_SECRET_KEY=dev-key \
  DJANGO_ALLOWED_HOSTS=localhost \
  DATABASE_URL=postgresql://pxp_app_user:pxp_app_pass@postgres:5432/pxp_app \
  poetry run python manage.py migrate'
```

✅ Toutes les migrations `accounts`, `ai_assistants`, `api`, `auth`, `sessions`, `token_blacklist` appliquées sans erreur.

## 3. Import des agents
- Utilisation des manifestes `backend/agents_v21`.
- Commande identique (même wrapper) avec `poetry run python manage.py import_agents --dir agents_v21`.
- Normalisation auto ajoutée dans `import_agents.py` (valeurs autorisées, conversion legacy ➜ v2.1).
- Résultat : 16 agents importés/mis à jour (`✓ MAJ/Créé: bruce … tom`).

## 4. API smoke tests
1. Lancement d’un `runserver` dev, exposé sur `127.0.0.1:8001`.
   ```bash
   docker compose -f ... run --detach -p 8001:8000 backend sh -lc '
     python -m pip install --upgrade pip &&
     pip install poetry &&
     export POETRY_VIRTUALENVS_CREATE=false &&
     poetry install &&
     APP_ENV=agents_activation \
     DJANGO_SECRET_KEY=dev-key \
     DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
     DATABASE_URL=postgresql://pxp_app_user:pxp_app_pass@postgres:5432/pxp_app \
     poetry run python manage.py runserver 0.0.0.0:8000 --noreload'
   ```
2. Création d’un superuser de test et login via `POST /api/auth/login/` (session stockée dans `/tmp/agent_cookies.txt`).
   ```json
   {"ok": true, "user": {"username": "ops_admin", "is_superuser": true}}
   ```
3. Ajout du flag gate dans la session : `pp_gate_ok=True`, `pp_gate_ts=<epoch>`.
4. **GET /api/agents/**
   ```bash
   curl -s -b /tmp/agent_cookies.txt http://127.0.0.1:8001/api/agents/ | jq '.agents | length'
   # 16
   ```
   Extrait :
   ```json
   {
     "slug": "bruce",
     "name": "Bruce",
     "model": "gpt-4o",
     "remaining_eur_today": "3.00",
     "schema_version": "2.1.0"
   }
   ```
5. **POST /api/agents/bruce/ask**
   ```bash
   nonce=$(APP_ENV=dev PYTHONPATH=backend python - <<'PY'
from ai_assistants.security import RequestNonce
print(RequestNonce.generate())
PY
)

   curl -s -b /tmp/agent_cookies.txt \
        -H 'Content-Type: application/json' \
        -H 'X-CSRFToken: <csrftoken>' \
        -H "X-Request-Nonce: $nonce" \
        -d '{"message":"Ping de test"}' \
        http://127.0.0.1:8001/api/agents/bruce/ask | jq
   ```
   Réponse :
   ```json
   {
     "ok": true,
     "agent": "bruce",
     "provider": "mock",
     "output": "[Bruce] Echo sécurisé : Ping de test",
     "tokens_in": 3,
     "tokens_out": 7,
     "latency_ms": 0
   }
   ```
6. **Throttle** (5 requêtes autorisées, 6ᵉ bloquée)
   ```bash
   for i in {1..6}; do
     nonce=$(APP_ENV=dev PYTHONPATH=backend python - <<'PY'
from ai_assistants.security import RequestNonce
print(RequestNonce.generate())
PY
)
     curl -s -o /dev/null -w "%{http_code}\n" \
       -b /tmp/agent_cookies.txt \
       -H 'Content-Type: application/json' \
       -H "X-CSRFToken: <csrftoken>" \
       -H "X-Request-Nonce: $nonce" \
       -d '{"message":"flood"}' \
       http://127.0.0.1:8001/api/agents/bruce/ask;
   done
   # 200 200 200 200 200 429
   ```
7. Arrêt du conteneur runserver : `docker stop <container_id>`.

## 5. Renforcements sécurité
- **Rate limiting** : `ask_agent` limité via DRF `ScopedRateThrottle` (`5/min`).
- **Nonce anti-replay** : en-tête `X-Request-Nonce` signé (TTL 60s, usage unique).
- **Headers HTTP** : `SecurityHeadersMiddleware` injecte `nosniff`, `Referrer-Policy=no-referrer`, `Permissions-Policy`, `COOP/COEP` si Caddy absent.
- **Logs redacted** : filtre `AgentPIIRedactionFilter` + hash SHA256 du prompt (aucune PII en clair).
- **CSRF** : cookies + en-tête CSRF obligatoires, sinon `403`.
- **Tests** : `APP_ENV=test PYTHONPATH=backend poetry run pytest -m agents` (throttle, headers, nonce/CSRF, redaction, import v2.1).

## 6. Incidents & correctifs
- **Importer legacy** : conversion automatique + validation stricte des champs immuables (`identity.*`, `tools[].name`).
- **Middleware gate** : session + superuser requis ; tests automatisés couvrent le flux.
- **Views** : remplacement de `is_enabled` par `is_active`, sauts vers 429 en cas de flood.

## 7. Nettoyage
- Conteneurs temporaires stoppés (`docker stop`).
- Superuser `ops_admin` désactivé :
  ```bash
  APP_ENV=dev poetry run python manage.py cleanup_ops_admin
  ```
- Cookies / fichiers temporaires (`/tmp/agent_cookies.txt`) supprimés après test.
