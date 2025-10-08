# PixelProwlers Studio — Sprint 1 Operator Checklist (Local Dev)

This checklist consolidates **Jour J (Sprint 0)** bring-up, **Auth/Security addendum**, and **Sprint 1 E2E** tasks into a single, operator‑friendly sequence.

> Priorities (always): **Sécurité → Ergonomie → Design**

---

## 0) Pre-flight

- [ ] Docker + Docker Compose installed
- [ ] Required local ports free: 80, 443, 3000, 8000, 4222/8222, 5432, 5678
- [ ] `dev.localhost` DNS works; if not, add to `/etc/hosts`:
  ```bash
  echo "127.0.0.1 dev.localhost api.dev.localhost n8n.dev.localhost nats.dev.localhost" | sudo tee -a /etc/hosts
  ```

---

## 1) Bring up Sprint 0 (Jour J)

- [ ] Start stack:
  ```bash
  docker compose -f deploy/docker-compose.yml up -d
  docker compose -f deploy/docker-compose.yml logs -f --tail=200
  ```

- [ ] Health & headers check (HTTP):
  ```bash
  curl -I http://dev.localhost
  curl -I http://api.dev.localhost/health
  ```

- [ ] n8n UI & webhook endpoints reachable:
  - UI: `http://n8n.dev.localhost`
  - Webhook (test): `http://n8n.dev.localhost/webhook-test/intake`

- [ ] NATS monitoring reachable: `http://nats.dev.localhost`

- [ ] Optional security gate v1 (Trivy + Semgrep):
  ```bash
  chmod +x ops/security/gate_v1.sh
  ./ops/security/gate_v1.sh
  ```

**References:** `README_JOUR_J.md`

---

## 2) Enable HTTPS locally (mkcert) — Sprint 1

- [ ] Install mkcert root:
  - Linux: see mkcert docs; typically `mkcert -install`

- [ ] Generate certs (from repo root):
  ```bash
  mkdir -p deploy/caddy/certs && cd deploy/caddy/certs
  mkcert -cert-file dev.localhost.crt  -key-file dev.localhost.key  "dev.localhost"
  mkcert -cert-file api.dev.localhost.crt -key-file api.dev.localhost.key "api.dev.localhost"
  mkcert -cert-file n8n.dev.localhost.crt -key-file n8n.dev.localhost.key "n8n.dev.localhost"
  mkcert -cert-file nats.dev.localhost.crt -key-file nats.dev.localhost.key "nats.dev.localhost"
  cd -
  docker compose -f deploy/docker-compose.yml restart caddy
  ```

- [ ] Verify HTTPS + headers:
  ```bash
  curl -I https://dev.localhost
  curl -I https://api.dev.localhost/health
  ```

**References:** `README_SPRINT_1.md`

---

## 3) Secrets (sops/age) — Sprint 1

- [ ] Generate age key (if not present) and encrypt HMAC secret:
  ```bash
  age-keygen -o ops/secret/keys/local.key
  head -c 32 /dev/urandom | xxd -p -c 64 > /tmp/events_hmac.key
  sops --encrypt /tmp/events_hmac.key > ops/secret/dev/events_gateway.hmac.key.age
  sops --decrypt ops/secret/dev/events_gateway.hmac.key.age > ops/secret/dev/events_gateway.hmac.key.dec
  rm /tmp/events_hmac.key
  ```

- [ ] (Optional) Prepare backend .env via sops:
  ```bash
  cat > /tmp/backend.env <<'EOF'
  DJANGO_SECRET_KEY=CHANGE_ME
  DATABASE_URL=postgresql://pxp_app_user:pxp_app_pass@postgres:5432/pxp_app
  ALLOWED_HOSTS=api.dev.localhost,localhost,127.0.0.1
  CSRF_TRUSTED_ORIGINS=https://dev.localhost,https://api.dev.localhost
  EOF

  sops --encrypt /tmp/backend.env > ops/secret/dev/backend.env.enc
  sops --decrypt ops/secret/dev/backend.env.enc > backend/.env
  rm /tmp/backend.env
  ```

**References:** `README_JOUR_J.md`, `README_SPRINT_1.md`

---

## 4) Events Gateway (HMAC) → NATS → Consumer → DB

- [ ] Confirm backend_consumer service is running (compose) and tail logs:
  ```bash
  docker compose -f deploy/docker-compose.yml ps
  docker compose -f deploy/docker-compose.yml logs -f backend_consumer
  ```

- [ ] Create HMAC-signed POST (helper function):
  ```bash
  SECRET_FILE="ops/secret/dev/events_gateway.hmac.key.dec"
  BODY_FILE="/tmp/body.json"
  TS="$(date +%s)"
  cat > "$BODY_FILE" <<'JSON'
  {
    "id": "lead_demo_001",
    "email": "alice@example.com",
    "project_name": "Dojo",
    "timestamp": "2025-01-01T00:00:00Z"
  }
  JSON

  hmac_sign() { local secret_file="$1"; local ts="$2"; local body_file="$3";
    local data="${ts}.$(cat "$body_file")"
    local hex; hex="$(printf "%s" "$data" | openssl dgst -sha256 -hmac "$(cat "$secret_file")" -binary | xxd -p -c 256)"
    printf "%s" "$hex"
  }

  SIG_HEX="$(hmac_sign "$SECRET_FILE" "$TS" "$BODY_FILE")"

  curl -sS -X POST "https://api.dev.localhost/api/events/intake.lead.created"     -H "Content-Type: application/json"     -H "X-Timestamp: ${TS}"     -H "X-Signature: sha256=${SIG_HEX}"     -H "X-Request-ID: demo-sprint1-123"     --data-binary "@${BODY_FILE}" | jq .
  ```

- [ ] Verify DB persistence:
  ```bash
  docker exec -it pxp_postgres psql -U postgres -d pxp_app -c     "SELECT event_id,email,project_name,request_id,received_at FROM api_lead ORDER BY received_at DESC LIMIT 5;"
  ```

**References:** `README_SPRINT_1.md`

---

## 5) n8n — Import/activate WF-01 and POST via Gateway

- [ ] Import WF via REST (adjust auth per your n8n setup):
  ```bash
  curl -sS -X POST "https://n8n.dev.localhost/rest/workflows"     -u "admin:admin"     -H "Content-Type: application/json"     --data-binary "@deploy/n8n/wf-01-intake.json" | jq .
  ```

- [ ] Activate workflow (replace {id}):
  ```bash
  curl -sS -X PATCH "https://n8n.dev.localhost/rest/workflows/{id}"     -u "admin:admin"     -H "Content-Type: application/json"     -d '{"active": true}' | jq .
  ```

- [ ] Modify WF-01 to call the Gateway with HMAC (use mounted secret `/run/secrets/n8n_hmac_secret` or a sidecar signer).
  Then trigger: `https://n8n.dev.localhost/webhook/intake`

- [ ] Confirm event processed by consumer + persisted in DB (see §4).

**References:** `README_SPRINT_1.md`

---

## 6) Security chores (Auth addendum + gates)

- [ ] Run security gate v1.1 (Trivy + Semgrep):
  ```bash
  ./ops/security/gate_v1.sh
  ```

- [ ] Verify CSP report endpoint works and produces no blocking:
  - `/api/csp-report` exists and returns `{ ok: true }`
  - Switch from `report-only` to `enforce` after 48–72h clean logs

- [ ] Verify auth rate-limits, cookie flags, JWKS, and Nextcloud seal command (when configured):
  - TOTP/WebAuthn ratelimits return 429 upon threshold exceed
  - Cookies use `__Host-` prefix, `HttpOnly; Secure; SameSite=Strict`
  - `GET /.well-known/jwks.json` exposed per realm
  - `python manage.py seal_laby_bundle --dry-run` succeeds

**References:** `README_AUTH.md`

---

## 7) Troubleshooting Quickies

- HTTPS 495/526 or trust issues → ensure `mkcert -install` and regenerate certs
- 401 `invalid_signature` → check `${timestamp}.${raw_body}`, skew ±60s, correct secret
- n8n REST 401/403 → enable Basic Auth or login in UI to obtain token
- Consumer idle → confirm Gateway returns 200; check NATS status; subject spelling
- DB empty → check consumer logs; verify required JSON fields

---

## 8) Nice-to-have Make targets (optional)

Add to `Makefile`:
```make
up: ; docker compose -f deploy/docker-compose.yml up -d
down: ; docker compose -f deploy/docker-compose.yml down
logs: ; docker compose -f deploy/docker-compose.yml logs -f --tail=200
certs:
	mkdir -p deploy/caddy/certs && cd deploy/caddy/certs && \
	mkcert -cert-file dev.localhost.crt -key-file dev.localhost.key dev.localhost && \
	mkcert -cert-file api.dev.localhost.crt -key-file api.dev.localhost.key api.dev.localhost && \
	mkcert -cert-file n8n.dev.localhost.crt -key-file n8n.dev.localhost.key n8n.dev.localhost && \
	mkcert -cert-file nats.dev.localhost.crt -key-file nats.dev.localhost.key nats.dev.localhost
sign:
	SECRET_FILE=ops/secret/dev/events_gateway.hmac.key.dec \
	BODY_FILE=/tmp/body.json \
	TS=$$(date +%s); \
	printf '%s' $$TS.$$(cat $$BODY_FILE) | openssl dgst -sha256 -hmac "$$(cat $$SECRET_FILE)" -binary | xxd -p -c 256
```

---

## 9) Operator Notes

- Do not commit any `.dec` files or secrets — ensure `.gitignore` covers them.
- Prefer pinning images by **digest** in production (compose supports `image@sha256:<digest>`).
- Keep **Request-ID** propagation in all calls for traceability (curl `-H 'X-Request-ID: …'`).
