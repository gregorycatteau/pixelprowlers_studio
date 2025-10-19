# Deploy — Quick README (NATS + n8n)

Minimal, copy-paste friendly commands to validate NATS and n8n locally.

Related files:
- `deploy/docker-compose.yml`
- `deploy/nats/nats.conf`
- `deploy/n8n/wf-01-intake.json`

Local hostnames (via Caddy, HTTP only for dev):
- n8n:      http://n8n.dev.localhost
- NATS UI:  http://nats.dev.localhost  (or http://localhost:8222)


## 1) Start the stack

From repo root:
```bash
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps
```


## 2) n8n — Trigger WF-01 Intake → Roadmap

Workflow export: `deploy/n8n/wf-01-intake.json`
- Trigger (POST): `/webhook/intake`
- Validates payload: `email`, `project_name`
- Publishes (Sprint 0 = logs) to `intake.lead.created`
- Responds with JSON

Trigger (production mode URL via Caddy):
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

Optional (test mode inside n8n):
```bash
curl -sS -X POST http://n8n.dev.localhost/webhook-test/intake \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","project_name":"Dojo"}' | jq .
```

Open n8n UI to activate/import the workflow if needed:
- http://n8n.dev.localhost


## 3) NATS — Publish / Subscribe (JetStream enabled)

Monitoring:
- http://nats.dev.localhost or http://localhost:8222

Local dev accounts (from `deploy/nats/nats.conf`; do not use in prod):
- DOJO     → user: `dojo_user`     / pass: `dojo_pass`
- CLIENTS  → user: `clients_user`  / pass: `clients_pass`
- HONEYPOT → user: `honeypot_user` / pass: `honeypot_pass`

Subjects (MVO):
- `intake.*`, `spec.*`, `build.*`, `release.*`, `incident.*`

Quick subscribe (DOJO) to `intake.>`:
```bash
docker run --rm -it --network host synadia/nats-box:0.14 \
  nats sub -s nats://dojo_user:dojo_pass@127.0.0.1:4222 'intake.>'
```

Quick publish (DOJO) to `intake.lead.created`:
```bash
docker run --rm -it --network host synadia/nats-box:0.14 \
  nats pub -s nats://dojo_user:dojo_pass@127.0.0.1:4222 'intake.lead.created' \
  '{"id":"demo-001","email":"alice@example.com","project_name":"Dojo","timestamp":"'"$(date -Iseconds)"'"}'
```

Tip: Run the subscriber first in one terminal, then publish from another to see the event arrive.


## 4) Stop / Clean up

```bash
docker compose -f deploy/docker-compose.yml stop
docker compose -f deploy/docker-compose.yml down
# Optional: remove volumes (DB, JetStream, etc.)
# docker compose -f deploy/docker-compose.yml down -v
```


## 5) Troubleshooting (quick)

- If `dev.localhost` subdomains don’t resolve (rare), add to `/etc/hosts`:
  ```
  127.0.0.1 dev.localhost api.dev.localhost n8n.dev.localhost nats.dev.localhost
  ```
- n8n webhook 404:
  - Ensure the workflow is activated and triggered on “Production” URL (`/webhook/…`).
- NATS connection refused:
  - Check the service is up: `docker compose -f deploy/docker-compose.yml ps`
  - Use `127.0.0.1:4222` in examples (host network in nats-box container).
- Credentials fail:
  - Confirm `deploy/nats/nats.conf` is mounted (compose does) and the server restarted.


## 6) Security notes (dev only)

- Local-only exposure (HTTP on `:80`, NATS monitoring on `:8222`).
- Credentials in this README are for local dev. For production:
  - switch to NKeys/JWT for NATS,
  - enable TLS/mTLS,
  - do not expose monitoring publicly.
