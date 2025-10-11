# Agents IA — PostgreSQL hybride & commandes utiles

Deux scénarios supportés pour travailler avec les agents IA en local :

1. **PostgreSQL déjà présent sur la machine** (ex: service local, port 5432).
   - Configure `DATABASE_URL` directement vers `postgresql://USER:PASSWORD@127.0.0.1:5432/pxp_app`.

2. **PostgreSQL via Docker Compose** (recommandé pour un environnement isolé).
   - `deploy/override.agent-activation.yml` expose l’instance containerisée sur `127.0.0.1:5544`.
   - Démarrage :
     ```bash
     docker compose -f deploy/docker-compose.yml \
       -f deploy/docker-compose.override.yml \
       -f deploy/override.agent-activation.yml \
       up -d postgres
     ```

## Commandes (idempotentes)

Utiliser le même `DATABASE_URL` dans les deux cas, en adaptant hôte/port si nécessaire :

```bash
APP_ENV=dev \
DATABASE_URL='postgresql://pxp_app_user:pxp_app_pass@127.0.0.1:5544/pxp_app' \
poetry run python manage.py migrate

APP_ENV=dev \
DATABASE_URL='postgresql://pxp_app_user:pxp_app_pass@127.0.0.1:5544/pxp_app' \
poetry run python manage.py import_agents --dir agents_v21
```

Diagnostic rapide :

```bash
APP_ENV=dev DB_HOST=127.0.0.1 DB_PORT=5432 DB_NAME=pxp_dev DB_USER=striker_dev DB_PASSWORD='******' \
poetry run python manage.py print_db_config
```

## Nettoyage

- Arrêter le conteneur :
  ```bash
  docker compose -f deploy/docker-compose.yml \
    -f deploy/docker-compose.override.yml \
    -f deploy/override.agent-activation.yml \
    stop postgres
  ```
- Supprimer le superuser temporaire utilisé pour les tests :
  ```bash
  APP_ENV=dev poetry run python manage.py cleanup_ops_admin
  ```
