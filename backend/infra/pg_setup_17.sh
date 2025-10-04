#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# pg_setup_17.sh — Provision PostgreSQL 17 (port 5434) pour PixelProwlers
# Corrigé : CREATE DATABASE hors transaction (pas de DO $$ ... $$)
# -----------------------------------------------------------------------------
set -Eeuo pipefail

PG_VER="17"
PG_CLUSTER="main"
PG_PORT="5434"
PG_HOST="127.0.0.1"

# ⚠️ Modifie ces mdp (local/dev uniquement)
PWD_DEV="change_this_dev_password"
PWD_TEST="change_this_test_password"
PWD_UPG="change_this_upg_password"

ROLE_DEV="pxp_dev_user"
ROLE_TEST="pxp_test_user"
ROLE_UPG="pxp_upg_user"

DB_DEV="pxp_dev"
DB_TEST="pxp_test"
DB_UPG="pxp_upgrade"

CONF_DIR="/etc/postgresql/${PG_VER}/${PG_CLUSTER}"
PG_HBA="${CONF_DIR}/pg_hba.conf"
PG_CONF="${CONF_DIR}/postgresql.conf"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"

say() { printf "%s\n" "$*"; }

# --- Vérif cluster ---
say "🔎 Vérification du cluster ${PG_VER}-${PG_CLUSTER}..."
systemctl is-active "postgresql@${PG_VER}-${PG_CLUSTER}.service" >/dev/null || {
  say "❌ Cluster ${PG_VER}-${PG_CLUSTER} inactif. Lance : sudo systemctl start postgresql@${PG_VER}-${PG_CLUSTER}"
  exit 1
}
say "✅ Cluster actif."

# --- Durcissement local ---
say "🔐 Durcissement local (SCRAM + loopback + timeouts)..."
# postgresql.conf
ensure_conf_line() {
  local key="$1"; local val="$2"
  grep -q "^${key} =" "${PG_CONF}" && sed -i "s|^${key} =.*|${key} = ${val}|" "${PG_CONF}" || echo "${key} = ${val}" >> "${PG_CONF}"
}
sed -i "s/^#\?password_encryption.*/password_encryption = 'scram-sha-256'/" "${PG_CONF}" || true
sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost'/" "${PG_CONF}" || true
ensure_conf_line "log_connections" "on"
ensure_conf_line "log_disconnections" "on"
ensure_conf_line "log_min_duration_statement" "200ms"
ensure_conf_line "statement_timeout" "'30s'"
ensure_conf_line "idle_in_transaction_session_timeout" "'60s'"
# profiling SQL
if ! grep -q "^shared_preload_libraries = 'pg_stat_statements'" "${PG_CONF}"; then
  if grep -q "^shared_preload_libraries" "${PG_CONF}"; then
    sed -i "s|^shared_preload_libraries =.*|shared_preload_libraries = 'pg_stat_statements'|" "${PG_CONF}"
  else
    echo "shared_preload_libraries = 'pg_stat_statements'" >> "${PG_CONF}"
  fi
fi

# pg_hba.conf
grep -q "127.0.0.1/32" "${PG_HBA}" || sed -i '1ihost    all             all             127.0.0.1/32            scram-sha-256' "${PG_HBA}"
grep -q "::1/128"      "${PG_HBA}" || sed -i '1ihost    all             all             ::1/128                  scram-sha-256' "${PG_HBA}"

say "🔁 Reload config..."
systemctl reload "postgresql@${PG_VER}-${PG_CLUSTER}.service"

# --- ROLES (OK dans DO $$) ---
say "👤 Création des rôles (port ${PG_PORT})..."
sudo -u postgres psql -p "${PG_PORT}" <<SQL
DO \$\$ BEGIN
  CREATE ROLE ${ROLE_DEV}  LOGIN PASSWORD '${PWD_DEV}';
EXCEPTION WHEN duplicate_object THEN RAISE NOTICE 'role ${ROLE_DEV} existe déjà'; END \$\$;
DO \$\$ BEGIN
  CREATE ROLE ${ROLE_TEST} LOGIN PASSWORD '${PWD_TEST}';
EXCEPTION WHEN duplicate_object THEN RAISE NOTICE 'role ${ROLE_TEST} existe déjà'; END \$\$;
DO \$\$ BEGIN
  CREATE ROLE ${ROLE_UPG}  LOGIN PASSWORD '${PWD_UPG}';
EXCEPTION WHEN duplicate_object THEN RAISE NOTICE 'role ${ROLE_UPG} existe déjà'; END \$\$;
SQL

# --- DATABASES (HORS transaction, via tests Bash) ---
create_db_if_missing () {
  local dbname="$1" owner="$2"
  if sudo -u postgres psql -p "${PG_PORT}" -Atqc "SELECT 1 FROM pg_database WHERE datname='${dbname}'" | grep -q 1; then
    say "  • DB ${dbname} existe déjà."
  else
    say "  • Création DB ${dbname} (OWNER ${owner})..."
    sudo -u postgres psql -p "${PG_PORT}" -c "CREATE DATABASE ${dbname} OWNER ${owner};"
  fi
}

say "🗄️ Création des bases (hors transaction)..."
create_db_if_missing "${DB_DEV}"  "${ROLE_DEV}"
create_db_if_missing "${DB_TEST}" "${ROLE_TEST}"
create_db_if_missing "${DB_UPG}"  "${ROLE_UPG}"

# --- Extensions ---
say "📊 Activation extension pg_stat_statements..."
for DB in "${DB_DEV}" "${DB_TEST}" "${DB_UPG}"; do
  sudo -u postgres psql -p "${PG_PORT}" -d "${DB}" -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;" || true
done

# --- .env.* ---
say "🧩 Génération des .env.* (si absents)..."
mkdir -p "${BACKEND_DIR}"
create_env() {
  local file="$1"; local app_env="$2"; local user="$3"; local pass="$4"; local db="$5"; local debug="$6"; local log="$7"
  if [[ -f "${file}" ]]; then
    say "  • ${file} existe, inchangé."
  else
cat > "${file}" <<ENV
APP_ENV=${app_env}
DJANGO_DEBUG=${debug}
DJANGO_SECRET_KEY=CHANGE_ME_${app_env^^}
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

DATABASE_URL=postgresql://${user}:${pass}@${PG_HOST}:${PG_PORT}/${db}?sslmode=disable
DJANGO_LOG_LEVEL=${log}
ENV
    say "  ✔ Créé : ${file}"
  fi
}
create_env "${BACKEND_DIR}/.env.dev"     "dev"     "${ROLE_DEV}"  "${PWD_DEV}"  "${DB_DEV}"     "true"  "DEBUG"
create_env "${BACKEND_DIR}/.env.test"    "test"    "${ROLE_TEST}" "${PWD_TEST}" "${DB_TEST}"    "false" "INFO"
create_env "${BACKEND_DIR}/.env.upgrade" "upgrade" "${ROLE_UPG}"  "${PWD_UPG}"  "${DB_UPG}"     "false" "DEBUG"

# --- Sanity checks ---
say "🧪 Sanity check connexions..."
psql -p "${PG_PORT}" -h "${PG_HOST}" -U "${ROLE_DEV}"  -d "${DB_DEV}"  -c "SELECT current_database();" >/dev/null
psql -p "${PG_PORT}" -h "${PG_HOST}" -U "${ROLE_TEST}" -d "${DB_TEST}" -c "SELECT current_database();" >/dev/null
psql -p "${PG_PORT}" -h "${PG_HOST}" -U "${ROLE_UPG}"  -d "${DB_UPG}"  -c "SELECT current_database();" >/dev/null
say "✅ Connexions OK (${PG_HOST}:${PG_PORT})"

say "ℹ️ URLs utiles :"
say "  DEV     : postgresql://${ROLE_DEV}:${PWD_DEV}@${PG_HOST}:${PG_PORT}/${DB_DEV}?sslmode=disable"
say "  TEST    : postgresql://${ROLE_TEST}:${PWD_TEST}@${PG_HOST}:${PG_PORT}/${DB_TEST}?sslmode=disable"
say "  UPGRADE : postgresql://${ROLE_UPG}:${PWD_UPG}@${PG_HOST}:${PG_PORT}/${DB_UPG}?sslmode=disable"

say "🎉 Provision terminé."
