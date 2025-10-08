# PixelProwlers Studio — README Jour J (Sprint 0)

Objectif: Environnement local utilisable dès aujourd’hui, avec artefacts testables, sécurité de base active.

Sommaire
- 1. Démarrage rapide
- 2. Endpoints (via Caddy)
- 3. Vérifications attendues (checkpoints)
- 4. n8n Workflow (WF-01 Intake→Roadmap)
- 5. NATS JetStream (publish/consume)
- 6. Secrets (sops/age)
- 7. Gate Sécurité v1 (Trivy + Semgrep)
- 8. Limitations connues
- 9. Next steps (hors périmètre Jour J)

Infos de référence
- Compose: deploy/docker-compose.yml
- Proxy: deploy/caddy/Caddyfile
- Postgres init: deploy/postgres/initdb/01_dbs.sql
- NATS conf: deploy/nats/nats.conf
- n8n workflow export: deploy/n8n/wf-01-intake.json
- Secrets doc: ops/secret/README.md
- Gate sécurité: ops/security/gate_v1.sh


1) Démarrage rapide
- Prérequis:
  - Docker + plugin Compose
  - Ports libres: 80 (Caddy), 4222/8222 (NATS), 5432 (Postgres — exposé au réseau bridge), 3000 (Nuxt via Caddy), 8000 (Django via Caddy), 5678 (n8n via Caddy)
- Démarrer:
  - Depuis la racine du repo:
    ```bash
    docker compose -f deploy/docker-compose.yml up -d
    ```
  - Suivre les logs (facultatif):
    ```bash
    docker compose -f deploy/docker-compose.yml logs -f --tail=200
    ```
- Résolution DNS locale:
  - La zone spéciale .localhost est résolue localement par la plupart des systèmes/navigateurs.
  - Si votre système ne résout pas dev.localhost (rare), ajoutez:
    ```bash
    # fallback possible
    echo "127.0.0.1 dev.localhost api.dev.localhost n8n.dev.localhost nats.dev.localhost" | sudo tee -a /etc/hosts
    ```

Notes sécurité de jour J
- Réseau local uniquement (Caddy écoute en 80).
- Pas de secrets en clair dans Git (voir sops/age plus bas).
- Images épinglées par tag stable (jour J). Pour la prod, pinner par digest (@sha256) — voir commentaire dans deploy/docker-compose.yml.


2) Endpoints (via Caddy)
- Frontend (Nuxt): http://dev.localhost
  - Health page: http://dev.localhost/health
    - Affiche l’X-Request-ID (corrélation).
- Backend (Django/DRF): http://api.dev.localhost
  - Liveness: http://api.dev.localhost/health
  - OpenAPI schema: http://api.dev.localhost/api/schema/
  - Hello: http://api.dev.localhost/api/hello/
- n8n (orchestrateur): http://n8n.dev.localhost
  - Web UI par défaut (non exposé en prod)
  - Webhook WF-01 (voir §4): http://n8n.dev.localhost/webhook/intake
- NATS monitoring: http://nats.dev.localhost (ou direct: http://localhost:8222)

En-têtes de sécurité (Caddy)
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: strict-origin-when-cross-origin
- Content-Security-Policy-Report-Only: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'
- X-Request-ID: géré par les upstreams (Nuxt, Django). Caddy transmet et ne supprime pas.


3) Vérifications attendues (checkpoints)
Checkpoint #1 (matin): Caddy + headers + X-Request-ID
- Nuxt (headers + X-Request-ID injecté côté Nuxt)
  ```bash
  curl -I http://dev.localhost
  ```
  Attendu: headers sécu présents, X-Request-ID présent.

- Django (headers via Caddy, X-Request-ID par middleware Django)
  ```bash
  curl -I http://api.dev.localhost/health
  ```

Checkpoint #2 (midi): Postgres + NATS
- Postgres (DBs créées):
  - pxp_app, pxp_n8n (créées par deploy/postgres/initdb/01_dbs.sql)
- NATS (publish/consume OK) — voir §5.

Checkpoint #3 (après-midi): n8n WF-01
- WF-01 activé, URL du trigger:
  - Production-mode: http://n8n.dev.localhost/webhook/intake
  - Test-mode (exécution manuelle): http://n8n.dev.localhost/webhook-test/intake
- POST avec payload minimal (voir §4) → publication simulée intake.lead.created loggée.

Jalon EOD:
- Nuxt /health OK (X-Request-ID affiché et propagation côté backend /api/hello).
- Django /api/schema/ OK.
- Gate Sécurité v1 exécutable (scripts fonctionnels, voir §7).
- Doc fournie (ce README).


4) n8n Workflow (WF-01 Intake→Roadmap)
- Export fourni: deploy/n8n/wf-01-intake.json
- Structure:
  - Trigger: Webhook POST /intake
  - Validate payload (email, project_name)
  - Publish to NATS (simulation Sprint 0: log propre du message subject intake.lead.created)
  - Create Epic & Tasks (TODO placeholder)
  - Notify (console log) → Respond 200 JSON

- URL du trigger:
  - http://n8n.dev.localhost/webhook/intake
  - Test manuel (n8n mode test):
    - http://n8n.dev.localhost/webhook-test/intake

- Exemple de POST:
  ```bash
  curl -sS -X POST http://n8n.dev.localhost/webhook/intake \
    -H 'Content-Type: application/json' \
    -H 'X-Request-ID: demo-n8n-123' \
    -d '{
      "email": "alice@example.com",
      "project_name": "Dojo",
      "description": "MVP brief"
    }' | jq .
  ```

Résultat attendu:
- 200 avec JSON { success:true, lead_id:..., epic_id:... } et logs n8n montrant:
  - [NATS Publish] Subject: intake.lead.created
  - Payload généré (id, email, project_name, timestamp, ...)


5) NATS JetStream (publish/consume)
- Serveur: nats:2.10 avec JetStream + accounts (dojo, clients, honeypot)
- Monitoring: http://nats.dev.localhost (varz, connz…)

Comptes & permissions (local/dev par défaut — à remplacer en prod):
- DOJO → user: dojo_user / pass: dojo_pass
  - Pub/Sub sur intake.*, spec.*, build.*, release.*, incident.* (+ $JS.>)
- CLIENTS → user: clients_user / pass: clients_pass
  - Publish intake.lead.>, intake.inquiry.>; subscribe _INBOX.> (réponses)
- HONEYPOT → user: honeypot_user / pass: honeypot_pass
  - Subscribe-only (lecture) sur sujets MVO

Tests rapides (via nats-box)
- Souscrire (dojo) à intake.>:
  ```bash
  docker run --rm -it --network host synadia/nats-box:0.14 \
    nats sub -s nats://dojo_user:dojo_pass@127.0.0.1:4222 'intake.>'
  ```

- Publier un message (dojo):
  ```bash
  docker run --rm -it --network host synadia/nats-box:0.14 \
    nats pub -s nats://dojo_user:dojo_pass@127.0.0.1:4222 'intake.lead.created' \
    '{"id":"demo-001","email":"alice@example.com","project_name":"Dojo","timestamp":"'"$(date -Iseconds)"'"}'
  ```

- Attendu: le subscriber affiche le message. Vous pouvez faire le POST n8n (cf. §4) pour simuler la publication côté orchestrateur (Sprint 0: log).


6) Secrets (sops/age)
- Doc d’usage: ops/secret/README.md
- Config SOPS: .sops.yaml (racine)
- Arbo:
  - ops/secret/keys/ (clés privées age — jamais commit)
  - ops/secret/dev|staging|prod/ (fichiers *.enc chiffrés)

Init local rapide:
```bash
# Générer une clé age (privée) — à ne PAS committer
age-keygen -o ops/secret/keys/local.key
grep 'public key' ops/secret/keys/local.key

# Chiffrer un .env d’exemple
cat > /tmp/backend.env <<'EOF'
DJANGO_SECRET_KEY=CHANGE_ME
DATABASE_URL=postgresql://pxp_app_user:pxp_app_pass@postgres:5432/pxp_app
ALLOWED_HOSTS=api.dev.localhost,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://dev.localhost,http://api.dev.localhost
EOF

sops --encrypt /tmp/backend.env > ops/secret/dev/backend.env.enc
rm /tmp/backend.env
```

Utiliser en local:
```bash
# Déchiffrer quand nécessaire
sops --decrypt ops/secret/dev/backend.env.enc > backend/.env
```


7) Gate Sécurité v1 (Trivy + Semgrep)
Script: ops/security/gate_v1.sh

- Pré-requis:
  - Docker (le script lance les scanners en containers)
- Lancer:
  ```bash
  chmod +x ops/security/gate_v1.sh
  ./ops/security/gate_v1.sh
  ```
- Comportement par défaut:
  - Trivy: bloque sur vulnérabilités HIGH/CRITICAL des images:
    caddy:2.8.4-alpine, node:22-alpine, python:3.13-slim, postgres:17.0-alpine, nats:2.10.8-alpine, n8nio/n8n:1.72.0
  - Semgrep: SAST sur backend et frontend (règles p/owasp-top-ten), bloque à partir de ERROR.
- Variables utiles:
  ```bash
  PXP_TRIVY_IMAGES="caddy:2.8.4-alpine python:3.13-slim" ./ops/security/gate_v1.sh
  PXP_SEMGREP_DIRS="backend frontend" ./ops/security/gate_v1.sh
  PXP_FAIL_ON_SEMGREP_WARNINGS=1 ./ops/security/gate_v1.sh  # bloque aussi sur WARNING
  ```
- Sortie:
  - PASS: code 0
  - FAIL: code 1 (liste les images/fichiers fautifs + log en ops/security/_logs/gate_*.log)


8) Limitations connues (Jour J)
- TLS local/mTLS: non activés (Caddy auto_https off). Option mkcert à prévoir si nécessaire rapidement.
- X-Request-ID côté proxy: Caddy relaie et n’injecte pas. Injection gérée par Nuxt (middleware server) et Django (middleware) — corrélation OK.
- n8n → NATS: publication simulée par logs (Sprint 0). Intégration client NATS dédiée à brancher dans les jours suivants.
- Auth forte:
  - TOTP et WebAuthn sont amorcés côté back/front (dépendances présentes) mais non finalisés pour Jour J (flux complet en prochaine itération).
- NATS accounts:
  - Credentials par défaut de dev dans deploy/nats/nats.conf (à remplacer par NKeys/JWT en prod, + mTLS).
- Images:
  - Épinglées par tag (jour J). À pinner par digest en prod.
- Exposition:
  - Monitoring NATS via Caddy (local uniquement). À restreindre en dehors du localhost.


9) Next steps (préparées mais non à faire aujourd’hui)
- WebAuthn complet (step-up sur endpoints sensibles), TOTP fallback consolidé.
- Playwright smoke E2E (login + 1 CRUD simple).
- Backups chiffrés automatisés + test de restauration (Postgres).
- Observabilité enrichie (Loki/Grafana), corrélation logs via X-Request-ID.
- n8n → NATS: publication réelle via client officiel, streams/consumers JetStream.



Annexe — Aide-mémoire commandes utiles

Services
```bash
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f caddy
docker compose -f deploy/docker-compose.yml logs -f backend
docker compose -f deploy/docker-compose.yml logs -f frontend
docker compose -f deploy/docker-compose.yml restart caddy
```

Caddy — headers
```bash
curl -I http://dev.localhost
curl -I http://api.dev.localhost/health
```

Frontend /health (propagation X-Request-ID)
```bash
# Définit un X-Request-ID custom et observe la propagation jusqu’au backend (via /api/hello)
curl -sS -H 'X-Request-ID: demo-123' http://dev.localhost/health | jq .
```

Backend (Django)
```bash
curl -sS http://api.dev.localhost/health | jq .
curl -sS http://api.dev.localhost/api/hello/ | jq .
curl -sS http://api.dev.localhost/api/schema/ | head -n 40
```

n8n — replay WF-01
```bash
curl -sS -X POST http://n8n.dev.localhost/webhook/intake \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","project_name":"Dojo"}' | jq .
```

NATS — publish/subscribe (dojo)
```bash
# Sub
docker run --rm -it --network host synadia/nats-box:0.14 \
  nats sub -s nats://dojo_user:dojo_pass@127.0.0.1:4222 'intake.>'

# Pub
docker run --rm -it --network host synadia/nats-box:0.14 \
  nats pub -s nats://dojo_user:dojo_pass@127.0.0.1:4222 'intake.lead.created' \
  '{"id":"demo-001","email":"alice@example.com","project_name":"Dojo"}'
```

Gate Sécurité v1
```bash
./ops/security/gate_v1.sh
# PASS → code 0, FAIL → code 1, logs sous ops/security/_logs/
```

Postgres — init attendu
- DB: pxp_app (owner: pxp_app_owner, app role: pxp_app_user)
- DB: pxp_n8n (owner: pxp_n8n_owner, app role: pxp_n8n_user)
- Privileges deny-by-default, GRANTs minimums.


Fin — Jour J
- Si blocage rencontré, documenté dans ce fichier et escaladé; passage à l’étape suivante pour tenir le jalon EOD.
- Pour toute anomalie reproductible, conserver la commande et la sortie console correspondantes.
