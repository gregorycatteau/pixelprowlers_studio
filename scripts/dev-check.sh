#!/usr/bin/env bash
set -euo pipefail

echo "🔎 Vérification environnement dev (PostgreSQL 5432 / Redis 6379)…"

check_postgres() {
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -h localhost -p 5432 >/dev/null 2>&1
    return $?
  fi

  if command -v ss >/dev/null 2>&1 && ss -ltn | grep -q ':5432'; then
    return 0
  fi

  if command -v lsof >/dev/null 2>&1 && lsof -iTCP:5432 -sTCP:LISTEN >/dev/null 2>&1; then
    return 0
  fi

  return 1
}

if check_postgres; then
  echo "✅ PostgreSQL écoute sur 5432"
else
  echo "❌ PostgreSQL n'écoute pas sur 5432" >&2
  echo "   → Lance ton service (ex: sudo systemctl start postgresql) ou vérifie avec 'psql -h localhost -p 5432 -U <user> <db>'" >&2
  exit 1
fi

if redis-cli ping >/dev/null 2>&1; then
  echo "✅ Redis accessible sur 6379"
elif command -v nc >/dev/null 2>&1 && nc -z localhost 6379 >/dev/null 2>&1; then
  echo "✅ Redis accessible sur 6379"
else
  echo "❌ Redis indisponible sur 6379" >&2
  echo "   → Installe/active redis-server ou lance 'docker run --name pxp_dev_redis -p 6379:6379 -d redis:7-alpine'" >&2
  exit 1
fi

echo "✅ Checks terminés"
