# Runbook — Gestion d’incident Dojo (corrélation request_id)

## Objectif

Identifier rapidement la cause d’une erreur perçue par un utilisateur Dojo en corrélant :
- la requête frontend (Nuxt),
- les logs backend (Django),
- l’entrée `AuditLog`,
- les événements Sentry,
- les métriques Prometheus exposées par `/metrics`.

## Informations clés

- Chaque requête reçoit un `X-Request-ID` unique (généré si absent).
- Les logs JSON (Nuxt + Django) incluent ce `request_id`.
- `AuditLog.request_id` permet de retrouver l’action côté base de données.
- Sentry enregistre le tag `request_id` et `http.status_code`.
- Compteurs Prometheus : `dojo_conversations_created_total`, `dojo_messages_created_total`, histogramme `dojo_request_latency_ms`.

## Étapes d’investigation

1. **Récupérer le `request_id`**
   - Depuis le navigateur : onglet Network → Requête en erreur → en-tête `X-Request-ID`.
   - Depuis les logs Nuxt (ex Playwright) :
     ```bash
     tail -n 100 frontend/.output/logs/nuxt.log | jq '{ts:.ts, rid:.request_id, level:.level, msg:.message}'
     ```

2. **Tracer dans les logs backend**
   ```bash
   tail -n 200 /var/log/django/app.log \
     | jq --arg RID "$REQUEST_ID" 'select(.request_id == $RID)'
   ```
   Vérifier le statut HTTP, la durée (`duration_ms`) et l’utilisateur (`user_id`).

3. **Consulter l’AuditLog**
   ```sql
   SELECT created_at, username, method, path, status_code
   FROM accounts_auditlog
   WHERE request_id = '<REQUEST_ID>';
   ```
   Permet de confirmer l’utilisateur et la ressource ciblée.

4. **Inspecter Sentry**
   - Filtrer par tag `request_id:<REQUEST_ID>`.
   - Vérifier si une exception a été remontée (stack trace et breadcrumbs réseau).

5. **Observer les métriques**
   ```bash
   curl -s http://localhost:8000/metrics \
     | grep -E 'dojo_conversations_created_total|dojo_messages_created_total|dojo_request_latency_ms'
   ```
   Vérifier s’il y a eu un pic de latence ou de créations.

6. **Vérifier Redis (nonce)**
   ```bash
   redis-cli -u "$REDIS_URL" keys "ask-agent-nonce:*" | head
   ```
   Contrôle si des nonces restent bloqués (rejeu potentiel).

## Actions correctives possibles

- **Nonce rejoué** : demander à l’utilisateur de rafraîchir la page (nouveau nonce).
- **CSRF manquant** : vérifier que le frontend a bien rafraîchi le token (`/api/auth/csrf/`).
- **Throttling 429** : confirmer via les logs (`error: rate_limited`) et communiquer le délai de backoff.
- **Erreur backend** : créer un ticket en incluant `request_id`, extrait de log JSON, entrée `AuditLog` et URL Sentry.

## Clôture

- Documenter la cause et l’impact dans le ticket d’incident.
- Ajouter, si besoin, un scénario de test (Playwright + smoke script) pour éviter la régression.
