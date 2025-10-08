#!/usr/bin/env bash
#
# PixelProwlers Studio — mTLS harness test script
#
# Validates that Caddy (front door) enforces client certificate authentication
# for the Dojo (Admins) realm:
#   1) With a valid client cert → /health returns 200 and JSON body contains "ok".
#   2) Without a client cert     → connection fails at proxy (TLS handshake) OR returns 4xx.
#   3) With an invalid client cert → connection fails or returns 4xx.
#
# Usage (from repo root, after bringing up the harness):
#   docker compose -f config/mTLS/docker-compose.mtls.yml up -d --build
#   bash scripts/test_mtls.sh
#
# Env overrides:
#   BASE=https://localhost:8443
#   CERT_DIR=config/mTLS/certs
#   CA_FILE=$CERT_DIR/ca_admin_clients.pem
#   VALID_CRT=$CERT_DIR/client-valid.pem
#   VALID_KEY=$CERT_DIR/client-valid.key
#   BAD_CRT=$CERT_DIR/client-invalid.pem
#   BAD_KEY=$CERT_DIR/client-invalid.key
#   TIMEOUT=10
#   RETRIES=30
#   DEBUG=1        # to enable bash xtrace
#

set -Eeuo pipefail

[[ "${DEBUG:-0}" == "1" ]] && set -x

# --- Configuration (overridable via env) ---
BASE="${BASE:-https://localhost:8443}"
CERT_DIR="${CERT_DIR:-config/mTLS/certs}"
CA_FILE="${CA_FILE:-$CERT_DIR/ca_admin_clients.pem}"
VALID_CRT="${VALID_CRT:-$CERT_DIR/client-valid.pem}"
VALID_KEY="${VALID_KEY:-$CERT_DIR/client-valid.key}"
BAD_CRT="${BAD_CRT:-$CERT_DIR/client-invalid.pem}"
BAD_KEY="${BAD_KEY:-$CERT_DIR/client-invalid.key}"
TIMEOUT="${TIMEOUT:-10}"
RETRIES="${RETRIES:-30}"

# --- Utilities ---
log() { printf -- "%s\n" "$*" >&2; }
ok()  { printf -- "\033[32m[OK]\033[0m %s\n" "$*"; }
info(){ printf -- "\033[36m[i]\033[0m %s\n" "$*"; }
warn(){ printf -- "\033[33m[!]\033[0m %s\n" "$*"; }
die() { printf -- "\033[31m[ERR]\033[0m %s\n" "$*" >&2; exit 1; }

require_file() {
  local f="$1"
  [[ -f "$f" ]] || die "Missing required file: $f"
}

# Wait for Caddy to accept TLS (we do not expect success without client cert,
# this only checks the socket is up by probing with the valid cert)
wait_for_caddy() {
  local attempts=0
  info "Waiting for Caddy at $BASE (up to ${RETRIES}*${TIMEOUT}s)..."
  until curl -ksS --max-time "$TIMEOUT" \
            --cacert "$CA_FILE" \
            --cert "$VALID_CRT" \
            --key "$VALID_KEY" \
            -o /dev/null "$BASE/health"; do
    attempts=$((attempts+1))
    if (( attempts >= RETRIES )); then
      die "Caddy did not become ready in time (tried ${RETRIES} times)"
    fi
    sleep 1
  done
  ok "Caddy is accepting connections with a valid client certificate"
}

# curl wrapper that returns 0 if HTTP status is 2xx and prints the body
curl_ok_body() {
  curl -ksS --max-time "$TIMEOUT" \
    --cacert "$CA_FILE" \
    "$@" \
    "$BASE/health"
}

# curl wrapper to fetch HTTP status code (or '000' if handshake failed)
curl_status_only() {
  curl -ksS --max-time "$TIMEOUT" \
    --cacert "$CA_FILE" \
    -o /dev/null -w '%{http_code}' \
    "$@" \
    "$BASE/health" || echo "000"
}

# --- Preconditions ---
require_file "$CA_FILE"
require_file "$VALID_CRT"
require_file "$VALID_KEY"
require_file "$BAD_CRT"
require_file "$BAD_KEY"

# --- 0) Wait for proxy with a valid client cert ---
wait_for_caddy

# --- 1) Valid client certificate should succeed (200 + body contains "ok") ---
info "[1] Testing with VALID client certificate..."
BODY="$(curl_ok_body --cert "$VALID_CRT" --key "$VALID_KEY" || true)"
STATUS="$(curl_status_only --cert "$VALID_CRT" --key "$VALID_KEY")"

[[ "$STATUS" == "200" ]] || die "Expected 200 with valid client cert, got: $STATUS"
echo "$BODY" | grep -qi "ok" || die "Expected response body to contain 'ok', got: $BODY"
ok "mTLS with valid client certificate: PASSED (status=$STATUS, body contains 'ok')"

# --- 2) No client certificate should fail (handshake or 4xx) ---
info "[2] Testing WITHOUT client certificate (should fail at proxy)..."
# Try to fetch; success indicates a problem
STATUS_NO_CERT="$(curl_status_only || true)"
if [[ "$STATUS_NO_CERT" == "200" ]]; then
  die "Expected failure without client cert, but received HTTP 200"
fi
# STATUS 000 means TLS handshake failure; 4xx means explicit denial — both are acceptable
if [[ "$STATUS_NO_CERT" != "000" && ! "$STATUS_NO_CERT" =~ ^4[0-9][0-9]$ ]]; then
  die "Expected TLS handshake failure or 4xx without client cert, got: $STATUS_NO_CERT"
fi
ok "mTLS without client certificate: PASSED (status=$STATUS_NO_CERT)"

# --- 3) Invalid client certificate should fail (handshake or 4xx) ---
info "[3] Testing with INVALID client certificate (should fail at proxy)..."
STATUS_BAD_CERT="$(curl_status_only --cert "$BAD_CRT" --key "$BAD_KEY" || true)"
if [[ "$STATUS_BAD_CERT" == "200" ]]; then
  die "Expected failure with invalid client cert, but received HTTP 200"
fi
if [[ "$STATUS_BAD_CERT" != "000" && ! "$STATUS_BAD_CERT" =~ ^4[0-9][0-9]$ ]]; then
  die "Expected TLS handshake failure or 4xx with invalid client cert, got: $STATUS_BAD_CERT"
fi
ok "mTLS with invalid client certificate: PASSED (status=$STATUS_BAD_CERT)"

ok "All mTLS tests passed"
