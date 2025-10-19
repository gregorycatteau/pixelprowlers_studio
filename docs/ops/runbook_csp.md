# Runbook — Basculer la CSP en mode “enforce”

## Objectif

Passer de `Content-Security-Policy-Report-Only` à `Content-Security-Policy` (enforce) pour le Studio Dojo tout en conservant la capacité de revenir rapidement en mode observation si un blocage est détecté.

## Pré-requis

- Accès au dépôt (branche `feat/front/dashboard-projects` ou dérivée).
- Accès aux hôtes Caddy/Nuxt/Django (dev ou staging) et capacité de redéployer.
- Outil CLI : `grep`, `jq`, `docker compose` (pour relancer l’environnement local).

## Vérifications préalables

1. **Collecte des rapports existants**
   ```bash
   # Récupérer les rapports CSP stockés par Nitro (logs app) sur les 100 dernières lignes
   tail -n 100 /var/log/nuxt/nuxt.log | jq 'select(.type == "CSP-REPORT")'
   ```
   Confirmer qu’il n’y a plus d’inline script/style bloquants.

2. **Tests automatisés**
   ```bash
   cd frontend
   npm run test:e2e
   ```
   Les nouveaux tests Playwright valident que le frontend fonctionne avec la politique stricte.

## Passage en mode enforce

1. Mettre à jour les en-têtes (déjà commité dans ce sprint) :
   - `nuxt.config.ts` expose `Content-Security-Policy` côté Nitro.
   - `deploy/caddy/Caddyfile` applique la même politique pour le reverse proxy et ajoute `Report-To`.
   - En développement (`npm run dev`), la CSP est automatiquement relâchée (`unsafe-inline`, `unsafe-eval`, `ws://localhost:5173`). En production, la politique reste stricte.

2. Déployer Caddy/Nuxt/Django :
   ```bash
   docker compose -f deploy/docker-compose.yml up -d caddy frontend backend
   ```

3. Lancer le smoke test HTTP pour valider le parcours complet :
   ```bash
   cd docs/auth
   bash smoke-dojo.http
   ```

4. Surveiller les logs JSON (frontend + backend) pendant au moins 15 minutes :
   ```bash
   tail -f /var/log/nuxt/nuxt.log /var/log/django/app.log \
     | jq 'select(.type == "CSP-REPORT" or .message | contains("refused to connect"))'
   ```

## Rollback (report-only)

1. Revenir temporairement sur la version précédente en remplaçant l’en-tête :
   - `Content-Security-Policy` → `Content-Security-Policy-Report-Only`.

2. Redéployer Caddy/Nuxt.

3. Conserver le `Report-To` afin de continuer à collecter les violations.

## Post-déploiement

- Documenter dans un ticket les violations observées (s’il y en a).
- Mettre à jour `docs/auth/smoke-dojo.http` si un nouveau domaine autorisé est nécessaire.
