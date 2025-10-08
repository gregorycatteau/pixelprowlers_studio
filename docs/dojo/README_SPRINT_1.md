# PixelProwlers Studio — README Sprint 1 (J+1 → J+2)

Objectif: rendre opérationnel le flux end-to-end sécurisé
Form → n8n (WF-01) → Events Gateway (HMAC) → NATS JetStream → Consumer → DB,
avec secrets chiffrés (sops/age), HTTPS local et probes/tests de validation.

Sommaire
- 0) Contexte & périmètre
- 1) HTTPS local (mkcert) + Caddy
- 2) Events Gateway (Django/DRF) — HMAC
- 3) Aide HMAC (helpers CLI Bash/Python)
- 4) Consumer JetStream (persist leads)
- 5) n8n — import/activation + POST signé
- 6) Gate Sécurité v1.1 + audits
- 7) Secrets (sops/age)
- 8) Checkpoints & Validation
- 9) Troubleshooting


0) Contexte & périmètre

- Proxy Caddy conservé, Request-ID injecté applicativement (Nuxt/Django).
- N8N n’obtient pas d’accès NATS: passage par un Gateway HTTP (HMAC) côté backend.
- Résultat attendu (EOD): POST intake → Gateway (HMAC) → NATS → Consumer → DB (leads),
  HTTPS local OK, gates de sécurité OK, doc et commandes prêtes.


1) HTTPS local (mkcert) + Caddy

Pré-requis
- mkcert installé et racine locale installée:
  - macOS: brew install mkcert nss; mkcert -install
  - Linux: voir https://github.com/FiloSottile/mkcert (mkcert -install)
- Certificats à générer pour 4 hôtes:
  - dev.localhost
  - api.dev.localhost
  - n8n.dev.localhost
  - nats.dev.localhost

Génération (depuis deploy/caddy/certs/)
- Crée le dossier si nécessaire:
  mkdir -p deploy/caddy/certs
- Génère les certs (répéter pour chaque hôte):
  cd deploy/caddy/certs
  mkcert -cert-file dev.localhost.crt  -key-file dev.localhost.key  "dev.localhost"
  mkcert -cert-file api.dev.localhost.crt -key-file api.dev.localhost.key "api.dev.localhost"
  mkcert -cert-file n8n.dev.localhost.crt -key-file n8n.dev.localhost.key "n8n.dev.localhost"
  mkcert -cert-file nats.dev.localhost.crt -key-file nats.dev.localhost.key "nats.dev.localhost"

Caddy (compose déjà prêt à monter les certs)
- Port 443 exposé, montage ./caddy/certs → /etc/caddy/certs
- Redémarrer le proxy:
  docker compose -f deploy/docker-compose.yml restart caddy

Vérification HTTPS
- En-têtes sécu et réponse en HTTPS (si la racine mkcert est bien installée, pas besoin de -k):
  curl -I https://dev.localhost
  curl -I https://api.dev.localhost/health

Attendus:
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- Content-Security-Policy-Report-Only: (policy)
- X-Request-ID: présent (injecté applicatif)


2) Events Gateway (Django/DRF) — HMAC

Endpoint (whitelist sujets)
- POST https://api.dev.localhost/api/events/intake.lead.created
- Uniquement ce sujet autorisé en Sprint 1 (deny-by-default).

Sécurité
- HMAC obligatoire:
  - Headers:
    - X-Timestamp: <epoch_seconds>
    - X-Signature: sha256=<hex_digest>  (ou uniquement <hex_digest>)
  - Base de signature: "${timestamp}.${raw_body}"
  - Secret: injecté côté gateway via env/fichier; côté n8n, fourni via fichier monté (runtime), jamais commité.

Rate-limit & skew
- Fenêtre temporelle: ±60s
- Rate-limit minimal par IP (si ratelimit dispo)

Publication NATS
- Gateway publie l’événement en JSON sur NATS (JetStream) avec:
  - subject, data (payload), request_id, timestamp
- request_id est toujours tracé.


3) Aide HMAC (helpers CLI Bash/Python)

Bash (avec openssl)
- Prérequis:
  - Secret en clair (dev) dans: ops/secret/dev/events_gateway.hmac.key.dec
  - Body JSON sauvegardé dans /tmp/body.json

Exemple 1 — fonction shell de signature
```bash
hmac_sign() {
  # Usage: hmac_sign <secret_file> <timestamp> <json_body_file>
  local secret_file="$1"; shift
  local ts="$1"; shift
  local body_file="$1"

  local data="${ts}.$(cat "$body_file")"
  # openssl renvoie "SHA256(stdin)= <hex>" selon env; -r retourne "<hex> *stdin"
  local hex
  hex="$(printf "%s" "$data" | openssl dgst -sha256 -hmac "$(cat "$secret_file")" -binary | xxd -p -c 256)"
  printf "%s" "$hex"
}
```

Exemple 2 — curl signé HMAC (Gateway)
```bash
SECRET_FILE="ops/secret/dev/events_gateway.hmac.key.dec"
BODY_FILE="/tmp/body.json"
TS="$(date +%s)"

# Corps d'exemple
cat > "$BODY_FILE" <<'JSON'
{
  "id": "lead_demo_001",
  "email": "alice@example.com",
  "project_name": "Dojo",
  "timestamp": "2025-01-01T00:00:00Z"
}
JSON

SIG_HEX="$(hmac_sign "$SECRET_FILE" "$TS" "$BODY_FILE")"

curl -sS -X POST "https://api.dev.localhost/api/events/intake.lead.created" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: ${TS}" \
  -H "X-Signature: sha256=${SIG_HEX}" \
  -H "X-Request-ID: demo-sprint1-123" \
  --data-binary "@${BODY_FILE}" | jq .
```

Python (one-liner)
```bash
python - <<'PY'
import hmac, hashlib, time, json, sys, pathlib
secret = pathlib.Path("ops/secret/dev/events_gateway.hmac.key.dec").read_text().strip().encode()
ts = str(int(time.time()))
body = json.dumps({
  "id": "lead_demo_002",
  "email": "bob@example.com",
  "project_name": "Dojo",
  "timestamp": "2025-01-01T00:00:01Z"
}, separators=(',',':'))
msg = f"{ts}.{body}".encode()
sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()
print("TS=", ts)
print("SIG_HEX=", sig)
print("BODY=", body)
PY
```


4) Consumer JetStream (persist leads)

Service
- Le consumer durable écoute intake.lead.created et persiste les événements en table api_lead.
- Service docker dédié: backend_consumer (compose) lance la management command:
  - python manage.py events_consumer

Observabilité
- Logs:
  docker compose -f deploy/docker-compose.yml logs -f backend_consumer

Vérifier la persistance
- Accès psql rapide:
  docker exec -it pxp_postgres psql -U postgres -d pxp_app -c \
    "SELECT event_id,email,project_name,request_id,received_at FROM api_lead ORDER BY received_at DESC LIMIT 5;"

Attendu: une ligne correspondant à votre POST HMAC (email, project_name, request_id, etc.).


5) n8n — import/activation + POST signé

Import/activation automatique (API n8n)
- Export workflow (fourni): deploy/n8n/wf-01-intake.json
- L’API n8n REST nécessite une authentification (Basic Auth, token, ou via UI).
  - En Sprint 1, selon votre configuration locale:
    - Si Basic Auth activée sur n8n (variables d’env): utilisez -u user:password
    - Sinon: utilisez l’UI n8n pour obtenir un cookie/token puis rejouer les appels REST.

Exemples (à adapter selon auth et version API):
- Créer le workflow:
```bash
curl -sS -X POST "https://n8n.dev.localhost/rest/workflows" \
  -u "admin:admin" \
  -H "Content-Type: application/json" \
  --data-binary "@deploy/n8n/wf-01-intake.json" | jq .
```

- Activer (si nécessaire, remplacer {id}):
```bash
curl -sS -X PATCH "https://n8n.dev.localhost/rest/workflows/{id}" \
  -u "admin:admin" \
  -H "Content-Type: application/json" \
  -d '{"active": true}' | jq .
```

Modifier WF-01 pour POST signer vers Gateway
- Dans WF-01, remplacer la “publication NATS simulée” par un HTTP Request vers:
  - URL: https://api.dev.localhost/api/events/intake.lead.created
  - Méthode: POST
  - Body: JSON (id, email, project_name, timestamp, request_id si dispo)
- HMAC:
  - Calculer X-Timestamp et X-Signature en amont de l’HTTP Request (via un node qui calcule la signature).
  - Secret: monté dans le container n8n comme fichier runtime (/run/secrets/n8n_hmac_secret).
  - Ne pas committer le secret dans le workflow JSON.
- Si la génération HMAC embarquée n’est pas supportée par vos nodes:
  - Option 1 (temporaire): appeler un signer local minimal (sidecar) qui retourne les headers à injecter.
  - Option 2: gateway accepte un header X-Signature pré-calculé (généré côté script) dans un premier temps pour valider l’E2E (à remplacer ensuite par signature n8n).

Webhook WF-01
- Production URL: https://n8n.dev.localhost/webhook/intake
- Test URL: https://n8n.dev.localhost/webhook-test/intake


6) Gate Sécurité v1.1 + audits

Gate (Trivy + Semgrep)
- Script (fail si vuln High/CRIT):
  ./ops/security/gate_v1.sh

Audits (warning-only pour Sprint 1)
- npm (frontend):
  (cd frontend && npm audit --audit-level=high || true)
- pip (backend) — si vous avez pip-audit:
  (cd backend && poetry run pip-audit || true)
  (ou pipx run pip-audit)

Digests (option check)
- Vous pouvez vérifier le digest d’une image:
  docker pull python:3.13-slim
  docker inspect --format='{{index .RepoDigests 0}}' python:3.13-slim
- Pour la prod, pinner par digest @sha256 (compose: image: <name>@sha256:<digest>).


7) Secrets (sops/age)

But
- Aucun secret en clair dans Git.
- Le secret HMAC du Gateway est géré par sops/age côté repo, et déchiffré localement avant montage runtime.

Exemple (Sprint 1)
- Générer un secret HMAC (ex. 32 bytes hex):
  head -c 32 /dev/urandom | xxd -p -c 64 > /tmp/events_hmac.key
- Chiffrer avec sops:
  sops --encrypt /tmp/events_hmac.key > ops/secret/dev/events_gateway.hmac.key.age
- Déchiffrer localement quand nécessaire (montage runtime par compose):
  sops --decrypt ops/secret/dev/events_gateway.hmac.key.age > ops/secret/dev/events_gateway.hmac.key.dec
- Le compose référence:
  secrets:
    n8n_hmac_secret:
      file: ../ops/secret/dev/events_gateway.hmac.key.dec
- Important:
  - .gitignore protège les .dec
  - Ne pas committer de .dec


8) Checkpoints & Validation

Checkpoint #1 — HTTPS + Gateway HMAC
- HTTPS OK:
  curl -I https://dev.localhost
  curl -I https://api.dev.localhost/health
- Gateway:
  - 401/403 sans X-Signature
  - 200 avec signature valide:
    (voir “Aide HMAC” pour curl signé)

Checkpoint #2 — Consumer + DB
- Logs consumer (consumed event):
  docker compose -f deploy/docker-compose.yml logs -f backend_consumer
- DB (ligne présente):
  docker exec -it pxp_postgres psql -U postgres -d pxp_app -c \
    "SELECT event_id,email,project_name,request_id,received_at FROM api_lead ORDER BY received_at DESC LIMIT 5;"

Checkpoint #3 — n8n auto-import + POST signé
- Import/activation via REST
- POST WF-01 → Gateway (HMAC) → 200
- Confirmer réception côté consumer + DB

Jalon EOD — E2E démontré
- Formulaire intake (ou POST manuel) → Gateway (HMAC) → NATS → Consumer → DB
- Gate v1.1 PASS (0 High), audits warning-only OK


9) Troubleshooting

- Certificat non reconnu (HTTPS):
  - Assurez-vous d’avoir exécuté mkcert -install et d’avoir généré les 4 certs dans deploy/caddy/certs/.
  - Redémarrez le service caddy.
- 401 invalid_signature:
  - Vérifier base de signature: "${timestamp}.${raw_body}" (raw exactement envoyé).
  - Vérifier horloge (skew ±60s).
  - Vérifier secret monté côté compose (fichier .dec présent et lisible).
- n8n REST 401/403:
  - Activer l’auth Basic (variables d’env) ou authentifiez-vous via l’UI pour obtenir un cookie/token.
- Consumer ne reçoit rien:
  - Vérifier que Gateway publie (réponse 200).
  - Vérifier NATS up (http(s)://nats.dev.localhost), et que le sujet intake.lead.created est correct.
- DB vide:
  - Vérifier logs consumer; vérifier table api_lead.
  - Vérifier que l’event contient id/email/project_name (validation MVO).

Références utiles
- Compose: deploy/docker-compose.yml
- Proxy Caddy: deploy/caddy/Caddyfile
- NATS conf: deploy/nats/nats.conf
- n8n export: deploy/n8n/wf-01-intake.json
- Secrets: ops/secret/README.md, .sops.yaml
- Gate: ops/security/gate_v1.sh

Fin Sprint 1 — prêt pour démonstration E2E sécurisée.
